"""System-wide rap scoring and edit-comparison engine.

The score engine is intentionally deterministic and offline. It combines the
existing lyric, beat, rhyme, meter, comparison, and Scansion Physics reports into
one stable scorecard for the whole rap, every section, and every bar/line. It is
not a judgment of artistic worth; it is a revision instrument that explains why
an edit improved or weakened the draft.
"""
from __future__ import annotations

import difflib
import math
from collections import Counter
from statistics import mean
from typing import Any, Dict, Iterable, List, Sequence

from beat_engine import attach_beat_guidance
from comparison_engine import build_comparison_report
from lyric_engine import (
    MODE_LABELS,
    WEAK_END_WORDS,
    analyze_lyrics,
    content_words,
    get_corpus_profile,
    normalize_word,
    rhyme_key,
    tokenize,
    unique_preserve,
)
from meter_engine import analyze_meter_text
from physics_engine import build_scansion_physics_report
from rhyme_engine import build_rhyme_suggestion_lab


SCORE_WEIGHTS = {
    "style_match": 0.13,
    "rhyme_power": 0.16,
    "cadence_fit": 0.15,
    "bar_structure": 0.14,
    "meter_stress": 0.12,
    "scansion_physics": 0.12,
    "content_clarity": 0.10,
    "reference_fit": 0.08,
}

BAR_COMPONENT_WEIGHTS = {
    "cadence_fit": 0.20,
    "rhyme_power": 0.22,
    "bar_fit": 0.16,
    "meter_stress": 0.14,
    "scansion_physics": 0.14,
    "content_clarity": 0.14,
}

GRADE_BANDS = [
    (92, "A+", "release-ready pocket"),
    (86, "A", "excellent draft"),
    (80, "A-", "strong draft"),
    (74, "B+", "solid with fixable friction"),
    (68, "B", "workable structure"),
    (60, "C+", "promising but uneven"),
    (50, "C", "needs focused revision"),
    (0, "D", "rebuild key bars"),
]


def _round(value: Any, digits: int = 2) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return round(number, digits)
    except Exception:
        pass
    return 0.0


def _pct(value: Any) -> int:
    try:
        number = float(value)
        if not math.isfinite(number):
            return 0
        return int(round(max(0.0, min(100.0, number))))
    except Exception:
        return 0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _avg(values: Iterable[Any]) -> float:
    nums = []
    for value in values:
        try:
            number = float(value)
        except Exception:
            continue
        if math.isfinite(number):
            nums.append(number)
    return _round(mean(nums), 2) if nums else 0.0


def _grade(score: Any) -> Dict[str, Any]:
    score_i = _pct(score)
    for threshold, letter, label in GRADE_BANDS:
        if score_i >= threshold:
            return {"score": score_i, "letter": letter, "label": label}
    return {"score": score_i, "letter": "D", "label": "rebuild key bars"}


def _component_row(name: str, score: Any, weight: float, description: str) -> Dict[str, Any]:
    return {
        "key": name,
        "label": name.replace("_", " ").title(),
        "score": _pct(score),
        "weight": _round(weight, 3),
        "contribution": _round(_pct(score) * weight, 2),
        "description": description,
    }


def _weighted_average(component_scores: Dict[str, Any], weights: Dict[str, float]) -> int:
    total_weight = 0.0
    total = 0.0
    for key, weight in weights.items():
        if key not in component_scores:
            continue
        total += _pct(component_scores[key]) * float(weight)
        total_weight += float(weight)
    if total_weight <= 0:
        return 0
    return _pct(total / total_weight)


def _score_target_range(value: Any, target: Sequence[int] | int | float | None) -> int:
    value_i = _safe_int(value, 0)
    if value_i <= 0:
        return 0
    if isinstance(target, (list, tuple)) and len(target) >= 2:
        low, high = _safe_int(target[0], 0), _safe_int(target[-1], 0)
        if low <= 0 or high <= 0:
            return 65
        if low <= value_i <= high:
            # Slightly reward center of pocket.
            mid = (low + high) / 2.0
            width = max(1.0, (high - low) / 2.0)
            return _pct(98 - min(8.0, abs(value_i - mid) / width * 6.0))
        if value_i < low:
            return _pct(92 - (low - value_i) * 9)
        return _pct(92 - (value_i - high) * 8)
    target_num = float(target or 12)
    if target_num <= 0:
        target_num = 12.0
    delta = abs(value_i - target_num)
    return _pct(100 - (delta / max(1.0, target_num)) * 110)


