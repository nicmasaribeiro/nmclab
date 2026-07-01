"""Active editing helpers for the NMC rap editing lab.

This module sits on top of lyric_engine.py and beat_engine.py. It converts the
raw analysis objects into editor-friendly fix cards, patch suggestions, and
ranked active-line coaching that the browser can poll asynchronously while the
user types.
"""
from __future__ import annotations

import difflib
import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence

from beat_engine import attach_beat_guidance
from comparison_engine import build_comparison_report, line_comparison_guidance
from meter_engine import analyze_meter_text, analyze_sentence_meter
from physics_engine import build_scansion_physics_report, build_sentence_physics_report
from rhyme_engine import build_rhyme_suggestion_lab
from score_engine import build_rap_score_report
from lyric_engine import (
    MODE_LABELS,
    analyze_lyrics,
    build_line_details,
    content_words,
    count_syllables,
    line_syllables,
    get_corpus_profile,
    normalize_word,
    possible_rhymes_for_word,
    rhyme_key,
    tokenize,
    unique_preserve,
)

SOFT_CONNECTORS = {
    "a", "an", "the", "of", "to", "for", "and", "or", "but", "that", "this", "these", "those",
    "is", "are", "was", "were", "be", "being", "been", "with", "within", "into", "in", "on", "at",
    "from", "as", "so", "just", "very", "really", "quite", "maybe", "sometimes", "still", "yet", "then",
}

HARD_LANDING_BANK = [
    "signal", "system", "sentence", "resonance", "medicine", "evidence", "vector", "surface",
    "purpose", "credit", "method", "rhythm", "script", "engine", "canvas", "circuit", "pressure",
    "texture", "signature", "precision", "dominance", "consonance", "paradise", "paradox",
]

IMAGE_BRIDGES = ["etched in", "wired through", "stitched inside", "measured by", "anchored on", "lit by"]
ACTION_BRIDGES = ["tighten", "anchor", "split", "compress", "stretch", "thread", "sync", "flip", "land", "cut"]

RHYME_HIGHLIGHT_CLASS_COUNT = 12
RHYME_HIGHLIGHT_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|\s+|[^A-Za-z0-9\s]+")


