"""Scansion physics layer for the NMC rap lab.

This module turns the notebook model into deterministic app data.  It treats a
rap line as a chain of syllable events with symbols:

σ = syllable event, S = stress strength, θ = beat phase inside the bar,
β = bar index/range, γ = rhyme family, τ = torsion/syncopation,
F = accent force, Ω = spin/repeated phonetic motion, ΔC = cadence change.

The output is intentionally inspectable JSON so the frontend can render a
"Scansion Physics" view, static line cards, and one-sentence feedback without
calling any external service.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from difflib import SequenceMatcher
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from beat_engine import attach_beat_guidance
from lyric_engine import (
    MODE_LABELS,
    analyze_lyrics,
    count_syllables,
    get_corpus_profile,
    line_syllables,
    normalize_word,
    rhyme_key,
    tokenize,
    unique_preserve,
)
from meter_engine import analyze_meter_text, analyze_sentence_meter

GRID_16 = ["1", "e", "&", "a", "2", "e", "&", "a", "3", "e", "&", "a", "4", "e", "&", "a"]
STRONG_GRID_INDICES = {0, 4, 8, 12}
HALF_GRID_INDICES = {2, 6, 10, 14}
OFF_GRID_INDICES = {1, 3, 5, 7, 9, 11, 13, 15}

SOFT_WORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "that", "this", "these", "those",
    "to", "of", "for", "from", "in", "on", "at", "by", "as", "with", "within", "into", "onto", "through",
    "is", "am", "are", "was", "were", "be", "been", "being", "do", "does", "did", "can", "could", "should",
    "would", "will", "may", "might", "must", "have", "has", "had", "not", "no", "so", "just", "very", "really",
    "quite", "maybe", "sometimes", "still", "yet", "there", "here", "it", "its", "it's", "i", "me", "my", "you",
    "your", "he", "him", "his", "she", "her", "we", "us", "our", "they", "them", "their",
}

PHYSICAL_ANCHORS = [
    "ink", "tongue", "breath", "page", "jaw", "teeth", "chest", "wire", "spark", "static",
    "mirror", "pressure", "pulse", "circuit", "friction", "signal", "socket", "engine", "canvas", "metal",
]

NOTEBOOK_TEST_PAIRS = [
    ("the operative effort", "tested metric"),
    ("eleven tickets", "metric records"),
    ("twisting lyric", "times detected"),
    ("setting the credit", "separate ethics"),
]

SYMBOL_LEGEND = [
    {"symbol": "σ", "name": "syllable event", "meaning": "One pronounceable unit in the rap line."},
    {"symbol": "S", "name": "stress strength", "meaning": "How hard the syllable wants to be accented."},
    {"symbol": "θ", "name": "beat phase", "meaning": "Where the syllable lands inside the 1-e-&-a / four-beat bar."},
    {"symbol": "β", "name": "bar index", "meaning": "The bar or bar range that carries the line."},
    {"symbol": "γ", "name": "rhyme family", "meaning": "The line's end-rhyme key or dominant repeated sound."},
    {"symbol": "τ", "name": "torsion", "meaning": "How much stressed motion twists off the strong beat grid."},
    {"symbol": "F", "name": "force", "meaning": "Accent impact from stress, content weight, and landing position."},
    {"symbol": "Ω", "name": "spin", "meaning": "Repeated phonetic motion from internal rhyme and alliteration."},
    {"symbol": "ΔC", "name": "cadence delta", "meaning": "Change in syllables/stresses/bar span from the previous line."},
]


def _round(value: Any, digits: int = 2) -> float:
    try:
        value = float(value)
        if math.isfinite(value):
            return round(value, digits)
    except Exception:
        pass
    return 0.0


def _pct(value: Any) -> int:
    try:
        return int(round(max(0.0, min(100.0, float(value)))))
    except Exception:
        return 0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return default


def _mean(values: Sequence[float]) -> float:
    values = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    return _round(sum(values) / max(1, len(values)), 3) if values else 0.0


def _label_delta(delta: int) -> str:
    if delta >= 4:
        return "expansion"
    if delta <= -4:
        return "compression"
    if delta >= 2:
        return "small expansion"
    if delta <= -2:
        return "small compression"
    return "stable pocket"


def _density_label(value: float) -> str:
    if value >= 0.72:
        return "high"
    if value >= 0.48:
        return "medium"
    if value > 0:
        return "low"
    return "none"


def _grid_for_syllable(index: int, total: int) -> Dict[str, Any]:
    total = max(1, int(total or 1))
    index = max(1, int(index or 1))
    # Center each syllable in an equal-width slot across a one-bar grid.
    phase = (index - 0.5) / total
    grid_index = max(0, min(15, int(math.floor(phase * 16))))
    nearest_strong = min(abs(grid_index - strong) for strong in STRONG_GRID_INDICES)
    nearest_strong = min(nearest_strong, 16 - nearest_strong)
    nearest_half = min(abs(grid_index - half) for half in HALF_GRID_INDICES)
    nearest_half = min(nearest_half, 16 - nearest_half)
    if grid_index in STRONG_GRID_INDICES:
        slot_type = "downbeat"
    elif grid_index in HALF_GRID_INDICES:
        slot_type = "backbeat/subdivision"
    else:
        slot_type = "off-grid subdivision"
    return {
        "theta": _round(phase, 3),
        "grid_index": grid_index,
        "grid_label": GRID_16[grid_index],
        "slot_type": slot_type,
        "nearest_strong_distance": int(nearest_strong),
        "nearest_half_distance": int(nearest_half),
    }


def _unit_force(unit: Dict[str, Any], end_word: str, line_key: str) -> float:
    word = normalize_word(unit.get("word", ""))
    stress = int(unit.get("stress", 0) or 0)
    base = 0.16
    if stress >= 2:
        base += 0.64
    elif stress >= 1:
        base += 0.52
    else:
        base += 0.08
    if word and word not in SOFT_WORDS:
        base += 0.16
    if word and word == normalize_word(end_word):
        base += 0.18
    if word and rhyme_key(word) == line_key and len(word) > 2:
        base += 0.08
    return _round(min(1.0, base), 3)


def _unit_torsion(unit: Dict[str, Any], grid: Dict[str, Any]) -> float:
    stress = int(unit.get("stress", 0) or 0)
    if stress <= 0:
        return 0.0
    distance = float(grid.get("nearest_strong_distance", 0))
    # Strong syllables on exact downbeats get low torsion; e/a positions get high torsion.
    return _round(min(1.0, distance / 2.0), 3)


def _row_lookup(rows: Sequence[Dict[str, Any]], number_key: str = "number") -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for row in rows or []:
        n = _safe_int(row.get(number_key), 0)
        if n:
            out[n] = row
    return out


def _beat_lookup(analysis: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for row in ((analysis.get("beat_alignment") or {}).get("per_line") or []):
        n = _safe_int(row.get("line_number"), 0)
        if n:
            out[n] = row
    return out


def _line_spin(detail: Dict[str, Any], line_key_count: int = 1) -> float:
    internal = sum(max(0, _safe_int(g.get("count"), 0) - 1) for g in detail.get("internal_rhymes", []) or [])
    allit = sum(max(0, _safe_int(g.get("count"), 0) - 1) for g in detail.get("alliteration", []) or [])
    repeated_bonus = max(0, line_key_count - 1)
    words = max(1, _safe_int(detail.get("word_count"), 0))
    score = (internal * 0.13) + (allit * 0.08) + min(0.18, repeated_bonus * 0.04)
    score += min(0.16, (internal + allit) / max(1, words) * 0.48)
    return _round(min(1.0, score), 3)


def _force_reading(force: float) -> str:
    if force >= 0.72:
        return "hard accent line; protect the delivery so it does not become blocky."
    if force >= 0.52:
        return "balanced accent force; enough anchors for the listener to track the line."
    if force > 0:
        return "soft force; move a concrete noun, hard verb, or rhyme word into a stronger slot."
    return "no force estimate."


def _torsion_reading(torsion: float) -> str:
    if torsion >= 0.55:
        return "high torsion: stressed syllables twist off the downbeat; rehearse the pocket or simplify the bar."
    if torsion >= 0.28:
        return "moderate torsion: syncopation is present but still controllable."
    return "low torsion: stress lands close to the grid; use this for clean punchlines or hooks."


def _cadence_actions(delta: int, stress_delta: int, torsion: float, force: float, spin: float, beat_plan: Dict[str, Any] | None) -> List[str]:
    actions: List[str] = []
    if delta <= -4:
        actions.append("Compression move: let this shorter line act as release or punch after the previous longer bar.")
    elif delta >= 4:
        actions.append("Expansion move: split at the cleanest clause if breath control feels rushed.")
    else:
        actions.append("Cadence is stable; make the difference with stress placement, rhyme color, or image choice.")
    if stress_delta <= -2:
        actions.append("Stress drops from the previous line; add one harder anchor if the bar loses energy.")
    elif stress_delta >= 2:
        actions.append("Stress increases from the previous line; leave a small pickup/rest before the landing.")
    if torsion >= 0.55:
        actions.append("Mark the intended beat phase before recording; high torsion can sound late if not deliberate.")
    if force < 0.48:
        actions.append("Raise force with a physical anchor word: " + ", ".join(PHYSICAL_ANCHORS[:6]) + ".")
    if spin < 0.25:
        actions.append("Add one internal echo or alliterative pair before the final rhyme.")
    if beat_plan and _safe_int(beat_plan.get("bar_span"), 1) > 1:
        actions.append("Beat-aware structure: split this multi-bar thought; give each half a separate γ rhyme landing.")
    return unique_preserve(actions, 6)


def _cadence_transition(prev: Dict[str, Any] | None, current: Dict[str, Any]) -> Dict[str, Any]:
    if not prev:
        return {
            "available": False,
            "delta_syllables": 0,
            "delta_stresses": 0,
            "delta_bar_span": 0,
            "rhyme_changed": False,
            "label": "opening line",
            "reading": "Opening line establishes the first cadence state.",
        }
    delta_s = _safe_int(current.get("syllables"), 0) - _safe_int(prev.get("syllables"), 0)
    delta_stress = _safe_int(current.get("stress_count"), 0) - _safe_int(prev.get("stress_count"), 0)
    delta_bar = _safe_int(current.get("bar_span"), 1) - _safe_int(prev.get("bar_span"), 1)
    rhyme_changed = bool(current.get("rhyme_key") != prev.get("rhyme_key"))
    label = _label_delta(delta_s)
    reading = f"{label}: {delta_s:+d} syllables, {delta_stress:+d} stresses from line {prev.get('line_number')}."
    if not rhyme_changed:
        reading += " γ rhyme family stays locked, so the cadence motion is easier to hear."
    else:
        reading += " γ rhyme family changes, creating a turn in the scheme."
    if delta_bar:
        reading += f" β bar span changes by {delta_bar:+d}."
    return {
        "available": True,
        "delta_syllables": delta_s,
        "delta_stresses": delta_stress,
        "delta_bar_span": delta_bar,
        "rhyme_changed": rhyme_changed,
        "label": label,
        "reading": reading,
    }


def _consonant_frame(text: str) -> str:
    letters = re.sub(r"[^a-z]", "", text.lower())
    cons = re.sub(r"[aeiouy]", "", letters)
    # Keep the frame readable by compressing repeated consonant runs.
    return re.sub(r"(.)\1+", r"\1", cons)


def _vowel_path(text: str) -> str:
    letters = re.sub(r"[^a-z]", "", text.lower())
    groups = re.findall(r"[aeiouy]+", letters)
    compact = "".join(group[0] for group in groups)
    return re.sub(r"(.)\1+", r"\1", compact)


def _skeleton(text: str, meter: Dict[str, Any] | None = None) -> Dict[str, Any]:
    words = tokenize(text)
    end_word = words[-1] if words else ""
    stress = ""
    if meter and meter.get("available"):
        stress = (meter.get("pattern") or {}).get("stress_string") or ""
    else:
        stress = (analyze_sentence_meter(text).get("pattern") or {}).get("stress_string") or ""
    return {
        "text": text,
        "word_count": len(words),
        "syllables": line_syllables(text),
        "consonant_frame": _consonant_frame(text),
        "vowel_path": _vowel_path(text),
        "stress_pattern": stress,
        "end_word": end_word,
        "rhyme_key": rhyme_key(end_word) if end_word else "",
    }


def _similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _skeleton_match(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    consonants = _similarity(a.get("consonant_frame", ""), b.get("consonant_frame", ""))
    vowels = _similarity(a.get("vowel_path", ""), b.get("vowel_path", ""))
    stress = _similarity(a.get("stress_pattern", ""), b.get("stress_pattern", ""))
    end = 1.0 if a.get("rhyme_key") and a.get("rhyme_key") == b.get("rhyme_key") else 0.0
    syllable_fit = 1.0 - min(1.0, abs(_safe_int(a.get("syllables"), 0) - _safe_int(b.get("syllables"), 0)) / max(1, max(_safe_int(a.get("syllables"), 1), _safe_int(b.get("syllables"), 1))))
    score = consonants * 0.34 + vowels * 0.20 + stress * 0.22 + end * 0.14 + syllable_fit * 0.10
    if score >= 0.72:
        label = "strong skeleton echo"
    elif score >= 0.55:
        label = "usable skeleton echo"
    elif end:
        label = "end-rhyme echo only"
    else:
        label = "weak skeleton relation"
    return {
        "score": _pct(score * 100),
        "label": label,
        "consonant_similarity_pct": _pct(consonants * 100),
        "vowel_similarity_pct": _pct(vowels * 100),
        "stress_similarity_pct": _pct(stress * 100),
        "same_rhyme_family": bool(end),
        "syllable_fit_pct": _pct(syllable_fit * 100),
        "reading": (
            f"{label}: consonants {int(round(consonants * 100))}%, vowels {int(round(vowels * 100))}%, "
            f"stress {int(round(stress * 100))}%, rhyme {'same' if end else 'different'}."
        ),
    }


def _notebook_pair_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for left, right in NOTEBOOK_TEST_PAIRS:
        a = _skeleton(left)
        b = _skeleton(right)
        match = _skeleton_match(a, b)
        rows.append({"left": a, "right": b, "match": match})
    return rows


def _skeleton_pairs(line_rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    skeletons = [row.get("skeleton", {}) for row in line_rows if row.get("skeleton")]
    pairs: List[Dict[str, Any]] = []
    for i in range(len(skeletons)):
        for j in range(i + 1, min(len(skeletons), i + 7)):
            a = skeletons[i]
            b = skeletons[j]
            match = _skeleton_match(a, b)
            if match["score"] >= 42 or match["same_rhyme_family"]:
                pairs.append({
                    "line_a": line_rows[i].get("line_number"),
                    "line_b": line_rows[j].get("line_number"),
                    "text_a": a.get("text", ""),
                    "text_b": b.get("text", ""),
                    "match": match,
                    "a": a,
                    "b": b,
                })
    pairs.sort(key=lambda row: (-_safe_int(row.get("match", {}).get("score"), 0), _safe_int(row.get("line_a"), 0), _safe_int(row.get("line_b"), 0)))
    adjacent = [row for row in pairs if _safe_int(row.get("line_b"), 0) == _safe_int(row.get("line_a"), 0) + 1]
    return {
        "available": bool(skeletons),
        "top_pairs": pairs[:18],
        "adjacent_pairs": adjacent[:12],
        "notebook_test_pairs": _notebook_pair_rows(),
        "interpretation": "Skeleton matching compares consonant frame, vowel path, stress pattern, syllable length, and γ rhyme family.",
    }


def _compression_sequences(line_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sequences: List[Dict[str, Any]] = []
    for window in (3, 4):
        for i in range(0, max(0, len(line_rows) - window + 1)):
            rows = list(line_rows[i:i + window])
            sylls = [_safe_int(row.get("syllables"), 0) for row in rows]
            forces = [float(row.get("force", 0)) for row in rows]
            spins = [float(row.get("spin", 0)) for row in rows]
            if not all(sylls):
                continue
            nonincreasing = all(a >= b for a, b in zip(sylls, sylls[1:]))
            total_drop = sylls[0] - sylls[-1]
            sound_gain = (forces[-1] + spins[-1]) - (forces[0] + spins[0])
            if nonincreasing and total_drop >= 3:
                sequences.append({
                    "line_numbers": [row.get("line_number") for row in rows],
                    "syllable_shape": sylls,
                    "force_shape": [_round(value, 2) for value in forces],
                    "spin_shape": [_round(value, 2) for value in spins],
                    "total_drop": total_drop,
                    "sound_gain": _round(sound_gain, 2),
                    "label": "compression sequence" if sound_gain >= -0.05 else "length compression",
                    "reading": (
                        f"Lines {rows[0].get('line_number')}–{rows[-1].get('line_number')} compress "
                        f"from {sylls[0]} to {sylls[-1]} syllables. Use the last line as release/punch."
                    ),
                })
    # Remove duplicate windows with identical line numbers.
    seen = set()
    unique: List[Dict[str, Any]] = []
    for seq in sorted(sequences, key=lambda row: (-_safe_int(row.get("total_drop"), 0), row.get("line_numbers", [999])[0])):
        key = tuple(seq.get("line_numbers") or [])
        if key in seen:
            continue
        seen.add(key)
        unique.append(seq)
    return unique[:12]


def _beat_grid_summary(beat: Dict[str, Any] | None) -> Dict[str, Any]:
    if not beat or not beat.get("available"):
        return {
            "available": False,
            "basis": "implied_one_bar_grid",
            "grid": "1 e & a 2 e & a 3 e & a 4 e & a",
            "reading": "No beat uploaded: θ phase is estimated by spreading each line evenly across one implied bar.",
        }
    return {
        "available": True,
        "basis": "uploaded_beat_grid",
        "grid": "1 e & a 2 e & a 3 e & a 4 e & a",
        "detected_bpm": beat.get("detected_bpm"),
        "rap_grid_bpm": beat.get("rap_grid_bpm"),
        "bar_duration_seconds": beat.get("bar_duration_seconds"),
        "beat_interval_seconds": beat.get("beat_interval_seconds"),
        "reading": "θ phase uses the uploaded beat's detected rap grid when bar windows are available.",
    }


def _line_physics(
    detail: Dict[str, Any],
    meter: Dict[str, Any],
    beat_plan: Dict[str, Any] | None,
    rhyme_counts: Counter[str],
) -> Dict[str, Any]:
    text = str(detail.get("text") or "")
    line_no = _safe_int(detail.get("number"), 0)
    line_key = str(detail.get("rhyme_key") or "")
    end_word = str(detail.get("end_word") or "")
    units = (meter.get("syllables") or []) if meter and meter.get("available") else []
    if not units:
        # Minimal fallback: one unit per word/syllable estimate.
        for word_index, word in enumerate(tokenize(text), start=1):
            n = max(1, count_syllables(word))
            for local in range(1, n + 1):
                units.append({
                    "index": len(units) + 1,
                    "word": word,
                    "normalized_word": normalize_word(word),
                    "word_index": word_index,
                    "syllable_in_word": local,
                    "syllable_label": word if local == 1 else "",
                    "stress": 0 if normalize_word(word) in SOFT_WORDS else 1,
                    "stressed": normalize_word(word) not in SOFT_WORDS,
                    "glyph": "○" if normalize_word(word) in SOFT_WORDS else "●",
                    "mark": "˘" if normalize_word(word) in SOFT_WORDS else "´",
                })
    total = len(units)
    phase_units: List[Dict[str, Any]] = []
    forces: List[float] = []
    torsions: List[float] = []
    stressed_torsions: List[float] = []
    beta = beat_plan.get("assigned_bars") if beat_plan else str(line_no)
    bar_span = _safe_int(beat_plan.get("bar_span"), 1) if beat_plan else 1
    for unit in units:
        idx = _safe_int(unit.get("index"), len(phase_units) + 1)
        grid = _grid_for_syllable(idx, total)
        force = _unit_force(unit, end_word, line_key)
        torsion = _unit_torsion(unit, grid)
        forces.append(force)
        torsions.append(torsion)
        if int(unit.get("stress", 0) or 0) > 0:
            stressed_torsions.append(torsion)
        phase_units.append({
            "sigma": idx,
            "word": unit.get("word", ""),
            "normalized_word": unit.get("normalized_word") or normalize_word(unit.get("word", "")),
            "syllable_label": unit.get("syllable_label", ""),
            "word_index": unit.get("word_index"),
            "syllable_in_word": unit.get("syllable_in_word"),
            "S": int(unit.get("stress", 0) or 0),
            "stress_mark": unit.get("mark") or ("´" if unit.get("stressed") else "˘"),
            "glyph": unit.get("glyph") or ("●" if unit.get("stressed") else "○"),
            "stressed": bool(unit.get("stressed")),
            "theta": grid["theta"],
            "theta_grid": grid["grid_label"],
            "theta_slot": grid["slot_type"],
            "beta": beta,
            "gamma": line_key,
            "F": force,
            "tau": torsion,
            "role": "rhyme landing" if normalize_word(unit.get("word", "")) == normalize_word(end_word) else "stress anchor" if unit.get("stressed") else "pickup/weak motion",
        })
    syllables = total or _safe_int(detail.get("syllables"), 0)
    stress_count = sum(1 for u in phase_units if u.get("stressed"))
    spin = _line_spin(detail, int(rhyme_counts.get(line_key, 1)))
    force = _mean(forces)
    torsion = _mean(stressed_torsions or torsions)
    meter_summary = meter.get("summary") or {}
    grid_string = " ".join(str(u["theta_grid"]) for u in phase_units)
    glyph_string = " ".join(str(u["glyph"]) for u in phase_units)
    stress_words = unique_preserve([u.get("word") for u in phase_units if u.get("stressed")], 8)
    skeleton = _skeleton(text, meter)
    return {
        "available": True,
        "line_number": line_no,
        "text": text,
        "symbols": {"sigma": syllables, "S": stress_count, "theta": "one-bar phase grid", "beta": beta, "gamma": line_key, "tau": torsion, "F": force, "Omega": spin},
        "syllables": syllables,
        "stress_count": stress_count,
        "stress_density_pct": _pct((stress_count / max(1, syllables)) * 100),
        "dominant_meter": meter_summary.get("dominant_meter", "mixed") if meter else "mixed",
        "rhyme_key": line_key,
        "end_word": end_word,
        "bar_span": bar_span,
        "assigned_bars": beta,
        "time_window": beat_plan.get("time_window") if beat_plan else "implied one-bar window",
        "force": force,
        "force_pct": _pct(force * 100),
        "force_label": _density_label(force),
        "torsion": torsion,
        "torsion_pct": _pct(torsion * 100),
        "torsion_label": _density_label(torsion),
        "spin": spin,
        "spin_pct": _pct(spin * 100),
        "spin_label": _density_label(spin),
        "phase_grid": {
            "labels": GRID_16,
            "unit_grid": grid_string,
            "stress_glyphs": glyph_string,
            "reading": "Read each syllable against the 1-e-&-a grid; stressed syllables on e/a slots create τ torsion.",
        },
        "phase_units": phase_units,
        "stress_anchors": stress_words,
        "skeleton": skeleton,
        "physics_reading": f"F {force:.2f} / τ {torsion:.2f} / Ω {spin:.2f}: {_force_reading(force)} {_torsion_reading(torsion)}",
        "actions": [],  # filled after cadence delta is known
    }


def _summary_from_rows(rows: Sequence[Dict[str, Any]], compression: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"available": False}
    forces = [float(row.get("force", 0)) for row in rows]
    torsions = [float(row.get("torsion", 0)) for row in rows]
    spins = [float(row.get("spin", 0)) for row in rows]
    deltas = [abs(_safe_int((row.get("cadence_delta") or {}).get("delta_syllables"), 0)) for row in rows if (row.get("cadence_delta") or {}).get("available")]
    high_torsion = [row for row in rows if float(row.get("torsion", 0)) >= 0.55]
    low_force = [row for row in rows if float(row.get("force", 0)) < 0.48]
    high_spin = [row for row in rows if float(row.get("spin", 0)) >= 0.45]
    stress_final = [row for row in rows if str(row.get("end_word", "")).lower() in {str(w).lower() for w in row.get("stress_anchors", [])}]
    return {
        "available": True,
        "line_count": len(rows),
        "avg_force": _round(mean(forces), 3) if forces else 0,
        "avg_force_pct": _pct((mean(forces) if forces else 0) * 100),
        "avg_torsion": _round(mean(torsions), 3) if torsions else 0,
        "avg_torsion_pct": _pct((mean(torsions) if torsions else 0) * 100),
        "avg_spin": _round(mean(spins), 3) if spins else 0,
        "avg_spin_pct": _pct((mean(spins) if spins else 0) * 100),
        "cadence_shift_count": sum(1 for d in deltas if d >= 3),
        "avg_cadence_delta_abs": _round(mean(deltas), 2) if deltas else 0,
        "cadence_delta_stddev": _round(pstdev(deltas), 2) if len(deltas) > 1 else 0,
        "compression_sequence_count": len(compression),
        "high_torsion_lines": [row.get("line_number") for row in high_torsion[:10]],
        "low_force_lines": [row.get("line_number") for row in low_force[:10]],
        "high_spin_lines": [row.get("line_number") for row in high_spin[:10]],
        "strong_landing_lines": [row.get("line_number") for row in stress_final[:10]],
        "reading": _physics_summary_reading(rows, high_torsion, low_force, high_spin, compression),
    }


def _physics_summary_reading(rows: Sequence[Dict[str, Any]], high_torsion: Sequence[Dict[str, Any]], low_force: Sequence[Dict[str, Any]], high_spin: Sequence[Dict[str, Any]], compression: Sequence[Dict[str, Any]]) -> str:
    parts: List[str] = []
    avg_force = _mean([float(row.get("force", 0)) for row in rows])
    avg_torsion = _mean([float(row.get("torsion", 0)) for row in rows])
    avg_spin = _mean([float(row.get("spin", 0)) for row in rows])
    parts.append(f"Average force F={avg_force:.2f}, torsion τ={avg_torsion:.2f}, spin Ω={avg_spin:.2f}.")
    if compression:
        parts.append(f"Detected {len(compression)} compression sequence(s); use the last line of each sequence as a punch/release.")
    if high_torsion:
        parts.append("High τ lines need rehearsed pocket marks: " + ", ".join(str(row.get("line_number")) for row in high_torsion[:6]) + ".")
    if low_force:
        parts.append("Low F lines need a harder noun/verb/physical anchor: " + ", ".join(str(row.get("line_number")) for row in low_force[:6]) + ".")
    if high_spin:
        parts.append("High Ω lines carry the most phonetic motion: " + ", ".join(str(row.get("line_number")) for row in high_spin[:6]) + ".")
    if len(parts) == 1:
        parts.append("No extreme physics warnings; polish by choosing where to intentionally expand, compress, and twist off-grid.")
    return " ".join(parts)


def _priority_actions(summary: Dict[str, Any], compression: Sequence[Dict[str, Any]]) -> List[str]:
    actions: List[str] = []
    if summary.get("low_force_lines"):
        actions.append("Force pass: add physical anchors or stronger verbs to lines " + ", ".join(map(str, summary["low_force_lines"][:6])) + ".")
    if summary.get("high_torsion_lines"):
        actions.append("Torsion pass: mark θ phase for lines " + ", ".join(map(str, summary["high_torsion_lines"][:6])) + " before recording.")
    if compression:
        actions.append("Compression pass: preserve these long→short shapes: " + "; ".join("-".join(map(str, seq.get("line_numbers", []))) for seq in compression[:4]) + ".")
    if summary.get("high_spin_lines"):
        actions.append("Spin pass: use high-Ω lines " + ", ".join(map(str, summary["high_spin_lines"][:6])) + " as rhyme motors for nearby bars.")
    if not actions:
        actions.append("Physics pass: choose one line to expand, one line to compress, and one line to twist off-grid for contrast.")
    return unique_preserve(actions, 8)


def build_scansion_physics_report(
    lyrics: str,
    mode: str = "match",
    beat: Dict[str, Any] | None = None,
    analysis: Dict[str, Any] | None = None,
    meter_report: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a whole-draft scansion physics report."""
    mode = mode if mode in MODE_LABELS else "match"
    if analysis is None:
        analysis = analyze_lyrics(lyrics, mode)
        if beat:
            analysis = attach_beat_guidance(analysis, beat)
    if meter_report is None:
        meter_report = analyze_meter_text(lyrics, beat=beat)

    details = [row for row in analysis.get("raw_line_details", []) or [] if row.get("text")]
    if not details:
        return {"available": False, "error": "No editable lyric lines found for scansion physics."}

    meter_by_line = {int(row.get("line_number", 0)): row.get("meter", {}) for row in (meter_report.get("line_details", []) if meter_report else [])}
    beat_by_line = _beat_lookup(analysis)
    rhyme_counts = Counter(str(row.get("rhyme_key") or "") for row in details if row.get("rhyme_key"))

    line_rows: List[Dict[str, Any]] = []
    previous: Dict[str, Any] | None = None
    for detail in details:
        line_no = _safe_int(detail.get("number"), 0)
        line_row = _line_physics(detail, meter_by_line.get(line_no, {}), beat_by_line.get(line_no), rhyme_counts)
        delta = _cadence_transition(previous, line_row)
        line_row["cadence_delta"] = delta
        line_row["actions"] = _cadence_actions(
            _safe_int(delta.get("delta_syllables"), 0),
            _safe_int(delta.get("delta_stresses"), 0),
            float(line_row.get("torsion", 0)),
            float(line_row.get("force", 0)),
            float(line_row.get("spin", 0)),
            beat_by_line.get(line_no),
        )
        line_rows.append(line_row)
        previous = line_row

    compression = _compression_sequences(line_rows)
    skeletons = _skeleton_pairs(line_rows)
    summary = _summary_from_rows(line_rows, compression)
    return {
        "available": True,
        "report_type": "scansion_physics",
        "model_name": "Notebook Cadence Δ / Force-Torsion-Spin Model",
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "notebook_reference": {
            "image_url": "/static/reference/scansion_notebook.jpg",
            "interpretation": "The uploaded notebook page is encoded as word → syllable/stress → θ phase → F/τ/Ω physics → rhythm/flow → sentence/flow advice.",
            "pipeline": ["word", "syllables", "stress", "theta phase", "force/torsion/spin", "cadence delta", "bar structure", "flow suggestion"],
            "physical_anchor_bank": PHYSICAL_ANCHORS,
        },
        "symbol_legend": SYMBOL_LEGEND,
        "beat_grid": _beat_grid_summary(beat or analysis.get("beat_analysis")),
        "summary": summary,
        "priority_actions": _priority_actions(summary, compression),
        "line_physics": line_rows,
        "compression_sequences": compression,
        "phonetic_skeletons": skeletons,
        "formula": {
            "force": "F = stress weight + content weight + rhyme landing bonus",
            "torsion": "τ = stressed-syllable distance from the nearest strong beat on the 1-e-&-a grid",
            "spin": "Ω = internal-rhyme loops + alliterative loops + repeated γ-family pressure",
            "cadence_delta": "ΔC = current syllables/stresses/bar span minus previous line",
        },
    }


def build_sentence_physics_report(
    sentence: str,
    beat: Dict[str, Any] | None = None,
    mode: str = "match",
) -> Dict[str, Any]:
    """Build a one-sentence version for the synchronous Sentence Lab."""
    text = str(sentence or "").strip()
    if not text or not tokenize(text):
        return {"available": False, "error": "No sentence text for physics analysis."}
    report = build_scansion_physics_report(text, mode=mode, beat=beat, analysis=None, meter_report=None)
    if not report.get("available"):
        return report
    line = (report.get("line_physics") or [{}])[0]
    summary = report.get("summary") or {}
    return {
        "available": True,
        "report_type": "sentence_scansion_physics",
        "sentence": text,
        "line": line,
        "summary": summary,
        "symbol_legend": SYMBOL_LEGEND,
        "notebook_reference": report.get("notebook_reference", {}),
        "beat_grid": report.get("beat_grid", {}),
        "phonetic_skeleton": line.get("skeleton", {}),
        "notebook_test_pairs": (report.get("phonetic_skeletons") or {}).get("notebook_test_pairs", []),
        "actions": line.get("actions", []),
        "reading": line.get("physics_reading", ""),
    }
