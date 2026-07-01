"""Sentence-level rhyme pattern comparison engine.

This module compares multiple candidate rap sentences as sound structures instead
of only as plain text. It extracts end-rhyme families, internal echo families,
stress-compatible tails, alliteration/consonance clusters, and then suggests
transferable rhyme patterns the writer can apply to the weaker sentence.

The engine is offline and publish-safe. It uses the compiled corpus profile and
advanced rhyme engine; it does not require or expose raw reference lyrics.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from lyric_engine import (
    CORE_VERBS,
    CONCRETE_IMAGE_WORDS,
    PUNCH_WORDS,
    STOPWORDS,
    WEAK_END_WORDS,
    build_line_details,
    content_words,
    count_syllables,
    end_word,
    get_corpus_profile,
    line_syllables,
    normalize_word,
    rhyme_key,
    tokenize,
    unique_preserve,
)
from rhyme_engine import advanced_rhyme_for_word, rhyme_similarity, word_signature

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9'\"“‘(])")
SECTION_MARKER_RE = re.compile(r"^\s*(?://\s*)?(intro|verse|chorus|hook|bridge|outro|refrain)\b", re.I)
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _round(value: Any, digits: int = 2) -> float:
    try:
        n = float(value)
        if math.isfinite(n):
            return round(n, digits)
    except Exception:
        pass
    return 0.0


def _pct(value: Any) -> int:
    try:
        return int(round(max(0.0, min(100.0, float(value)))))
    except Exception:
        return 0


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa = {x for x in a if x}
    sb = {x for x in b if x}
    if not sa and not sb:
        return 0.0
    return len(sa & sb) / max(1, len(sa | sb))


def _seq_similarity(a: Sequence[Any], b: Sequence[Any]) -> float:
    if not a or not b:
        return 0.0
    length_score = min(len(a), len(b)) / max(len(a), len(b))
    overlap_score = _jaccard([str(x) for x in a], [str(x) for x in b])
    suffix = 0
    for left, right in zip(reversed(a), reversed(b)):
        if left == right:
            suffix += 1
        else:
            break
    suffix_score = suffix / max(1, min(len(a), len(b)))
    return max(overlap_score, suffix_score * 0.75 + length_score * 0.25)


def _safe_detail(sentence: str, number: int = 1) -> Dict[str, Any]:
    details = build_line_details(sentence)
    if details:
        detail = dict(details[0])
        detail["number"] = number
        return detail
    words = tokenize(sentence)
    cw = content_words(words)
    ew = end_word(sentence)
    return {
        "number": number,
        "text": sentence.strip(),
        "words": words,
        "content_words": cw,
        "word_count": len(words),
        "syllables": line_syllables(sentence),
        "end_word": ew,
        "rhyme_key": rhyme_key(ew),
        "internal_rhymes": [],
        "alliteration": [],
        "motif_hits": {},
        "abstract_words": [],
        "image_words": [],
        "filler_words": [],
        "cut_candidates": [],
    }


def split_candidate_sentences(text_or_sentences: str | Sequence[str], limit: int = 16) -> List[str]:
    """Split input into usable sentences/bars.

    Line breaks are treated as intentional rap sentence candidates. If the input
    is one paragraph, punctuation is used as the fallback split.
    """
    if isinstance(text_or_sentences, (list, tuple)):
        raw_items = [str(item).strip() for item in text_or_sentences]
    else:
        text = str(text_or_sentences or "").replace("\r\n", "\n")
        raw_lines = [line.strip() for line in text.split("\n") if line.strip()]
        # Lyrics are usually entered line-by-line; preserve that first.
        if len([line for line in raw_lines if not SECTION_MARKER_RE.match(line)]) >= 2:
            raw_items = raw_lines
        else:
            raw_items = []
            for chunk in raw_lines or [text.strip()]:
                raw_items.extend(part.strip() for part in SENTENCE_SPLIT_RE.split(chunk) if part.strip())
    cleaned: List[str] = []
    for item in raw_items:
        item = re.sub(r"\s+", " ", str(item).strip())
        if not item or SECTION_MARKER_RE.match(item):
            continue
        if len(tokenize(item)) < 2:
            continue
        cleaned.append(item)
        if len(cleaned) >= limit:
            break
    return unique_preserve(cleaned, limit)


def _letter_sequence(keys: Sequence[str], end_key: str = "") -> Tuple[List[Dict[str, Any]], str]:
    counts = Counter(key for key in keys if key)
    ordered = []
    for key in keys:
        if key and key not in ordered:
            ordered.append(key)
    letter_for_key = {key: LETTERS[i % len(LETTERS)] for i, key in enumerate(ordered)}
    rows: List[Dict[str, Any]] = []
    compact: List[str] = []
    for key in keys:
        if not key:
            label = "·"
            role = "empty"
        else:
            label = letter_for_key.get(key, "?")
            role = "repeat" if counts[key] > 1 else "single"
            if key == end_key:
                role = "end" if counts[key] <= 1 else "repeat_end"
        rows.append({"key": key, "letter": label, "role": role, "count": int(counts.get(key, 0))})
        compact.append(label if key and (counts[key] > 1 or key == end_key) else "·")
    return rows, " ".join(compact)


def _token_rows(words: Sequence[str], end: str) -> List[Dict[str, Any]]:
    keys = [rhyme_key(w) for w in words]
    counts = Counter(key for key in keys if key)
    end_norm = normalize_word(end)
    rows: List[Dict[str, Any]] = []
    last_end_index = max((i for i, w in enumerate(words) if normalize_word(w) == end_norm), default=len(words) - 1)
    for index, word in enumerate(words):
        key = keys[index]
        sig = word_signature(word)
        rows.append({
            "word": word,
            "index": index,
            "position_pct": _round(((index + 1) / max(1, len(words))) * 100, 1),
            "rhyme_key": key,
            "syllables": sig.get("syllables", count_syllables(word)),
            "stress_signature": sig.get("stress_signature", ""),
            "role": "end" if index == last_end_index else "internal" if counts.get(key, 0) > 1 and word not in STOPWORDS else "content" if word not in STOPWORDS else "function",
            "family_count": int(counts.get(key, 0)),
        })
    return rows


def sentence_rhyme_signature(sentence: str, index: int = 1, mode: str = "match", profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    profile = profile or get_corpus_profile()
    detail = _safe_detail(sentence, number=index)
    words = detail.get("words") or tokenize(sentence)
    cwords = detail.get("content_words") or content_words(words)
    end = normalize_word(detail.get("end_word") or end_word(sentence))
    end_key = rhyme_key(end)
    content_keys = [rhyme_key(w) for w in cwords if rhyme_key(w)]
    all_keys = [rhyme_key(w) for w in words if rhyme_key(w)]
    key_counts = Counter(content_keys + ([end_key] if end_key else []))
    letter_rows, compact_scheme = _letter_sequence(all_keys, end_key=end_key)
    repeated_families = [
        {"key": key, "count": int(count), "words": unique_preserve([w for w in cwords if rhyme_key(w) == key], 10)}
        for key, count in key_counts.most_common()
        if count >= 2 and key
    ]
    end_report = advanced_rhyme_for_word(end, profile=profile, line_text=sentence, mode=mode, limit=10) if end else {"available": False}
    tail_words = cwords[-3:] if cwords else words[-3:]
    tail = []
    for word in tail_words:
        sig = word_signature(word)
        tail.append({
            "word": word,
            "rhyme_key": sig.get("rhyme_key"),
            "syllables": sig.get("syllables"),
            "stress_signature": sig.get("stress_signature"),
            "stressed_tail": sig.get("stressed_tail"),
        })
    internal_groups = detail.get("internal_rhymes") or []
    internal_token_hits = sum(int(row.get("count") or len(row.get("words") or [])) for row in internal_groups)
    alliteration_groups = detail.get("alliteration") or []
    allit_hits = sum(int(row.get("count") or len(row.get("words") or [])) for row in alliteration_groups)
    rhyme_density = _pct((internal_token_hits / max(1, len(cwords))) * 100)
    alliteration_density = _pct((allit_hits / max(1, len(cwords))) * 100)
    end_strength = 0
    if end_report.get("available"):
        end_strength = int((end_report.get("summary") or {}).get("best_score") or 0)
    if end and end not in WEAK_END_WORDS:
        end_strength = min(100, end_strength + 8)
    if end in WEAK_END_WORDS:
        end_strength = max(0, end_strength - 18)
    pattern_strength = _pct(end_strength * 0.42 + rhyme_density * 0.28 + alliteration_density * 0.12 + min(100, len(repeated_families) * 18) + min(20, len(cwords)))
    if compact_scheme.strip(" ·"):
        structure_label = compact_scheme
    else:
        structure_label = f"single landing /{end_key or 'none'}/"
    return {
        "index": index,
        "sentence": sentence.strip(),
        "summary": {
            "word_count": int(detail.get("word_count") or len(words)),
            "content_word_count": len(cwords),
            "syllables": int(detail.get("syllables") or line_syllables(sentence)),
            "end_word": end,
            "end_rhyme_key": end_key,
            "compact_scheme": structure_label,
            "pattern_strength": pattern_strength,
            "rhyme_density_pct": rhyme_density,
            "alliteration_density_pct": alliteration_density,
            "internal_group_count": len(internal_groups),
            "repeated_family_count": len(repeated_families),
        },
        "tokens": _token_rows(words, end),
        "rhyme_letters": letter_rows,
        "content_rhyme_keys": content_keys,
        "all_rhyme_keys": all_keys,
        "repeated_families": repeated_families,
        "internal_rhyme_groups": internal_groups,
        "alliteration_groups": alliteration_groups,
        "tail_pattern": tail,
        "end_report": {
            "available": bool(end_report.get("available")),
            "summary": end_report.get("summary", {}),
            "word_lists": end_report.get("word_lists", {}),
            "rhyme_ladder": end_report.get("rhyme_ladder", []),
        },
        "diagnosis": _sentence_diagnosis(sentence, detail, pattern_strength, rhyme_density, end_report),
    }


def _sentence_diagnosis(sentence: str, detail: Dict[str, Any], strength: int, density: int, end_report: Dict[str, Any]) -> List[str]:
    notes: List[str] = []
    end = normalize_word(detail.get("end_word", ""))
    if strength >= 78:
        notes.append("Strong rhyme structure: use this sentence as a pattern donor for weaker lines.")
    elif strength >= 56:
        notes.append("Usable rhyme structure: add one internal echo or sharpen the final landing.")
    else:
        notes.append("Weak rhyme structure: pick an anchor family, then place one echo before the final word.")
    if density < 18 and int(detail.get("word_count") or 0) >= 7:
        notes.append("Internal rhyme density is low for a sentence this long.")
    if end in WEAK_END_WORDS:
        notes.append("The final word is weak; move a noun or technical image into the landing slot.")
    if end_report.get("available") and (end_report.get("summary") or {}).get("candidate_count", 0) < 3:
        notes.append("The end word has a sparse rhyme bank; consider rotating to a stronger family.")
    return unique_preserve(notes, 5)


def _compare_pair(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    a_summary = a.get("summary", {})
    b_summary = b.get("summary", {})
    a_end = a_summary.get("end_word", "")
    b_end = b_summary.get("end_word", "")
    sim = rhyme_similarity(str(a_end), str(b_end)) if a_end and b_end else {"score": 0, "kind": "none", "reasons": []}
    end_score = int(sim.get("score") or 0)
    key_overlap = _jaccard(a.get("content_rhyme_keys") or [], b.get("content_rhyme_keys") or [])
    all_key_overlap = _jaccard(a.get("all_rhyme_keys") or [], b.get("all_rhyme_keys") or [])
    tail_stress_a = [row.get("stress_signature") for row in a.get("tail_pattern", [])]
    tail_stress_b = [row.get("stress_signature") for row in b.get("tail_pattern", [])]
    tail_key_a = [row.get("rhyme_key") for row in a.get("tail_pattern", [])]
    tail_key_b = [row.get("rhyme_key") for row in b.get("tail_pattern", [])]
    stress_score = _seq_similarity(tail_stress_a, tail_stress_b) * 100
    tail_key_score = _seq_similarity(tail_key_a, tail_key_b) * 100
    syllable_delta = int(b_summary.get("syllables") or 0) - int(a_summary.get("syllables") or 0)
    syllable_fit = max(0, 100 - abs(syllable_delta) * 7)
    density_delta = int(b_summary.get("rhyme_density_pct") or 0) - int(a_summary.get("rhyme_density_pct") or 0)
    density_fit = max(0, 100 - abs(density_delta) * 1.1)
    overall = _pct(end_score * 0.32 + key_overlap * 100 * 0.18 + all_key_overlap * 100 * 0.12 + stress_score * 0.14 + tail_key_score * 0.10 + syllable_fit * 0.08 + density_fit * 0.06)
    if overall >= 78:
        relation = "parallel rhyme architecture"
    elif end_score >= 62:
        relation = "slant/end-rhyme cousin"
    elif key_overlap >= 0.34:
        relation = "internal-echo cousin"
    elif syllable_fit >= 82 and stress_score >= 55:
        relation = "cadence match, rhyme contrast"
    else:
        relation = "contrast pattern"
    shared_keys = sorted(set(a.get("all_rhyme_keys") or []) & set(b.get("all_rhyme_keys") or []))
    advice = []
    if relation.startswith("parallel"):
        advice.append("Use these as a couplet: keep the tail stress and rotate exact end words inside the same/slant family.")
    elif end_score < 52:
        advice.append("The endings do not answer each other yet; choose a slant or family option from the stronger sentence's end word.")
    if abs(density_delta) >= 18:
        donor = "first" if density_delta < 0 else "second"
        receiver = "second" if density_delta < 0 else "first"
        advice.append(f"The {receiver} sentence is thinner internally; mirror one internal echo from the {donor} sentence.")
    if abs(syllable_delta) >= 4:
        advice.append("Cadence lengths are far apart; split the longer sentence or pad the shorter one before comparing rhyme structure.")
    if not advice:
        advice.append("The pair is usable; improve by adding one mid-sentence echo before the final landing.")
    return {
        "left_index": a.get("index"),
        "right_index": b.get("index"),
        "score": overall,
        "relationship": relation,
        "end_rhyme_similarity": end_score,
        "end_rhyme_kind": sim.get("kind"),
        "shared_rhyme_keys": shared_keys[:12],
        "content_key_overlap_pct": _round(key_overlap * 100, 1),
        "tail_stress_match_pct": _round(stress_score, 1),
        "tail_key_match_pct": _round(tail_key_score, 1),
        "syllable_delta": syllable_delta,
        "density_delta_pct": _round(density_delta, 1),
        "reasons": unique_preserve(list(sim.get("reasons", [])) + advice, 8),
    }


def _replace_last_word(line: str, new_word: str) -> str:
    matches = list(re.finditer(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", line))
    if not matches:
        return new_word
    last = matches[-1]
    return (line[:last.start()] + str(new_word).strip() + line[last.end():]).strip()


def _insert_before_last_word(line: str, phrase: str) -> str:
    phrase = str(phrase or "").strip()
    matches = list(re.finditer(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", line))
    if not matches or not phrase:
        return line
    last = matches[-1]
    left = line[:last.start()].rstrip()
    right = line[last.start():].lstrip()
    return f"{left} {phrase} {right}".strip()


def _pattern_blueprints(signatures: Sequence[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    end_keys = [s.get("summary", {}).get("end_rhyme_key") for s in signatures if s.get("summary", {}).get("end_rhyme_key")]
    end_counts = Counter(end_keys)
    top_profile = profile.get("top_rhymes", [])[:8]
    anchor_key = end_counts.most_common(1)[0][0] if end_counts else (top_profile[0].get("key") if top_profile else "ence")
    anchor_words = []
    for row in top_profile:
        if row.get("key") == anchor_key:
            anchor_words = list(row.get("words") or [])
            break
    if not anchor_words:
        for s in signatures:
            if s.get("summary", {}).get("end_rhyme_key") == anchor_key:
                anchor_words.append(s.get("summary", {}).get("end_word", ""))
        if anchor_words:
            anchor_words.extend((advanced_rhyme_for_word(anchor_words[0]).get("word_lists") or {}).get("end_rhymes", []))
    anchor_words = unique_preserve(anchor_words, 12)
    profile_families = [
        {"key": row.get("key"), "words": unique_preserve(row.get("words") or [], 8), "count": row.get("count", 0)}
        for row in top_profile
        if row.get("key")
    ]
    blueprints = [
        {
            "name": "Anchor-chain couplet",
            "scheme": "A / A",
            "structure": "same end family, different exact word",
            "use_when": "Two sentences need to sound connected without repeating the same final word.",
            "steps": [
                f"Choose /{anchor_key}/ as the landing family.",
                "Put one same-family word in the middle of each sentence.",
                "End both sentences with different words from the same or slant family.",
            ],
            "word_bank": anchor_words,
        },
        {
            "name": "Internal ladder into landing",
            "scheme": "a a A",
            "structure": "two internal echoes before the end rhyme",
            "use_when": "A sentence is long but the rhyme only appears at the end.",
            "steps": [
                "Place a light echo around 35% of the sentence.",
                "Place a second echo around 65% of the sentence.",
                "Let the final word land as the loudest family member.",
            ],
            "word_bank": anchor_words,
        },
        {
            "name": "Slant turn release",
            "scheme": "A / A′ / B",
            "structure": "repeat, slant, then rotate",
            "use_when": "The rhyme family is starting to feel overused.",
            "steps": [
                "Keep one direct family landing.",
                "Answer it with a slant rhyme instead of a perfect rhyme.",
                "Move to a new family on the third sentence for release.",
            ],
            "word_bank": anchor_words,
        },
        {
            "name": "Call-response mirror",
            "scheme": "A-B / A-B",
            "structure": "match internal family and end family across two sentences",
            "use_when": "Two sentences should feel like question and answer.",
            "steps": [
                "Copy the stronger sentence's internal rhyme key into the weaker sentence.",
                "Keep both sentences near the same syllable count.",
                "End with either the same family or a clear slant cousin.",
            ],
            "word_bank": anchor_words,
        },
    ]
    if profile_families:
        blueprints.append({
            "name": "Corpus-family rotation",
            "scheme": "A / B / C / A",
            "structure": "rotate through your strongest recurring families, then return to the hook family",
            "use_when": "The verse needs more movement while staying in your style DNA.",
            "steps": [f"Use /{row['key']}/ with {', '.join(row['words'][:4])}." for row in profile_families[:4]],
            "families": profile_families,
            "word_bank": unique_preserve([word for row in profile_families for word in row.get("words", [])], 24),
        })
    return blueprints


def _sentence_rewrites(sig: Dict[str, Any], strongest: Dict[str, Any] | None, mode: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    sentence = str(sig.get("sentence") or "")
    summary = sig.get("summary", {})
    end = str(summary.get("end_word") or "")
    end_report = sig.get("end_report", {}) or {}
    lists = end_report.get("word_lists", {}) or {}
    rewrites: List[Dict[str, Any]] = []
    # Self-improvement options.
    if lists.get("end_rhymes"):
        word = lists["end_rhymes"][0]
        rewrites.append({
            "type": "end_family_swap",
            "label": f"Rotate landing to {word}",
            "text": _replace_last_word(sentence, word),
            "why": "Keeps the current sentence frame but gives the final word a stronger same/family rhyme landing.",
        })
    if lists.get("internal_echoes"):
        echo = lists["internal_echoes"][0]
        rewrites.append({
            "type": "add_internal_echo",
            "label": f"Add mid-sentence echo {echo}",
            "text": _insert_before_last_word(sentence, echo),
            "why": "Adds a sound pocket before the end rhyme so the sentence is not only end-weighted.",
        })
    if lists.get("multi_syllable_endings"):
        phrase = str(lists["multi_syllable_endings"][0])
        rewrites.append({
            "type": "multi_syllable_landing",
            "label": f"Use multi-syllable landing {phrase}",
            "text": _replace_last_word(sentence, phrase),
            "why": "Turns the tail into a more technical multi-word rhyme landing.",
        })
    # Transfer the strongest sentence's pattern.
    if strongest and strongest is not sig:
        strong_end = strongest.get("summary", {}).get("end_word")
        strong_report = advanced_rhyme_for_word(strong_end, profile=profile, mode=mode, limit=8) if strong_end else {}
        strong_lists = strong_report.get("word_lists", {}) if strong_report.get("available") else {}
        if strong_lists.get("near_rhymes"):
            word = strong_lists["near_rhymes"][0]
            rewrites.append({
                "type": "match_strongest_pattern",
                "label": f"Answer strongest sentence with {word}",
                "text": _replace_last_word(sentence, word),
                "why": "Copies the stronger sentence's rhyme family as a response pattern.",
                "source_sentence_index": strongest.get("index"),
            })
    # Freshness option.
    if mode == "break":
        pool = unique_preserve(list(CORE_VERBS) + list(CONCRETE_IMAGE_WORDS) + list(PUNCH_WORDS), 12)
        if pool:
            rewrites.append({
                "type": "break_pattern_image",
                "label": f"Break abstraction with {pool[0]}",
                "text": _insert_before_last_word(sentence, pool[0]),
                "why": "Keeps the rhyme path but inserts a physical anchor to freshen the sentence.",
            })
    # Deduplicate.
    seen = set()
    clean = []
    for row in rewrites:
        text = str(row.get("text") or "").strip()
        if not text or text == sentence or text.lower() in seen:
            continue
        seen.add(text.lower())
        row["syllables"] = line_syllables(text)
        row["delta_syllables"] = row["syllables"] - int(summary.get("syllables") or 0)
        clean.append(row)
    return clean[:5]


def _global_recommendations(signatures: Sequence[Dict[str, Any]], pairs: Sequence[Dict[str, Any]]) -> List[str]:
    notes: List[str] = []
    if not signatures:
        return ["Add at least two sentences to compare rhyme structure."]
    avg_strength = sum(int(s.get("summary", {}).get("pattern_strength") or 0) for s in signatures) / max(1, len(signatures))
    avg_density = sum(int(s.get("summary", {}).get("rhyme_density_pct") or 0) for s in signatures) / max(1, len(signatures))
    if avg_strength < 55:
        notes.append("Overall sentence rhyme architecture is light; choose one anchor family and repeat it across two sentences before rotating.")
    elif avg_strength >= 72:
        notes.append("The sentence set has strong rhyme architecture; focus on rotating exact end words rather than adding more density.")
    if avg_density < 20:
        notes.append("Most rhyme weight is at the end. Add one internal echo to each long sentence before the final landing.")
    if pairs:
        best = max(pairs, key=lambda row: int(row.get("score") or 0))
        if int(best.get("score") or 0) >= 70:
            notes.append(f"Sentences {best.get('left_index')} and {best.get('right_index')} form the clearest pattern pair; use them as the model for adjacent edits.")
        weak_pairs = [p for p in pairs if int(p.get("score") or 0) < 45]
        if weak_pairs and len(signatures) >= 3:
            notes.append("Some sentence pairs are pure contrast. That can work, but place contrast after a strong couplet so it feels intentional.")
    end_keys = [s.get("summary", {}).get("end_rhyme_key") for s in signatures if s.get("summary", {}).get("end_rhyme_key")]
    counts = Counter(end_keys)
    if counts:
        key, count = counts.most_common(1)[0]
        if count >= 2:
            notes.append(f"/{key}/ is already acting as an anchor family. Keep it for the hook/couplet, then use a slant turn for release.")
    return unique_preserve(notes, 6)


def compare_sentence_rhyme_patterns(
    text_or_sentences: str | Sequence[str],
    mode: str = "match",
    profile: Dict[str, Any] | None = None,
    max_sentences: int = 16,
) -> Dict[str, Any]:
    profile = profile or get_corpus_profile()
    sentences = split_candidate_sentences(text_or_sentences, limit=max_sentences)
    if len(sentences) < 1:
        return {"available": False, "error": "Provide at least one sentence or rap line to analyze."}
    signatures = [sentence_rhyme_signature(sentence, index=i + 1, mode=mode, profile=profile) for i, sentence in enumerate(sentences)]
    pairs: List[Dict[str, Any]] = []
    for i in range(len(signatures)):
        for j in range(i + 1, len(signatures)):
            pairs.append(_compare_pair(signatures[i], signatures[j]))
    pairs.sort(key=lambda row: (-int(row.get("score") or 0), int(row.get("left_index") or 0), int(row.get("right_index") or 0)))
    strongest = max(signatures, key=lambda row: int(row.get("summary", {}).get("pattern_strength") or 0)) if signatures else None
    weakest = min(signatures, key=lambda row: int(row.get("summary", {}).get("pattern_strength") or 0)) if signatures else None
    for sig in signatures:
        sig["rewrite_suggestions"] = _sentence_rewrites(sig, strongest, mode, profile)
        sig["compare_role"] = "strongest_pattern_donor" if strongest and sig.get("index") == strongest.get("index") else "weakest_pattern_receiver" if weakest and sig.get("index") == weakest.get("index") else "middle_pattern"
    end_counts = Counter(s.get("summary", {}).get("end_rhyme_key") for s in signatures if s.get("summary", {}).get("end_rhyme_key"))
    all_key_counts = Counter(key for s in signatures for key in s.get("all_rhyme_keys", []) if key)
    avg_strength = _round(sum(int(s.get("summary", {}).get("pattern_strength") or 0) for s in signatures) / max(1, len(signatures)), 1)
    avg_density = _round(sum(int(s.get("summary", {}).get("rhyme_density_pct") or 0) for s in signatures) / max(1, len(signatures)), 1)
    return {
        "available": True,
        "report_type": "sentence_rhyme_pattern_comparison",
        "mode": mode,
        "summary": {
            "sentences": len(signatures),
            "avg_pattern_strength": avg_strength,
            "avg_internal_rhyme_density_pct": avg_density,
            "strongest_sentence_index": strongest.get("index") if strongest else None,
            "strongest_sentence_score": strongest.get("summary", {}).get("pattern_strength") if strongest else 0,
            "weakest_sentence_index": weakest.get("index") if weakest else None,
            "weakest_sentence_score": weakest.get("summary", {}).get("pattern_strength") if weakest else 0,
            "best_pair_score": pairs[0].get("score") if pairs else 0,
            "dominant_end_families": [{"key": key, "count": count} for key, count in end_counts.most_common(8)],
            "dominant_internal_families": [{"key": key, "count": count} for key, count in all_key_counts.most_common(8)],
        },
        "sentences": signatures,
        "pairwise": pairs,
        "best_pairs": pairs[:8],
        "pattern_blueprints": _pattern_blueprints(signatures, profile),
        "recommendations": _global_recommendations(signatures, pairs),
        "corpus_targets": {
            "top_rhyme_families": profile.get("top_rhymes", [])[:10],
            "signature_words": [row.get("word") for row in profile.get("signature_words", [])[:16] if row.get("word")],
            "note": "The pattern suggestions use derived corpus/profile statistics rather than raw reference lyrics.",
        },
    }
