"""Reference-rapper benchmark profiles for the beta rap lab.

The comparison data is profile-only: the app loads statistical summaries derived
from the user's uploaded comparison file, not raw commercial lyrics. That keeps
beta deployments lighter and avoids bundling copyrighted lyric text while still
supporting cadence, rhyme-density, entropy, and bar-structure benchmarks.
"""
from __future__ import annotations

import json
import math
import os
from collections import Counter
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Sequence

from lyric_engine import build_line_details, content_words, normalize_word, rhyme_key, tokenize, unique_preserve

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_COMPARISON_PATH = Path(os.getenv("NMC_COMPARISON_PROFILE_PATH", str(BASE_DIR / "data" / "comparison_profiles.json"))).expanduser()
if not DEFAULT_COMPARISON_PATH.is_absolute():
    DEFAULT_COMPARISON_PATH = BASE_DIR / DEFAULT_COMPARISON_PATH

SYLLABLE_BINS = ["micro_0_6", "short_7_10", "pocket_11_14", "long_15_18", "extended_19_plus"]
WORD_COUNT_BINS = ["micro_0_4", "short_5_8", "standard_9_12", "dense_13_16", "packed_17_plus"]


def _round(value: Any, digits: int = 2) -> float:
    try:
        if math.isfinite(float(value)):
            return round(float(value), digits)
    except Exception:
        pass
    return 0.0


def _pct(value: float) -> int:
    if not math.isfinite(value):
        return 0
    return int(round(max(0.0, min(100.0, value))))


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return number
    except Exception:
        pass
    return default


def _entropy(counter: Counter) -> Dict[str, Any]:
    clean = Counter({str(k): int(v) for k, v in counter.items() if int(v) > 0 and str(k)})
    total = sum(clean.values())
    if total <= 0:
        return {"entropy_bits": 0.0, "perplexity": 0.0, "normalized_entropy": 0, "unique": 0, "top": []}
    entropy = 0.0
    for count in clean.values():
        p = count / total
        entropy -= p * math.log2(p)
    max_entropy = math.log2(len(clean)) if len(clean) > 1 else 0.0
    top = []
    for key, count in clean.most_common(12):
        p = count / total
        top.append({"key": key, "count": count, "pct": _round(p * 100, 1), "self_information_bits": _round(-math.log2(p), 2)})
    return {
        "entropy_bits": _round(entropy, 3),
        "perplexity": _round(2 ** entropy, 2),
        "normalized_entropy": _pct((entropy / max_entropy) * 100) if max_entropy else 0,
        "unique": len(clean),
        "top": top,
    }


def _syllable_bin(value: Any) -> str:
    syllables = int(_safe_number(value, 0))
    if syllables <= 6:
        return "micro_0_6"
    if syllables <= 10:
        return "short_7_10"
    if syllables <= 14:
        return "pocket_11_14"
    if syllables <= 18:
        return "long_15_18"
    return "extended_19_plus"


def _word_count_bin(value: Any) -> str:
    words = int(_safe_number(value, 0))
    if words <= 4:
        return "micro_0_4"
    if words <= 8:
        return "short_5_8"
    if words <= 12:
        return "standard_9_12"
    if words <= 16:
        return "dense_13_16"
    return "packed_17_plus"


def _quartiles(values: Sequence[int]) -> List[float]:
    if not values:
        return [0.0, 0.0, 0.0]
    vals = sorted(int(v) for v in values)
    def q(p: float) -> float:
        if len(vals) == 1:
            return float(vals[0])
        pos = (len(vals) - 1) * p
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return float(vals[lo])
        return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)
    return [_round(q(0.25), 1), _round(q(0.5), 1), _round(q(0.75), 1)]


def _histogram_from_bins(values: Sequence[str], bins: Sequence[str]) -> List[Dict[str, Any]]:
    counts = Counter(values)
    total = sum(counts.values()) or 1
    return [{"key": key, "count": int(counts.get(key, 0)), "pct": _round((counts.get(key, 0) / total) * 100, 1)} for key in bins]


