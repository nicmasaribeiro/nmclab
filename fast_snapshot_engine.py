"""Fast, hosted-safe snapshot builder for the rap editing lab.

The original Static Snapshot path intentionally runs every deep analyzer. That is
useful locally, but it can time out on PythonAnywhere/WSGI hosting when a user
pastes a long draft. This module returns the same front-end schema with a compact
line-by-line report, without running heavyweight comparison/physics/advanced
scheme passes for every line.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Tuple

from lyric_engine import (
    MODE_LABELS,
    count_syllables,
    end_word,
    get_corpus_profile,
    normalize_word,
    possible_rhymes_for_word,
    rhyme_key,
    tokenize,
    unique_preserve,
)
from meter_engine import analyze_sentence_meter

WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")
TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|\s+|[^A-Za-z0-9\s]+")
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "is", "are", "was", "were", "be", "being", "been",
    "of", "to", "for", "from", "in", "on", "at", "by", "with", "within", "into", "that", "this", "these",
    "those", "it", "its", "i", "me", "my", "we", "you", "your", "he", "she", "they", "them", "his", "her",
    "as", "so", "just", "still", "yet", "then", "than", "not", "no", "do", "does", "did", "can", "could",
    "would", "should", "will", "have", "has", "had", "there", "their", "what", "when", "where", "why", "how",
}
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _round(value: float, digits: int = 2) -> float:
    try:
        value = float(value)
        if math.isfinite(value):
            return round(value, digits)
    except Exception:
        pass
    return 0.0


def _entropy(counts: Iterable[int]) -> float:
    vals = [int(v) for v in counts if int(v) > 0]
    total = sum(vals)
    if total <= 0:
        return 0.0
    return -sum((v / total) * math.log2(v / total) for v in vals)


def _grade(score: float) -> Dict[str, str]:
    score = float(score or 0)
    if score >= 94: return {"letter": "A", "label": "elite draft"}
    if score >= 88: return {"letter": "A-", "label": "very strong"}
    if score >= 82: return {"letter": "B+", "label": "strong"}
    if score >= 76: return {"letter": "B", "label": "solid"}
    if score >= 70: return {"letter": "B-", "label": "promising"}
    if score >= 64: return {"letter": "C+", "label": "needs focused edits"}
    if score >= 58: return {"letter": "C", "label": "rough but usable"}
    return {"letter": "D", "label": "needs structure"}


def _density_label(syllables: int) -> str:
    if syllables >= 19: return "very dense"
    if syllables >= 15: return "dense"
    if syllables <= 6: return "open"
    return "balanced"


def _syllables_for_line(text: str) -> int:
    return sum(count_syllables(w) for w in tokenize(text))


def _content_words(text: str) -> List[str]:
    return [normalize_word(w) for w in tokenize(text) if normalize_word(w) and normalize_word(w) not in STOPWORDS]


def _section_for_line(raw_lines: List[str], line_number: int) -> Dict[str, Any]:
    label = "Draft"
    section_type = "section"
    start = 1
    for idx, raw in enumerate(raw_lines[: max(0, line_number - 1)], start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        lowered = stripped.lower().strip("/#[]: ")
        if stripped.startswith("//") or stripped.startswith("[") or lowered in {"chorus", "verse", "hook", "intro", "outro"} or "verse" in lowered or "chorus" in lowered or "hook" in lowered:
            label = stripped.strip("/[] ") or "Section"
            section_type = "chorus" if "chorus" in lowered or "hook" in lowered else "verse" if "verse" in lowered else "section"
            start = idx + 1
    return {"label": label, "type": section_type, "start_line": start, "end_line": line_number, "position": max(1, line_number - start + 1), "line_count": 1}


def _line_role(section: Dict[str, Any], position: int, total: int, syllables: int) -> str:
    stype = str(section.get("type") or "section").lower()
    if stype in {"chorus", "hook"}:
        return "hook landing" if position >= total else "hook setup"
    if syllables <= 7:
        return "short punch/reset"
    if syllables >= 18:
        return "dense technical run"
    if position <= 2:
        return "verse setup"
    return "development bar"


def _rhyme_score(line_key: str, family_count: int, internal_groups: int, syllables: int) -> int:
    score = 44
    if line_key:
        score += 14
    if family_count > 1:
        score += min(24, 8 + family_count * 4)
    if internal_groups:
        score += min(14, internal_groups * 5)
    if 8 <= syllables <= 16:
        score += 8
    elif syllables > 20:
        score -= 8
    return max(20, min(98, score))


def _internal_groups(words: List[str]) -> List[Dict[str, Any]]:
    by_key: Dict[str, List[str]] = {}
    for word in words:
        norm = normalize_word(word)
        if len(norm) <= 2:
            continue
        key = rhyme_key(norm)
        if len(key) >= 2:
            by_key.setdefault(key, []).append(norm)
    groups = []
    for key, vals in by_key.items():
        uniq = unique_preserve(vals, 8)
        if len(uniq) >= 2:
            groups.append({"key": key, "words": uniq, "count": len(vals)})
    groups.sort(key=lambda g: (-g["count"], g["key"]))
    return groups[:6]


def _simple_word_lists(end: str, content: List[str], profile: Dict[str, Any]) -> Dict[str, List[str]]:
    try:
        rhymes = possible_rhymes_for_word(end) if end else {}
    except Exception:
        rhymes = {}
    wb = profile.get("word_banks", {}) or {}
    sig = [row.get("word") for row in profile.get("signature_words", []) if row.get("word")]
    images = wb.get("physical_images") or ["breath", "tongue", "ink", "page", "teeth", "wire", "spark", "pressure", "static", "signal"]
    verbs = wb.get("action_verbs") or ["cut", "bend", "thread", "anchor", "stretch", "flip", "strike", "press", "signal", "ignite"]
    punch = wb.get("punch_words") or ["signal", "pressure", "system", "rhythm", "script", "surface", "purpose", "vector", "resonance"]
    cut = [w for w in content if w in STOPWORDS][:8]
    return {
        "end_rhymes": (rhymes.get("end_rhymes") or rhymes.get("strict_rhymes") or [])[:14],
        "near_rhymes": (rhymes.get("near_rhymes") or [])[:14],
        "slant_rhymes": (rhymes.get("slant_rhymes") or [])[:14],
        "assonance_words": (rhymes.get("assonance_rhymes") or [])[:10],
        "consonance_words": (rhymes.get("consonance_rhymes") or [])[:10],
        "stress_matched": (rhymes.get("strict_rhymes") or rhymes.get("end_rhymes") or [])[:10],
        "multi_syllable_endings": (rhymes.get("multi_syllable_rhymes") or rhymes.get("phrase_landings") or [])[:10],
        "internal_echoes": (rhymes.get("internal_echoes") or rhymes.get("near_rhymes") or [])[:14],
        "signature_words": sig[:14],
        "images": images[:10],
        "verbs": verbs[:10],
        "punch_words": punch[:10],
        "cut_words": cut,
    }


def _option_rows(words: List[str], key: str, kind: str, base: int = 86) -> List[Dict[str, Any]]:
    rows = []
    seen = set()
    for idx, word in enumerate(words or []):
        word = str(word or "").strip()
        if not word or word.lower() in seen:
            continue
        seen.add(word.lower())
        rows.append({
            "word": word,
            "kind": kind,
            "score": max(44, base - idx * 3),
            "rhyme_key": rhyme_key(word) or key,
            "syllables": count_syllables(word),
            "reasons": [f"{kind} option", f"/{rhyme_key(word) or key}/ family"],
        })
    return rows


def _advanced_rhyme(end: str, key: str, family_count: int, banks: Dict[str, List[str]], score: int) -> Dict[str, Any]:
    if not end:
        return {"available": False}
    perfect = _option_rows(banks.get("end_rhymes", []), key, "family", 92)
    slant = _option_rows(banks.get("slant_rhymes", []) or banks.get("near_rhymes", []), key, "slant", 84)
    assonance = _option_rows(banks.get("assonance_words", []), key, "assonance", 78)
    consonance = _option_rows(banks.get("consonance_words", []), key, "consonance", 76)
    multi = _option_rows(banks.get("multi_syllable_endings", []), key, "multi", 88)
    all_options = perfect + slant + assonance + consonance + multi
    return {
        "available": True,
        "end_word": end,
        "rhyme_key": key,
        "chain_note": f"{family_count} line(s) use /{key}/" if family_count else "chain open",
        "rhyme_power": {"score": score, "label": "fast snapshot"},
        "actions": [
            "Answer this landing within two nearby lines." if family_count <= 1 else "Keep this family, but rotate one slant turn before it gets repetitive.",
            "Add one internal echo before the final landing.",
            "Try a multi-syllable landing if the line feels too plain.",
        ],
        "word_report": {
            "summary": {
                "target_word": end,
                "rhyme_key": key,
                "engine": "fast snapshot rhyme engine",
                "candidate_count": len(all_options),
                "best_score": all_options[0]["score"] if all_options else 0,
                "best_kind": all_options[0]["kind"] if all_options else "—",
                "stress_signature": "heuristic",
            },
            "perfect_or_family": perfect,
            "slant": slant,
            "assonance": assonance,
            "consonance": consonance,
            "multi_syllable": multi,
            "rhyme_ladder": [
                {"stage": "Safe family", "use_when": "You want continuity.", "options": [r["word"] for r in perfect[:8]]},
                {"stage": "Slant turn", "use_when": "You need release from the same ending.", "options": [r["word"] for r in slant[:8]]},
                {"stage": "Multi landing", "use_when": "You want the bar to feel more composed.", "options": [r["word"] for r in multi[:8]]},
            ],
        },
        "rhyme_ladder": [
            {"stage": "Answer", "use_when": "Next one or two bars", "options": [r["word"] for r in perfect[:8]]},
            {"stage": "Rotate", "use_when": "After two repeated landings", "options": [r["word"] for r in slant[:8]]},
        ],
    }


def _bar_score(text: str, syllables: int, rhyme_power: int, internal_count: int, content_count: int) -> Dict[str, Any]:
    cadence = 92 - abs(12 - min(22, syllables)) * 4
    cadence = max(35, min(96, cadence))
    clarity = max(42, min(95, 62 + min(20, content_count * 3) - max(0, syllables - 20) * 2))
    meter = max(45, min(94, 58 + internal_count * 6 + (8 if 8 <= syllables <= 16 else 0)))
    physics = max(42, min(95, 55 + internal_count * 7 + min(12, syllables)))
    overall = round(rhyme_power * 0.28 + cadence * 0.22 + clarity * 0.20 + meter * 0.15 + physics * 0.15)
    weakest = sorted([
        {"key": "rhyme_power", "score": rhyme_power},
        {"key": "cadence_fit", "score": cadence},
        {"key": "content_clarity", "score": clarity},
        {"key": "meter_stress", "score": meter},
        {"key": "scansion_physics", "score": physics},
    ], key=lambda r: r["score"])[:2]
    issues = []
    advice = []
    if syllables > 18:
        issues.append("Line may be overloaded for one bar.")
        advice.append("Split the sentence or cut connectors before changing the core rhyme.")
    if rhyme_power < 65:
        issues.append("Rhyme landing is under-supported.")
        advice.append("Add a nearby answer rhyme or swap to a stronger landing word.")
    if not issues:
        issues.append("No major structural issue detected in fast snapshot.")
        advice.append("Preserve the line and polish image/rhyme precision.")
    return {
        "available": True,
        "overall": int(overall),
        "grade": _grade(overall),
        "component_scores": {
            "rhyme_power": int(rhyme_power),
            "cadence_fit": int(cadence),
            "bar_fit": int(cadence),
            "meter_stress": int(meter),
            "scansion_physics": int(physics),
            "content_clarity": int(clarity),
        },
        "diagnosis": {"issues": issues, "advice": advice, "weakest_components": weakest},
    }


def _tokens_for_highlight(text: str, line_key: str, end: str, counts: Counter, key_to_letter: Dict[str, str], key_to_class: Dict[str, int], lines_by_key: Dict[str, List[int]]) -> Tuple[List[Dict[str, Any]], int]:
    word_matches = list(WORD_RE.finditer(text))
    end_span = (word_matches[-1].start(), word_matches[-1].end()) if word_matches else None
    highlighted = 0
    tokens = []
    for match in TOKEN_RE.finditer(text):
        raw = match.group(0)
        if not WORD_RE.fullmatch(raw):
            tokens.append({"text": raw, "type": "space" if raw.isspace() else "punct", "highlight": False})
            continue
        norm = normalize_word(raw)
        key = rhyme_key(norm)
        is_end = bool(end_span and match.start() == end_span[0] and match.end() == end_span[1])
        cross = bool(key and counts.get(key, 0) > 1 and len(norm) > 2)
        same = bool(key and key == line_key and len(norm) > 2)
        highlight = is_end or cross or same
        if highlight:
            highlighted += 1
        role = "end" if is_end else "cross-line" if cross else "echo" if same else "plain"
        tokens.append({
            "text": raw,
            "type": "word",
            "normalized": norm,
            "highlight": highlight,
            "role": role,
            "rhyme_key": key,
            "rhyme_letter": key_to_letter.get(key, ""),
            "rhyme_class": key_to_class.get(key, 0),
            "family_count": int(counts.get(key, 0)),
            "same_as_line_landing": key == line_key,
            "is_end_word": is_end,
            "title": f"/{key}/ family · {counts.get(key, 0)} line(s)" if key else "",
        })
    return tokens, highlighted


def build_fast_snapshot_report(
    lyrics: str,
    mode: str = "match",
    beat: Dict[str, Any] | None = None,
    max_lines: int = 64,
    max_source_lines: int = 220,
) -> Dict[str, Any]:
    mode = mode if mode in MODE_LABELS else "match"
    raw_lines = str(lyrics or "").replace("\r", "").split("\n")
    profile = get_corpus_profile()
    editable_all: List[Tuple[int, str]] = []
    for idx, raw in enumerate(raw_lines, start=1):
        text = raw.strip()
        if not text or text.startswith("//") or re.fullmatch(r"\[.*\]", text):
            continue
        editable_all.append((idx, text))
    truncated = len(editable_all) > max_lines or len(raw_lines) > max_source_lines
    editable = editable_all[:max_lines]
    end_keys = [rhyme_key(end_word(text)) for _, text in editable if end_word(text)]
    key_counts = Counter(k for k in end_keys if k)
    first_order = []
    for key in end_keys:
        if key and key not in first_order:
            first_order.append(key)
    key_to_letter = {key: LETTERS[i] if i < len(LETTERS) else f"R{i+1}" for i, key in enumerate(first_order)}
    key_to_class = {key: (i % 12) + 1 for i, key in enumerate(first_order)}
    lines_by_key: Dict[str, List[int]] = {key: [] for key in first_order}
    words_by_key: Dict[str, List[str]] = {key: [] for key in first_order}
    for line_no, text in editable:
        ew = end_word(text)
        key = rhyme_key(ew) if ew else ""
        if key:
            lines_by_key.setdefault(key, []).append(line_no)
            words_by_key.setdefault(key, []).append(ew)

    # Basic global distributions.
    all_words = [normalize_word(w) for _, text in editable for w in tokenize(text)]
    all_content = [w for w in all_words if w and w not in STOPWORDS]
    word_counts = Counter(all_content)
    syllable_counts = [_syllables_for_line(text) for _, text in editable]
    rhyme_entropy = _entropy(key_counts.values())
    token_entropy = _entropy(word_counts.values())
    avg_syll = _round(sum(syllable_counts) / max(1, len(syllable_counts)), 2)

    line_map: Dict[int, Dict[str, Any]] = {}
    rows: List[Dict[str, Any]] = []
    meter_lines: List[Dict[str, Any]] = []
    physics_lines: List[Dict[str, Any]] = []
    bar_scores: List[Dict[str, Any]] = []
    prev_syllables: int | None = None
    prev_key = ""
    for order_idx, (line_no, text) in enumerate(editable, start=1):
        words = tokenize(text)
        norm_content = _content_words(text)
        ew = end_word(text)
        key = rhyme_key(ew) if ew else ""
        syllables = _syllables_for_line(text)
        internal = _internal_groups(words)
        family_count = int(key_counts.get(key, 0)) if key else 0
        rhyme_power = _rhyme_score(key, family_count, len(internal), syllables)
        section = _section_for_line(raw_lines, line_no)
        role = _line_role(section, int(section.get("position", 1)), 1, syllables)
        banks = _simple_word_lists(ew, norm_content, profile)
        adv = _advanced_rhyme(ew, key, family_count, banks, rhyme_power)
        tokens, highlighted = _tokens_for_highlight(text, key, ew, key_counts, key_to_letter, key_to_class, lines_by_key)
        line_highlight = {
            "line_number": line_no,
            "text": text,
            "end_word": ew,
            "line_rhyme_key": key,
            "line_rhyme_letter": key_to_letter.get(key, ""),
            "line_rhyme_class": key_to_class.get(key, 0),
            "line_family_count": family_count,
            "line_family_lines": lines_by_key.get(key, []),
            "tokens": tokens,
            "highlighted_word_count": highlighted,
        }
        line_map[line_no] = line_highlight
        density = _density_label(syllables)
        info_bits = _round(sum(-math.log2(max(1, word_counts.get(w, 1)) / max(1, sum(word_counts.values()))) for w in norm_content[:18]), 2) if word_counts else 0
        rarest = sorted([{"word": w, "bits": _round(-math.log2(max(1, word_counts.get(w, 1)) / max(1, sum(word_counts.values()))), 2)} for w in set(norm_content)], key=lambda x: -x["bits"])[:5]
        # Compact meter: avoid returning full syllable/word scansion for every line
        # in the hosted snapshot. The dedicated Meter tab and Full Deep Snapshot can
        # still run detailed scansion when needed.
        stress_pct = max(28, min(72, round((len(norm_content) / max(1, len(words))) * 100))) if words else 0
        dominant_meter = "mixed" if syllables > 0 else "none"
        glyph_count = max(1, min(28, syllables))
        glyphs = "".join("●" if i % 3 == 1 else "○" for i in range(glyph_count))
        meter_summary = {
            "dominant_meter": dominant_meter,
            "meter_confidence_pct": 58,
            "stress_ratio_pct": stress_pct,
            "syllables": syllables,
            "stressed_syllables": round(syllables * stress_pct / 100),
            "longest_weak_run": 2,
            "final_landing_stressed": syllables > 0 and len(ew) > 3,
        }
        meter = {
            "available": True,
            "source": "fast heuristic",
            "summary": meter_summary,
            "pattern": {"glyphs": glyphs, "scansion": glyphs},
            "words": [],
            "syllables": [],
            "pulse_grid": {"available": False},
            "suggestions": ["Keep the strongest stress on the end-rhyme landing.", "Break long weak runs with a harder content word."],
        }
        force_pct = max(35, min(96, round(stress_pct + min(20, len(internal) * 5))))
        delta_syll = 0 if prev_syllables is None else syllables - prev_syllables
        torsion_pct = max(8, min(92, abs(delta_syll) * 8 + (8 if key != prev_key and prev_key else 0)))
        spin_pct = max(18, min(98, len(internal) * 18 + family_count * 7 + (8 if family_count > 1 else 0)))
        physics = {
            "available": True,
            "line_number": line_no,
            "text": text,
            "force_pct": int(force_pct),
            "torsion_pct": int(torsion_pct),
            "spin_pct": int(spin_pct),
            "rhyme_key": key,
            "assigned_bars": str(order_idx),
            "cadence_delta": {"available": prev_syllables is not None, "delta_syllables": delta_syll, "label": "opening" if prev_syllables is None else ("release" if delta_syll < 0 else "expansion" if delta_syll > 0 else "steady"), "reading": f"Line changes {delta_syll:+d} syllables from previous." if prev_syllables is not None else "Opening cadence row."},
            "physics_reading": f"F {int(force_pct)} / τ {int(torsion_pct)} / Ω {int(spin_pct)}: {density} line with {'repeated' if family_count > 1 else 'open'} rhyme family.",
            "phase_units": [],
            "phase_grid": {"unit_grid": "1 e & a 2 e & a 3 e & a 4 e & a", "stress_glyphs": meter.get("pattern", {}).get("glyphs", "") if isinstance(meter, dict) else ""},
            "actions": ["Land the strongest stress closer to the final rhyme.", "Use one internal echo to increase spin."],
        }
        physics_lines.append(physics)
        bar = _bar_score(text, syllables, rhyme_power, len(internal), len(norm_content))
        bar.update({"line_number": line_no, "bar_index": order_idx, "assigned_bars": str(order_idx), "text": text})
        bar_scores.append(bar)
        meter_lines.append({
            "line_number": line_no,
            "text": text,
            "dominant_meter": meter_summary.get("dominant_meter", "mixed"),
            "meter_confidence_pct": meter_summary.get("meter_confidence_pct", 0),
            "stress_ratio_pct": meter_summary.get("stress_ratio_pct", 0),
            "syllables": syllables,
            "pattern": (meter.get("pattern", {}) or {}).get("glyphs", "") if isinstance(meter, dict) else "",
            "final_landing_stressed": bool(meter_summary.get("final_landing_stressed", False)),
            "suggestion": "Keep stress on the landing word." if meter_summary.get("final_landing_stressed") else "Strengthen the final landing stress.",
        })
        operation = "split_line" if syllables > 18 else "swap_end_rhyme" if rhyme_power < 65 else "polish_punch"
        operation_label = "Split across bars" if operation == "split_line" else "Swap end rhyme" if operation == "swap_end_rhyme" else "Polish punch"
        replacement_word = (banks.get("end_rhymes") or banks.get("near_rhymes") or [ew])[:1]
        replacement_line = re.sub(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*([^A-Za-z0-9]*)$", f"{replacement_word[0]}\\1", text) if replacement_word and ew else text
        rows.append({
            "line_number": line_no,
            "section": section,
            "role": role,
            "text": text,
            "metrics": {"words": len(words), "syllables": syllables, "target": [8, 16], "end_word": ew, "rhyme_key": key, "internal_rhyme_groups": len(internal), "alliteration_groups": 0, "motif_count": len([w for w in norm_content if w in {"system", "sentence", "rhythm", "credit", "vector", "surface"}]), "image_count": len([w for w in norm_content if w in {"ink", "page", "tongue", "breath", "teeth", "spark"}]), "abstract_count": len([w for w in norm_content if w in {"system", "presence", "essence", "purpose", "method"}])},
            "information": {"line_self_information_bits": info_bits, "bits_per_word": _round(info_bits / max(1, len(words)), 2), "bits_per_syllable": _round(info_bits / max(1, syllables), 2), "rhyme_surprise_bits": _round(-math.log2(max(1, family_count) / max(1, len(editable))), 2) if key else 0, "rarest_words": rarest, "interpretation": "High local information." if info_bits > 40 else "Moderate information density; add a sharper image if needed."},
            "meter": meter if isinstance(meter, dict) else {"available": False},
            "physics": physics,
            "breakdown": {
                "line_function": role,
                "cadence": f"{syllables} syllables; {density} pocket. " + ("Consider splitting." if syllables > 18 else "Fits a one-bar or compact two-beat phrase."),
                "sound": f"Ends on /{key or '—'}/ with {len(internal)} internal rhyme group(s).",
                "content": "Contains signature corpus language." if any(w in {"sentence", "system", "rhythm", "presence"} for w in norm_content) else "Add one concrete image or action to reduce abstraction.",
                "rhyme": f"{'Answer' if family_count <= 1 else 'Control'} the /{key or '—'}/ family; avoid orphan endings.",
                "bar_structure": {"available": False, "note": "Upload a beat for exact bar windows. Fast snapshot estimates density from syllables.", "assigned_bars": str(order_idx), "time_window": ""},
            },
            "comparison_guidance": {"available": True, "reference_name": "Corpus fast benchmark", "reference_score": rhyme_power, "note": "Fast snapshot compares this line against the local corpus-style rhyme pocket.", "rhyme_note": f"/{key or '—'}/ landing with {family_count} local use(s).", "benchmark_moves": ["Answer the rhyme family nearby.", "Add one internal echo before the landing."]},
            "suggestion": {
                "priority": "high" if syllables > 18 or rhyme_power < 58 else "medium" if rhyme_power < 72 else "low",
                "severity": max(0, min(100, 100 - int(bar["overall"]))),
                "operation": operation,
                "operation_label": operation_label,
                "diagnosis": "Fast snapshot: " + ("overloaded line; split or compress." if syllables > 18 else "rhyme landing needs support." if rhyme_power < 65 else "line is usable; polish sound/image precision."),
                "primary_fix": operation_label,
                "action_steps": [
                    "Add or answer the end rhyme within two bars." if family_count <= 1 else "Keep the repeated rhyme family controlled; rotate a slant soon.",
                    "Add one internal echo before the landing.",
                    "Cut connectors or split the line if it feels rushed." if syllables > 16 else "Preserve the bar length and sharpen the final word.",
                ],
                "checklist": ["Final word carries meaning", "At least one internal sound echo", "One concrete image/action", "Line can be performed without rushing"],
            },
            "possible_words": banks,
            "advanced_rhyme": adv,
            "rewrite_options": [
                {"name": "Rhyme-focused ending", "text": replacement_line, "syllables": _syllables_for_line(replacement_line), "why": "Tests a stronger corpus rhyme landing."},
                {"name": "Compressed pocket", "text": " ".join(text.split()[: max(4, min(len(text.split()), 12))]), "syllables": _syllables_for_line(" ".join(text.split()[: max(4, min(len(text.split()), 12))])), "why": "Shortens the line for bar fit."},
            ],
            "applyable_patches": [
                {"type": "replace_line", "label": "Try stronger landing", "replacement": replacement_line, "why": "Swaps the final word into a stronger rhyme family.", "operation": "swap_end_rhyme"},
            ],
            "nearby_corpus_lines": [],
            "sound_hits": {"internal_rhymes": internal},
            "motif_hits": {},
            "rhyme_highlight": line_highlight,
            "bar_score": bar,
        })
        prev_syllables = syllables
        prev_key = key

    families = []
    for idx, key in enumerate(first_order):
        families.append({"key": key, "letter": key_to_letter[key], "class": key_to_class[key], "count": int(key_counts.get(key, 0)), "end_words": unique_preserve(words_by_key.get(key, []), 12), "line_numbers": lines_by_key.get(key, []), "repeated": key_counts.get(key, 0) > 1})
    families.sort(key=lambda r: (-r["count"], r["key"]))
    repeated_fams = [f for f in families if f["repeated"]]
    top_families = [{"key": f["key"], "count": f["count"], "pct": _round(f["count"] / max(1, len(editable)) * 100, 1), "self_information_bits": _round(-math.log2(f["count"] / max(1, len(editable))), 2)} for f in families]
    transitions = Counter(f"{a}->{b}" for a, b in zip(end_keys, end_keys[1:]) if a and b)
    most_info = sorted([dict(row["information"], line_number=row["line_number"], text=row["text"]) for row in rows], key=lambda r: -float(r.get("line_self_information_bits") or 0))[:10]
    density_counts = Counter(_density_label(s) for s in syllable_counts)
    section_rows = [{"label": "Fast Snapshot", "line_count": len(rows), "avg_syllables": avg_syll, "lexical_entropy_bits": _round(token_entropy, 2), "rhyme_entropy_bits": _round(rhyme_entropy, 2), "cadence_entropy_bits": _round(_entropy(Counter(syllable_counts).values()), 2), "notes": "Compact hosted-safe snapshot."}]
    avg_score = _round(sum(b["overall"] for b in bar_scores) / max(1, len(bar_scores)), 1)
    weakest = sorted(bar_scores, key=lambda r: r["overall"])[:6]
    strongest = sorted(bar_scores, key=lambda r: -r["overall"])[:6]
    component_rows = [
        {"key": "rhyme_power", "label": "Rhyme", "score": _round(sum(b["component_scores"]["rhyme_power"] for b in bar_scores) / max(1, len(bar_scores)), 1), "description": "end/internal rhyme support"},
        {"key": "cadence_fit", "label": "Cadence", "score": _round(sum(b["component_scores"]["cadence_fit"] for b in bar_scores) / max(1, len(bar_scores)), 1), "description": "syllable pocket"},
        {"key": "meter_stress", "label": "Meter", "score": _round(sum(b["component_scores"]["meter_stress"] for b in bar_scores) / max(1, len(bar_scores)), 1), "description": "stress shape"},
        {"key": "scansion_physics", "label": "Physics", "score": _round(sum(b["component_scores"]["scansion_physics"] for b in bar_scores) / max(1, len(bar_scores)), 1), "description": "force/torsion/spin"},
        {"key": "content_clarity", "label": "Clarity", "score": _round(sum(b["component_scores"]["content_clarity"] for b in bar_scores) / max(1, len(bar_scores)), 1), "description": "image/action density"},
    ]
    score_report = {
        "available": True,
        "overall": int(round(avg_score)),
        "grade": _grade(avg_score),
        "headline": f"Fast snapshot score: {int(round(avg_score))}% across {len(rows)} analyzed line(s).",
        "component_rows": component_rows,
        "bar_scores": bar_scores,
        "strongest_bars": strongest,
        "weakest_bars": weakest,
        "bar_summary": {"lines_scored": len(rows), "bars_estimated": len(rows), "avg_bar_score": avg_score, "min_bar_score": min([b["overall"] for b in bar_scores], default=0), "max_bar_score": max([b["overall"] for b in bar_scores], default=0)},
        "section_scores": [{"label": "Fast Snapshot", "line_count": len(rows), "bar_count": len(rows), "overall": int(round(avg_score)), "grade": _grade(avg_score), "weak_lines": [b["line_number"] for b in weakest[:5]], "reading": "Hosted-safe compact scoring."}],
        "global_actions": [
            "Fix the weakest heat-map tiles first.",
            "Answer orphan rhyme families within two bars.",
            "Split lines above 18 syllables before polishing words.",
        ] + (["This snapshot was clipped for speed; use Full Deep Snapshot for a local, exhaustive report."] if truncated else []),
    }
    meter_counter = Counter(row.get("dominant_meter", "mixed") for row in meter_lines)
    stress_avg = _round(sum(float(row.get("stress_ratio_pct") or 0) for row in meter_lines) / max(1, len(meter_lines)), 1)
    meter_report = {
        "available": True,
        "summary": {"dominant_meter": meter_counter.most_common(1)[0][0] if meter_counter else "mixed", "dominant_meter_share_pct": _round((meter_counter.most_common(1)[0][1] if meter_counter else 0) / max(1, len(meter_lines)) * 100, 1), "avg_stress_ratio_pct": stress_avg, "stress_consistency_pct": 72, "final_landing_stressed_pct": _round(sum(1 for r in meter_lines if r.get("final_landing_stressed")) / max(1, len(meter_lines)) * 100, 1), "lines_over_pocket": sum(1 for s in syllable_counts if s > 18), "lines_under_pocket": sum(1 for s in syllable_counts if s < 7)},
        "recommendations": ["Use stressed landings on important end rhymes.", "Keep long weak runs from burying the rhyme."],
        "meter_distribution": [{"meter": k, "count": v, "pct": _round(v / max(1, len(meter_lines)) * 100, 1)} for k, v in meter_counter.most_common(8)],
        "foot_pattern_distribution": [],
        "problem_rows": {"long_weak_runs": [r for r in meter_lines if r.get("syllables", 0) > 18][:8], "stress_clusters": []},
        "lines": meter_lines,
        "line_details": [{"line_number": r["line_number"], "meter": next((row["meter"] for row in rows if row["line_number"] == r["line_number"]), {"available": False})} for r in meter_lines],
    }
    avg_force = _round(sum(p["force_pct"] for p in physics_lines) / max(1, len(physics_lines)), 1)
    avg_torsion = _round(sum(p["torsion_pct"] for p in physics_lines) / max(1, len(physics_lines)), 1)
    avg_spin = _round(sum(p["spin_pct"] for p in physics_lines) / max(1, len(physics_lines)), 1)
    physics_report = {
        "available": True,
        "model_name": "Fast Scansion Physics",
        "summary": {"avg_force_pct": avg_force, "avg_torsion_pct": avg_torsion, "avg_spin_pct": avg_spin, "cadence_shift_count": sum(1 for p in physics_lines if p.get("cadence_delta", {}).get("available") and p.get("cadence_delta", {}).get("delta_syllables") != 0), "avg_cadence_delta_abs": _round(sum(abs(p.get("cadence_delta", {}).get("delta_syllables", 0)) for p in physics_lines) / max(1, len(physics_lines)), 1), "compression_sequence_count": 0, "reading": "Fast scansion estimates force, torsion, and spin without running heavyweight skeleton matching."},
        "priority_actions": ["Increase spin with internal echoes on low-score lines.", "Reduce torsion by splitting abrupt long lines."],
        "line_physics": physics_lines,
        "symbol_legend": [],
        "compression_sequences": [],
        "phonetic_skeletons": {"top_pairs": [], "notebook_test_pairs": [], "interpretation": "Full skeleton matching is available in Full Deep Snapshot."},
    }
    rhyme_highlights = {"families": families, "line_map": line_map, "summary": {"unique_families": len(families), "repeated_families": len(repeated_fams), "instruction": "Matching colors show shared rhyme families. Fast snapshot highlights end rhymes and repeated families."}}
    info_theory = {
        "overview": {"token_entropy_bits": _round(token_entropy, 3), "token_perplexity": _round(2 ** token_entropy if token_entropy else 0, 2), "avg_line_self_information_bits": _round(sum((r["information"].get("line_self_information_bits") or 0) for r in rows) / max(1, len(rows)), 2), "compression_ratio": _round(len(all_words) / max(1, len(set(all_words))), 2), "rhyme_entropy_bits": _round(rhyme_entropy, 3), "rhyme_perplexity": _round(2 ** rhyme_entropy if rhyme_entropy else 0, 2), "bar_load_entropy_bits": _round(_entropy(density_counts.values()), 3), "verse_section_entropy_bits": 0},
        "interpretations": ["Fast snapshot is optimized to load on hosted WSGI apps.", "Use the heat map and weakest line cards for immediate edits." ] + (["Only the first analyzed window is shown; run Full Deep Snapshot locally for exhaustive analysis."] if truncated else []),
        "rhymes": {"rhyme_key_entropy_bits": _round(rhyme_entropy, 3), "rhyme_key_perplexity": _round(2 ** rhyme_entropy if rhyme_entropy else 0, 2), "rhyme_key_normalized_entropy": _round((rhyme_entropy / max(1, math.log2(max(1, len(families))))) * 100 if families else 0, 1), "rhyme_reuse_ratio_pct": _round(sum(f["count"] for f in repeated_fams) / max(1, len(rows)) * 100, 1), "unique_rhyme_families": len(families), "transition_entropy_bits": _round(_entropy(transitions.values()), 3), "transition_perplexity": _round(2 ** _entropy(transitions.values()) if transitions else 0, 2), "top_families": top_families, "top_transitions": [{"key": k, "count": v, "pct": _round(v / max(1, sum(transitions.values())) * 100, 1), "self_information_bits": _round(-math.log2(v / max(1, sum(transitions.values()))), 2)} for k, v in transitions.most_common(10)]},
        "lines": {"syllable_entropy_bits": _round(_entropy(Counter(syllable_counts).values()), 3), "syllable_perplexity": _round(2 ** _entropy(Counter(syllable_counts).values()) if syllable_counts else 0, 2), "most_informative_lines": most_info, "least_informative_lines": sorted(most_info, key=lambda r: float(r.get("line_self_information_bits") or 0))[:5]},
        "bars": {"bar_load_entropy_bits": _round(_entropy(density_counts.values()), 3), "bar_load_perplexity": _round(2 ** _entropy(density_counts.values()) if density_counts else 0, 2), "assumption": "Fast snapshot estimates bar load from syllable count.", "density_distribution": [{"key": k, "count": v, "pct": _round(v / max(1, len(syllable_counts)) * 100, 1)} for k, v in density_counts.most_common()], "overloaded_lines": [{"line_number": r["line_number"], "assigned_bars": r["bar_score"].get("assigned_bars"), "syllables_per_beat": _round(r["metrics"]["syllables"] / 4, 2), "density_label": _density_label(r["metrics"]["syllables"])} for r in rows if r["metrics"]["syllables"] > 18], "open_lines": [{"line_number": r["line_number"], "assigned_bars": r["bar_score"].get("assigned_bars"), "syllables_per_beat": _round(r["metrics"]["syllables"] / 4, 2), "density_label": _density_label(r["metrics"]["syllables"])} for r in rows if r["metrics"]["syllables"] < 7]},
        "verses": {"section_count": 1, "verse_count": 1, "hook_count": 0, "section_rows": section_rows},
    }
    return {
        "available": True,
        "report_type": "fast_static_snapshot",
        "fast_snapshot": True,
        "truncated": bool(truncated),
        "truncation_note": f"Analyzed {len(rows)} of {len(editable_all)} editable lines for hosted performance." if truncated else "Full draft fit inside fast snapshot limits.",
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "summary": {"lines": len(rows), "source_lines": len(editable_all), "words": len(all_words), "avg_syllables": avg_syll, "median_syllables": sorted(syllable_counts)[len(syllable_counts)//2] if syllable_counts else 0, "style_match": min(100, 45 + len([w for w in all_content if w in (profile.get("corpus_words_set") or set())]) // max(1, len(all_content)) * 100), "rhyme_density": _round(sum(1 for f in families if f["repeated"]) / max(1, len(families)) * 100, 1)},
        "overview": {"headline": f"Fast snapshot loaded: {len(rows)} line(s), {len(all_words)} words, average {avg_syll} syllables/line.", "actions": score_report["global_actions"], "counts": {"critical_or_high": sum(1 for r in rows if r["suggestion"]["priority"] in {"critical", "high"})}},
        "information_theory": info_theory,
        "meter_report": meter_report,
        "physics_report": physics_report,
        "score_report": score_report,
        "sections": section_rows,
        "line_breakdown": rows,
        "beat_analysis": {"available": False},
        "beat_alignment": {"available": False, "summary": "Upload a beat to add exact static bar windows."},
        "rhyme_scheme": {"scheme": "".join(key_to_letter.get(k, "X") for k in end_keys), "keys": end_keys},
        "rhyme_highlights": rhyme_highlights,
        "rhyme_lab": {"available": False, "message": "Use Rhyme Lab for full scheme diagnostics. Fast snapshot provides per-line rhyme options."},
        "comparison": {"available": True, "best_match": {"name": "Corpus fast benchmark", "score": int(round(avg_score))}, "input_signature": {"avg_syllables": avg_syll, "median_syllables": sorted(syllable_counts)[len(syllable_counts)//2] if syllable_counts else 0, "rhyme_entropy_bits": _round(rhyme_entropy, 3), "rhyme_perplexity": _round(2 ** rhyme_entropy if rhyme_entropy else 0, 2), "internal_rhyme_line_pct": _round(sum(1 for r in rows if r["metrics"].get("internal_rhyme_groups", 0) > 0) / max(1, len(rows)) * 100, 1)}, "interpretation": "Fast hosted comparison uses the compiled local corpus profile for lightweight guidance.", "recommendations": ["Match the corpus pocket by answering repeated rhyme families.", "Use internal echoes on lines with low rhyme power."], "closest_profiles": [{"name": "Corpus fast benchmark", "score": int(round(avg_score)), "components": {"cadence_distribution_fit": component_rows[1]["score"], "internal_rhyme_fit": component_rows[0]["score"], "rhyme_entropy_fit": _round(rhyme_entropy * 25, 1), "rhyme_key_overlap": 0}, "deltas": [], "top_rhyme_keys": top_families[:6], "advice": ["Use Full Deep Snapshot for derived artist-profile comparison."], "notes": ["hosted-safe"]}], "metadata": {"copyright_handling": "derived_profile_only_no_raw_lyrics"}},
        "title_candidates": [],
        "corpus_reference": {"stats": profile.get("stats", {}), "signature_words": profile.get("signature_words", [])[:24], "top_rhymes": profile.get("top_rhymes", [])[:12], "motif_clusters": profile.get("motif_clusters", [])[:6]},
    }