def _round(value: float, digits: int = 2) -> float:
    try:
        if math.isfinite(float(value)):
            return round(float(value), digits)
    except Exception:
        pass
    return 0.0


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _line_lookup(analysis: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    return {int(card.get("number", -1)): card for card in analysis.get("line_suggestions", [])}


def _detail_lookup(analysis: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    return {int(row.get("number", -1)): row for row in analysis.get("raw_line_details", [])}


def _beat_lookup(analysis: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for row in analysis.get("beat_alignment", {}).get("per_line", []) or []:
        out[int(row.get("line_number", -1))] = row
    return out


def _replace_last_word(line: str, new_word: str) -> str:
    if not new_word:
        return line
    match = list(re.finditer(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", line))
    if not match:
        return new_word
    last = match[-1]
    return line[: last.start()] + new_word + line[last.end() :]


def _remove_words_preserve_order(line: str, remove: Sequence[str], max_remove: int = 3) -> str:
    remove_set = {normalize_word(w) for w in remove[:max_remove] if normalize_word(w)}
    if not remove_set:
        return line
    words = re.findall(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|[^A-Za-z0-9]+", line)
    removed = 0
    out: List[str] = []
    for token in words:
        norm = normalize_word(token)
        if norm in remove_set and removed < max_remove:
            removed += 1
            continue
        out.append(token)
    text = "".join(out)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text or line


def _insert_before_last_word(line: str, phrase: str) -> str:
    phrase = phrase.strip()
    if not phrase:
        return line
    matches = list(re.finditer(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", line))
    if not matches:
        return f"{line} {phrase}".strip()
    last = matches[-1]
    spacer = " " if last.start() > 0 and not line[last.start() - 1].isspace() else ""
    return (line[: last.start()] + phrase + spacer + line[last.start() :]).strip()


def _split_line_variant(line: str, split_preview: Dict[str, str] | None) -> str:
    if split_preview and split_preview.get("bar_1") and split_preview.get("bar_2_plus"):
        return f"{split_preview['bar_1']}\n{split_preview['bar_2_plus']}"
    words = line.split()
    if len(words) < 8:
        return line
    midpoint = len(words) // 2
    return " ".join(words[:midpoint]) + "\n" + " ".join(words[midpoint:])


def _syllable_delta_label(syllables: int, target: Sequence[int] | int | float) -> str:
    if isinstance(target, (list, tuple)) and len(target) >= 2:
        low, high = int(target[0]), int(target[1])
        if syllables < low:
            return f"{low - syllables} syllables under pocket"
        if syllables > high:
            return f"{syllables - high} syllables over pocket"
        return "inside pocket"
    target_num = int(round(float(target or 12)))
    delta = syllables - target_num
    if abs(delta) <= 2:
        return "near corpus target"
    return f"{abs(delta)} syllables {'over' if delta > 0 else 'under'} corpus target"


def _severity(card: Dict[str, Any], beat_plan: Dict[str, Any] | None) -> int:
    score = 0
    issues = card.get("issues") or []
    issue_types = {str(issue.get("type", "")).lower() for issue in issues}
    score += len(issues) * 12
    if "cadence" in issue_types:
        score += 18
    if "end word" in issue_types or "repetition" in issue_types:
        score += 14
    if "internal rhyme" in issue_types:
        score += 10
    if beat_plan:
        density = str(beat_plan.get("density_label", "")).lower()
        span = _safe_int(beat_plan.get("bar_span"), 1)
        if density == "very dense":
            score += 18
        elif density == "open":
            score += 10
        if span > 1:
            score += 16
    return max(0, min(100, score))


def _priority_label(score: int) -> str:
    if score >= 76:
        return "critical"
    if score >= 54:
        return "high"
    if score >= 28:
        return "medium"
    return "low"


def _main_diagnosis(card: Dict[str, Any], beat_plan: Dict[str, Any] | None) -> str:
    issues = card.get("issues") or []
    if beat_plan and _safe_int(beat_plan.get("bar_span"), 1) > 1:
        return "Line is too large for one bar on the uploaded beat; split the thought and give each bar a landing."
    if beat_plan and str(beat_plan.get("density_label", "")).lower() == "very dense":
        return "Pocket is overcrowded; trim connective words or perform it as double-time with clearer stress points."
    if issues:
        return str(issues[0].get("message") or "Revise this line first.")
    return "Solid line; use a precision pass for a sharper image, internal echo, or final-word landing."


def _recommended_operation(card: Dict[str, Any], beat_plan: Dict[str, Any] | None) -> str:
    issue_types = {str(issue.get("type", "")).lower() for issue in card.get("issues", [])}
    if beat_plan and _safe_int(beat_plan.get("bar_span"), 1) > 1:
        return "split_line"
    if beat_plan and str(beat_plan.get("density_label", "")).lower() == "very dense":
        return "compress_line"
    if "end word" in issue_types or "repetition" in issue_types:
        return "swap_end_rhyme"
    if "internal rhyme" in issue_types:
        return "add_internal_echo"
    if "imagery" in issue_types:
        return "add_image"
    if "cadence" in issue_types:
        return "rebalance_cadence"
    return "polish_punch"


def _operation_label(operation: str) -> str:
    labels = {
        "split_line": "Split across bars",
        "compress_line": "Compress for pocket",
        "swap_end_rhyme": "Swap end rhyme",
        "add_internal_echo": "Add inner echo",
        "add_image": "Add concrete image",
        "rebalance_cadence": "Rebalance cadence",
        "polish_punch": "Sharpen punch",
    }
    return labels.get(operation, "Fix line")


def _patches_for_line(card: Dict[str, Any], detail: Dict[str, Any], beat_plan: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    line = card.get("text") or detail.get("text") or ""
    words = detail.get("words") or tokenize(line)
    possible = card.get("possible_words") or {}
    end_rhymes = possible.get("end_rhymes_from_your_corpus") or []
    internal = possible.get("internal_echo_words") or []
    images = possible.get("concrete_image_words") or []
    verbs = possible.get("stronger_verbs") or []
    cut_words = unique_preserve((possible.get("cut_or_replace") or []) + [w for w in words if normalize_word(w) in SOFT_CONNECTORS], 12)
    patches: List[Dict[str, Any]] = []

    advanced = card.get("advanced_rhyme") or {}
    for adv_patch in advanced.get("patches", [])[:3]:
        replacement = str(adv_patch.get("replacement") or "").strip()
        if replacement and replacement != line:
            patches.append({
                "type": adv_patch.get("type", "replace_line"),
                "label": adv_patch.get("label", "Advanced rhyme patch"),
                "replacement": replacement,
                "why": adv_patch.get("why", "Advanced rhyme suggestion."),
                "delta_syllables": line_syllables(replacement) - line_syllables(line),
                "operation": adv_patch.get("operation", "advanced_rhyme"),
            })

    trimmed = _remove_words_preserve_order(line, cut_words, max_remove=3)
    if trimmed != line:
        patches.append({
            "type": "replace_line",
            "label": "Apply compression",
            "replacement": trimmed,
            "why": "Cuts low-information connective/filler words so the bar has more breath.",
            "delta_syllables": line_syllables(trimmed) - line_syllables(line),
        })

    if beat_plan and _safe_int(beat_plan.get("bar_span"), 1) > 1:
        split = _split_line_variant(line, beat_plan.get("split_preview") or {})
        if split != line:
            patches.append({
                "type": "replace_line",
                "label": "Apply beat split",
                "replacement": split,
                "why": "Turns one overloaded thought into two performable bar landings.",
                "delta_syllables": 0,
            })

    if end_rhymes:
        swapped = _replace_last_word(line, end_rhymes[0])
        if swapped != line:
            patches.append({
                "type": "replace_line",
                "label": f"Land on “{end_rhymes[0]}”",
                "replacement": swapped,
                "why": "Keeps the setup but rotates the final word toward a corpus rhyme family.",
                "delta_syllables": line_syllables(swapped) - line_syllables(line),
            })

    if internal:
        echo = internal[0]
        bridge = IMAGE_BRIDGES[0]
        inserted = _insert_before_last_word(line, f"{bridge} {echo}")
        if inserted != line:
            patches.append({
                "type": "replace_line",
                "label": f"Add echo “{echo}”",
                "replacement": inserted,
                "why": "Adds a mid-line sound pocket before the final rhyme.",
                "delta_syllables": line_syllables(inserted) - line_syllables(line),
            })

    if images or verbs:
        image = images[0] if images else "signal"
        verb = verbs[0] if verbs else "anchor"
        inserted = _insert_before_last_word(line, f"{verb} the {image}")
        if inserted != line:
            patches.append({
                "type": "replace_line",
                "label": f"Add image “{image}”",
                "replacement": inserted,
                "why": "Makes the abstraction more visible and performable.",
                "delta_syllables": line_syllables(inserted) - line_syllables(line),
            })

    return patches[:5]


def _rewrite_variants(card: Dict[str, Any], detail: Dict[str, Any], beat_plan: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    line = card.get("text") or detail.get("text") or ""
    possible = card.get("possible_words") or {}
    variants: List[Dict[str, Any]] = []
    for patch in _patches_for_line(card, detail, beat_plan):
        variants.append({
            "name": patch["label"],
            "text": patch["replacement"],
            "why": patch["why"],
            "syllables": line_syllables(patch["replacement"]),
        })
    if len(variants) < 3:
        end_options = (
            possible.get("end_rhymes_from_your_corpus")
            or possible.get("slant_rhyme_words")
            or possible.get("multi_syllable_endings")
            or possible.get("near_rhymes_from_your_corpus")
            or HARD_LANDING_BANK
        )
        motif_options = possible.get("signature_motif_words") or HARD_LANDING_BANK
        verb_options = possible.get("stronger_verbs") or ACTION_BRIDGES
        for end in end_options[:4]:
            motif = motif_options[0] if motif_options else "signal"
            verb = verb_options[0] if verb_options else "anchor"
            candidate = f"{verb.capitalize()} the {motif} till it lands in {end}"
            variants.append({
                "name": "Fresh rewrite seed",
                "text": candidate,
                "why": "A compact rewrite seed that keeps your technical motif style while changing the line shape.",
                "syllables": line_syllables(candidate),
            })
            if len(variants) >= 4:
                break
    return variants[:4]


def _word_bank_summary(card: Dict[str, Any]) -> Dict[str, List[str]]:
    possible = card.get("possible_words") or {}
    return {
        "end_rhymes": possible.get("end_rhymes_from_your_corpus", [])[:12],
        "near_rhymes": possible.get("near_rhymes_from_your_corpus", [])[:12],
        "slant_rhymes": possible.get("slant_rhyme_words", [])[:12],
        "assonance_words": possible.get("assonance_words", [])[:12],
        "consonance_words": possible.get("consonance_words", [])[:12],
        "stress_matched": possible.get("stress_matched_words", [])[:12],
        "multi_syllable_endings": possible.get("multi_syllable_endings", [])[:12],
        "internal_echoes": possible.get("internal_echo_words", [])[:12],
        "signature_words": possible.get("signature_motif_words", [])[:12],
        "images": possible.get("concrete_image_words", [])[:10],
        "verbs": possible.get("stronger_verbs", [])[:10],
        "punch_words": possible.get("punch_words", [])[:10],
        "cut_words": possible.get("cut_or_replace", [])[:10],
    }


def _fix_card(card: Dict[str, Any], detail: Dict[str, Any], beat_plan: Dict[str, Any] | None, active: bool = False) -> Dict[str, Any]:
    severity = _severity(card, beat_plan)
    operation = _recommended_operation(card, beat_plan)
    metrics = card.get("metrics") or {}
    target = beat_plan.get("target_syllables_per_bar") if beat_plan else metrics.get("target_syllables")
    beat_moves = beat_plan.get("beat_moves", []) if beat_plan else []
    patches = _patches_for_line(card, detail, beat_plan)
    variants = _rewrite_variants(card, detail, beat_plan)
    replacement = variants[0]["text"] if variants else card.get("text", "")
    original = card.get("text", "")
    diff = list(difflib.ndiff(original.split(), replacement.split())) if replacement != original else []
    return {
        "line_number": int(card.get("number", detail.get("number", 0))),
        "text": original,
        "active": active,
        "severity": severity,
        "priority": _priority_label(severity),
        "operation": operation,
        "operation_label": _operation_label(operation),
        "diagnosis": _main_diagnosis(card, beat_plan),
        "syllable_status": _syllable_delta_label(_safe_int(metrics.get("syllables")), target or 12),
        "metrics": metrics,
        "issues": card.get("issues", []),
        "specific_moves": unique_preserve((card.get("specific_moves") or []) + beat_moves, 10),
        "word_banks": _word_bank_summary(card),
        "advanced_rhyme": card.get("advanced_rhyme", {}),
        "patches": patches,
        "rewrite_variants": variants,
        "beat_guidance": beat_plan or {},
        "diff_preview": diff[:80],
        "nearby_corpus_lines": card.get("nearby_corpus_lines", []),
        "sound_hits": card.get("sound_hits", {}),
        "motif_hits": card.get("motif_hits", {}),
    }


def _nearest_line_number(line_numbers: Sequence[int], active_line: int | None) -> int | None:
    if not line_numbers:
        return None
    if not active_line:
        return line_numbers[0]
    return min(line_numbers, key=lambda n: abs(n - active_line))


def _global_editor_actions(analysis: Dict[str, Any], fixes: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    if analysis.get("beat_alignment", {}).get("available"):
        ba = analysis["beat_alignment"]
        if ba.get("split_lines", 0):
            actions.append({
                "title": "Split overloaded bars",
                "detail": f"{ba.get('split_lines')} line(s) want multi-bar treatment on this beat. Apply split patches before polishing rhymes.",
                "line_numbers": [f["line_number"] for f in fixes if f.get("operation") == "split_line"][:8],
            })
        if ba.get("compress_lines", 0):
            actions.append({
                "title": "Compress dense one-bar lines",
                "detail": f"{ba.get('compress_lines')} line(s) are close to fitting but need cuts. Remove connectors before changing core images.",
                "line_numbers": [f["line_number"] for f in fixes if f.get("operation") == "compress_line"][:8],
            })
    for action in analysis.get("priority_actions", [])[:3]:
        actions.append({"title": action.get("title", "Priority"), "detail": action.get("detail", ""), "line_numbers": []})
    if not actions:
        actions.append({"title": "Polish pass", "detail": "Draft has no critical structural issue. Work through the medium cards for end-rhyme weight and images.", "line_numbers": []})
    return actions[:6]


def _editor_score(analysis: Dict[str, Any], fixes: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    style = int(analysis.get("stats", {}).get("style_match", 0))
    severe = len([f for f in fixes if f.get("priority") in {"critical", "high"}])
    beat_score = 100
    if analysis.get("beat_alignment", {}).get("available"):
        ba = analysis["beat_alignment"]
        total = max(1, len(fixes))
        beat_score = int(round(100 - ((ba.get("split_lines", 0) + ba.get("compress_lines", 0)) / total) * 100))
        beat_score = max(0, min(100, beat_score))
    fix_score = max(0, 100 - severe * 12)
    overall = int(round(style * 0.38 + beat_score * 0.32 + fix_score * 0.30))
    return {
        "overall": overall,
        "style_match": style,
        "beat_fit": beat_score,
        "fix_load": fix_score,
        "critical_or_high_cards": severe,
    }


def _rhyme_highlight_report(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Build color-class metadata for end rhymes and internal echoes.

    The frontend receives semantic tokens instead of pre-rendered HTML, so it can
    safely highlight rhymes in the static snapshot, live cards, and JSON views.
    """
    details = analysis.get("raw_line_details", []) or []
    clean_details = [detail for detail in details if detail.get("text")]
    end_key_counts = Counter(detail.get("rhyme_key") for detail in clean_details if detail.get("rhyme_key"))
    first_order: List[str] = []
    for detail in clean_details:
        key = str(detail.get("rhyme_key") or "")
        if key and key not in first_order:
            first_order.append(key)

    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    key_to_letter: Dict[str, str] = {}
    key_to_class: Dict[str, int] = {}
    for idx, key in enumerate(first_order):
        key_to_letter[key] = letters[idx] if idx < len(letters) else f"R{idx + 1}"
        key_to_class[key] = (idx % RHYME_HIGHLIGHT_CLASS_COUNT) + 1

    line_numbers_by_key: Dict[str, List[int]] = {}
    end_words_by_key: Dict[str, List[str]] = {}
    for key in first_order:
        rows = [detail for detail in clean_details if detail.get("rhyme_key") == key]
        line_numbers_by_key[key] = [int(row.get("number", 0)) for row in rows if row.get("number")]
        end_words_by_key[key] = unique_preserve([row.get("end_word", "") for row in rows], 12)

    families = []
    for key in first_order:
        families.append({
            "key": key,
            "letter": key_to_letter.get(key, ""),
            "class": key_to_class.get(key, 1),
            "count": int(end_key_counts.get(key, 0)),
            "end_words": end_words_by_key.get(key, []),
            "line_numbers": line_numbers_by_key.get(key, []),
            "repeated": int(end_key_counts.get(key, 0)) > 1,
        })
    families.sort(key=lambda row: (-int(row.get("count", 0)), first_order.index(row["key"]) if row.get("key") in first_order else 999))

    def line_tokens(detail: Dict[str, Any]) -> Dict[str, Any]:
        text = str(detail.get("text") or "")
        line_key = str(detail.get("rhyme_key") or "")
        line_number = int(detail.get("number") or 0)
        word_matches = list(re.finditer(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", text))
        last_word_span = (word_matches[-1].start(), word_matches[-1].end()) if word_matches else None
        internal_keys = {
            str(group.get("key"))
            for group in (detail.get("internal_rhymes") or [])
            if group.get("key")
        }
        tokens: List[Dict[str, Any]] = []
        highlighted_words = 0
        for match in RHYME_HIGHLIGHT_TOKEN_RE.finditer(text):
            raw = match.group(0)
            is_word = bool(re.match(r"^[A-Za-z0-9]", raw))
            if not is_word:
                tokens.append({"text": raw, "type": "space" if raw.isspace() else "punct", "highlight": False})
                continue
            norm = normalize_word(raw)
            key = rhyme_key(norm)
            family_count = int(end_key_counts.get(key, 0)) if key else 0
            same_as_landing = bool(key and key == line_key)
            is_end = bool(last_word_span and match.start() == last_word_span[0] and match.end() == last_word_span[1])
            is_internal = bool(key and key in internal_keys and len(key) >= 2 and len(norm) > 2)
            is_cross_line = bool(key and family_count > 1 and len(key) >= 2 and (len(norm) > 2 or is_end))
            highlight = bool(is_end or is_internal or is_cross_line or (same_as_landing and len(norm) > 2))
            if is_end:
                role = "end"
            elif is_internal:
                role = "internal"
            elif is_cross_line:
                role = "cross-line"
            elif same_as_landing:
                role = "echo"
            else:
                role = "plain"
            if highlight:
                highlighted_words += 1
            tokens.append({
                "text": raw,
                "type": "word",
                "normalized": norm,
                "highlight": highlight,
                "role": role,
                "rhyme_key": key,
                "rhyme_letter": key_to_letter.get(key, ""),
                "rhyme_class": key_to_class.get(key, 0),
                "family_count": family_count,
                "same_as_line_landing": same_as_landing,
                "is_end_word": is_end,
                "title": (
                    f"/{key}/ family · {key_to_letter.get(key, '—')} · "
                    f"{family_count} line{'s' if family_count != 1 else ''}"
                ) if highlight and key else "",
            })
        return {
            "line_number": line_number,
            "text": text,
            "end_word": detail.get("end_word", ""),
            "line_rhyme_key": line_key,
            "line_rhyme_letter": key_to_letter.get(line_key, ""),
            "line_rhyme_class": key_to_class.get(line_key, 0),
            "line_family_count": int(end_key_counts.get(line_key, 0)) if line_key else 0,
            "line_family_lines": line_numbers_by_key.get(line_key, []),
            "internal_rhyme_keys": sorted(internal_keys),
            "highlighted_word_count": highlighted_words,
            "tokens": tokens,
        }

    line_map = {int(detail.get("number", 0)): line_tokens(detail) for detail in clean_details if detail.get("number")}
    repeated = [family for family in families if family.get("repeated")]
    return {
        "available": bool(clean_details),
        "scheme": analysis.get("rhyme_scheme", {}).get("scheme", ""),
        "density": analysis.get("rhyme_scheme", {}).get("density", 0),
        "families": families,
        "repeated_families": repeated,
        "line_map": line_map,
        "summary": {
            "unique_families": len(families),
            "repeated_families": len(repeated),
            "highlighted_lines": sum(1 for item in line_map.values() if item.get("highlighted_word_count", 0) > 0),
            "instruction": "Matching colors show shared rhyme families. Underlined tokens are end rhymes; dashed tokens are internal echoes.",
        },
    }


def build_editing_lab_result(
    lyrics: str,
    mode: str = "match",
    active_line: int | None = None,
    beat: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return the full active-editor result for a lyric draft."""
    mode = mode if mode in MODE_LABELS else "match"
    analysis = analyze_lyrics(lyrics, mode)
    if beat:
        analysis = attach_beat_guidance(analysis, beat)
    else:
        analysis["beat_analysis"] = {"available": False}
        analysis["beat_alignment"] = {"available": False, "summary": "Upload a beat to enable live bar-structure patches."}

    comparison_report = build_comparison_report(lyrics, analysis)
    meter_report = analyze_meter_text(lyrics, beat=beat)
    physics_report = build_scansion_physics_report(lyrics, mode=mode, beat=beat, analysis=analysis, meter_report=meter_report)
    rhyme_lab = build_rhyme_suggestion_lab(lyrics, mode=mode, active_line=active_line)
    score_report = build_rap_score_report(lyrics, mode=mode, beat=beat)
    score_by_line = {int(row.get("line_number", -1)): row for row in score_report.get("bar_scores", [])}
    physics_by_line = {int(row.get("line_number", -1)): row for row in physics_report.get("line_physics", [])}
    meter_by_line = {int(row.get("line_number", -1)): row.get("meter", {}) for row in meter_report.get("line_details", [])}

    cards = _line_lookup(analysis)
    details = _detail_lookup(analysis)
    beats = _beat_lookup(analysis)
    line_numbers = sorted(cards)
    active_no = _nearest_line_number(line_numbers, active_line)

    highlight_report = _rhyme_highlight_report(analysis)
    highlight_by_line = highlight_report.get("line_map", {})

    fixes = []
    for line_no in line_numbers:
        detail = details.get(line_no, {})
        fix = _fix_card(cards[line_no], detail, beats.get(line_no), active=(line_no == active_no))
        fix["rhyme_highlight"] = highlight_by_line.get(line_no, {})
        fix["meter"] = meter_by_line.get(line_no, {})
        fix["physics"] = physics_by_line.get(line_no, {})
        fix["bar_score"] = score_by_line.get(line_no, {})
        fix["comparison_guidance"] = line_comparison_guidance(detail, comparison_report)
        fixes.append(fix)
    fixes.sort(key=lambda f: (0 if f.get("active") else 1, -int(f.get("severity", 0)), f.get("line_number", 9999)))
    # Keep all fixes in the API, but provide a display queue already ranked.
    ranked_queue = sorted(fixes, key=lambda f: (-int(f.get("severity", 0)), f.get("line_number", 9999)))
    active_card = next((f for f in fixes if f.get("active")), ranked_queue[0] if ranked_queue else None)

    profile = get_corpus_profile()
    result = {
        "available": True,
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "active_line_number": active_no,
        "editor_score": _editor_score(analysis, ranked_queue),
        "rap_score": score_report,
        "summary": {
            "lines": analysis.get("stats", {}).get("lines", 0),
            "words": analysis.get("stats", {}).get("words", 0),
            "avg_syllables": analysis.get("stats", {}).get("avg_syllables", 0),
            "rhyme_density": analysis.get("stats", {}).get("rhyme_density", 0),
            "style_match": analysis.get("stats", {}).get("style_match", 0),
            "title_candidates": analysis.get("title_candidates", [])[:8],
        },
        "active_fix": active_card,
        "fix_queue": ranked_queue,
        "line_fixes": sorted(fixes, key=lambda f: f.get("line_number", 9999)),
        "editor_actions": _global_editor_actions(analysis, ranked_queue),
        "beat_analysis": analysis.get("beat_analysis", {}),
        "beat_alignment": analysis.get("beat_alignment", {}),
        "rhyme_scheme": analysis.get("rhyme_scheme", {}),
        "rhyme_highlights": highlight_report,
        "rhyme_lab": rhyme_lab,
        "meter_report": meter_report,
        "physics_report": physics_report,
        "score_report": score_report,
        "comparison": comparison_report,
        "top_input_words": analysis.get("top_input_words", []),
        "motifs_used": analysis.get("motifs_used", []),
        "corpus_dna": {
            "stats": profile.get("stats", {}),
            "signature_words": profile.get("signature_words", [])[:30],
            "top_rhymes": profile.get("top_rhymes", [])[:16],
            "motif_clusters": profile.get("motif_clusters", [])[:8],
        },
        "raw_analysis": analysis,
    }
    return result


def _section_line_lookup(analysis: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    """Map original draft line numbers to their section metadata."""
    lookup: Dict[int, Dict[str, Any]] = {}
    for section in analysis.get("sections", []) or []:
        rows = section.get("lines", []) or []
        total = max(1, len(rows))
        for index, row in enumerate(rows, start=1):
            try:
                number = int(row.get("number", 0))
            except Exception:
                continue
            lookup[number] = {
                "label": section.get("label") or "Section",
                "type": section.get("type") or "section",
                "position": index,
                "line_count": total,
                "start_line": section.get("start_line"),
                "end_line": section.get("end_line"),
            }
    return lookup


def _line_function(section_type: str, position: int, total: int, detail: Dict[str, Any]) -> str:
    """Readable role label for the static report."""
    section_type = (section_type or "section").lower()
    if section_type in {"chorus", "hook", "refrain"}:
        if position == 1:
            return "hook opener / title setup"
        if position == total:
            return "hook landing / repeatable close"
        return "hook support / chantable middle"
    if section_type == "bridge":
        return "contrast line / breath reset"
    if position == 1:
        return "verse setup"
    if position == total:
        return "verse landing / exit punch"
    if detail.get("internal_rhymes"):
        return "dense technical run"
    return "development bar"


def _cadence_sentence(syllables: int, target: Sequence[int] | int | float) -> str:
    if isinstance(target, (list, tuple)) and len(target) >= 2:
        low, high = int(target[0]), int(target[1])
        if syllables < low:
            return f"{syllables} syllables sits below the beat pocket of {low}-{high}; add a short pickup phrase or leave the space as a deliberate breath."
        if syllables > high:
            return f"{syllables} syllables pushes past the beat pocket of {low}-{high}; cut filler or split the thought before the final rhyme."
        return f"{syllables} syllables is inside the beat pocket of {low}-{high}; keep the shape and sharpen the landing word."
    target_num = int(round(float(target or 12)))
    delta = syllables - target_num
    if abs(delta) <= 2:
        return f"{syllables} syllables is close to the corpus target near {target_num}; revise for clarity and punch, not length."
    if delta > 0:
        return f"{syllables} syllables runs about {delta} over the corpus target near {target_num}; compress the middle."
    return f"{syllables} syllables is about {abs(delta)} under the corpus target near {target_num}; add one concrete image or internal echo."


def _sound_sentence(detail: Dict[str, Any]) -> str:
    internal = detail.get("internal_rhymes") or []
    allit = detail.get("alliteration") or []
    if internal:
        first = internal[0]
        return f"Internal rhyme is active on the {first.get('key', 'sound')} family: {', '.join(first.get('words', [])[:5])}."
    if allit:
        first = allit[0]
        return f"Alliteration is carrying sound with the “{first.get('letter', '')}” cluster: {', '.join(first.get('words', [])[:5])}."
    return "Sound is mostly end-loaded; add one mid-bar echo so the line feels less flat before the final word."


def _content_sentence(detail: Dict[str, Any]) -> str:
    motifs = detail.get("motif_hits") or {}
    images = detail.get("image_words") or []
    abstract = detail.get("abstract_words") or []
    if motifs and images:
        return f"Strong corpus DNA: {', '.join(list(motifs.keys())[:2])}; visible objects already present: {', '.join(images[:4])}."
    if motifs:
        return f"Corpus DNA is present through {', '.join(list(motifs.keys())[:2])}; add one visible object to make the idea easier to picture."
    if abstract:
        return f"Concept-heavy line: {', '.join(abstract[:4])}; convert one abstraction into a scene/object."
    return "Content is readable, but it could use a sharper signature motif or more concrete scenery."


def _rhyme_instruction(detail: Dict[str, Any], fix: Dict[str, Any]) -> str:
    end_word = detail.get("end_word") or "the end word"
    key = detail.get("rhyme_key") or "—"
    banks = fix.get("word_banks") or {}
    options = banks.get("end_rhymes") or banks.get("near_rhymes") or []
    if options:
        return f"Current landing is “{end_word}” / {key}. Try ending on {', '.join(options[:5])} to stay inside a corpus rhyme family."
    return f"Current landing is “{end_word}” / {key}. Keep the rhyme family, but move a harder noun or concept into the final slot."


def _static_action_steps(fix: Dict[str, Any], detail: Dict[str, Any], beat_plan: Dict[str, Any] | None) -> List[str]:
    steps: List[str] = []
    operation = fix.get("operation") or "polish_punch"
    if operation == "split_line":
        steps.append("Split this into two lines or two bars; make each half land on its own final word.")
    elif operation == "compress_line":
        steps.append("Cut two or three connective words first, then re-check whether the main image still lands.")
    elif operation == "swap_end_rhyme":
        steps.append("Keep the setup but replace the final word with a stronger corpus rhyme option.")
    elif operation == "add_internal_echo":
        steps.append("Place one echo word before the comma/turn so the middle of the bar has motion.")
    elif operation == "add_image":
        steps.append("Replace an abstract phrase with a concrete object from the word bank.")
    else:
        steps.append("Keep the line shape and make one punch-word upgrade.")

    for move in fix.get("specific_moves", [])[:3]:
        if move not in steps:
            steps.append(str(move))
    banks = fix.get("word_banks") or {}
    if banks.get("cut_words"):
        steps.append(f"First trim candidates: {', '.join(banks['cut_words'][:6])}.")
    if beat_plan and beat_plan.get("bar_structure_options"):
        steps.append(str(beat_plan["bar_structure_options"][0]))
    return unique_preserve(steps, 6)


def _bar_structure_note(fix: Dict[str, Any], beat_plan: Dict[str, Any] | None) -> Dict[str, Any]:
    if not beat_plan:
        return {
            "available": False,
            "note": "No beat uploaded; using corpus cadence only. Upload a beat to get exact bar windows.",
            "options": ["One-line = one-bar default", "Long line = split at the cleanest clause", "Short line = leave breath or add pickup"],
        }
    density = beat_plan.get("density_label") or "balanced"
    span = _safe_int(beat_plan.get("bar_span"), 1)
    if span > 1:
        note = f"Assign this as a {span}-bar thought over bars {beat_plan.get('assigned_bars')}; split near word {beat_plan.get('split_after_word')} and give the second half the harder landing."
    elif str(density).lower() == "very dense":
        note = f"One-bar fit is possible but crowded on bars {beat_plan.get('assigned_bars')}; compress before performing double-time."
    elif str(density).lower() == "open":
        note = f"Line is open on bars {beat_plan.get('assigned_bars')}; stretch the vowel, add a pickup, or leave a breath before the next line."
    else:
        note = f"Line fits as one bar on bars {beat_plan.get('assigned_bars')}; protect the final-quarter landing near {beat_plan.get('landing_time')}."
    return {
        "available": True,
        "assigned_bars": beat_plan.get("assigned_bars"),
        "time_window": beat_plan.get("time_window"),
        "landing_time": beat_plan.get("landing_time"),
        "density": density,
        "syllables_per_beat": beat_plan.get("syllables_per_beat"),
        "target_syllables_per_bar": beat_plan.get("target_syllables_per_bar"),
        "note": note,
        "options": beat_plan.get("bar_structure_options", [])[:4],
        "split_preview": beat_plan.get("split_preview") or {},
    }


def _static_overview(analysis: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    severe = [row for row in rows if row.get("suggestion", {}).get("priority") in {"critical", "high"}]
    split = [row for row in rows if row.get("suggestion", {}).get("operation") == "split_line"]
    compression = [row for row in rows if row.get("suggestion", {}).get("operation") == "compress_line"]
    end_swap = [row for row in rows if row.get("suggestion", {}).get("operation") == "swap_end_rhyme"]
    actions: List[str] = []
    if split:
        actions.append(f"Static first pass: split lines {', '.join(str(r['line_number']) for r in split[:8])} before changing vocabulary.")
    if compression:
        actions.append(f"Compression pass: tighten lines {', '.join(str(r['line_number']) for r in compression[:8])} by cutting filler/connectors.")
    if end_swap:
        actions.append(f"Rhyme pass: rotate weak/repeated endings on lines {', '.join(str(r['line_number']) for r in end_swap[:8])}.")
    if not actions:
        actions.append("Static first pass: no major structural overload detected; polish images, internal echoes, and end-word weight.")
    beat_alignment = analysis.get("beat_alignment", {}) or {}
    if beat_alignment.get("available"):
        actions.append(str(beat_alignment.get("fit_status") or "Beat guidance is active for the static report."))
    return {
        "headline": f"{len(rows)} editable lines analyzed; {len(severe)} high-priority line(s) need attention.",
        "actions": unique_preserve(actions, 5),
        "counts": {
            "critical_or_high": len(severe),
            "split_lines": len(split),
            "compress_lines": len(compression),
            "end_rhyme_swaps": len(end_swap),
        },
    }



# ---------------------------------------------------------------------------
# Information-theoretic snapshot metrics
# ---------------------------------------------------------------------------

def _entropy_stats(counter: Counter) -> Dict[str, Any]:
    """Return Shannon-style summary stats for a discrete distribution."""
    clean = Counter({str(k): int(v) for k, v in counter.items() if int(v) > 0 and str(k)})
    total = sum(clean.values())
    unique = len(clean)
    if total <= 0 or unique == 0:
        return {
            "total": 0,
            "unique": 0,
            "entropy_bits": 0.0,
            "max_entropy_bits": 0.0,
            "normalized_entropy": 0,
            "perplexity": 0.0,
            "concentration": 0.0,
            "top": [],
        }
    entropy = 0.0
    concentration = 0.0
    for count in clean.values():
        p = count / total
        entropy -= p * math.log2(p)
        concentration += p * p
    max_entropy = math.log2(unique) if unique > 1 else 0.0
    rows = []
    for key, count in clean.most_common(18):
        p = count / total
        rows.append({
            "key": key,
            "count": count,
            "pct": _round(p * 100, 1),
            "self_information_bits": _round(-math.log2(p), 2) if p > 0 else 0.0,
        })
    return {
        "total": total,
        "unique": unique,
        "entropy_bits": _round(entropy, 3),
        "max_entropy_bits": _round(max_entropy, 3),
        "normalized_entropy": int(round((entropy / max_entropy) * 100)) if max_entropy else 0,
        "perplexity": _round(2 ** entropy, 2),
        "concentration": _round(concentration, 3),
        "top": rows,
    }


def _syllable_bin(value: Any) -> str:
    syllables = _safe_int(value, 0)
    if syllables <= 6:
        return "micro 0-6"
    if syllables <= 10:
        return "short 7-10"
    if syllables <= 14:
        return "pocket 11-14"
    if syllables <= 18:
        return "long 15-18"
    return "extended 19+"


def _word_count_bin(value: Any) -> str:
    words = _safe_int(value, 0)
    if words <= 4:
        return "micro 0-4"
    if words <= 8:
        return "short 5-8"
    if words <= 12:
        return "standard 9-12"
    if words <= 16:
        return "dense 13-16"
    return "packed 17+"


def _density_bin(value: Any) -> str:
    density = float(value or 0)
    if density <= 2.2:
        return "open 0-2.2"
    if density <= 3.4:
        return "balanced 2.3-3.4"
    if density <= 4.6:
        return "dense 3.5-4.6"
    return "very dense 4.7+"


def _line_information_map(analysis: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    """Compute per-line self-information using the draft distribution.

    This is not a language-model probability. It is a local entropy view: common
    draft words carry fewer bits; rare content words and rare rhyme landings carry
    more bits. That makes it useful for finding lines that are either too generic
    or unusually dense.
    """
    details = analysis.get("raw_line_details", []) or []
    all_content = [word for detail in details for word in (detail.get("content_words") or [])]
    all_words = [word for detail in details for word in (detail.get("words") or [])]
    word_counts = Counter(all_content or all_words)
    total = sum(word_counts.values())
    vocab = max(1, len(word_counts))
    rhyme_counts = Counter(detail.get("rhyme_key") for detail in details if detail.get("rhyme_key"))
    total_rhymes = sum(rhyme_counts.values())
    out: Dict[int, Dict[str, Any]] = {}
    for detail in details:
        line_no = _safe_int(detail.get("number"), 0)
        tokens = detail.get("content_words") or detail.get("words") or []
        bits = 0.0
        rarest: List[Dict[str, Any]] = []
        for word in tokens:
            p = (word_counts.get(word, 0) + 1) / max(1, total + vocab)
            word_bits = -math.log2(p)
            bits += word_bits
            rarest.append({"word": word, "bits": _round(word_bits, 2)})
        rarest.sort(key=lambda row: (-row["bits"], row["word"]))
        rhyme_key_value = detail.get("rhyme_key") or ""
        if rhyme_key_value and total_rhymes:
            rhyme_p = rhyme_counts[rhyme_key_value] / total_rhymes
            rhyme_surprise = -math.log2(rhyme_p)
        else:
            rhyme_p = 0.0
            rhyme_surprise = 0.0
        syllables = _safe_int(detail.get("syllables"), 0)
        word_count = _safe_int(detail.get("word_count"), 0)
        out[line_no] = {
            "line_self_information_bits": _round(bits, 2),
            "bits_per_word": _round(bits / max(1, len(tokens)), 2),
            "bits_per_syllable": _round(bits / max(1, syllables), 2),
            "rhyme_surprise_bits": _round(rhyme_surprise, 2),
            "rhyme_probability_pct": _round(rhyme_p * 100, 1),
            "syllable_bin": _syllable_bin(syllables),
            "word_count_bin": _word_count_bin(word_count),
            "rarest_words": rarest[:6],
            "interpretation": _line_information_sentence(bits, len(tokens), syllables, rhyme_surprise),
        }
    return out


def _line_information_sentence(bits: float, token_count: int, syllables: int, rhyme_surprise: float) -> str:
    bits_per_word = bits / max(1, token_count)
    if bits_per_word >= 4.8 and syllables >= 16:
        base = "High information density: rare words are stacked inside a long bar, so delivery clarity matters."
    elif bits_per_word >= 4.8:
        base = "High lexical surprise: the words are distinctive; protect the meaning while tightening cadence."
    elif bits_per_word <= 3.1:
        base = "Low lexical surprise: the wording is familiar in this draft; upgrade one noun, verb, or image."
    else:
        base = "Moderate information density: the line should be readable if the rhyme landing is clear."
    if rhyme_surprise >= 3.0:
        return base + " The end rhyme is rare for this draft, so it can create a useful turn."
    if rhyme_surprise and rhyme_surprise <= 1.4:
        return base + " The end rhyme is heavily reused, so consider rotating the landing word."
    return base


def _section_entropy_rows(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    details_by_number = {int(row.get("number", 0)): row for row in analysis.get("raw_line_details", []) or []}
    rows: List[Dict[str, Any]] = []
    for section in analysis.get("sections", []) or []:
        line_numbers = [_safe_int(row.get("number"), 0) for row in section.get("lines", []) or []]
        section_details = [details_by_number[n] for n in line_numbers if n in details_by_number]
        if not section_details:
            continue
        words = [word for row in section_details for word in (row.get("content_words") or row.get("words") or [])]
        rhymes = [row.get("rhyme_key") for row in section_details if row.get("rhyme_key")]
        syllable_bins = Counter(_syllable_bin(row.get("syllables")) for row in section_details)
        word_entropy = _entropy_stats(Counter(words))
        rhyme_entropy = _entropy_stats(Counter(rhymes))
        syll_entropy = _entropy_stats(syllable_bins)
        rows.append({
            "label": section.get("label") or "Section",
            "type": section.get("type") or "section",
            "start_line": section.get("start_line"),
            "end_line": section.get("end_line"),
            "line_count": len(section_details),
            "word_count": sum(_safe_int(row.get("word_count"), 0) for row in section_details),
            "avg_syllables": _round(sum(_safe_int(row.get("syllables"), 0) for row in section_details) / max(1, len(section_details)), 1),
            "lexical_entropy_bits": word_entropy["entropy_bits"],
            "lexical_perplexity": word_entropy["perplexity"],
            "rhyme_entropy_bits": rhyme_entropy["entropy_bits"],
            "rhyme_perplexity": rhyme_entropy["perplexity"],
            "cadence_entropy_bits": syll_entropy["entropy_bits"],
            "dominant_rhyme": rhyme_entropy["top"][0]["key"] if rhyme_entropy["top"] else "—",
            "notes": _section_entropy_sentence(section.get("type"), word_entropy, rhyme_entropy, syll_entropy),
        })
    return rows


def _section_entropy_sentence(section_type: Any, word_entropy: Dict[str, Any], rhyme_entropy: Dict[str, Any], syll_entropy: Dict[str, Any]) -> str:
    section_type = str(section_type or "section").lower()
    parts: List[str] = []
    if rhyme_entropy.get("normalized_entropy", 0) <= 35 and rhyme_entropy.get("unique", 0) > 1:
        parts.append("rhyme is concentrated, good for hook memory")
    elif rhyme_entropy.get("normalized_entropy", 0) >= 75:
        parts.append("rhyme is diverse, good for verse movement")
    else:
        parts.append("rhyme variety is moderate")
    if syll_entropy.get("normalized_entropy", 0) >= 70:
        parts.append("cadence lengths vary heavily")
    elif syll_entropy.get("unique", 0) <= 1:
        parts.append("cadence length is very uniform")
    else:
        parts.append("cadence has controlled variation")
    if section_type in {"chorus", "hook", "refrain"} and rhyme_entropy.get("normalized_entropy", 100) > 60:
        parts.append("consider a tighter repeated ending for chantability")
    return "; ".join(parts) + "."


def _bar_theory(analysis: Dict[str, Any]) -> Dict[str, Any]:
    details = analysis.get("raw_line_details", []) or []
    alignment = analysis.get("beat_alignment", {}) or {}
    per_line = alignment.get("per_line", []) or [] if alignment.get("available") else []
    rows: List[Dict[str, Any]] = []
    if per_line:
        for row in per_line:
            span = max(1, _safe_int(row.get("bar_span"), 1))
            syllables = _safe_int(row.get("syllables"), 0)
            spb = syllables / span
            rows.append({
                "line_number": _safe_int(row.get("line_number"), 0),
                "syllables": syllables,
                "bar_span": span,
                "assigned_bars": row.get("assigned_bars"),
                "density_label": row.get("density_label") or _density_bin(syllables / 4),
                "syllables_per_bar": _round(spb, 2),
                "syllables_per_beat": _round(row.get("syllables_per_beat") or (spb / 4), 2),
                "time_window": row.get("time_window") or "",
            })
        available = True
        assumption = "Uploaded beat grid: bars and time windows come from the detected rap BPM."
    else:
        for detail in details:
            syllables = _safe_int(detail.get("syllables"), 0)
            rows.append({
                "line_number": _safe_int(detail.get("number"), 0),
                "syllables": syllables,
                "bar_span": 1,
                "assigned_bars": str(detail.get("number", "")),
                "density_label": _density_bin(syllables / 4),
                "syllables_per_bar": syllables,
                "syllables_per_beat": _round(syllables / 4, 2),
                "time_window": "implied one-line bar",
            })
        available = False
        assumption = "No beat uploaded: the snapshot treats each lyric line as one implied bar."
    bar_load_bins = Counter(_syllable_bin(row["syllables_per_bar"]) for row in rows)
    density_counter = Counter(row["density_label"] for row in rows)
    span_counter = Counter(str(row["bar_span"]) for row in rows)
    load_entropy = _entropy_stats(bar_load_bins)
    density_entropy = _entropy_stats(density_counter)
    span_entropy = _entropy_stats(span_counter)
    overloaded = [row for row in rows if row["density_label"] in {"very dense", "dense 3.5-4.6"} or row["syllables_per_beat"] > 4.6]
    open_rows = [row for row in rows if row["syllables_per_beat"] <= 2.2]
    return {
        "beat_available": available,
        "assumption": assumption,
        "implied_or_detected_bars": len(rows),
        "estimated_needed_bars": alignment.get("bars_needed_by_lyrics") if alignment.get("available") else len(rows),
        "bar_load_entropy_bits": load_entropy["entropy_bits"],
        "bar_load_normalized_entropy": load_entropy["normalized_entropy"],
        "bar_load_perplexity": load_entropy["perplexity"],
        "density_entropy_bits": density_entropy["entropy_bits"],
        "span_entropy_bits": span_entropy["entropy_bits"],
        "density_distribution": density_entropy["top"],
        "span_distribution": span_entropy["top"],
        "overloaded_lines": overloaded[:12],
        "open_lines": open_rows[:12],
        "line_bar_table": rows[:80],
        "interpretation": _bar_theory_sentence(available, load_entropy, overloaded, open_rows, alignment),
    }


def _bar_theory_sentence(available: bool, load_entropy: Dict[str, Any], overloaded: Sequence[Dict[str, Any]], open_rows: Sequence[Dict[str, Any]], alignment: Dict[str, Any]) -> str:
    if available and alignment.get("fit_status"):
        lead = str(alignment.get("fit_status"))
    elif available:
        lead = "Beat-aware bar grid is active."
    else:
        lead = "This is an implied bar map until a beat is uploaded."
    if load_entropy.get("normalized_entropy", 0) >= 70:
        lead += " Bar density varies a lot, so the performance will need deliberate pauses and speed changes."
    elif load_entropy.get("unique", 0) <= 1:
        lead += " Bar density is extremely uniform; add one short rest or double-time pocket for contrast."
    else:
        lead += " Bar density has usable variation."
    if overloaded:
        lead += f" First structural priority: split or compress lines {', '.join(str(r['line_number']) for r in overloaded[:6])}."
    elif open_rows:
        lead += f" Open-space priority: lines {', '.join(str(r['line_number']) for r in open_rows[:6])} can take pickups, adlibs, or breath."
    return lead


def _information_theory_report(analysis: Dict[str, Any], rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    details = analysis.get("raw_line_details", []) or []
    all_words = [word for detail in details for word in (detail.get("words") or [])]
    all_content = [word for detail in details for word in (detail.get("content_words") or [])]
    rhyme_keys = [detail.get("rhyme_key") for detail in details if detail.get("rhyme_key")]
    end_words = [detail.get("end_word") for detail in details if detail.get("end_word")]
    syllables = [_safe_int(detail.get("syllables"), 0) for detail in details]
    word_counts = [_safe_int(detail.get("word_count"), 0) for detail in details]
    token_entropy = _entropy_stats(Counter(all_content or all_words))
    rhyme_entropy = _entropy_stats(Counter(rhyme_keys))
    end_word_entropy = _entropy_stats(Counter(end_words))
    syllable_entropy = _entropy_stats(Counter(_syllable_bin(v) for v in syllables))
    word_count_entropy = _entropy_stats(Counter(_word_count_bin(v) for v in word_counts))
    transitions = [f"{a}→{b}" for a, b in zip(rhyme_keys, rhyme_keys[1:])]
    transition_entropy = _entropy_stats(Counter(transitions))
    section_rows = _section_entropy_rows(analysis)
    section_length_entropy = _entropy_stats(Counter(_word_count_bin(row["line_count"]) for row in section_rows))
    bar_stats = _bar_theory(analysis)
    line_info_rows = []
    for row in rows:
        info = row.get("information") or {}
        line_info_rows.append({
            "line_number": row.get("line_number"),
            "text": row.get("text"),
            "section": row.get("section", {}).get("label"),
            "line_self_information_bits": info.get("line_self_information_bits", 0),
            "bits_per_word": info.get("bits_per_word", 0),
            "bits_per_syllable": info.get("bits_per_syllable", 0),
            "rhyme_surprise_bits": info.get("rhyme_surprise_bits", 0),
            "interpretation": info.get("interpretation", ""),
        })
    line_info_rows.sort(key=lambda row: (-float(row.get("line_self_information_bits") or 0), int(row.get("line_number") or 0)))
    predictable = sorted(line_info_rows, key=lambda row: (float(row.get("line_self_information_bits") or 0), int(row.get("line_number") or 0)))
    repeated_lines = Counter((row.get("text") or "").strip().lower() for row in rows if (row.get("text") or "").strip())
    repeated_line_count = sum(count - 1 for count in repeated_lines.values() if count > 1)
    compression_ratio = _round(len(all_words) / max(1, len(set(all_words))), 2)
    rhyme_reuse_ratio = _round((len(rhyme_keys) - len(set(rhyme_keys))) / max(1, len(rhyme_keys)) * 100, 1)
    overview = {
        "token_entropy_bits": token_entropy["entropy_bits"],
        "token_perplexity": token_entropy["perplexity"],
        "rhyme_entropy_bits": rhyme_entropy["entropy_bits"],
        "rhyme_perplexity": rhyme_entropy["perplexity"],
        "line_length_entropy_bits": syllable_entropy["entropy_bits"],
        "bar_load_entropy_bits": bar_stats["bar_load_entropy_bits"],
        "verse_section_entropy_bits": section_length_entropy["entropy_bits"],
        "avg_line_self_information_bits": _round(sum(float(row.get("line_self_information_bits") or 0) for row in line_info_rows) / max(1, len(line_info_rows)), 2),
        "compression_ratio": compression_ratio,
        "rhyme_reuse_ratio_pct": rhyme_reuse_ratio,
        "repeated_line_count": repeated_line_count,
    }
    interpretations = _information_interpretations(overview, rhyme_entropy, syllable_entropy, bar_stats, section_rows)
    top_families = []
    for top in rhyme_entropy["top"][:12]:
        key = top["key"]
        words_for_key = unique_preserve([detail.get("end_word") for detail in details if detail.get("rhyme_key") == key], 10)
        top_families.append({**top, "end_words": words_for_key})
    return {
        "overview": overview,
        "interpretations": interpretations,
        "rhymes": {
            "rhyme_key_entropy_bits": rhyme_entropy["entropy_bits"],
            "rhyme_key_normalized_entropy": rhyme_entropy["normalized_entropy"],
            "rhyme_key_perplexity": rhyme_entropy["perplexity"],
            "rhyme_concentration": rhyme_entropy["concentration"],
            "rhyme_reuse_ratio_pct": rhyme_reuse_ratio,
            "unique_rhyme_families": rhyme_entropy["unique"],
            "end_word_entropy_bits": end_word_entropy["entropy_bits"],
            "end_word_perplexity": end_word_entropy["perplexity"],
            "transition_entropy_bits": transition_entropy["entropy_bits"],
            "transition_perplexity": transition_entropy["perplexity"],
            "top_families": top_families,
            "top_transitions": transition_entropy["top"][:12],
        },
        "lines": {
            "lexical_entropy_bits": token_entropy["entropy_bits"],
            "lexical_normalized_entropy": token_entropy["normalized_entropy"],
            "lexical_perplexity": token_entropy["perplexity"],
            "syllable_entropy_bits": syllable_entropy["entropy_bits"],
            "syllable_perplexity": syllable_entropy["perplexity"],
            "word_count_entropy_bits": word_count_entropy["entropy_bits"],
            "word_count_perplexity": word_count_entropy["perplexity"],
            "avg_syllables": _round(sum(syllables) / max(1, len(syllables)), 1),
            "avg_words": _round(sum(word_counts) / max(1, len(word_counts)), 1),
            "most_informative_lines": line_info_rows[:12],
            "least_informative_lines": predictable[:8],
            "syllable_distribution": syllable_entropy["top"],
            "word_count_distribution": word_count_entropy["top"],
        },
        "bars": bar_stats,
        "verses": {
            "section_count": len(section_rows),
            "verse_count": len([row for row in section_rows if str(row.get("type", "")).lower() == "verse"]),
            "hook_count": len([row for row in section_rows if str(row.get("type", "")).lower() in {"hook", "chorus", "refrain"}]),
            "section_length_entropy_bits": section_length_entropy["entropy_bits"],
            "section_length_perplexity": section_length_entropy["perplexity"],
            "section_rows": section_rows,
        },
    }


def _information_interpretations(
    overview: Dict[str, Any],
    rhyme_entropy: Dict[str, Any],
    syllable_entropy: Dict[str, Any],
    bar_stats: Dict[str, Any],
    section_rows: Sequence[Dict[str, Any]],
) -> List[str]:
    notes: List[str] = []
    rhyme_norm = int(rhyme_entropy.get("normalized_entropy", 0))
    if rhyme_norm >= 75:
        notes.append("Rhyme entropy is high: the draft moves through many rhyme families, which helps verse complexity but can weaken hook memorability.")
    elif rhyme_norm <= 35 and rhyme_entropy.get("unique", 0) > 1:
        notes.append("Rhyme entropy is low: the draft concentrates on a few families, which is good for motif identity but risks repetitive landings.")
    else:
        notes.append("Rhyme entropy is balanced: there is enough reuse for identity and enough variety for movement.")
    if syllable_entropy.get("normalized_entropy", 0) >= 70:
        notes.append("Line-length entropy is high: bar lengths vary sharply, so the performance should mark rests, pickups, and double-time pockets deliberately.")
    else:
        notes.append("Line-length entropy is controlled: the draft has a recognizable cadence shape.")
    notes.append(bar_stats.get("interpretation") or "Bar entropy is available in the bar-structure panel.")
    if overview.get("compression_ratio", 0) >= 3.0:
        notes.append("Lexical compression is high: many words repeat, so small swaps can noticeably increase freshness without changing the whole verse.")
    else:
        notes.append("Lexical compression is moderate: the vocabulary is not overly repetitive for the current draft length.")
    verse_rows = [row for row in section_rows if str(row.get("type", "")).lower() == "verse"]
    if verse_rows:
        highest = max(verse_rows, key=lambda row: float(row.get("lexical_entropy_bits") or 0))
        notes.append(f"Most lexically complex verse section: {highest.get('label')} at {highest.get('lexical_entropy_bits')} bits.")
    return unique_preserve(notes, 6)

def build_static_line_breakdown(
    lyrics: str,
    mode: str = "match",
    beat: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a stable line-by-line report for the current draft.

    Unlike the live editor queue, this endpoint is deliberately synchronous and
    snapshot-based. The browser can generate it on demand, copy it, and compare
    it against later drafts without the report changing while the user types.
    """
    mode = mode if mode in MODE_LABELS else "match"
    analysis = analyze_lyrics(lyrics, mode)
    if beat:
        analysis = attach_beat_guidance(analysis, beat)
    else:
        analysis["beat_analysis"] = {"available": False}
        analysis["beat_alignment"] = {"available": False, "summary": "Upload a beat to add static bar windows."}

    comparison_report = build_comparison_report(lyrics, analysis)
    meter_report = analyze_meter_text(lyrics, beat=beat)
    physics_report = build_scansion_physics_report(lyrics, mode=mode, beat=beat, analysis=analysis, meter_report=meter_report)
    rhyme_lab = build_rhyme_suggestion_lab(lyrics, mode=mode)
    score_report = build_rap_score_report(lyrics, mode=mode, beat=beat)
    score_by_line = {int(row.get("line_number", -1)): row for row in score_report.get("bar_scores", [])}
    physics_by_line = {int(row.get("line_number", -1)): row for row in physics_report.get("line_physics", [])}
    meter_by_line = {int(row.get("line_number", -1)): row.get("meter", {}) for row in meter_report.get("line_details", [])}

    cards = _line_lookup(analysis)
    details = _detail_lookup(analysis)
    beats = _beat_lookup(analysis)
    sections = _section_line_lookup(analysis)
    information_by_line = _line_information_map(analysis)
    highlight_report = _rhyme_highlight_report(analysis)
    highlight_by_line = highlight_report.get("line_map", {})
    rows: List[Dict[str, Any]] = []
    for line_no in sorted(cards):
        detail = details.get(line_no, {})
        beat_plan = beats.get(line_no)
        fix = _fix_card(cards[line_no], detail, beat_plan, active=False)
        section = sections.get(line_no, {"label": "Section", "type": "section", "position": 1, "line_count": 1})
        target = beat_plan.get("target_syllables_per_bar") if beat_plan else fix.get("metrics", {}).get("target_syllables")
        role = _line_function(section.get("type", "section"), _safe_int(section.get("position"), 1), _safe_int(section.get("line_count"), 1), detail)
        comparison_guidance = line_comparison_guidance(detail, comparison_report)
        rows.append({
            "line_number": line_no,
            "section": section,
            "role": role,
            "text": fix.get("text", ""),
            "metrics": {
                "words": detail.get("word_count", 0),
                "syllables": detail.get("syllables", 0),
                "target": target,
                "end_word": detail.get("end_word", ""),
                "rhyme_key": detail.get("rhyme_key", ""),
                "internal_rhyme_groups": len(detail.get("internal_rhymes", []) or []),
                "alliteration_groups": len(detail.get("alliteration", []) or []),
                "motif_count": len(detail.get("motif_hits", {}) or {}),
                "image_count": len(detail.get("image_words", []) or []),
                "abstract_count": len(detail.get("abstract_words", []) or []),
            },
            "information": information_by_line.get(line_no, {}),
            "meter": meter_by_line.get(line_no, analyze_sentence_meter(fix.get("text", ""), beat=beat, target_syllables=target if isinstance(target, (list, tuple)) else None)),
            "physics": physics_by_line.get(line_no, {}),
            "breakdown": {
                "line_function": role,
                "cadence": _cadence_sentence(_safe_int(detail.get("syllables")), target or 12),
                "sound": _sound_sentence(detail),
                "content": _content_sentence(detail),
                "rhyme": _rhyme_instruction(detail, fix),
                "bar_structure": _bar_structure_note(fix, beat_plan),
            },
            "comparison_guidance": comparison_guidance,
            "suggestion": {
                "priority": fix.get("priority"),
                "severity": fix.get("severity"),
                "operation": fix.get("operation"),
                "operation_label": fix.get("operation_label"),
                "diagnosis": fix.get("diagnosis"),
                "primary_fix": _operation_label(fix.get("operation", "polish_punch")),
                "action_steps": _static_action_steps(fix, detail, beat_plan),
                "checklist": [
                    "Does the final word carry meaning and rhyme?",
                    "Is there at least one internal sound echo?" if _safe_int(detail.get("word_count")) >= 8 else "Does the short line leave useful breath?",
                    "Can the listener picture one object or action?",
                    "Can this fit the assigned bar without rushing?" if beat_plan else "Would this fit a one-bar pocket when performed aloud?",
                ],
            },
            "possible_words": fix.get("word_banks", {}),
            "advanced_rhyme": fix.get("advanced_rhyme", {}),
            "rewrite_options": fix.get("rewrite_variants", []),
            "applyable_patches": fix.get("patches", []),
            "nearby_corpus_lines": fix.get("nearby_corpus_lines", []),
            "sound_hits": fix.get("sound_hits", {}),
            "motif_hits": fix.get("motif_hits", {}),
            "rhyme_highlight": highlight_by_line.get(line_no, {}),
            "bar_score": score_by_line.get(line_no, {}),
        })

    profile = get_corpus_profile()
    return {
        "available": True,
        "report_type": "static_line_breakdown",
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "summary": {
            "lines": analysis.get("stats", {}).get("lines", 0),
            "words": analysis.get("stats", {}).get("words", 0),
            "avg_syllables": analysis.get("stats", {}).get("avg_syllables", 0),
            "median_syllables": analysis.get("stats", {}).get("median_syllables", 0),
            "style_match": analysis.get("stats", {}).get("style_match", 0),
            "rhyme_density": analysis.get("stats", {}).get("rhyme_density", 0),
        },
        "overview": _static_overview(analysis, rows),
        "information_theory": _information_theory_report(analysis, rows),
        "meter_report": meter_report,
        "physics_report": physics_report,
        "score_report": score_report,
        "sections": analysis.get("sections", []),
        "line_breakdown": rows,
        "beat_analysis": analysis.get("beat_analysis", {}),
        "beat_alignment": analysis.get("beat_alignment", {}),
        "rhyme_scheme": analysis.get("rhyme_scheme", {}),
        "rhyme_highlights": highlight_report,
        "rhyme_lab": rhyme_lab,
        "comparison": comparison_report,
        "title_candidates": analysis.get("title_candidates", [])[:8],
        "corpus_reference": {
            "stats": profile.get("stats", {}),
            "signature_words": profile.get("signature_words", [])[:24],
            "top_rhymes": profile.get("top_rhymes", [])[:12],
            "motif_clusters": profile.get("motif_clusters", [])[:6],
        },
    }


# ---------------------------------------------------------------------------
# Synchronous one-sentence lab
# ---------------------------------------------------------------------------

SENTENCE_DELIMITER_RE = re.compile(r"([.!?;:]+|—|--)")


def _clean_sentence_text(value: Any) -> str:
    """Normalize a one-sentence input without destroying rap punctuation."""
    text = str(value or "").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _sentence_clauses(sentence: str) -> List[Dict[str, Any]]:
    """Break a sentence into breath/clause units for bar-structure advice."""
    raw_parts = re.split(r"\s*(?:,|;|:|—|--|\(|\)|\band\b|\bbut\b|\bthen\b)\s*", sentence, flags=re.I)
    parts = [part.strip(" ,;:—-()") for part in raw_parts if tokenize(part)]
    if not parts and sentence:
        parts = [sentence]
    rows = []
    for idx, part in enumerate(parts, start=1):
        words = tokenize(part)
        rows.append({
            "index": idx,
            "text": part,
            "words": len(words),
            "syllables": line_syllables(part),
            "end_word": words[-1] if words else "",
            "rhyme_key": rhyme_key(words[-1]) if words else "",
        })
    return rows


def _split_after_word_for_sentence(sentence: str, target_syllables: int | float | Sequence[int] | None = None) -> Dict[str, Any]:
    """Find a practical sentence split close to half the syllable load."""
    words = re.findall(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|[^A-Za-z0-9]+", sentence)
    word_tokens = [token for token in words if tokenize(token)]
    if len(word_tokens) < 7:
        return {"available": False, "reason": "Sentence is short enough to keep as one unit."}

    syll_by_word = [line_syllables(word) for word in word_tokens]
    total = sum(syll_by_word)
    if isinstance(target_syllables, (list, tuple)) and target_syllables:
        desired = int(round(float(target_syllables[-1])))
    elif target_syllables:
        desired = int(round(float(target_syllables)))
    else:
        desired = max(1, total // 2)
    # Split near half unless a beat/corpus target creates a more natural one-bar first half.
    half = max(1, min(total - 1, total / 2))
    desired = max(1, min(total - 1, desired))
    target = min(half, desired) if total > desired + 4 else half
    running = 0
    best_index = 0
    best_score = 9999.0
    for idx, syllables in enumerate(syll_by_word, start=1):
        running += syllables
        if idx >= len(word_tokens):
            break
        # Prefer split points near punctuation already in the raw sentence.
        prefix_word_count = idx
        prefix_words = " ".join(word_tokens[:prefix_word_count])
        prefix_end_pos = sentence.lower().find(prefix_words.lower())
        punctuation_bonus = 0.0
        if prefix_end_pos >= 0:
            tail = sentence[prefix_end_pos + len(prefix_words): prefix_end_pos + len(prefix_words) + 4]
            if re.search(r"[,;:—-]", tail):
                punctuation_bonus = 1.5
        score = abs(running - target) - punctuation_bonus
        if score < best_score:
            best_score = score
            best_index = idx
    if best_index <= 0:
        best_index = max(1, len(word_tokens) // 2)
    first = " ".join(word_tokens[:best_index])
    second = " ".join(word_tokens[best_index:])
    return {
        "available": True,
        "split_after_word": best_index,
        "first_half": first,
        "second_half": second,
        "formatted_split": f"{first}\n{second}",
        "first_half_syllables": line_syllables(first),
        "second_half_syllables": line_syllables(second),
        "reason": "Split point chosen near the syllable midpoint, with punctuation/clause boundaries preferred when available.",
    }


def _corpus_information_for_sentence(detail: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    """Corpus-relative information estimate for a single sentence.

    This uses the compiled private corpus profile rather than the one-sentence
    local distribution, so it remains useful for short synchronous inputs.
    """
    signature_counts = Counter({row.get("word", ""): int(row.get("count", 0)) for row in profile.get("signature_words", []) if row.get("word")})
    total = sum(signature_counts.values())
    vocab = max(1, len(profile.get("corpus_words_set", []) or signature_counts))
    tokens = detail.get("content_words") or detail.get("words") or []
    rows: List[Dict[str, Any]] = []
    total_bits = 0.0
    in_signature = 0
    in_corpus = 0
    corpus_set = set(profile.get("corpus_words_set", []) or [])
    for word in tokens:
        count = signature_counts.get(word, 0)
        if count:
            in_signature += 1
        if word in corpus_set:
            in_corpus += 1
        p = (count + 1) / max(1, total + vocab)
        bits = -math.log2(p)
        total_bits += bits
        rows.append({
            "word": word,
            "count_in_signature_profile": count,
            "self_information_bits": _round(bits, 2),
            "in_corpus_profile": word in corpus_set,
        })
    rows.sort(key=lambda row: (-row["self_information_bits"], row["word"]))
    end = detail.get("end_word") or ""
    end_key = detail.get("rhyme_key") or ""
    rhyme_counts = Counter({row.get("key", ""): int(row.get("count", 0)) for row in profile.get("top_rhymes", []) if row.get("key")})
    rhyme_total = sum(rhyme_counts.values())
    rhyme_vocab = max(1, len(rhyme_counts))
    rhyme_p = (rhyme_counts.get(end_key, 0) + 1) / max(1, rhyme_total + rhyme_vocab)
    return {
        "basis": "compiled_corpus_profile",
        "content_tokens": len(tokens),
        "profile_overlap_pct": _round((in_corpus / max(1, len(tokens))) * 100, 1),
        "signature_overlap_pct": _round((in_signature / max(1, len(tokens))) * 100, 1),
        "sentence_self_information_bits": _round(total_bits, 2),
        "bits_per_content_word": _round(total_bits / max(1, len(tokens)), 2),
        "rarest_words": rows[:8],
        "end_word": end,
        "rhyme_key": end_key,
        "rhyme_surprise_bits_vs_corpus": _round(-math.log2(rhyme_p), 2),
        "interpretation": _sentence_information_interpretation(total_bits / max(1, len(tokens)), in_corpus / max(1, len(tokens)), -math.log2(rhyme_p)),
    }


def _sentence_information_interpretation(bits_per_word: float, corpus_overlap: float, rhyme_bits: float) -> str:
    if bits_per_word >= 7.0 and corpus_overlap < 0.25:
        base = "High novelty against your corpus: the sentence introduces uncommon words, so make the meaning extra clear."
    elif bits_per_word <= 5.0 and corpus_overlap >= 0.55:
        base = "High corpus familiarity: the sentence sits inside your known vocabulary, so freshness must come from structure or imagery."
    else:
        base = "Balanced corpus information: enough signature DNA is present without making the sentence fully predictable."
    if rhyme_bits >= 4.0:
        return base + " The end rhyme is a surprise family; repeat or resolve it soon."
    return base + " The end rhyme is close enough to your known rhyme space to work as a stable landing."


def _sentence_bar_plan(detail: Dict[str, Any], fix: Dict[str, Any], beat_plan: Dict[str, Any] | None, profile: Dict[str, Any]) -> Dict[str, Any]:
    syllables = _safe_int(detail.get("syllables"), 0)
    target = beat_plan.get("target_syllables_per_bar") if beat_plan else None
    if isinstance(target, (list, tuple)) and len(target) >= 2:
        low, high = int(target[0]), int(target[-1])
        source = "uploaded_beat"
    else:
        median_target = int(round(float(profile.get("stats", {}).get("median_syllables") or 12)))
        low, high = max(5, median_target - 3), median_target + 3
        source = "corpus_cadence"
    estimated_span = max(1, math.ceil(syllables / max(1, high + 1)))
    split = _split_after_word_for_sentence(detail.get("text", ""), [low, high])
    if syllables > high + 4:
        primary = "split_or_compress"
        instruction = f"This sentence is {syllables - high} syllables over the {source} one-bar ceiling; split the thought or cut connective words."
    elif syllables < low - 3:
        primary = "stretch_or_pickup"
        instruction = f"This sentence is {low - syllables} syllables under the {source} pocket; add a pickup, image, or internal echo."
    else:
        primary = "keep_one_bar"
        instruction = "The sentence can work as one bar; protect the final-quarter landing and polish word choice."
    return {
        "available": True,
        "basis": source,
        "syllables": syllables,
        "target_syllables_per_bar": [low, high],
        "estimated_bar_span": estimated_span,
        "primary_action": primary,
        "instruction": instruction,
        "beat_guidance": beat_plan or {},
        "static_bar_note": _bar_structure_note(fix, beat_plan),
        "split_plan": split,
    }


def _sentence_pct(value: float) -> int:
    try:
        return int(round(max(0.0, min(100.0, float(value)))))
    except Exception:
        return 0


def _sentence_scores(detail: Dict[str, Any], fix: Dict[str, Any], comparison_guidance: Dict[str, Any], bar_plan: Dict[str, Any]) -> Dict[str, Any]:
    syllables = _safe_int(detail.get("syllables"), 0)
    low, high = (bar_plan.get("target_syllables_per_bar") or [9, 15])[:2]
    if low <= syllables <= high:
        cadence = 100
    else:
        cadence = _sentence_pct(100 - (min(abs(syllables - low), abs(syllables - high)) / max(1, high)) * 100)
    internal = min(100, len(detail.get("internal_rhymes") or []) * 38 + len(detail.get("alliteration") or []) * 18)
    rhyme_strength = 70 if detail.get("end_word") else 0
    if detail.get("end_word") and normalize_word(detail.get("end_word")) not in SOFT_CONNECTORS:
        rhyme_strength += 15
    if fix.get("word_banks", {}).get("end_rhymes"):
        rhyme_strength += 10
    imagery = 55 + min(35, len(detail.get("image_words") or []) * 20) - min(25, max(0, len(detail.get("abstract_words") or []) - 1) * 8)
    reference = _safe_int(comparison_guidance.get("reference_score"), 50) if comparison_guidance.get("available") else 50
    overall = _sentence_pct(cadence * 0.25 + min(100, rhyme_strength) * 0.22 + internal * 0.18 + imagery * 0.15 + reference * 0.20)
    return {
        "overall": overall,
        "cadence_fit": cadence,
        "rhyme_landing": min(100, rhyme_strength),
        "internal_sound": internal,
        "image_balance": max(0, min(100, imagery)),
        "reference_fit": reference,
        "reading": "Strong synchronous sentence candidate." if overall >= 78 else "Needs a targeted sentence-level fix before it joins the full draft." if overall < 58 else "Usable sentence; polish one dimension before moving on.",
    }


def _sentence_rewrite_set(sentence: str, detail: Dict[str, Any], fix: Dict[str, Any], bar_plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    variants: List[Dict[str, Any]] = []
    for patch in fix.get("patches", [])[:4]:
        variants.append({
            "name": patch.get("label") or "Patch",
            "text": patch.get("replacement") or sentence,
            "why": patch.get("why") or "Direct sentence-level patch.",
            "syllables": line_syllables(patch.get("replacement") or sentence),
            "kind": "patch",
        })
    split = bar_plan.get("split_plan") or {}
    if split.get("available"):
        variants.append({
            "name": "Two-bar split",
            "text": split.get("formatted_split"),
            "why": "Breaks the sentence into two performable bar units while preserving the idea.",
            "syllables": detail.get("syllables", 0),
            "kind": "bar_split",
        })
    banks = fix.get("word_banks") or {}
    end = (banks.get("end_rhymes") or banks.get("near_rhymes") or [])[:2]
    verbs = (banks.get("verbs") or ["anchor", "thread", "compress"])[:2]
    images = (banks.get("images") or ["signal", "engine", "surface"])[:2]
    punches = (banks.get("punch_words") or ["resonance", "evidence", "signature"])[:2]
    if end:
        swapped = _replace_last_word(sentence, end[0])
        if swapped != sentence:
            variants.append({
                "name": f"Rhyme landing: {end[0]}",
                "text": swapped,
                "why": "Keeps the sentence frame but changes the final landing to a suggested rhyme option.",
                "syllables": line_syllables(swapped),
                "kind": "rhyme_swap",
            })
    if verbs and images and punches:
        seed = f"{str(verbs[0]).capitalize()} the {images[0]} till the bar reveals {punches[0]}"
        variants.append({
            "name": "Fresh sentence seed",
            "text": seed,
            "why": "A compact rewrite seed using a verb, image, and punch word from the current sentence banks.",
            "syllables": line_syllables(seed),
            "kind": "fresh_seed",
        })
    return unique_preserve_dicts(variants, "text", 6)


def unique_preserve_dicts(rows: Iterable[Dict[str, Any]], key: str, limit: int | None = None) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        value = str(row.get(key, "")).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(row)
        if limit is not None and len(out) >= limit:
            break
    return out


def build_sentence_sync_feedback(
    sentence: str,
    mode: str = "match",
    beat: Dict[str, Any] | None = None,
    context_lyrics: str | None = None,
) -> Dict[str, Any]:
    """Return immediate, synchronous feedback for one sentence.

    This intentionally avoids the async job queue used by the live draft editor.
    It is designed for a side lab where the user can fix one thought/bar at a
    time, see word choices, and then paste/apply a rewrite back into the draft.
    """
    mode = mode if mode in MODE_LABELS else "match"
    clean_sentence = _clean_sentence_text(sentence)
    if not clean_sentence or not tokenize(clean_sentence):
        return {"available": False, "error": "Type one sentence to analyze."}

    analysis = analyze_lyrics(clean_sentence, mode)
    if beat:
        analysis = attach_beat_guidance(analysis, beat)
    else:
        analysis["beat_analysis"] = {"available": False}
        analysis["beat_alignment"] = {"available": False, "summary": "Upload a beat to make sentence bar feedback beat-aware."}

    cards = _line_lookup(analysis)
    details = _detail_lookup(analysis)
    beats = _beat_lookup(analysis)
    if not cards or not details:
        return {"available": False, "error": "No analyzable sentence found."}
    line_no = sorted(cards)[0]
    detail = details.get(line_no, {})
    card = cards[line_no]
    beat_plan = beats.get(line_no)
    fix = _fix_card(card, detail, beat_plan, active=True)
    comparison_report = build_comparison_report(clean_sentence, analysis)
    comparison_guidance = line_comparison_guidance(detail, comparison_report)
    fix["comparison_guidance"] = comparison_guidance
    highlight_report = _rhyme_highlight_report(analysis)
    highlight = (highlight_report.get("line_map") or {}).get(line_no, {})
    fix["rhyme_highlight"] = highlight

    profile = get_corpus_profile()
    bar_plan = _sentence_bar_plan(detail, fix, beat_plan, profile)
    info = _corpus_information_for_sentence(detail, profile)
    scores = _sentence_scores(detail, fix, comparison_guidance, bar_plan)
    clauses = _sentence_clauses(clean_sentence)
    rewrites = _sentence_rewrite_set(clean_sentence, detail, fix, bar_plan)
    meter = analyze_sentence_meter(clean_sentence, beat=beat, target_syllables=bar_plan.get("target_syllables_per_bar"))
    physics = build_sentence_physics_report(clean_sentence, beat=beat, mode=mode)
    for clause in clauses:
        clause["meter"] = analyze_sentence_meter(clause.get("text", ""), beat=beat)

    next_actions = []
    op = fix.get("operation")
    if op == "compress_line" or bar_plan.get("primary_action") == "split_or_compress":
        next_actions.append("First decide whether this is one bar or two bars; do not change the rhyme until the length is right.")
    if fix.get("word_banks", {}).get("cut_words"):
        next_actions.append(f"Cut or replace: {', '.join(fix['word_banks']['cut_words'][:5])}.")
    if fix.get("word_banks", {}).get("internal_echoes"):
        next_actions.append(f"Add one internal echo before the turn: {', '.join(fix['word_banks']['internal_echoes'][:5])}.")
    if fix.get("word_banks", {}).get("end_rhymes"):
        next_actions.append(f"Try a stronger landing: {', '.join(fix['word_banks']['end_rhymes'][:5])}.")
    if physics.get("available"):
        next_actions.extend((physics.get("actions") or [])[:3])
    if not next_actions:
        next_actions.extend(fix.get("specific_moves", [])[:3])

    return {
        "available": True,
        "report_type": "synchronous_sentence_feedback",
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "sentence": clean_sentence,
        "context_received": bool(context_lyrics),
        "metrics": {
            "words": detail.get("word_count", 0),
            "content_words": len(detail.get("content_words", []) or []),
            "syllables": detail.get("syllables", 0),
            "end_word": detail.get("end_word", ""),
            "rhyme_key": detail.get("rhyme_key", ""),
            "internal_rhyme_groups": len(detail.get("internal_rhymes", []) or []),
            "alliteration_groups": len(detail.get("alliteration", []) or []),
            "motif_count": len(detail.get("motif_hits", {}) or {}),
            "abstract_count": len(detail.get("abstract_words", []) or []),
            "image_count": len(detail.get("image_words", []) or []),
            "stress_ratio_pct": (meter.get("summary") or {}).get("stress_ratio_pct", 0) if meter.get("available") else 0,
            "dominant_meter": (meter.get("summary") or {}).get("dominant_meter", "mixed") if meter.get("available") else "mixed",
            "force_pct": ((physics.get("line") or {}).get("force_pct", 0)) if physics.get("available") else 0,
            "torsion_pct": ((physics.get("line") or {}).get("torsion_pct", 0)) if physics.get("available") else 0,
            "spin_pct": ((physics.get("line") or {}).get("spin_pct", 0)) if physics.get("available") else 0,
        },
        "meter": meter,
        "physics": physics,
        "scores": scores,
        "headline": f"{scores['overall']}% sentence fit · {fix.get('operation_label')} · {detail.get('syllables', 0)} syllables",
        "diagnosis": fix.get("diagnosis"),
        "next_actions": unique_preserve(next_actions, 6),
        "clauses": clauses,
        "bar_plan": bar_plan,
        "information": info,
        "suggestion": {
            "operation": fix.get("operation"),
            "operation_label": fix.get("operation_label"),
            "priority": fix.get("priority"),
            "severity": fix.get("severity"),
            "specific_moves": fix.get("specific_moves", []),
            "issues": fix.get("issues", []),
        },
        "possible_words": fix.get("word_banks", {}),
        "advanced_rhyme": fix.get("advanced_rhyme", {}),
        "rewrite_options": rewrites,
        "applyable_patches": fix.get("patches", []),
        "rhyme_highlight": highlight,
        "sound_hits": {
            "internal_rhymes": detail.get("internal_rhymes", []),
            "alliteration": detail.get("alliteration", []),
        },
        "motif_hits": detail.get("motif_hits", {}),
        "comparison_guidance": comparison_guidance,
        "comparison": comparison_report,
        "raw_detail": detail,
    }


def build_line_fix(lyrics: str, line_number: int, mode: str = "match", beat: Dict[str, Any] | None = None) -> Dict[str, Any]:
    result = build_editing_lab_result(lyrics, mode, active_line=line_number, beat=beat)
    return result.get("active_fix") or {"available": False, "error": "No editable lyric line found."}