def _bar_structure_score(detail: Dict[str, Any], beat_plan: Dict[str, Any] | None, target: Sequence[int] | int | float | None) -> int:
    syllables = _safe_int(detail.get("syllables"), 0)
    if beat_plan:
        span = max(1, _safe_int(beat_plan.get("bar_span"), 1))
        target_range = beat_plan.get("target_syllables_per_bar") or target
        if isinstance(target_range, (list, tuple)) and len(target_range) >= 2:
            high = max(1, _safe_int(target_range[-1], 12))
            per_bar = syllables / max(1, span)
            base = _score_target_range(round(per_bar), target_range)
        else:
            base = _score_target_range(syllables, target)
        density_label = str(beat_plan.get("density_label") or "balanced").lower()
        if density_label == "very dense":
            base -= 18
        elif density_label == "dense":
            base -= 7
        elif density_label == "open":
            base -= 5
        if span > 2:
            base -= min(18, (span - 2) * 7)
        energy = beat_plan.get("energy_context") or {}
        if str(energy.get("label", "")).lower() == "high" and syllables <= (target_range[-1] if isinstance(target_range, (list, tuple)) else 14):
            base += 4
        return _pct(base)
    return _score_target_range(syllables, target)


def _meter_score(meter: Dict[str, Any]) -> int:
    if not meter or not meter.get("available"):
        return 58
    summary = meter.get("summary") or {}
    stress_ratio = float(summary.get("stress_ratio_pct") or 0)
    # Rap stress usually wants enough anchors without making every syllable heavy.
    ratio_score = _pct(100 - abs(stress_ratio - 43.0) * 2.2)
    confidence = _pct(summary.get("meter_confidence_pct") or 0)
    final_bonus = 12 if summary.get("final_landing_stressed") else -10
    weak_penalty = max(0, _safe_int(summary.get("longest_weak_run"), 0) - 4) * 6
    cluster_penalty = max(0, _safe_int(summary.get("longest_stress_cluster"), 0) - 3) * 4
    return _pct(ratio_score * 0.58 + confidence * 0.22 + 70 * 0.20 + final_bonus - weak_penalty - cluster_penalty)


def _physics_score(physics: Dict[str, Any]) -> int:
    if not physics or not physics.get("available"):
        return 58
    force = _pct(physics.get("force_pct", 0))
    spin = _pct(physics.get("spin_pct", 0))
    torsion = _pct(physics.get("torsion_pct", 0))
    # Torsion is useful when controlled; very low can be plain, very high can be late/rushed.
    torsion_control = _pct(100 - abs(torsion - 38) * 1.55)
    return _pct(force * 0.38 + spin * 0.34 + torsion_control * 0.28)


def _clarity_score(detail: Dict[str, Any], card: Dict[str, Any] | None = None) -> int:
    words = detail.get("words") or []
    content = detail.get("content_words") or []
    images = detail.get("image_words") or []
    abstract = detail.get("abstract_words") or []
    motifs = detail.get("motif_hits") or {}
    filler = detail.get("filler_words") or []
    score = 67
    score += min(13, len(images) * 7)
    score += min(9, len(motifs) * 4)
    score += min(6, len(content) * 0.6)
    if abstract and not images:
        score -= min(18, len(abstract) * 6)
    score -= min(13, len(filler) * 5)
    if len(words) > 17:
        score -= min(12, (len(words) - 17) * 2)
    if card:
        issue_types = {str(issue.get("type", "")).lower() for issue in card.get("issues", [])}
        if "imagery" in issue_types:
            score -= 8
        if "fine tune" in issue_types and len(issue_types) == 1:
            score += 4
    return _pct(score)


def _issue_load_score(card: Dict[str, Any] | None) -> int:
    if not card:
        return 62
    issues = card.get("issues") or []
    score = 100 - len(issues) * 12
    for issue in issues:
        kind = str(issue.get("type", "")).lower()
        if kind in {"cadence", "end word", "repetition"}:
            score -= 6
    return _pct(score)