def _hist_map(rows: Sequence[Dict[str, Any]]) -> Dict[str, float]:
    return {str(row.get("key", "")): _safe_number(row.get("pct"), 0.0) / 100.0 for row in rows or []}


def _hist_similarity(a_rows: Sequence[Dict[str, Any]], b_rows: Sequence[Dict[str, Any]], bins: Sequence[str]) -> int:
    a = _hist_map(a_rows)
    b = _hist_map(b_rows)
    l1 = sum(abs(a.get(key, 0.0) - b.get(key, 0.0)) for key in bins)
    return _pct(100 - (l1 / 2.0) * 100)


def _closeness(a: Any, b: Any, scale: float) -> int:
    if scale <= 0:
        return 0
    return _pct(100 - (abs(_safe_number(a) - _safe_number(b)) / scale) * 100)


@lru_cache(maxsize=1)
def load_comparison_profiles() -> Dict[str, Any]:
    if not DEFAULT_COMPARISON_PATH.exists():
        return {
            "metadata": {
                "available": False,
                "message": "No comparison profile file found.",
                "expected_path": str(DEFAULT_COMPARISON_PATH),
            },
            "profiles": [],
        }
    try:
        data = json.loads(DEFAULT_COMPARISON_PATH.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        return {
            "metadata": {"available": False, "message": f"Comparison profile file could not be read: {exc}"},
            "profiles": [],
        }
    data.setdefault("metadata", {})["available"] = bool(data.get("profiles"))
    data["metadata"].setdefault("copyright_handling", "derived_profile_only_no_raw_lyrics")
    return data


def comparison_summary() -> Dict[str, Any]:
    data = load_comparison_profiles()
    profiles = data.get("profiles", []) or []
    return {
        "metadata": data.get("metadata", {}),
        "profiles": [
            {
                "id": profile.get("id"),
                "name": profile.get("name"),
                "source_label": profile.get("source_label"),
                "content_policy": profile.get("content_policy", "derived_profile_only_no_raw_lyrics"),
                "stats": {
                    "line_count": profile.get("stats", {}).get("line_count", 0),
                    "avg_syllables": profile.get("stats", {}).get("avg_syllables", 0),
                    "median_syllables": profile.get("stats", {}).get("median_syllables", 0),
                    "internal_rhyme_line_pct": profile.get("stats", {}).get("internal_rhyme_line_pct", 0),
                    "rhyme_entropy_bits": profile.get("stats", {}).get("rhyme_entropy_bits", 0),
                    "rhyme_perplexity": profile.get("stats", {}).get("rhyme_perplexity", 0),
                    "type_token_ratio": profile.get("stats", {}).get("type_token_ratio", 0),
                },
                "top_rhyme_keys": profile.get("top_rhyme_keys", [])[:8],
                "benchmark_moves": profile.get("benchmark_moves", [])[:4],
                "notes": profile.get("notes", [])[:4],
                "line_targets": profile.get("line_targets", {}),
            }
            for profile in profiles
        ],
    }


def _stats_from_details(details: Sequence[Dict[str, Any]], lyrics: str) -> Dict[str, Any]:
    words = tokenize(lyrics)
    all_content = content_words(words)
    syllables = [int(row.get("syllables") or 0) for row in details if row.get("syllables")]
    word_counts = [int(row.get("word_count") or 0) for row in details if row.get("word_count")]
    rhyme_keys = [str(row.get("rhyme_key") or "") for row in details if row.get("rhyme_key")]
    end_words = [str(row.get("end_word") or "") for row in details if row.get("end_word")]
    internal_lines = sum(1 for row in details if row.get("internal_rhymes"))
    alliteration_lines = sum(1 for row in details if row.get("alliteration"))
    internal_groups = sum(len(row.get("internal_rhymes") or []) for row in details)
    alliteration_groups = sum(len(row.get("alliteration") or []) for row in details)
    rhyme_counts = Counter(rhyme_keys)
    repeated_keys = sum(1 for count in rhyme_counts.values() if count > 1)
    end_counts = Counter(end_words)
    repeated_end_words = sum(1 for count in end_counts.values() if count > 1)
    token_entropy = _entropy(Counter(all_content or words))
    rhyme_entropy = _entropy(rhyme_counts)
    syll_hist = _histogram_from_bins([_syllable_bin(value) for value in syllables], SYLLABLE_BINS)
    word_hist = _histogram_from_bins([_word_count_bin(value) for value in word_counts], WORD_COUNT_BINS)
    top_rhyme_keys = []
    for key, count in rhyme_counts.most_common(14):
        top_rhyme_keys.append({"key": key, "count": count, "pct": _round((count / max(1, len(rhyme_keys))) * 100, 1)})
    return {
        "line_count": len(details),
        "word_count": len(words),
        "unique_words": len(set(words)),
        "content_words": len(all_content),
        "unique_content_words": len(set(all_content)),
        "type_token_ratio": _round(len(set(words)) / max(1, len(words)), 3),
        "content_type_token_ratio": _round(len(set(all_content)) / max(1, len(all_content)), 3),
        "avg_words": _round(sum(word_counts) / max(1, len(word_counts)), 1),
        "median_words": _round(float(median(word_counts)), 1) if word_counts else 0.0,
        "word_count_q1_median_q3": _quartiles(word_counts),
        "avg_syllables": _round(sum(syllables) / max(1, len(syllables)), 1),
        "median_syllables": _round(float(median(syllables)), 1) if syllables else 0.0,
        "syllable_q1_median_q3": _quartiles(syllables),
        "dense_line_pct": _round(sum(1 for value in syllables if value >= 16) / max(1, len(syllables)) * 100, 1),
        "open_line_pct": _round(sum(1 for value in syllables if value <= 8) / max(1, len(syllables)) * 100, 1),
        "internal_rhyme_line_pct": _round(internal_lines / max(1, len(details)) * 100, 1),
        "alliteration_line_pct": _round(alliteration_lines / max(1, len(details)) * 100, 1),
        "avg_internal_groups_per_line": _round(internal_groups / max(1, len(details)), 2),
        "avg_alliteration_groups_per_line": _round(alliteration_groups / max(1, len(details)), 2),
        "unique_rhyme_keys": len(rhyme_counts),
        "rhyme_reuse_ratio_pct": _round(repeated_keys / max(1, len(rhyme_counts)) * 100, 1),
        "repeated_end_word_pct": _round(repeated_end_words / max(1, len(end_counts)) * 100, 1),
        "lexical_entropy_bits": token_entropy["entropy_bits"],
        "lexical_perplexity": token_entropy["perplexity"],
        "rhyme_entropy_bits": rhyme_entropy["entropy_bits"],
        "rhyme_perplexity": rhyme_entropy["perplexity"],
        "rhyme_normalized_entropy": rhyme_entropy["normalized_entropy"],
        "syllable_entropy_bits": _entropy(Counter(_syllable_bin(value) for value in syllables))["entropy_bits"],
        "word_count_entropy_bits": _entropy(Counter(_word_count_bin(value) for value in word_counts))["entropy_bits"],
        "cadence_histogram": syll_hist,
        "word_count_histogram": word_hist,
        "top_rhyme_keys": top_rhyme_keys,
    }


def _component_scores(input_stats: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, int]:
    pstats = profile.get("stats", {}) or {}
    cadence_hist = _hist_similarity(input_stats.get("cadence_histogram", []), profile.get("cadence_histogram", []), SYLLABLE_BINS)
    word_hist = _hist_similarity(input_stats.get("word_count_histogram", []), profile.get("word_count_histogram", []), WORD_COUNT_BINS)
    input_keys = {row.get("key") for row in input_stats.get("top_rhyme_keys", [])[:12] if row.get("key")}
    profile_keys = {row.get("key") for row in profile.get("top_rhyme_keys", [])[:12] if row.get("key")}
    if input_keys or profile_keys:
        key_overlap = _pct((len(input_keys & profile_keys) / max(1, len(input_keys | profile_keys))) * 100)
    else:
        key_overlap = 0
    return {
        "avg_syllable_fit": _closeness(input_stats.get("avg_syllables"), pstats.get("avg_syllables"), 8.0),
        "median_syllable_fit": _closeness(input_stats.get("median_syllables"), pstats.get("median_syllables"), 8.0),
        "avg_word_fit": _closeness(input_stats.get("avg_words"), pstats.get("avg_words"), 6.0),
        "cadence_distribution_fit": cadence_hist,
        "word_count_distribution_fit": word_hist,
        "internal_rhyme_fit": _closeness(input_stats.get("internal_rhyme_line_pct"), pstats.get("internal_rhyme_line_pct"), 55.0),
        "alliteration_fit": _closeness(input_stats.get("alliteration_line_pct"), pstats.get("alliteration_line_pct"), 55.0),
        "rhyme_entropy_fit": _closeness(input_stats.get("rhyme_entropy_bits"), pstats.get("rhyme_entropy_bits"), 4.0),
        "rhyme_reuse_fit": _closeness(input_stats.get("rhyme_reuse_ratio_pct"), pstats.get("rhyme_reuse_ratio_pct"), 80.0),
        "lexical_variety_fit": _closeness(input_stats.get("type_token_ratio"), pstats.get("type_token_ratio"), 0.55),
        "rhyme_key_overlap": key_overlap,
    }


def _weighted_score(components: Dict[str, int]) -> int:
    weights = {
        "avg_syllable_fit": 0.12,
        "median_syllable_fit": 0.09,
        "avg_word_fit": 0.08,
        "cadence_distribution_fit": 0.13,
        "word_count_distribution_fit": 0.08,
        "internal_rhyme_fit": 0.12,
        "alliteration_fit": 0.07,
        "rhyme_entropy_fit": 0.13,
        "rhyme_reuse_fit": 0.08,
        "lexical_variety_fit": 0.05,
        "rhyme_key_overlap": 0.05,
    }
    return _pct(sum(components.get(key, 0) * weight for key, weight in weights.items()))


def _delta_rows(input_stats: Dict[str, Any], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    pstats = profile.get("stats", {}) or {}
    pairs = [
        ("avg_syllables", "Avg syllables", "syllables"),
        ("median_syllables", "Median syllables", "syllables"),
        ("avg_words", "Avg words", "words"),
        ("internal_rhyme_line_pct", "Internal-rhyme lines", "pct"),
        ("rhyme_entropy_bits", "Rhyme entropy", "bits"),
        ("rhyme_reuse_ratio_pct", "Rhyme reuse", "pct"),
        ("type_token_ratio", "Lexical variety", "ratio"),
    ]
    rows = []
    for key, label, unit in pairs:
        input_value = _safe_number(input_stats.get(key), 0)
        ref_value = _safe_number(pstats.get(key), 0)
        rows.append({
            "key": key,
            "label": label,
            "input": _round(input_value, 3 if unit == "ratio" else 2),
            "reference": _round(ref_value, 3 if unit == "ratio" else 2),
            "delta": _round(input_value - ref_value, 3 if unit == "ratio" else 2),
            "unit": unit,
        })
    return rows


def _advice_for_profile(input_stats: Dict[str, Any], profile: Dict[str, Any], components: Dict[str, int]) -> List[str]:
    pstats = profile.get("stats", {}) or {}
    name = str(profile.get("name") or "reference")
    notes: List[str] = []
    syll_delta = _safe_number(input_stats.get("avg_syllables")) - _safe_number(pstats.get("avg_syllables"))
    if syll_delta >= 3:
        notes.append(f"Compared with {name}, your average line is longer; split overloaded thoughts or cut connective words before changing rhymes.")
    elif syll_delta <= -3:
        notes.append(f"Compared with {name}, your average line is shorter; add pickups, internal echoes, or one concrete image before the landing.")
    else:
        notes.append(f"Cadence length is close to {name}; focus on stress placement, line endings, and internal sound.")

    internal_delta = _safe_number(input_stats.get("internal_rhyme_line_pct")) - _safe_number(pstats.get("internal_rhyme_line_pct"))
    if internal_delta <= -12:
        notes.append("Internal-rhyme density is below this reference; add one mid-line slant echo in longer bars.")
    elif internal_delta >= 18:
        notes.append("Internal-rhyme density is above this reference; clarify the syntax so the listener does not lose the point.")

    entropy_delta = _safe_number(input_stats.get("rhyme_entropy_bits")) - _safe_number(pstats.get("rhyme_entropy_bits"))
    if entropy_delta <= -1.0:
        notes.append("Rhyme entropy is lower than the reference; rotate more rhyme families across the verse to avoid one-sound fatigue.")
    elif entropy_delta >= 1.0:
        notes.append("Rhyme entropy is higher than the reference; reuse one strong family inside the hook or every four bars for identity.")

    if components.get("rhyme_key_overlap", 0) < 20:
        top_keys = ", ".join(f"/{row.get('key')}/" for row in profile.get("top_rhyme_keys", [])[:4] if row.get("key"))
        if top_keys:
            notes.append(f"Your endings do not overlap much with this reference; try writing a four-line pocket around {top_keys}.")
    for move in profile.get("benchmark_moves", [])[:2]:
        if move not in notes:
            notes.append(str(move))
    return unique_preserve(notes, 6)


def build_comparison_report(lyrics: str, analysis: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = load_comparison_profiles()
    profiles = data.get("profiles", []) or []
    if not profiles:
        return {
            "available": False,
            "metadata": data.get("metadata", {}),
            "message": "No reference profiles are available.",
            "closest_profiles": [],
        }
    details = (analysis or {}).get("raw_line_details") or build_line_details(lyrics)
    if not details:
        return {
            "available": False,
            "metadata": data.get("metadata", {}),
            "message": "Add lyric lines before comparing to rapper benchmarks.",
            "closest_profiles": [],
        }
    input_stats = _stats_from_details(details, lyrics)
    rows: List[Dict[str, Any]] = []
    for profile in profiles:
        components = _component_scores(input_stats, profile)
        score = _weighted_score(components)
        rows.append({
            "id": profile.get("id"),
            "name": profile.get("name"),
            "artist_family": profile.get("artist_family"),
            "source_label": profile.get("source_label"),
            "score": score,
            "components": components,
            "reference_stats": profile.get("stats", {}),
            "line_targets": profile.get("line_targets", {}),
            "top_rhyme_keys": profile.get("top_rhyme_keys", [])[:8],
            "deltas": _delta_rows(input_stats, profile),
            "notes": profile.get("notes", [])[:4],
            "advice": _advice_for_profile(input_stats, profile, components),
            "content_policy": profile.get("content_policy", "derived_profile_only_no_raw_lyrics"),
        })
    rows.sort(key=lambda row: (-int(row.get("score", 0)), str(row.get("name") or "")))
    individual_rows = [row for row in rows if row.get("id") != "real_rapper_blend"]
    best = individual_rows[0] if individual_rows else rows[0]
    blend = next((row for row in rows if row.get("id") == "real_rapper_blend"), None)
    recommendations = _overall_recommendations(input_stats, best, blend)
    return {
        "available": True,
        "metadata": data.get("metadata", {}),
        "input_signature": input_stats,
        "best_match": best,
        "blend_match": blend,
        "closest_profiles": rows[:8],
        "recommendations": recommendations,
        "interpretation": "Scores compare measurable flow/rhyme features. They are coaching benchmarks, not copying targets.",
    }


def _overall_recommendations(input_stats: Dict[str, Any], best: Dict[str, Any] | None, blend: Dict[str, Any] | None) -> List[str]:
    if not best:
        return []
    ref_stats = best.get("reference_stats", {}) or {}
    name = str(best.get("name") or "closest reference")
    notes: List[str] = []
    score = int(best.get("score", 0))
    if score >= 78:
        notes.append(f"Closest benchmark is {name}; your measurable pocket is already close, so revise for originality and clearer imagery.")
    elif score >= 55:
        notes.append(f"Closest benchmark is {name}, but there is still room to align cadence, internal rhymes, and rhyme-family movement.")
    else:
        notes.append(f"No single benchmark dominates; choose a target: technical density, hook bounce, narrative scope, or oblique compression.")

    q = best.get("line_targets", {}).get("one_bar_syllables") or ref_stats.get("syllable_q1_median_q3") or []
    if isinstance(q, list) and len(q) >= 2:
        notes.append(f"Use {name}'s one-bar window as a guide: roughly {q[0]}–{q[-1]} syllables before beat-specific adjustments.")
    if _safe_number(input_stats.get("rhyme_entropy_bits")) < _safe_number(ref_stats.get("rhyme_entropy_bits")) - 1:
        notes.append("Add a new rhyme family every four to eight lines so the verse evolves instead of circling one ending.")
    if _safe_number(input_stats.get("rhyme_entropy_bits")) > _safe_number(ref_stats.get("rhyme_entropy_bits")) + 1:
        notes.append("Repeat one chosen rhyme family in the hook/landing bars so the listener has a pattern to remember.")
    if _safe_number(input_stats.get("internal_rhyme_line_pct")) < _safe_number(ref_stats.get("internal_rhyme_line_pct")) - 10:
        notes.append("Raise technical pressure by adding mid-bar echoes only to lines longer than eight words.")
    if blend and int(blend.get("score", 0)) > int(best.get("score", 0)) + 8:
        notes.append("The blended benchmark fits better than an individual artist profile; keep the hybrid lane instead of forcing one comparison style.")
    return unique_preserve(notes, 6)


def line_comparison_guidance(detail: Dict[str, Any], comparison: Dict[str, Any] | None) -> Dict[str, Any]:
    if not comparison or not comparison.get("available"):
        return {"available": False, "note": "No reference benchmark guidance available."}
    best = comparison.get("best_match") or {}
    ref_name = str(best.get("name") or "closest reference")
    targets = best.get("line_targets") or {}
    target_range = targets.get("one_bar_syllables") or targets.get("syllable_q1_median_q3") or []
    target_median = _safe_number(targets.get("median_line_syllables") or (target_range[1] if len(target_range) >= 3 else 12), 12)
    low = _safe_number(target_range[0], max(6, target_median - 3)) if isinstance(target_range, list) and target_range else max(6, target_median - 3)
    high = _safe_number(target_range[-1], target_median + 3) if isinstance(target_range, list) and target_range else target_median + 3
    syllables = _safe_number(detail.get("syllables"), 0)
    if syllables > high + 2:
        action = "compress_or_split"
        note = f"Against {ref_name}, this line is over the reference pocket; cut filler or split before the final landing."
    elif syllables < low - 2:
        action = "stretch_or_pickup"
        note = f"Against {ref_name}, this line is under the reference pocket; add a pickup phrase, image, or internal echo."
    else:
        action = "protect_pocket"
        note = f"This line sits near the {ref_name} pocket; revise end-word weight and stress placement rather than length."
    line_key = str(detail.get("rhyme_key") or "")
    top_keys = [str(row.get("key")) for row in best.get("top_rhyme_keys", []) if row.get("key")]
    if line_key and line_key in top_keys:
        rhyme_note = f"/{line_key}/ overlaps the closest reference's common rhyme families."
    elif line_key:
        rhyme_note = f"/{line_key}/ is a more surprising landing against the closest reference; repeat it intentionally or resolve it quickly."
    else:
        rhyme_note = "No end-rhyme key detected for comparison."
    return {
        "available": True,
        "reference_id": best.get("id"),
        "reference_name": ref_name,
        "reference_score": best.get("score", 0),
        "target_syllable_range": [_round(low, 1), _round(high, 1)],
        "target_median_syllables": _round(target_median, 1),
        "line_syllables": _round(syllables, 1),
        "action": action,
        "note": note,
        "rhyme_note": rhyme_note,
        "benchmark_moves": best.get("advice", [])[:3],
    }
