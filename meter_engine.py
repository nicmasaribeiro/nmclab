"""Sentence meter and stress analysis for the NMC rap lab.

The meter model is intentionally local/offline.  When the optional
``pronouncing`` package is available it uses CMUdict stress marks; otherwise it
falls back to deterministic rap-focused heuristics.  The result is not meant to
be a classical poetry scansion oracle.  It gives useful, inspectable cues for
where a rapper will likely place strong syllables, weak pickups, breath pivots,
and bar landings.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from statistics import mean, median, pstdev
from typing import Any, Dict, Iterable, List, Sequence, Tuple

try:  # Optional. Safe to run without internet or external API calls.
    import pronouncing  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pronouncing = None  # type: ignore

from lyric_engine import (
    count_syllables,
    get_corpus_profile,
    is_section_marker,
    line_syllables,
    normalize_word,
    tokenize,
    unique_preserve,
)

WORD_OR_SPACE_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|\s+|[^A-Za-z0-9\s]+")
VOWEL_GROUP_RE = re.compile(r"[aeiouy]+", re.I)

# Words that normally work as unstressed pickups unless they are line-final or
# deliberately emphasized by performance.
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "that", "this", "these", "those",
    "to", "of", "for", "from", "in", "on", "at", "by", "as", "with", "within", "into", "onto", "through",
    "is", "am", "are", "was", "were", "be", "been", "being", "do", "does", "did", "can", "could", "should",
    "would", "will", "shall", "may", "might", "must", "have", "has", "had", "not", "no", "so", "just",
    "very", "really", "quite", "maybe", "sometimes", "still", "yet", "there", "here", "it", "its", "it's",
    "i", "i'm", "im", "i've", "ive", "i'll", "ill", "me", "my", "mine", "you", "your", "yours", "he", "him",
    "his", "she", "her", "we", "us", "our", "they", "them", "their", "who", "what", "when", "where", "why", "how",
}

WEAK_PREFIXES = (
    "a", "be", "de", "dis", "en", "em", "ex", "im", "in", "ir", "mis", "pre", "pro", "re", "sub", "un",
)

LAST_STRESS_SUFFIXES = (
    "ade", "ee", "eer", "ese", "ette", "ique", "oon", "self", "selves",
)

PENULT_STRESS_SUFFIXES = (
    "tion", "sion", "cian", "tial", "cial", "ic", "ics", "ity", "ety", "ify", "itive", "uous", "ian",
)

ANTE_PENULT_SUFFIXES = (
    "ical", "ity", "ety", "graphy", "logy", "meter", "metry", "ative", "atory",
)

FOOT_LABELS = {
    "uS": "iamb",
    "Su": "trochee",
    "SS": "spondee",
    "uu": "pyrrhic",
    "uuS": "anapest",
    "Suu": "dactyl",
    "uSu": "amphibrach",
    "SSu": "front-loaded rap foot",
    "uSS": "rising double-stress foot",
    "SuS": "syncopated stress foot",
}


def _round(value: float, digits: int = 2) -> float:
    try:
        value = float(value)
        if math.isfinite(value):
            return round(value, digits)
    except Exception:
        pass
    return 0.0


def _pct(value: float) -> int:
    try:
        return int(round(max(0.0, min(100.0, float(value)))))
    except Exception:
        return 0


def _entropy(counter: Counter[str]) -> Dict[str, Any]:
    total = sum(counter.values())
    if total <= 0:
        return {"entropy_bits": 0.0, "perplexity": 0.0, "normalized_entropy_pct": 0, "unique": 0, "total": 0}
    entropy = 0.0
    for count in counter.values():
        p = count / total
        entropy -= p * math.log2(p)
    max_entropy = math.log2(max(1, len(counter)))
    return {
        "entropy_bits": _round(entropy, 3),
        "perplexity": _round(2 ** entropy, 2),
        "normalized_entropy_pct": _pct((entropy / max_entropy) * 100 if max_entropy else 0),
        "unique": len(counter),
        "total": total,
    }


def _source_label(used_pronouncing: bool) -> str:
    if used_pronouncing:
        return "cmudict_plus_heuristic"
    return "heuristic_fallback"


@lru_cache(maxsize=16000)
def _cmu_stress_digits(word: str) -> Tuple[Tuple[int, ...], str]:
    """Return CMUdict stress digits if available.

    Digits are 0 = unstressed, 1 = primary, 2 = secondary.  The first
    dictionary pronunciation is used because this is a beta UI feature, not a
    full disambiguating parser.
    """
    clean = normalize_word(word)
    if not clean or pronouncing is None:
        return tuple(), "heuristic"
    lookup = clean.replace("'", "")
    try:
        phones = pronouncing.phones_for_word(lookup)
    except Exception:
        phones = []
    if not phones:
        # Try a few common rap-writing spellings.
        alt = lookup.replace("in'", "ing").replace("n'", "ng")
        if alt != lookup:
            try:
                phones = pronouncing.phones_for_word(alt)
            except Exception:
                phones = []
    if not phones:
        return tuple(), "heuristic"
    try:
        digits = tuple(int(ch) for ch in pronouncing.stresses(phones[0]) if ch.isdigit())
    except Exception:
        digits = tuple()
    return digits, "cmudict" if digits else "heuristic"


def _fit_stresses_to_syllables(stresses: Sequence[int], syllable_count: int, word: str) -> Tuple[List[int], str]:
    syllable_count = max(1, int(syllable_count or 1))
    if len(stresses) == syllable_count:
        return list(stresses), "cmudict"
    if stresses and len(stresses) > syllable_count:
        # Keep primary/secondary information but trim extra schwas.
        return list(stresses[:syllable_count]), "cmudict_adjusted"
    if stresses and len(stresses) < syllable_count:
        padded = list(stresses) + [0] * (syllable_count - len(stresses))
        return padded, "cmudict_adjusted"
    return _heuristic_word_stresses(word, syllable_count), "heuristic"


def _heuristic_word_stresses(word: str, syllable_count: int | None = None) -> List[int]:
    clean = normalize_word(word)
    if not clean:
        return []
    syllables = max(1, int(syllable_count or count_syllables(clean) or 1))
    if syllables == 1:
        return [0 if clean in FUNCTION_WORDS else 1]

    stresses = [0] * syllables

    if any(clean.endswith(suffix) for suffix in LAST_STRESS_SUFFIXES):
        stresses[-1] = 1
        return stresses

    if any(clean.endswith(suffix) for suffix in ANTE_PENULT_SUFFIXES) and syllables >= 3:
        stresses[-3] = 1
        return stresses

    if any(clean.endswith(suffix) for suffix in PENULT_STRESS_SUFFIXES) and syllables >= 2:
        stresses[-2] = 1
        return stresses

    # Common two-syllable function chunks often work as a pickup plus stress.
    if clean.startswith(WEAK_PREFIXES) and syllables == 2 and len(clean) > 4:
        stresses[1] = 1
        return stresses

    # Rap diction often stresses the first content syllable in words such as
    # sentence, presence, system, method, credit, vector, surface.
    stresses[0] = 1
    if syllables >= 4:
        stresses[-2] = 2
    return stresses


def estimate_word_stress(word: str, is_last_word: bool = False) -> Dict[str, Any]:
    clean = normalize_word(word)
    syllable_count = max(1, count_syllables(clean)) if clean else 0
    if not clean:
        return {"word": word, "normalized": clean, "syllables": 0, "stresses": [], "source": "none"}
    cmu_digits, cmu_source = _cmu_stress_digits(clean)
    stresses, source = _fit_stresses_to_syllables(cmu_digits, syllable_count, clean)

    # In rap performance, a meaningful line-final monosyllable almost always
    # receives landing stress even if its dictionary role can be weak.
    if is_last_word and syllable_count == 1 and clean not in FUNCTION_WORDS:
        stresses = [max(1, stresses[0] if stresses else 1)]

    stress_string = "".join("S" if value else "u" for value in stresses)
    glyph_string = "".join("●" if value else "○" for value in stresses)
    return {
        "word": word,
        "normalized": clean,
        "syllables": syllable_count,
        "stresses": stresses,
        "stress_string": stress_string,
        "glyphs": glyph_string,
        "source": source if source != "heuristic" else cmu_source,
        "is_function_word": clean in FUNCTION_WORDS,
        "primary_stress_index": (max(range(len(stresses)), key=lambda i: stresses[i]) + 1) if stresses and max(stresses) > 0 else None,
        "final_syllable_stressed": bool(stresses and stresses[-1] > 0),
    }


def _rough_syllable_labels(word: str, syllable_count: int) -> List[str]:
    """Return compact syllable labels for display, not linguistic truth."""
    text = str(word or "")
    syllable_count = max(1, int(syllable_count or 1))
    if syllable_count <= 1 or len(text) <= 4:
        return [text]
    matches = list(VOWEL_GROUP_RE.finditer(text))
    if not matches:
        return [text] + [""] * (syllable_count - 1)
    cut_positions: List[int] = []
    for match in matches[:-1]:
        cut = min(len(text), match.end() + 1)
        if 1 < cut < len(text):
            cut_positions.append(cut)
    cut_positions = sorted(set(cut_positions))[: syllable_count - 1]
    parts: List[str] = []
    start = 0
    for cut in cut_positions:
        parts.append(text[start:cut])
        start = cut
    parts.append(text[start:])
    while len(parts) < syllable_count:
        parts.append("")
    if len(parts) > syllable_count:
        parts = parts[: syllable_count - 1] + ["".join(parts[syllable_count - 1:])]
    return parts


def _foot_rows(stress_string: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
    compact = "".join(ch for ch in stress_string if ch in "Su")
    pair_counter: Counter[str] = Counter()
    triple_counter: Counter[str] = Counter()
    pair_rows: List[Dict[str, Any]] = []
    triple_rows: List[Dict[str, Any]] = []

    for i in range(0, len(compact) - 1, 2):
        foot = compact[i:i + 2]
        if len(foot) == 2:
            pair_counter[foot] += 1
            pair_rows.append({"position": len(pair_rows) + 1, "pattern": foot, "name": FOOT_LABELS.get(foot, "mixed"), "syllables": [i + 1, i + 2]})
    for i in range(0, len(compact) - 2, 3):
        foot = compact[i:i + 3]
        if len(foot) == 3:
            triple_counter[foot] += 1
            triple_rows.append({"position": len(triple_rows) + 1, "pattern": foot, "name": FOOT_LABELS.get(foot, "mixed triple"), "syllables": [i + 1, i + 2, i + 3]})

    candidates: List[Tuple[str, str, int, str]] = []
    for pattern, count in pair_counter.items():
        candidates.append((pattern, FOOT_LABELS.get(pattern, "mixed"), count, "duple"))
    for pattern, count in triple_counter.items():
        candidates.append((pattern, FOOT_LABELS.get(pattern, "mixed triple"), count, "triple"))
    if candidates:
        pattern, name, count, grouping = max(candidates, key=lambda item: (item[2], len(item[0])))
        denominator = max(1, len(pair_rows) if grouping == "duple" else len(triple_rows))
        dominant = {
            "pattern": pattern,
            "name": name,
            "count": count,
            "grouping": grouping,
            "confidence_pct": _pct((count / denominator) * 100),
        }
    else:
        dominant = {"pattern": "", "name": "none", "count": 0, "grouping": "none", "confidence_pct": 0}

    return pair_rows, dominant, triple_rows


def _stress_positions(stress_values: Sequence[int]) -> List[int]:
    return [idx + 1 for idx, value in enumerate(stress_values) if int(value) > 0]


def _stress_intervals(positions: Sequence[int]) -> List[int]:
    return [int(positions[i] - positions[i - 1]) for i in range(1, len(positions))]


def _weak_runs(stress_values: Sequence[int]) -> List[Dict[str, int]]:
    runs: List[Dict[str, int]] = []
    start = None
    for idx, value in enumerate(stress_values, start=1):
        if int(value) == 0 and start is None:
            start = idx
        elif int(value) > 0 and start is not None:
            runs.append({"start": start, "end": idx - 1, "length": idx - start})
            start = None
    if start is not None:
        runs.append({"start": start, "end": len(stress_values), "length": len(stress_values) - start + 1})
    return runs


def _stress_clusters(stress_values: Sequence[int]) -> List[Dict[str, int]]:
    clusters: List[Dict[str, int]] = []
    start = None
    for idx, value in enumerate(stress_values, start=1):
        if int(value) > 0 and start is None:
            start = idx
        elif int(value) == 0 and start is not None:
            if idx - start >= 2:
                clusters.append({"start": start, "end": idx - 1, "length": idx - start})
            start = None
    if start is not None and len(stress_values) - start + 1 >= 2:
        clusters.append({"start": start, "end": len(stress_values), "length": len(stress_values) - start + 1})
    return clusters


def _pulse_grid(units: Sequence[Dict[str, Any]], beat: Dict[str, Any] | None = None) -> Dict[str, Any]:
    n = len(units)
    if n <= 0:
        return {"available": False, "beats": []}
    beat_count = 4
    buckets: List[Dict[str, Any]] = [{"beat": i, "pattern": "", "syllable_count": 0, "stress_count": 0, "words": []} for i in range(1, beat_count + 1)]
    for i, unit in enumerate(units, start=1):
        beat_no = min(beat_count, max(1, int(math.floor(((i - 1) / max(1, n)) * beat_count)) + 1))
        bucket = buckets[beat_no - 1]
        bucket["syllable_count"] += 1
        bucket["stress_count"] += 1 if unit.get("stressed") else 0
        bucket["pattern"] += "●" if unit.get("stressed") else "○"
        bucket["words"].append(unit.get("word", ""))
    for bucket in buckets:
        bucket["words"] = unique_preserve(bucket["words"], 8)
        bucket["stress_density_pct"] = _pct((bucket["stress_count"] / max(1, bucket["syllable_count"])) * 100)
    bar_seconds = None
    beat_seconds = None
    if beat and beat.get("available"):
        bar_seconds = beat.get("bar_duration_seconds")
        beat_seconds = beat.get("beat_interval_seconds")
    return {
        "available": True,
        "basis": "one_bar_four_beat_grid",
        "bar_seconds": bar_seconds,
        "beat_seconds": beat_seconds,
        "beats": buckets,
        "reading": _pulse_grid_reading(buckets),
    }


def _pulse_grid_reading(buckets: Sequence[Dict[str, Any]]) -> str:
    if not buckets:
        return "No pulse grid available."
    first = buckets[0].get("stress_count", 0)
    last = buckets[-1].get("stress_count", 0)
    middle = sum(int(b.get("stress_count", 0)) for b in buckets[1:3])
    if last and first:
        return "Strong setup-and-landing shape: stress appears near beat 1 and beat 4."
    if last and not first:
        return "Delayed entrance: the landing is stronger than the setup; this can work as a pickup flow."
    if middle > first + last:
        return "Middle-heavy stress: the sentence may rush through beats 2–3 unless you leave breath before the landing."
    return "Even stress spread: perform it clearly or choose one stronger landing word."


def _cadence_complexity(stress_values: Sequence[int]) -> Dict[str, Any]:
    positions = _stress_positions(stress_values)
    intervals = _stress_intervals(positions)
    weak = _weak_runs(stress_values)
    clusters = _stress_clusters(stress_values)
    stress_count = len(positions)
    syllables = len(stress_values)
    counter = Counter("S" if v else "u" for v in stress_values)
    entropy = _entropy(counter)
    interval_std = pstdev(intervals) if len(intervals) > 1 else 0.0
    return {
        "syllables": syllables,
        "stress_count": stress_count,
        "weak_count": syllables - stress_count,
        "stress_ratio_pct": _pct((stress_count / max(1, syllables)) * 100),
        "stress_positions": positions,
        "stress_intervals": intervals,
        "average_stress_gap": _round(mean(intervals), 2) if intervals else 0,
        "stress_gap_stddev": _round(interval_std, 2),
        "longest_weak_run": max((row["length"] for row in weak), default=0),
        "longest_stress_cluster": max((row["length"] for row in clusters), default=0),
        "weak_runs": weak,
        "stress_clusters": clusters,
        "stress_entropy_bits": entropy.get("entropy_bits", 0),
        "stress_entropy_normalized_pct": entropy.get("normalized_entropy_pct", 0),
    }


def _meter_suggestions(
    text: str,
    word_rows: Sequence[Dict[str, Any]],
    stress_values: Sequence[int],
    dominant: Dict[str, Any],
    complexity: Dict[str, Any],
    pulse: Dict[str, Any],
    target_syllables: Sequence[int] | None = None,
) -> List[str]:
    suggestions: List[str] = []
    syllables = int(complexity.get("syllables", 0))
    longest_weak = int(complexity.get("longest_weak_run", 0))
    longest_cluster = int(complexity.get("longest_stress_cluster", 0))
    stress_ratio = int(complexity.get("stress_ratio_pct", 0))
    words = [row.get("normalized", "") for row in word_rows if row.get("normalized")]
    end = word_rows[-1] if word_rows else {}

    if target_syllables and len(target_syllables) >= 2:
        low, high = int(target_syllables[0]), int(target_syllables[-1])
        if syllables > high:
            suggestions.append(f"Meter length is heavy: cut about {syllables - high} syllable(s) or split the sentence into two stress arcs.")
        elif syllables < low:
            suggestions.append(f"Meter length is open: add {low - syllables} syllable(s), a pickup, or leave that space as an intentional rest.")
        else:
            suggestions.append(f"Syllable count fits the target pocket ({low}-{high}); focus on stress placement rather than length.")

    if longest_weak >= 4:
        suggestions.append("There is a long weak-syllable run; move a concrete noun or hard verb earlier so the bar does not sag.")
    if longest_cluster >= 3:
        suggestions.append("Three or more stressed syllables are packed together; add a weak pickup/rest or swap one hard word for a smoother connector.")
    if stress_ratio < 28 and syllables >= 8:
        suggestions.append("Stress density is low; add one heavier image word before the rhyme landing.")
    elif stress_ratio > 62 and syllables >= 8:
        suggestions.append("Stress density is high; perform it clipped/double-time or remove one hard noun cluster.")

    if end and not end.get("final_syllable_stressed") and end.get("normalized") not in FUNCTION_WORDS:
        suggestions.append(f"The final word “{end.get('word')}” has a softer final syllable; exaggerate it vocally or choose a punchier landing.")
    elif end and end.get("normalized") in FUNCTION_WORDS:
        suggestions.append(f"The sentence ends on a weak function word (“{end.get('word')}”); move the rhyme to a stronger noun, verb, or image.")
    else:
        suggestions.append("The final landing can carry stress; keep the rhyme word near the final quarter of the bar.")

    name = dominant.get("name") or "mixed"
    confidence = int(dominant.get("confidence_pct") or 0)
    if confidence >= 55:
        suggestions.append(f"Dominant meter leans {name}; keep that foot for two adjacent bars before breaking it for emphasis.")
    else:
        suggestions.append("Meter is mixed/syncopated; mark the intended stress words in rehearsal so the listener hears the pattern.")

    if pulse.get("available"):
        suggestions.append(pulse.get("reading") or "Use the pulse grid to choose a stronger beat-1 or beat-4 stress.")

    # A tiny word-level hint grounded in the sentence itself.
    strong_words = [row.get("word") for row in word_rows if row.get("is_content_stressed")]
    if strong_words:
        suggestions.append(f"Current stress anchors: {', '.join(unique_preserve(strong_words, 5))}.")
    elif words:
        suggestions.append("No obvious stress anchor detected; make one content word the performance center.")

    return unique_preserve(suggestions, 8)


def _target_from_beat_or_corpus(beat: Dict[str, Any] | None = None, target_syllables: Sequence[int] | None = None) -> Tuple[List[int], str]:
    if target_syllables and len(target_syllables) >= 2:
        return [int(target_syllables[0]), int(target_syllables[-1])], "provided_target"
    if beat and beat.get("available"):
        pockets = (((beat.get("pocket") or {}).get("pockets") or {}).get("balanced") or {}).get("range")
        if isinstance(pockets, (list, tuple)) and len(pockets) >= 2:
            return [int(pockets[0]), int(pockets[-1])], "uploaded_beat_balanced_pocket"
    profile = get_corpus_profile()
    median_syll = int(round(float((profile.get("stats") or {}).get("median_syllables") or 14)))
    return [max(5, median_syll - 3), median_syll + 3], "compiled_corpus_median"


def analyze_sentence_meter(
    text: str,
    beat: Dict[str, Any] | None = None,
    target_syllables: Sequence[int] | None = None,
) -> Dict[str, Any]:
    """Analyze one sentence/line for stress, meter, and rap pulse."""
    raw = str(text or "").strip()
    tokens = tokenize(raw)
    if not raw or not tokens:
        return {"available": False, "error": "No analyzable words for meter."}

    target, target_basis = _target_from_beat_or_corpus(beat, target_syllables)
    words = [match.group(0) for match in WORD_OR_SPACE_RE.finditer(raw) if tokenize(match.group(0))]
    word_rows: List[Dict[str, Any]] = []
    units: List[Dict[str, Any]] = []
    used_cmudict = False
    syllable_index = 0
    last_word_index = len(words) - 1

    for word_index, word in enumerate(words):
        row = estimate_word_stress(word, is_last_word=word_index == last_word_index)
        if str(row.get("source", "")).startswith("cmudict"):
            used_cmudict = True
        labels = _rough_syllable_labels(word, int(row.get("syllables") or 1))
        stress_values = [int(v) for v in row.get("stresses", [])]
        row_units: List[Dict[str, Any]] = []
        for local_index, stress in enumerate(stress_values, start=1):
            syllable_index += 1
            unit = {
                "index": syllable_index,
                "word": word,
                "normalized_word": row.get("normalized", ""),
                "word_index": word_index + 1,
                "syllable_in_word": local_index,
                "syllable_label": labels[local_index - 1] if local_index - 1 < len(labels) else "",
                "stress": int(stress),
                "stressed": int(stress) > 0,
                "mark": "´" if int(stress) > 0 else "˘",
                "glyph": "●" if int(stress) > 0 else "○",
            }
            units.append(unit)
            row_units.append(unit)
        row["syllable_units"] = row_units
        row["is_content_stressed"] = bool(row.get("normalized") not in FUNCTION_WORDS and any(int(v) > 0 for v in stress_values))
        word_rows.append(row)

    stress_values = [int(unit.get("stress", 0)) for unit in units]
    stress_string = "".join("S" if v else "u" for v in stress_values)
    scansion = " ".join("´" if v else "˘" for v in stress_values)
    glyphs = " ".join("●" if v else "○" for v in stress_values)
    pair_feet, dominant, triple_feet = _foot_rows(stress_string)
    complexity = _cadence_complexity(stress_values)
    pulse = _pulse_grid(units, beat)
    suggestions = _meter_suggestions(raw, word_rows, stress_values, dominant, complexity, pulse, target)

    strong_words = unique_preserve([row.get("word") for row in word_rows if row.get("is_content_stressed")], 12)
    weak_pickups = unique_preserve([row.get("word") for row in word_rows if row.get("normalized") in FUNCTION_WORDS], 12)
    end_row = word_rows[-1] if word_rows else {}

    return {
        "available": True,
        "analysis_type": "sentence_meter_stress",
        "text": raw,
        "source": _source_label(used_cmudict),
        "target": {"syllables": target, "basis": target_basis},
        "summary": {
            "syllables": len(units),
            "words": len(word_rows),
            "stressed_syllables": complexity.get("stress_count", 0),
            "weak_syllables": complexity.get("weak_count", 0),
            "stress_ratio_pct": complexity.get("stress_ratio_pct", 0),
            "dominant_meter": dominant.get("name", "mixed"),
            "dominant_meter_pattern": dominant.get("pattern", ""),
            "meter_confidence_pct": dominant.get("confidence_pct", 0),
            "average_stress_gap": complexity.get("average_stress_gap", 0),
            "stress_gap_stddev": complexity.get("stress_gap_stddev", 0),
            "longest_weak_run": complexity.get("longest_weak_run", 0),
            "longest_stress_cluster": complexity.get("longest_stress_cluster", 0),
            "final_landing_word": end_row.get("word", ""),
            "final_landing_stressed": bool(end_row.get("final_syllable_stressed")),
            "stress_entropy_bits": complexity.get("stress_entropy_bits", 0),
            "stress_entropy_normalized_pct": complexity.get("stress_entropy_normalized_pct", 0),
        },
        "pattern": {
            "stress_string": stress_string,
            "scansion": scansion,
            "glyphs": glyphs,
            "compact": "".join("/" if v else "x" for v in stress_values),
            "legend": "● or ´ = likely stressed syllable; ○ or ˘ = likely weak/pickup syllable.",
        },
        "syllables": units,
        "words": word_rows,
        "feet": {
            "dominant": dominant,
            "duple": pair_feet,
            "triple": triple_feet,
        },
        "complexity": complexity,
        "pulse_grid": pulse,
        "stress_anchors": strong_words,
        "weak_pickups": weak_pickups,
        "suggestions": suggestions,
        "display": {
            "word_scansion": " ".join(f"{row.get('word')}[{row.get('glyphs')}]" for row in word_rows),
            "stress_anchor_text": ", ".join(str(w) for w in strong_words[:6]) or "none detected",
        },
    }


def _meter_line_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    meter = row.get("meter") or {}
    summary = meter.get("summary") or {}
    return {
        "line_number": row.get("line_number"),
        "text": row.get("text", ""),
        "syllables": summary.get("syllables", 0),
        "stress_ratio_pct": summary.get("stress_ratio_pct", 0),
        "dominant_meter": summary.get("dominant_meter", "mixed"),
        "meter_confidence_pct": summary.get("meter_confidence_pct", 0),
        "longest_weak_run": summary.get("longest_weak_run", 0),
        "longest_stress_cluster": summary.get("longest_stress_cluster", 0),
        "final_landing_stressed": summary.get("final_landing_stressed", False),
        "pattern": (meter.get("pattern") or {}).get("glyphs", ""),
        "suggestion": (meter.get("suggestions") or [""])[0],
    }


def analyze_meter_text(
    text: str,
    beat: Dict[str, Any] | None = None,
    target_syllables: Sequence[int] | None = None,
) -> Dict[str, Any]:
    """Analyze every editable lyric line and summarize meter/stress behavior."""
    rows: List[Dict[str, Any]] = []
    for original_line_number, raw_line in enumerate(str(text or "").splitlines(), start=1):
        raw = raw_line.strip()
        if not raw or is_section_marker(raw):
            continue
        meter = analyze_sentence_meter(raw, beat=beat, target_syllables=target_syllables)
        rows.append({"line_number": original_line_number, "text": raw, "meter": meter})

    if not rows:
        return {"available": False, "error": "No editable lyric lines found for meter analysis.", "lines": []}

    summaries = [_meter_line_summary(row) for row in rows]
    stress_ratios = [float(row.get("stress_ratio_pct") or 0) for row in summaries]
    syllables = [int(row.get("syllables") or 0) for row in summaries]
    meter_counter = Counter(str(row.get("dominant_meter") or "mixed") for row in summaries)
    pattern_counter = Counter(str(((row.get("meter") or {}).get("feet") or {}).get("dominant", {}).get("pattern") or "mixed") for row in rows)
    final_stressed = sum(1 for row in summaries if row.get("final_landing_stressed"))
    weak_problem_rows = sorted(summaries, key=lambda row: int(row.get("longest_weak_run") or 0), reverse=True)[:6]
    cluster_problem_rows = sorted(summaries, key=lambda row: int(row.get("longest_stress_cluster") or 0), reverse=True)[:6]

    target, target_basis = _target_from_beat_or_corpus(beat, target_syllables)
    low, high = target
    over = [row for row in summaries if int(row.get("syllables") or 0) > high]
    under = [row for row in summaries if int(row.get("syllables") or 0) < low]

    avg_stress = mean(stress_ratios) if stress_ratios else 0.0
    consistency = _pct(100 - min(100, (pstdev(stress_ratios) if len(stress_ratios) > 1 else 0.0) * 2.2))
    dominant_meter, dominant_count = meter_counter.most_common(1)[0]

    recommendations: List[str] = []
    if over:
        recommendations.append(f"{len(over)} line(s) are above the meter pocket {low}-{high}; split them or cut weak connective syllables first.")
    if under:
        recommendations.append(f"{len(under)} line(s) are below the meter pocket {low}-{high}; use rests deliberately or add stressed image words.")
    if avg_stress < 32:
        recommendations.append("Average stress density is low; the draft may sound too prosaic unless the delivery adds sharper accents.")
    elif avg_stress > 60:
        recommendations.append("Average stress density is high; use clipped delivery or more weak pickups to avoid a blocky cadence.")
    else:
        recommendations.append("Average stress density is balanced for rap: enough anchors without every syllable hitting hard.")
    if final_stressed / max(1, len(summaries)) < 0.65:
        recommendations.append("Many final landings are not strongly stressed; move rhyme words to harder nouns/verbs or exaggerate the ending vocally.")
    else:
        recommendations.append("Most line endings can carry stress, which helps rhyme land cleanly on beat 4.")
    recommendations.append(f"Dominant meter tendency is {dominant_meter}; preserve it for identity, then break it near punchlines or section turns.")

    return {
        "available": True,
        "analysis_type": "lyric_meter_stress",
        "source": (rows[0].get("meter") or {}).get("source", "heuristic_fallback"),
        "target": {"syllables": target, "basis": target_basis},
        "summary": {
            "lines": len(summaries),
            "avg_syllables": _round(mean(syllables), 2),
            "median_syllables": _round(median(syllables), 2),
            "avg_stress_ratio_pct": _round(avg_stress, 1),
            "stress_ratio_stddev": _round(pstdev(stress_ratios) if len(stress_ratios) > 1 else 0.0, 2),
            "stress_consistency_pct": consistency,
            "dominant_meter": dominant_meter,
            "dominant_meter_share_pct": _pct((dominant_count / max(1, len(summaries))) * 100),
            "final_landing_stressed_pct": _pct((final_stressed / max(1, len(summaries))) * 100),
            "lines_over_pocket": len(over),
            "lines_under_pocket": len(under),
            "stress_entropy": _entropy(Counter(str(row.get("stress_ratio_pct")) for row in summaries)),
        },
        "meter_distribution": [
            {"meter": name, "count": count, "pct": _pct((count / max(1, len(summaries))) * 100)}
            for name, count in meter_counter.most_common(12)
        ],
        "foot_pattern_distribution": [
            {"pattern": pattern, "name": FOOT_LABELS.get(pattern, "mixed"), "count": count, "pct": _pct((count / max(1, len(summaries))) * 100)}
            for pattern, count in pattern_counter.most_common(12)
        ],
        "recommendations": unique_preserve(recommendations, 8),
        "problem_rows": {
            "long_weak_runs": weak_problem_rows,
            "stress_clusters": cluster_problem_rows,
            "over_pocket": over[:8],
            "under_pocket": under[:8],
        },
        "lines": summaries,
        "line_details": rows,
    }