def _section_lookup(analysis: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    lookup: Dict[int, Dict[str, Any]] = {}
    for section in analysis.get("sections", []) or []:
        rows = section.get("lines", []) or []
        total = max(1, len(rows))
        for pos, row in enumerate(rows, start=1):
            n = _safe_int(row.get("number"), 0)
            if not n:
                continue
            lookup[n] = {
                "label": section.get("label") or "Section",
                "type": section.get("type") or "section",
                "position": pos,
                "line_count": total,
                "start_line": section.get("start_line"),
                "end_line": section.get("end_line"),
            }
    return lookup


def _diagnose_bar(scores: Dict[str, int], detail: Dict[str, Any], beat_plan: Dict[str, Any] | None, rhyme_report: Dict[str, Any] | None, meter: Dict[str, Any], physics: Dict[str, Any]) -> Dict[str, Any]:
    weakest = sorted(scores.items(), key=lambda item: item[1])[:3]
    issues: List[str] = []
    advice: List[str] = []
    syllables = _safe_int(detail.get("syllables"), 0)
    end = str(detail.get("end_word") or "")
    if scores.get("bar_fit", 100) < 62:
        if beat_plan:
            density = str(beat_plan.get("density_label") or "").lower()
            if density in {"dense", "very dense"}:
                issues.append("bar is overcrowded against the uploaded beat")
                advice.append("Cut connector words or split the sentence into separate β bar landings.")
            else:
                issues.append("bar length is outside the target pocket")
                advice.append("Add a pickup phrase or leave the open space as deliberate breath.")
        else:
            issues.append("bar length is far from the corpus pocket")
            advice.append("Rebalance syllables before changing the idea.")
    if scores.get("rhyme_power", 100) < 58:
        issues.append("rhyme landing is light")
        if rhyme_report and (rhyme_report.get("word_lists") or {}).get("end_rhymes"):
            advice.append("Try a stronger landing: " + ", ".join((rhyme_report.get("word_lists") or {}).get("end_rhymes", [])[:5]) + ".")
        else:
            advice.append("Move a heavier noun or concept to the final word slot.")
    if end in WEAK_END_WORDS:
        issues.append("weak final word")
        advice.append("Do not let a pronoun, connector, or filler carry the γ rhyme landing.")
    if scores.get("meter_stress", 100) < 58:
        summary = meter.get("summary") or {}
        if not summary.get("final_landing_stressed"):
            advice.append("Make the final landing stressed or give it a rest before the next bar.")
        if _safe_int(summary.get("longest_weak_run"), 0) >= 5:
            advice.append("Break the long weak pickup run with one hard content word.")
        issues.append("stress pattern needs clearer anchors")
    if scores.get("content_clarity", 100) < 58:
        issues.append("abstract content needs a visual anchor")
        advice.append("Add one physical object/action such as ink, tongue, breath, page, teeth, wire, spark, or pressure.")
    if scores.get("scansion_physics", 100) < 58:
        if _pct(physics.get("torsion_pct", 0)) >= 65:
            advice.append("High τ torsion: mark the θ phase or simplify the phrase before recording.")
        elif _pct(physics.get("force_pct", 0)) < 45:
            advice.append("Low F force: add a stronger verb or a stressed physical anchor.")
        else:
            advice.append("Raise Ω spin with a mid-bar echo or alliterative pair.")
        issues.append("Scansion Physics balance is weak")
    if not issues:
        issues.append("bar is structurally healthy")
        advice.append("Protect this bar; polish only the image, internal echo, or delivery emphasis.")
    return {
        "weakest_components": [{"key": k, "score": v} for k, v in weakest],
        "issues": unique_preserve(issues, 5),
        "advice": unique_preserve(advice, 6),
        "performance_note": _performance_note(syllables, beat_plan, meter, physics),
    }


def _performance_note(syllables: int, beat_plan: Dict[str, Any] | None, meter: Dict[str, Any], physics: Dict[str, Any]) -> str:
    if beat_plan:
        span = max(1, _safe_int(beat_plan.get("bar_span"), 1))
        if span > 1:
            return f"Perform as a {span}-bar thought; give each half its own breath and rhyme landing."
        density = str(beat_plan.get("density_label") or "").lower()
        if density == "very dense":
            return "Rap it double-time only if the stressed words remain intelligible."
        if density == "open":
            return "Use the open space as attitude, not dead air; place ad-lib or breath intentionally."
    if meter and meter.get("summary", {}).get("final_landing_stressed"):
        return "The final stress can carry the punch; leave room after it."
    if physics and _pct(physics.get("spin_pct", 0)) >= 70:
        return "High Ω spin bar; use it as a motor and keep articulation crisp."
    if syllables >= 16:
        return "Long bar; rehearse breath and split if the idea blurs."
    return "One-bar pocket is plausible; focus on landing the final word clearly."


def _build_bar_scores(
    analysis: Dict[str, Any],
    rhyme_lab: Dict[str, Any],
    meter_report: Dict[str, Any],
    physics_report: Dict[str, Any],
) -> List[Dict[str, Any]]:
    details = [d for d in analysis.get("raw_line_details", []) or [] if d.get("text")]
    cards = {int(card.get("number", -1)): card for card in analysis.get("line_suggestions", []) or []}
    beat_rows = {int(row.get("line_number", -1)): row for row in (analysis.get("beat_alignment", {}).get("per_line", []) or [])}
    rhyme_rows = {int(row.get("line_number", -1)): row for row in (rhyme_lab.get("line_reports", []) or [])}
    meter_rows = {int(row.get("line_number", -1)): row.get("meter", {}) for row in (meter_report.get("line_details", []) or [])}
    physics_rows = {int(row.get("line_number", -1)): row for row in (physics_report.get("line_physics", []) or [])}
    sections = _section_lookup(analysis)
    profile = get_corpus_profile()
    target_default = profile.get("stats", {}).get("median_syllables") or analysis.get("stats", {}).get("median_syllables") or 12

    bars: List[Dict[str, Any]] = []
    implied_bar = 1
    for index, detail in enumerate(details, start=1):
        line_no = _safe_int(detail.get("number"), index)
        beat_plan = beat_rows.get(line_no)
        card = cards.get(line_no, {})
        rhyme_report = rhyme_rows.get(line_no, {})
        meter = meter_rows.get(line_no, {})
        physics = physics_rows.get(line_no, {})
        target = beat_plan.get("target_syllables_per_bar") if beat_plan else target_default
        span = max(1, _safe_int(beat_plan.get("bar_span"), 1)) if beat_plan else 1
        bar_start = _safe_int(beat_plan.get("bar_start"), implied_bar) if beat_plan else implied_bar
        assigned = beat_plan.get("assigned_bars") if beat_plan else str(implied_bar)
        rhyme_power = _pct((rhyme_report.get("rhyme_power") or {}).get("score", 0)) if rhyme_report else 58
        component_scores = {
            "cadence_fit": _score_target_range(detail.get("syllables"), target),
            "rhyme_power": rhyme_power,
            "bar_fit": _bar_structure_score(detail, beat_plan, target),
            "meter_stress": _meter_score(meter),
            "scansion_physics": _physics_score(physics),
            "content_clarity": _clarity_score(detail, card),
        }
        issue_load = _issue_load_score(card)
        overall = _weighted_average(component_scores, BAR_COMPONENT_WEIGHTS)
        # The issue load is a small braking term; it prevents a bar with many known fixes from looking done.
        overall = _pct(overall * 0.90 + issue_load * 0.10)
        diagnosis = _diagnose_bar(component_scores, detail, beat_plan, rhyme_report, meter, physics)
        bars.append({
            "bar_index": bar_start,
            "bar_span": span,
            "assigned_bars": assigned,
            "line_number": line_no,
            "text": detail.get("text", ""),
            "section": sections.get(line_no, {"label": "Section", "type": "section", "position": index, "line_count": len(details)}),
            "overall": overall,
            "grade": _grade(overall),
            "component_scores": component_scores,
            "component_rows": [
                _component_row("cadence_fit", component_scores["cadence_fit"], BAR_COMPONENT_WEIGHTS["cadence_fit"], "syllable length against beat/corpus pocket"),
                _component_row("rhyme_power", component_scores["rhyme_power"], BAR_COMPONENT_WEIGHTS["rhyme_power"], "end rhyme, internal echoes, alliteration, and landing strength"),
                _component_row("bar_fit", component_scores["bar_fit"], BAR_COMPONENT_WEIGHTS["bar_fit"], "one-bar or multi-bar structural fit"),
                _component_row("meter_stress", component_scores["meter_stress"], BAR_COMPONENT_WEIGHTS["meter_stress"], "stress density, final landing, weak runs, and clusters"),
                _component_row("scansion_physics", component_scores["scansion_physics"], BAR_COMPONENT_WEIGHTS["scansion_physics"], "F force, τ torsion, and Ω spin balance"),
                _component_row("content_clarity", component_scores["content_clarity"], BAR_COMPONENT_WEIGHTS["content_clarity"], "imagery, abstraction control, filler, and motif clarity"),
            ],
            "metrics": {
                "words": detail.get("word_count", 0),
                "syllables": detail.get("syllables", 0),
                "end_word": detail.get("end_word", ""),
                "rhyme_key": detail.get("rhyme_key", ""),
                "internal_rhyme_groups": len(detail.get("internal_rhymes", []) or []),
                "alliteration_groups": len(detail.get("alliteration", []) or []),
                "stress_density_pct": (meter.get("summary") or {}).get("stress_ratio_pct", 0),
                "force_pct": physics.get("force_pct", 0),
                "torsion_pct": physics.get("torsion_pct", 0),
                "spin_pct": physics.get("spin_pct", 0),
                "target_syllables": target,
            },
            "beat_guidance": beat_plan or {"available": False},
            "rhyme_power": rhyme_report.get("rhyme_power", {}),
            "diagnosis": diagnosis,
            "issues_from_line_coach": card.get("issues", []) if card else [],
            "recommended_operation": (card.get("advanced_rhyme", {}) or {}).get("actions", [])[:2] if card else [],
        })
        implied_bar = bar_start + span
    return bars


def _component_descriptions() -> Dict[str, str]:
    return {
        "style_match": "fit to the compiled private NMC corpus profile",
        "rhyme_power": "average line rhyme power from the advanced rhyme engine",
        "cadence_fit": "bar/line syllable fit against corpus or beat pocket",
        "bar_structure": "how well lines occupy one-bar or multi-bar windows",
        "meter_stress": "stress anchors, final landing strength, and meter consistency",
        "scansion_physics": "average F force, τ torsion control, and Ω spin",
        "content_clarity": "imagery, abstraction control, filler load, and motif readability",
        "reference_fit": "closest derived benchmark profile score",
    }


def _global_actions(component_scores: Dict[str, Any], bars: Sequence[Dict[str, Any]], analysis: Dict[str, Any], beat: Dict[str, Any] | None) -> List[str]:
    actions: List[str] = []
    low_components = sorted(component_scores.items(), key=lambda item: _pct(item[1]))[:4]
    for key, score in low_components:
        score_i = _pct(score)
        if score_i >= 72:
            continue
        if key == "rhyme_power":
            weak = [b.get("line_number") for b in bars if _pct((b.get("component_scores") or {}).get("rhyme_power")) < 58][:8]
            actions.append("Rhyme pass: upgrade the γ landing and internal echo on lines " + ", ".join(map(str, weak)) + ".")
        elif key == "cadence_fit":
            weak = [b.get("line_number") for b in bars if _pct((b.get("component_scores") or {}).get("cadence_fit")) < 58][:8]
            actions.append("Cadence pass: rebalance syllable counts on lines " + ", ".join(map(str, weak)) + ".")
        elif key == "bar_structure":
            if beat and beat.get("available"):
                actions.append("Beat pass: split overloaded bars and preserve the final-quarter rhyme landing on the uploaded grid.")
            else:
                actions.append("Bar pass: upload a beat or set a target pocket, then check which lines should become 1-bar versus 2-bar thoughts.")
        elif key == "meter_stress":
            weak = [b.get("line_number") for b in bars if _pct((b.get("component_scores") or {}).get("meter_stress")) < 58][:8]
            actions.append("Stress pass: make final landings and content-word anchors stronger on lines " + ", ".join(map(str, weak)) + ".")
        elif key == "scansion_physics":
            actions.append("Physics pass: raise F/Ω with physical anchors and internal sound loops; lower extreme τ by simplifying off-grid phrases.")
        elif key == "content_clarity":
            actions.append("Clarity pass: replace abstract clusters with visible nouns/actions without losing your system/sentence/rhythm motifs.")
        elif key == "style_match":
            actions.append("Style pass: inject one signature motif family—sentence, rhythm, method, vector, credit, surface—per 4-bar block.")
    weakest_bars = sorted(bars, key=lambda row: _pct(row.get("overall")))[:5]
    if weakest_bars:
        actions.append("Work first on bars/lines " + ", ".join(str(row.get("line_number")) for row in weakest_bars) + "; they have the lowest total score.")
    strong_bars = [row for row in bars if _pct(row.get("overall")) >= 84]
    if strong_bars:
        actions.append("Keep the strongest bar shapes intact: " + ", ".join(str(row.get("line_number")) for row in strong_bars[:6]) + ".")
    return unique_preserve(actions, 7)


def _section_scores(bars: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    section_meta: Dict[str, Dict[str, Any]] = {}
    for bar in bars:
        section = bar.get("section") or {}
        key = f"{section.get('label', 'Section')}:{section.get('start_line', '')}:{section.get('end_line', '')}"
        grouped.setdefault(key, []).append(bar)
        section_meta[key] = section
    rows: List[Dict[str, Any]] = []
    for key, items in grouped.items():
        comp_keys = list(BAR_COMPONENT_WEIGHTS.keys())
        comps = {comp: _avg((row.get("component_scores") or {}).get(comp, 0) for row in items) for comp in comp_keys}
        overall = _pct(_avg(row.get("overall", 0) for row in items))
        weak = [row.get("line_number") for row in sorted(items, key=lambda row: _pct(row.get("overall")))[:5] if _pct(row.get("overall")) < 70]
        rows.append({
            "label": section_meta[key].get("label") or "Section",
            "type": section_meta[key].get("type") or "section",
            "line_count": len(items),
            "bar_count": sum(max(1, _safe_int(row.get("bar_span"), 1)) for row in items),
            "start_line": section_meta[key].get("start_line"),
            "end_line": section_meta[key].get("end_line"),
            "overall": overall,
            "grade": _grade(overall),
            "component_scores": comps,
            "weak_lines": weak,
            "reading": _section_reading(section_meta[key].get("type", "section"), overall, weak),
        })
    return rows


def _section_reading(kind: str, score: int, weak_lines: Sequence[int]) -> str:
    kind_l = (kind or "section").lower()
    if score >= 82:
        return "Section is strong; preserve the shape and make only precision edits."
    if kind_l in {"chorus", "hook", "refrain"} and score < 74:
        return "Hook needs more repeatability: simplify cadence, strengthen title phrase, and keep rhyme families more stable."
    if weak_lines:
        return "Section works, but line(s) " + ", ".join(map(str, weak_lines)) + " should be revised first."
    return "Section has a usable base; polish transitions and bar landings."


def _score_distribution(values: Sequence[int]) -> Dict[str, Any]:
    bins = {"elite_85_plus": 0, "strong_75_84": 0, "workable_65_74": 0, "fragile_50_64": 0, "rebuild_under_50": 0}
    for value in values:
        v = _pct(value)
        if v >= 85:
            bins["elite_85_plus"] += 1
        elif v >= 75:
            bins["strong_75_84"] += 1
        elif v >= 65:
            bins["workable_65_74"] += 1
        elif v >= 50:
            bins["fragile_50_64"] += 1
        else:
            bins["rebuild_under_50"] += 1
    total = max(1, len(values))
    return {key: {"count": count, "pct": _round(count / total * 100, 1)} for key, count in bins.items()}


def build_rap_score_report(
    lyrics: str,
    mode: str = "match",
    beat: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a system-wide score for the rap and every bar/line."""
    mode = mode if mode in MODE_LABELS else "match"
    if not str(lyrics or "").strip():
        return {"available": False, "error": "Provide lyrics before scoring."}
    analysis = analyze_lyrics(lyrics, mode)
    if beat:
        analysis = attach_beat_guidance(analysis, beat)
    else:
        analysis["beat_analysis"] = {"available": False}
        analysis["beat_alignment"] = {"available": False, "summary": "No beat loaded; bar score uses corpus cadence targets."}

    comparison = build_comparison_report(lyrics, analysis)
    meter_report = analyze_meter_text(lyrics, beat=beat)
    physics_report = build_scansion_physics_report(lyrics, mode=mode, beat=beat, analysis=analysis, meter_report=meter_report)
    rhyme_lab = build_rhyme_suggestion_lab(lyrics, mode=mode)
    bars = _build_bar_scores(analysis, rhyme_lab, meter_report, physics_report)
    section_rows = _section_scores(bars)

    avg_bar_components = {key: _avg((bar.get("component_scores") or {}).get(key, 0) for bar in bars) for key in BAR_COMPONENT_WEIGHTS}
    reference_score = _pct((comparison.get("best_match") or {}).get("score", 0)) if comparison.get("available", True) else 0
    component_scores = {
        "style_match": _pct(analysis.get("stats", {}).get("style_match", 0)),
        "rhyme_power": _pct((rhyme_lab.get("summary") or {}).get("avg_rhyme_power", avg_bar_components.get("rhyme_power", 0))),
        "cadence_fit": _pct(avg_bar_components.get("cadence_fit", 0)),
        "bar_structure": _pct(avg_bar_components.get("bar_fit", 0)),
        "meter_stress": _pct(avg_bar_components.get("meter_stress", 0)),
        "scansion_physics": _pct(avg_bar_components.get("scansion_physics", 0)),
        "content_clarity": _pct(avg_bar_components.get("content_clarity", 0)),
        "reference_fit": reference_score,
    }
    overall = _weighted_average(component_scores, SCORE_WEIGHTS)
    descriptions = _component_descriptions()
    component_rows = [
        _component_row(key, component_scores[key], SCORE_WEIGHTS[key], descriptions.get(key, ""))
        for key in SCORE_WEIGHTS
    ]
    bar_values = [_pct(bar.get("overall")) for bar in bars]
    weakest = sorted(bars, key=lambda row: _pct(row.get("overall")))[:8]
    strongest = sorted(bars, key=lambda row: -_pct(row.get("overall")))[:8]
    profile = get_corpus_profile()
    target = analysis.get("beat_alignment", {}).get("target_syllables_per_bar") or profile.get("stats", {}).get("median_syllables") or 12
    report = {
        "available": True,
        "report_type": "system_wide_rap_score",
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "overall": overall,
        "grade": _grade(overall),
        "headline": _headline(overall, component_scores, bool(beat and beat.get("available"))),
        "formula": {
            "global_weights": SCORE_WEIGHTS,
            "bar_weights": BAR_COMPONENT_WEIGHTS,
            "note": "Scores are deterministic coaching signals, not artistic truth. Use deltas to guide revision passes.",
        },
        "component_scores": component_scores,
        "component_rows": component_rows,
        "bar_summary": {
            "lines_scored": len(bars),
            "bars_estimated": sum(max(1, _safe_int(row.get("bar_span"), 1)) for row in bars),
            "avg_bar_score": _round(_avg(bar_values), 1),
            "min_bar_score": min(bar_values) if bar_values else 0,
            "max_bar_score": max(bar_values) if bar_values else 0,
            "distribution": _score_distribution(bar_values),
            "target_syllables": target,
            "beat_aware": bool(beat and beat.get("available")),
        },
        "bar_scores": bars,
        "section_scores": section_rows,
        "weakest_bars": [_bar_digest(row) for row in weakest],
        "strongest_bars": [_bar_digest(row) for row in strongest],
        "global_actions": _global_actions(component_scores, bars, analysis, beat),
        "analysis_refs": {
            "lyric_stats": analysis.get("stats", {}),
            "rhyme_summary": rhyme_lab.get("summary", {}),
            "meter_summary": meter_report.get("summary", {}),
            "physics_summary": physics_report.get("summary", {}),
            "comparison_best_match": comparison.get("best_match", {}),
            "beat_alignment": analysis.get("beat_alignment", {}),
        },
    }
    return report


def _headline(score: int, components: Dict[str, Any], beat_aware: bool) -> str:
    grade = _grade(score)
    weakest = min(components.items(), key=lambda item: _pct(item[1]))[0] if components else "structure"
    if score >= 84:
        return f"{grade['letter']} system score: the rap is structurally strong; next pass should target {weakest.replace('_', ' ')} only."
    if score >= 70:
        return f"{grade['letter']} system score: the rap is usable, but {weakest.replace('_', ' ')} is the clearest revision lane."
    beat_note = " on the uploaded beat" if beat_aware else " before beat-locking"
    return f"{grade['letter']} system score: rebuild the weakest bars{beat_note}, starting with {weakest.replace('_', ' ')}."


def _bar_digest(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "line_number": row.get("line_number"),
        "assigned_bars": row.get("assigned_bars"),
        "overall": row.get("overall"),
        "grade": row.get("grade"),
        "text": row.get("text"),
        "weakest_components": (row.get("diagnosis") or {}).get("weakest_components", [])[:3],
        "advice": (row.get("diagnosis") or {}).get("advice", [])[:3],
    }


def _line_list(text: str) -> List[str]:
    # Keep same filtering logic as lyric_engine by scoring first; this function is
    # only for edit diff display and can be lightweight.
    return [line.strip() for line in str(text or "").splitlines() if line.strip() and not line.strip().lower().startswith("//")]


def _word_jaccard(a: str, b: str) -> float:
    aw = set(content_words(tokenize(a)))
    bw = set(content_words(tokenize(b)))
    if not aw and not bw:
        return 1.0
    return len(aw & bw) / max(1, len(aw | bw))


def _line_similarity(a: str, b: str) -> int:
    seq = difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()
    jac = _word_jaccard(a, b)
    same_rhyme = 1.0 if rhyme_key((tokenize(a) or [""])[-1]) == rhyme_key((tokenize(b) or [""])[-1]) else 0.0
    return _pct(seq * 55 + jac * 30 + same_rhyme * 15)


def _component_delta_rows(original: Dict[str, Any], edited: Dict[str, Any]) -> List[Dict[str, Any]]:
    a = original.get("component_scores", {}) or {}
    b = edited.get("component_scores", {}) or {}
    rows = []
    for key in SCORE_WEIGHTS:
        old = _pct(a.get(key, 0))
        new = _pct(b.get(key, 0))
        rows.append({
            "key": key,
            "label": key.replace("_", " ").title(),
            "original": old,
            "edited": new,
            "delta": new - old,
            "verdict": "improved" if new > old else "weaker" if new < old else "unchanged",
        })
    rows.sort(key=lambda row: (-abs(int(row["delta"])), row["key"]))
    return rows


def _bar_delta_rows(original: Dict[str, Any], edited: Dict[str, Any]) -> List[Dict[str, Any]]:
    old_bars = original.get("bar_scores", []) or []
    new_bars = edited.get("bar_scores", []) or []
    max_len = max(len(old_bars), len(new_bars))
    rows: List[Dict[str, Any]] = []
    for idx in range(max_len):
        old = old_bars[idx] if idx < len(old_bars) else {}
        new = new_bars[idx] if idx < len(new_bars) else {}
        old_text = str(old.get("text") or "")
        new_text = str(new.get("text") or "")
        old_score = _pct(old.get("overall", 0)) if old else 0
        new_score = _pct(new.get("overall", 0)) if new else 0
        if old and not new:
            status = "removed"
            verdict = "removed bar"
        elif new and not old:
            status = "added"
            verdict = "added bar"
        else:
            sim = _line_similarity(old_text, new_text)
            status = "changed" if sim < 96 or old_score != new_score else "unchanged"
            verdict = "improved" if new_score > old_score else "weaker" if new_score < old_score else status
        old_components = old.get("component_scores", {}) or {}
        new_components = new.get("component_scores", {}) or {}
        component_delta = {
            key: _pct(new_components.get(key, 0)) - _pct(old_components.get(key, 0))
            for key in BAR_COMPONENT_WEIGHTS
        }
        rows.append({
            "bar_index": idx + 1,
            "original_line_number": old.get("line_number"),
            "edited_line_number": new.get("line_number"),
            "original_assigned_bars": old.get("assigned_bars"),
            "edited_assigned_bars": new.get("assigned_bars"),
            "original_score": old_score,
            "edited_score": new_score,
            "delta": new_score - old_score,
            "status": status,
            "verdict": verdict,
            "similarity_pct": _line_similarity(old_text, new_text) if old and new else 0,
            "original_text": old_text,
            "edited_text": new_text,
            "component_delta": component_delta,
            "main_gain": _main_delta(component_delta, positive=True),
            "main_loss": _main_delta(component_delta, positive=False),
            "edited_advice": (new.get("diagnosis") or {}).get("advice", [])[:3] if new else [],
        })
    return rows


def _main_delta(delta: Dict[str, int], positive: bool) -> Dict[str, Any]:
    if not delta:
        return {"key": "", "delta": 0}
    if positive:
        key, value = max(delta.items(), key=lambda item: item[1])
    else:
        key, value = min(delta.items(), key=lambda item: item[1])
    return {"key": key, "label": key.replace("_", " ").title(), "delta": value}


def _edit_recommendation(delta: int, comp_rows: Sequence[Dict[str, Any]], bar_rows: Sequence[Dict[str, Any]]) -> str:
    if delta >= 6:
        return "Keep the edit: the system score improved meaningfully. Review any individual bars that dropped before finalizing."
    if delta >= 1:
        return "Keep most of the edit: it is a small net improvement. Preserve the bars with gains and rework bars with negative deltas."
    if delta == 0:
        return "Neutral edit: choose based on meaning and delivery. The score did not change materially."
    biggest_loss = next((row for row in comp_rows if int(row.get("delta", 0)) < 0), None)
    weak_bars = [row for row in bar_rows if int(row.get("delta", 0)) <= -5]
    if biggest_loss:
        return f"Revise before keeping: the edit weakened {biggest_loss.get('label')}. Start with changed bars " + ", ".join(str(row.get("bar_index")) for row in weak_bars[:5]) + "."
    return "Revise before keeping: the edit weakened several bar-level signals. Compare the changed bars and recover the stronger old landings."


def compare_rap_edits(
    original_lyrics: str,
    edited_lyrics: str,
    mode: str = "match",
    beat: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Score two drafts and return component/bar deltas."""
    if not str(original_lyrics or "").strip():
        return {"available": False, "error": "Provide the original/baseline lyrics."}
    if not str(edited_lyrics or "").strip():
        return {"available": False, "error": "Provide the edited lyrics."}
    original = build_rap_score_report(original_lyrics, mode=mode, beat=beat)
    edited = build_rap_score_report(edited_lyrics, mode=mode, beat=beat)
    if not original.get("available"):
        return original
    if not edited.get("available"):
        return edited
    delta = _pct(edited.get("overall", 0)) - _pct(original.get("overall", 0))
    comp_rows = _component_delta_rows(original, edited)
    bar_rows = _bar_delta_rows(original, edited)
    improved = [row for row in bar_rows if int(row.get("delta", 0)) > 0]
    weakened = [row for row in bar_rows if int(row.get("delta", 0)) < 0]
    changed = [row for row in bar_rows if row.get("status") != "unchanged"]
    return {
        "available": True,
        "report_type": "rap_edit_comparison",
        "mode": mode,
        "mode_label": MODE_LABELS.get(mode, mode),
        "original": original,
        "edited": edited,
        "summary": {
            "original_score": original.get("overall", 0),
            "edited_score": edited.get("overall", 0),
            "delta": delta,
            "original_grade": original.get("grade", {}),
            "edited_grade": edited.get("grade", {}),
            "changed_bars": len(changed),
            "improved_bars": len(improved),
            "weakened_bars": len(weakened),
            "verdict": "improved" if delta > 0 else "weaker" if delta < 0 else "neutral",
            "recommendation": _edit_recommendation(delta, comp_rows, bar_rows),
        },
        "component_deltas": comp_rows,
        "bar_deltas": bar_rows,
        "top_gains": sorted(improved, key=lambda row: -int(row.get("delta", 0)))[:10],
        "top_losses": sorted(weakened, key=lambda row: int(row.get("delta", 0)))[:10],
        "changed_bars": changed[:80],
    }
