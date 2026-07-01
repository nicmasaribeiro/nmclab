"""Advanced rhyme suggestion engine for the NMC rap lab.

The base lyric engine already detects rhyme families and highlights them. This
module adds a more writer-facing rhyme coach: phonetic/slant scoring, multisyllable
endings, internal echo placement, line-by-line rhyme repair, scheme-level
recommendations, and publish-safe comparison-profile awareness.

No raw commercial lyrics are required. The engine works from the compiled user
corpus profile, the derived comparison profiles, and optional CMUdict phonetics.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from statistics import median
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from lyric_engine import (
    CONCRETE_IMAGE_WORDS,
    CORE_VERBS,
    PUNCH_WORDS,
    STOPWORDS,
    WEAK_END_WORDS,
    build_line_details,
    content_words,
    count_syllables,
    end_word as line_end_word,
    get_corpus_profile,
    line_syllables,
    normalize_word,
    possible_rhymes_for_word,
    rhyme_key,
    section_blocks,
    tokenize,
    unique_preserve,
)

try:  # cmudict is small and already installed by pronouncing on most setups.
    import cmudict  # type: ignore
except Exception:  # pragma: no cover - optional dependency path
    cmudict = None  # type: ignore

VOWEL_PHONE_RE = re.compile(r"[AEIOU].*\d")
PHONE_STRESS_RE = re.compile(r"\d")
WORD_OR_PHRASE_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")

RHYME_KIND_ORDER = {
    "perfect": 0,
    "family": 1,
    "multisyllable": 2,
    "slant": 3,
    "assonance": 4,
    "consonance": 5,
    "texture": 6,
}

FALLBACK_RHYME_WORDS = [
    "sentence", "presence", "essence", "resonance", "evidence", "medicine", "venom", "system",
    "rhythm", "signal", "script", "surface", "purpose", "service", "universe", "reverse",
    "credit", "method", "vector", "texture", "pressure", "precision", "signature", "structure",
    "picture", "scripture", "mixture", "friction", "diction", "direction", "projection", "reflection",
    "dominance", "consonance", "confidence", "monuments", "documents", "elements", "delicate",
    "intricate", "infinite", "intimate", "significant", "digital", "physical", "criminal", "critical",
    "lyrics", "physics", "schematics", "mathematics", "paradise", "device", "price", "dice",
    "spark", "dark", "mark", "heart", "start", "part", "art", "cards",
    "thread", "spread", "debt", "fed", "vetted", "embedded", "tested", "rested",
]

BRIDGE_PHRASES = [
    "etched in", "stitched through", "wired with", "measured by", "anchored in", "threaded through",
    "coded as", "pressed against", "carved into", "bent around", "split by", "locked inside",
]

RHYME_BLUEPRINTS = [
    "Keep the setup, place an internal echo near the middle, then land the final word clean.",
    "Use a two-syllable setup before the landing so the rhyme feels intentional, not accidental.",
    "Repeat the rhyme family for one more line if you are building pressure; rotate it if the family already dominates the verse.",
    "For a punch line, move the hardest noun to the final slot and let the softer connector words happen earlier.",
]


def _round(value: Any, digits: int = 2) -> float:
    try:
        number = float(value)
        if math.isfinite(number):
            return round(number, digits)
    except Exception:
        pass
    return 0.0


def _pct(value: float) -> int:
    try:
        return int(round(max(0.0, min(100.0, float(value)))))
    except Exception:
        return 0


@lru_cache(maxsize=1)
def _cmu_index() -> Dict[str, List[List[str]]]:
    if cmudict is None:
        return {}
    try:
        index: Dict[str, List[List[str]]] = defaultdict(list)
        for word, phones in cmudict.entries():
            key = normalize_word(word)
            if key:
                index[key].append(list(phones))
        return dict(index)
    except Exception:
        return {}


def _strip_phone_stress(phone: str) -> str:
    return PHONE_STRESS_RE.sub("", str(phone))


def _is_vowel_phone(phone: str) -> bool:
    return bool(VOWEL_PHONE_RE.match(str(phone)))


def _fallback_phones(word: str) -> List[str]:
    """Return a deterministic pseudo-phone list when cmudict lacks a word.

    This is not a full grapheme-to-phoneme model; it is a suffix-aware fallback
    that keeps rhyme scoring useful for slang, proper nouns, and invented words.
    """
    word = normalize_word(word)
    if not word:
        return []
    chunks = re.findall(r"[aeiouy]+|[^aeiouy]+", word)
    phones: List[str] = []
    for chunk in chunks:
        if re.fullmatch(r"[aeiouy]+", chunk):
            phones.append(chunk.upper() + "1")
        else:
            # Keep consonant clusters because clusters matter for rap texture.
            phones.extend([ch.upper() for ch in chunk if ch.isalpha()])
    return phones or [word.upper() + "1"]


def _candidate_cmu_keys(word: str) -> List[str]:
    word = normalize_word(word)
    keys = [word]
    if word.endswith("in'"):
        keys.append(word[:-3] + "ing")
    if word.endswith("ing") and len(word) > 5:
        keys.append(word[:-3])
    if word.endswith("ed") and len(word) > 4:
        keys.append(word[:-2])
    if word.endswith("s") and len(word) > 4:
        keys.append(word[:-1])
    if "-" in word:
        keys.extend([part for part in word.split("-") if part])
    return unique_preserve(keys, 8)


def phones_for_word(word: str) -> Tuple[List[str], str]:
    index = _cmu_index()
    for key in _candidate_cmu_keys(word):
        entries = index.get(key)
        if entries:
            # Prefer the pronunciation with the most explicit stress marks.
            phones = max(entries, key=lambda row: sum(1 for phone in row if _is_vowel_phone(phone)))
            return list(phones), "cmudict"
    return _fallback_phones(word), "heuristic"


def _last_stressed_vowel_index(phones: Sequence[str]) -> int:
    vowel_indexes = [i for i, phone in enumerate(phones) if _is_vowel_phone(phone)]
    stressed = [i for i in vowel_indexes if "1" in str(phones[i]) or "2" in str(phones[i])]
    if stressed:
        return stressed[-1]
    return vowel_indexes[-1] if vowel_indexes else max(0, len(phones) - 1)


def _stress_pattern_from_phones(phones: Sequence[str], fallback_syllables: int = 1) -> List[int]:
    pattern: List[int] = []
    for phone in phones:
        if _is_vowel_phone(phone):
            if "1" in str(phone):
                pattern.append(1)
            elif "2" in str(phone):
                pattern.append(2)
            else:
                pattern.append(0)
    if pattern:
        return pattern
    fallback_syllables = max(1, int(fallback_syllables or 1))
    if fallback_syllables == 1:
        return [1]
    return [0] * (fallback_syllables - 1) + [1]


def word_signature(word: str) -> Dict[str, Any]:
    norm = normalize_word(word)
    phones, source = phones_for_word(norm)
    bare = [_strip_phone_stress(phone) for phone in phones]
    vowels = [_strip_phone_stress(phone) for phone in phones if _is_vowel_phone(phone)]
    consonants = [_strip_phone_stress(phone) for phone in phones if not _is_vowel_phone(phone)]
    tail_index = _last_stressed_vowel_index(phones)
    stressed_tail = tuple(_strip_phone_stress(phone) for phone in phones[tail_index:]) if phones else tuple()
    final_phones = tuple(bare[-4:]) if bare else tuple()
    stress = _stress_pattern_from_phones(phones, count_syllables(norm))
    ending_cluster = "".join(ch for ch in norm[-4:] if ch not in "aeiouy")[-3:]
    initial_cluster_match = re.match(r"[^aeiouy]+", norm)
    return {
        "word": norm,
        "display": word,
        "source": source,
        "phones": phones,
        "phones_plain": bare,
        "syllables": max(1, len(stress), count_syllables(norm)),
        "stress_pattern": stress,
        "stress_signature": "".join(str(x) for x in stress),
        "rhyme_key": rhyme_key(norm),
        "stressed_tail": list(stressed_tail),
        "stressed_tail_key": " ".join(stressed_tail),
        "final_phones": list(final_phones),
        "vowel_tail": vowels[-3:],
        "consonant_tail": consonants[-4:],
        "letter_tail": norm[-5:],
        "ending_cluster": ending_cluster,
        "initial_cluster": initial_cluster_match.group(0) if initial_cluster_match else norm[:1],
    }


@lru_cache(maxsize=20000)
def _word_signature_cached(word: str) -> str:
    # Cache through JSON-ish stable text avoided to keep lru simple? Not used directly.
    return word


def _seq_ratio(a: Sequence[Any], b: Sequence[Any]) -> float:
    if not a or not b:
        return 0.0
    a_list = list(a)
    b_list = list(b)
    # Longest common suffix matters more than generic edit distance for rhyme.
    suffix = 0
    for x, y in zip(reversed(a_list), reversed(b_list)):
        if x == y:
            suffix += 1
        else:
            break
    overlap = len(set(a_list) & set(b_list))
    return max(suffix / max(len(a_list), len(b_list)), overlap / max(len(set(a_list) | set(b_list)), 1))


def _letter_suffix_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    suffix = 0
    for x, y in zip(reversed(a), reversed(b)):
        if x == y:
            suffix += 1
        else:
            break
    return min(1.0, suffix / 4.0)


def _stress_compatibility(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    ap = list(a.get("stress_pattern") or [])
    bp = list(b.get("stress_pattern") or [])
    if not ap or not bp:
        return 0.0
    if ap == bp:
        return 1.0
    if ap[-1] == bp[-1]:
        return 0.7
    if len(ap) == len(bp):
        return 0.45
    return 0.15


def rhyme_similarity(target: str | Dict[str, Any], candidate: str | Dict[str, Any]) -> Dict[str, Any]:
    a = word_signature(target) if isinstance(target, str) else target
    b = word_signature(candidate) if isinstance(candidate, str) else candidate
    aw = normalize_word(str(a.get("word") or ""))
    bw = normalize_word(str(b.get("word") or ""))
    if not aw or not bw or aw == bw:
        return {"score": 0, "kind": "texture", "reasons": ["same or empty word"]}

    exact_key = bool(a.get("rhyme_key") and a.get("rhyme_key") == b.get("rhyme_key"))
    tail_exact = bool(a.get("stressed_tail") and a.get("stressed_tail") == b.get("stressed_tail"))
    final_ratio = _seq_ratio(a.get("final_phones") or [], b.get("final_phones") or [])
    vowel_ratio = _seq_ratio(a.get("vowel_tail") or [], b.get("vowel_tail") or [])
    consonant_ratio = _seq_ratio(a.get("consonant_tail") or [], b.get("consonant_tail") or [])
    letter_ratio = _letter_suffix_score(aw, bw)
    stress_ratio = _stress_compatibility(a, b)
    syllable_bonus = 1.0 if int(a.get("syllables") or 1) == int(b.get("syllables") or 1) else 0.35
    cluster_bonus = 1.0 if a.get("ending_cluster") and a.get("ending_cluster") == b.get("ending_cluster") else 0.0

    score = 0.0
    score += 28 if tail_exact else 0
    score += 18 if exact_key else 0
    score += final_ratio * 18
    score += vowel_ratio * 14
    score += consonant_ratio * 10
    score += letter_ratio * 8
    score += stress_ratio * 8
    score += syllable_bonus * 5
    score += cluster_bonus * 5
    score = _pct(score)

    if tail_exact and exact_key and score >= 82:
        kind = "perfect"
    elif exact_key and score >= 68:
        kind = "family"
    elif int(b.get("syllables") or 1) >= 2 and (tail_exact or score >= 72):
        kind = "multisyllable"
    elif vowel_ratio >= 0.55 and consonant_ratio >= 0.35:
        kind = "slant"
    elif vowel_ratio >= 0.55:
        kind = "assonance"
    elif consonant_ratio >= 0.45 or cluster_bonus:
        kind = "consonance"
    else:
        kind = "texture"

    reasons: List[str] = []
    if tail_exact:
        reasons.append("same stressed phone tail")
    if exact_key:
        reasons.append(f"same /{a.get('rhyme_key')}/ family")
    if vowel_ratio >= 0.55:
        reasons.append("strong vowel echo")
    if consonant_ratio >= 0.45 or cluster_bonus:
        reasons.append("consonant tail matches")
    if stress_ratio >= 0.7:
        reasons.append("stress-compatible landing")
    if syllable_bonus >= 1:
        reasons.append("same syllable count")
    if not reasons:
        reasons.append("texture/slant option")
    return {
        "score": score,
        "kind": kind,
        "reasons": unique_preserve(reasons, 5),
        "target_signature": {
            "rhyme_key": a.get("rhyme_key"),
            "stressed_tail": a.get("stressed_tail"),
            "stress_signature": a.get("stress_signature"),
        },
        "candidate_signature": {
            "rhyme_key": b.get("rhyme_key"),
            "stressed_tail": b.get("stressed_tail"),
            "stress_signature": b.get("stress_signature"),
        },
        "components": {
            "tail_exact": tail_exact,
            "rhyme_key": exact_key,
            "final_phone_ratio": _round(final_ratio, 3),
            "vowel_ratio": _round(vowel_ratio, 3),
            "consonant_ratio": _round(consonant_ratio, 3),
            "letter_suffix_ratio": _round(letter_ratio, 3),
            "stress_ratio": _round(stress_ratio, 3),
            "syllable_match": bool(syllable_bonus >= 1),
        },
    }


def _profile_word_pool(profile: Dict[str, Any]) -> List[str]:
    banks = profile.get("word_banks", {}) or {}
    words: List[str] = []
    for name in ("signature", "punch", "images", "actions", "all"):
        words.extend(banks.get(name, []) or [])
    for row in profile.get("top_rhymes", []) or []:
        words.extend(row.get("words", []) or [])
    for bank_name in ("rhyme_bank", "echo_bank"):
        for vals in (profile.get(bank_name, {}) or {}).values():
            words.extend(vals or [])
    words.extend(FALLBACK_RHYME_WORDS)
    words.extend(sorted(CONCRETE_IMAGE_WORDS | CORE_VERBS | PUNCH_WORDS))
    return unique_preserve([normalize_word(w) for w in words if normalize_word(w)], 2200)


def _phrase_pool(profile: Dict[str, Any], limit: int = 400) -> List[str]:
    phrases: List[str] = []
    for row in profile.get("phrases", []) or []:
        phrase = str(row.get("phrase") or "").strip()
        if 2 <= len(tokenize(phrase)) <= 5:
            phrases.append(phrase)
    # Build safe micro-phrases from derived word banks so the engine works in
    # production where phrase samples may be hidden.
    banks = profile.get("word_banks", {}) or {}
    verbs = unique_preserve((banks.get("actions") or []) + list(CORE_VERBS), 16)
    images = unique_preserve((banks.get("images") or []) + list(CONCRETE_IMAGE_WORDS), 24)
    punches = unique_preserve((banks.get("punch") or []) + list(PUNCH_WORDS), 24)
    for verb in verbs[:12]:
        for noun in images[:10]:
            phrases.append(f"{verb} the {noun}")
    for bridge in BRIDGE_PHRASES:
        for punch in punches[:18]:
            phrases.append(f"{bridge} {punch}")
    return unique_preserve(phrases, limit)


def _candidate_rows_for_word(word: str, profile: Dict[str, Any], limit: int = 80) -> List[Dict[str, Any]]:
    target_sig = word_signature(word)
    target = normalize_word(word)
    scored: List[Dict[str, Any]] = []
    base = possible_rhymes_for_word(word, profile, 40)
    priority_words = []
    priority_words.extend(base.get("end_rhymes", []) or [])
    priority_words.extend(base.get("near_rhymes", []) or [])
    priority_words.extend(base.get("internal_echoes", []) or [])
    pool = unique_preserve(priority_words + _profile_word_pool(profile), 2500)
    for candidate in pool:
        c = normalize_word(candidate)
        if not c or c == target or c in STOPWORDS:
            continue
        sim = rhyme_similarity(target_sig, c)
        score = int(sim.get("score") or 0)
        if score < 34:
            continue
        sig = word_signature(c)
        scored.append({
            "word": c,
            "display": c,
            "score": score,
            "kind": sim.get("kind"),
            "rhyme_key": sig.get("rhyme_key"),
            "syllables": sig.get("syllables"),
            "stress_signature": sig.get("stress_signature"),
            "stressed_tail": sig.get("stressed_tail"),
            "reasons": sim.get("reasons", []),
            "components": sim.get("components", {}),
        })
    scored.sort(key=lambda row: (-int(row.get("score", 0)), RHYME_KIND_ORDER.get(str(row.get("kind")), 9), str(row.get("word"))))
    return unique_preserve_dicts(scored, "word", limit)


def unique_preserve_dicts(rows: Iterable[Dict[str, Any]], key: str, limit: int | None = None) -> List[Dict[str, Any]]:
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        value = normalize_word(str(row.get(key, ""))) or str(row.get(key, "")).lower()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(row)
        if limit is not None and len(out) >= limit:
            break
    return out


def _phrase_score(target_word: str, phrase: str) -> Dict[str, Any]:
    words = tokenize(phrase)
    if not words:
        return {"score": 0, "kind": "texture", "reasons": []}
    tail = words[-1]
    sim = rhyme_similarity(target_word, tail)
    score = int(sim.get("score") or 0)
    # Add modest bonus for multisyllable phrase mass and internal repetition.
    phrase_keys = [rhyme_key(w) for w in words if rhyme_key(w)]
    repeated = sum(1 for _, count in Counter(phrase_keys).items() if count > 1)
    score = _pct(score + min(10, max(0, len(words) - 1) * 2 + repeated * 3))
    return {**sim, "score": score, "phrase_end_word": tail}


def _candidate_phrases_for_word(word: str, profile: Dict[str, Any], limit: int = 16) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    target = normalize_word(word)
    for phrase in _phrase_pool(profile, 500):
        words = tokenize(phrase)
        if not words or words[-1] == target:
            continue
        sim = _phrase_score(word, phrase)
        if int(sim.get("score") or 0) < 48:
            continue
        rows.append({
            "phrase": phrase,
            "end_word": words[-1],
            "score": int(sim.get("score") or 0),
            "kind": "multisyllable" if len(words) >= 2 else sim.get("kind"),
            "rhyme_key": rhyme_key(words[-1]),
            "syllables": line_syllables(phrase),
            "word_count": len(words),
            "reasons": unique_preserve(["multiword landing"] + list(sim.get("reasons", [])), 5),
        })
    rows.sort(key=lambda row: (-int(row.get("score", 0)), int(row.get("word_count", 0)), str(row.get("phrase"))))
    return unique_preserve_dicts(rows, "phrase", limit)


def advanced_rhyme_for_word(
    word: str,
    profile: Dict[str, Any] | None = None,
    line_text: str = "",
    mode: str = "match",
    limit: int = 16,
) -> Dict[str, Any]:
    """Return a categorized set of rhyme suggestions for one target word."""
    profile = profile or get_corpus_profile()
    target = normalize_word(word)
    if not target:
        return {"available": False, "error": "No word supplied."}
    signature = word_signature(target)
    scored = _candidate_rows_for_word(target, profile, limit=120)

    def by_kind(*kinds: str, n: int = limit) -> List[Dict[str, Any]]:
        return [row for row in scored if str(row.get("kind")) in kinds][:n]

    exact = [row for row in scored if row.get("components", {}).get("tail_exact")][:limit]
    family = by_kind("perfect", "family", "multisyllable", n=limit)
    slant = by_kind("slant", n=limit)
    assonance = by_kind("assonance", n=limit)
    consonance = by_kind("consonance", n=limit)
    stress_matched = [row for row in scored if row.get("stress_signature") == signature.get("stress_signature")][:limit]
    phrase_rows = _candidate_phrases_for_word(target, profile, limit=limit)

    # If any category is sparse, promote high-scoring rows instead of returning blanks.
    if not family:
        family = scored[:limit]
    if not slant:
        slant = [row for row in scored if row not in family][:limit]
    if not assonance:
        assonance = [row for row in scored if row.get("components", {}).get("vowel_ratio", 0) >= 0.35][:limit]
    if not consonance:
        consonance = [row for row in scored if row.get("components", {}).get("consonant_ratio", 0) >= 0.3][:limit]

    internal_echoes = unique_preserve(
        [row["word"] for row in scored if int(row.get("score", 0)) >= 48 and row.get("word") not in WEAK_END_WORDS],
        limit,
    )
    end_options = unique_preserve([row["word"] for row in family + slant + scored if row.get("word") not in WEAK_END_WORDS], limit)
    near_options = unique_preserve([row["word"] for row in slant + assonance + consonance], limit)
    phrase_options = unique_preserve([row["phrase"] for row in phrase_rows], limit)

    blueprints = list(RHYME_BLUEPRINTS)
    if mode == "break":
        blueprints.insert(0, "Use a related slant rhyme instead of the most obvious family match to avoid repeating your usual ending.")
    if line_text:
        blueprints.insert(0, f"Target the current landing “{target}”: add one echo before it, then decide whether to keep or rotate the final family.")

    return {
        "available": True,
        "target_word": target,
        "signature": signature,
        "summary": {
            "candidate_count": len(scored),
            "best_score": scored[0]["score"] if scored else 0,
            "best_kind": scored[0]["kind"] if scored else "none",
            "rhyme_key": signature.get("rhyme_key"),
            "stress_signature": signature.get("stress_signature"),
            "syllables": signature.get("syllables"),
            "engine": "cmudict+heuristic" if _cmu_index() else "heuristic",
        },
        "word_lists": {
            "end_rhymes": end_options,
            "near_rhymes": near_options,
            "slant_rhymes": unique_preserve([row["word"] for row in slant], limit),
            "assonance_words": unique_preserve([row["word"] for row in assonance], limit),
            "consonance_words": unique_preserve([row["word"] for row in consonance], limit),
            "internal_echoes": internal_echoes,
            "stress_matched": unique_preserve([row["word"] for row in stress_matched], limit),
            "multi_syllable_endings": phrase_options,
        },
        "ranked": scored[:limit],
        "perfect_or_family": family[:limit],
        "slant": slant[:limit],
        "assonance": assonance[:limit],
        "consonance": consonance[:limit],
        "stress_matched": stress_matched[:limit],
        "multi_syllable": phrase_rows[:limit],
        "rhyme_ladder": [
            {"stage": "1. Tight family", "use_when": "You want the chain to feel locked.", "options": unique_preserve([row["word"] for row in family], 8)},
            {"stage": "2. Slant turn", "use_when": "You want movement without abandoning the sound.", "options": unique_preserve([row["word"] for row in slant], 8)},
            {"stage": "3. Multi-syllable landing", "use_when": "You want the ending to feel more technical.", "options": phrase_options[:8]},
            {"stage": "4. Internal setup", "use_when": "The end word is good but the bar needs motion before it.", "options": internal_echoes[:8]},
        ],
        "blueprints": unique_preserve(blueprints, 6),
    }


def _replace_last_word(line: str, new_word: str) -> str:
    if not line or not new_word:
        return line
    matches = list(WORD_OR_PHRASE_RE.finditer(line))
    if not matches:
        return new_word
    last = matches[-1]
    return line[:last.start()] + str(new_word).strip() + line[last.end():]


def _insert_before_last_word(line: str, phrase: str) -> str:
    phrase = str(phrase or "").strip()
    if not line or not phrase:
        return line
    matches = list(WORD_OR_PHRASE_RE.finditer(line))
    if not matches:
        return f"{line} {phrase}".strip()
    last = matches[-1]
    space_before = "" if last.start() == 0 or line[last.start() - 1].isspace() else " "
    return (line[:last.start()] + phrase + space_before + line[last.start():]).strip()


def _replace_tail_phrase(line: str, phrase: str, tail_words: int = 2) -> str:
    matches = list(WORD_OR_PHRASE_RE.finditer(line))
    if not matches:
        return phrase
    start_match = matches[-min(tail_words, len(matches))]
    return (line[:start_match.start()] + str(phrase).strip() + line[matches[-1].end():]).strip()


def _rhyme_power_score(detail: Dict[str, Any], word_report: Dict[str, Any], end_counts: Counter | None = None) -> Dict[str, Any]:
    end = normalize_word(detail.get("end_word", ""))
    score = 35
    if end and end not in WEAK_END_WORDS:
        score += 14
    if detail.get("internal_rhymes"):
        score += min(18, len(detail.get("internal_rhymes") or []) * 7)
    if detail.get("alliteration"):
        score += min(10, len(detail.get("alliteration") or []) * 4)
    best = (word_report.get("summary") or {}).get("best_score", 0)
    score += min(18, int(best) // 7)
    if end_counts and end and end_counts.get(end, 0) > 1:
        score -= min(18, (end_counts[end] - 1) * 7)
    if end in WEAK_END_WORDS:
        score -= 15
    return {
        "score": _pct(score),
        "label": "heavy" if score >= 78 else "stable" if score >= 60 else "light" if score >= 42 else "weak",
    }


def advanced_rhyme_for_line(
    detail: Dict[str, Any],
    profile: Dict[str, Any] | None = None,
    mode: str = "match",
    end_counts: Counter | None = None,
    previous_detail: Dict[str, Any] | None = None,
    next_detail: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    profile = profile or get_corpus_profile()
    line = str(detail.get("text") or "")
    end = normalize_word(str(detail.get("end_word") or line_end_word(line)))
    if not end:
        return {"available": False, "error": "Line has no end word."}
    word_report = advanced_rhyme_for_word(end, profile=profile, line_text=line, mode=mode, limit=14)
    lists = word_report.get("word_lists", {}) or {}
    power = _rhyme_power_score(detail, word_report, end_counts=end_counts)
    end_count = int((end_counts or Counter()).get(end, 0))

    actions: List[str] = []
    if end in WEAK_END_WORDS:
        actions.append("Move a heavier noun/concept to the end; the current landing is a connector or pronoun.")
    if end_count > 1:
        actions.append(f"The end word repeats {end_count} times; keep the family but rotate the exact word.")
    if not detail.get("internal_rhymes") and int(detail.get("word_count") or 0) >= 8:
        actions.append("Add one internal echo before the final third of the line.")
    if power["score"] < 58:
        actions.append("Upgrade the landing from a light rhyme to at least a slant/family rhyme.")
    if previous_detail and previous_detail.get("rhyme_key") == detail.get("rhyme_key"):
        actions.append("Previous line already uses this family; either continue the chain deliberately or rotate on the next line.")
    if next_detail and next_detail.get("rhyme_key") == detail.get("rhyme_key"):
        actions.append("Next line resolves this family; protect this landing and add internal motion instead of changing the end.")
    if not actions:
        actions.append("The rhyme landing is usable; upgrade it with a multi-syllable setup or an internal echo.")

    patches: List[Dict[str, Any]] = []
    if lists.get("end_rhymes"):
        new_word = lists["end_rhymes"][0]
        patches.append({
            "type": "replace_line",
            "operation": "advanced_end_swap",
            "label": f"Rhyme swap → {new_word}",
            "replacement": _replace_last_word(line, new_word),
            "why": "Keeps the sentence frame but changes the landing to a stronger scored rhyme option.",
        })
    if lists.get("internal_echoes"):
        echo = lists["internal_echoes"][0]
        bridge = BRIDGE_PHRASES[0]
        patches.append({
            "type": "replace_line",
            "operation": "advanced_internal_echo",
            "label": f"Add internal echo → {echo}",
            "replacement": _insert_before_last_word(line, f"{bridge} {echo}"),
            "why": "Builds a mid-bar sound pocket before the end rhyme.",
        })
    if lists.get("multi_syllable_endings"):
        phrase = lists["multi_syllable_endings"][0]
        patches.append({
            "type": "replace_line",
            "operation": "advanced_multi_end",
            "label": f"Multi-syllable end → {phrase}",
            "replacement": _replace_tail_phrase(line, phrase, tail_words=2),
            "why": "Turns the last beat into a multiword rhyme landing.",
        })
    if lists.get("slant_rhymes"):
        slant = lists["slant_rhymes"][0]
        patches.append({
            "type": "replace_line",
            "operation": "advanced_slant_turn",
            "label": f"Slant turn → {slant}",
            "replacement": _replace_last_word(line, slant),
            "why": "Uses a related sound instead of the obvious family to make the chain move.",
        })

    # Remove duplicates and add syllable deltas.
    clean_patches = []
    seen_replacements = set()
    original_syllables = line_syllables(line)
    for patch in patches:
        repl = str(patch.get("replacement") or "").strip()
        if not repl or repl == line or repl.lower() in seen_replacements:
            continue
        seen_replacements.add(repl.lower())
        patch["syllables"] = line_syllables(repl)
        patch["delta_syllables"] = patch["syllables"] - original_syllables
        clean_patches.append(patch)

    chain_note = "single-use family"
    if end_counts:
        family_count = int(sum(1 for _ in [1] if detail.get("rhyme_key")))
        # The family count is computed by caller in whole-lab mode; this fallback
        # is still useful for line-only calls.
        if end_count > 1:
            chain_note = f"repeated exact end word ×{end_count}"
        elif previous_detail and previous_detail.get("rhyme_key") == detail.get("rhyme_key"):
            chain_note = "continues previous-line rhyme family"
        elif next_detail and next_detail.get("rhyme_key") == detail.get("rhyme_key"):
            chain_note = "sets up next-line rhyme family"
        else:
            _ = family_count

    return {
        "available": True,
        "line_number": detail.get("number"),
        "text": line,
        "end_word": end,
        "rhyme_key": detail.get("rhyme_key") or rhyme_key(end),
        "rhyme_power": power,
        "chain_note": chain_note,
        "word_report": word_report,
        "actions": unique_preserve(actions, 7),
        "patches": clean_patches[:5],
        "word_lists": lists,
        "ranked_options": word_report.get("ranked", [])[:12],
        "rhyme_ladder": word_report.get("rhyme_ladder", []),
        "blueprints": word_report.get("blueprints", []),
    }


def _entropy(counter: Counter) -> Dict[str, Any]:
    clean = Counter({str(k): int(v) for k, v in counter.items() if str(k) and int(v) > 0})
    total = sum(clean.values())
    if total <= 0:
        return {"entropy_bits": 0.0, "perplexity": 0.0, "unique": 0, "top": []}
    ent = 0.0
    for count in clean.values():
        p = count / total
        ent -= p * math.log2(p)
    top = []
    for key, count in clean.most_common(12):
        p = count / total
        top.append({"key": key, "count": count, "pct": _round(p * 100, 1), "bits": _round(-math.log2(p), 2)})
    return {"entropy_bits": _round(ent, 3), "perplexity": _round(2 ** ent, 2), "unique": len(clean), "top": top}


def _scheme_transitions(details: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for prev, cur in zip(details, details[1:]):
        pk = str(prev.get("rhyme_key") or "")
        ck = str(cur.get("rhyme_key") or "")
        if not pk or not ck:
            continue
        move = "repeat" if pk == ck else "turn"
        rows.append({
            "from_line": prev.get("number"),
            "to_line": cur.get("number"),
            "from_key": pk,
            "to_key": ck,
            "move": move,
            "label": f"/{pk}/ → /{ck}/",
        })
    return rows


def _scheme_recommendations(details: Sequence[Dict[str, Any]], rhyme_counts: Counter, end_counts: Counter) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    total = max(1, len([d for d in details if d.get("rhyme_key")]))
    repeated_families = [key for key, count in rhyme_counts.items() if count > 1]
    if not repeated_families:
        notes.append({
            "title": "Choose an anchor family",
            "detail": "Almost every ending is single-use. Pick one strong family and repeat it for two or four lines so the listener can hear the scheme.",
            "line_numbers": [],
        })
    for key, count in rhyme_counts.most_common(3):
        pct = count / total
        if pct >= 0.33 and total >= 6:
            lines = [int(d.get("number") or 0) for d in details if d.get("rhyme_key") == key]
            notes.append({
                "title": f"Rotate the /{key}/ family",
                "detail": f"/{key}/ owns {int(round(pct * 100))}% of the current endings. Keep it for hooks or punch lines, but rotate one verse line to a slant family.",
                "line_numbers": lines[:8],
            })
    repeated_words = [word for word, count in end_counts.items() if count > 1 and word not in WEAK_END_WORDS]
    if repeated_words:
        notes.append({
            "title": "Same end word repeats",
            "detail": "The rhyme family can repeat, but the exact final word should usually rotate unless it is a hook.",
            "line_numbers": [int(d.get("number") or 0) for d in details if d.get("end_word") in repeated_words][:10],
        })
    transitions = _scheme_transitions(details)
    repeat_runs = []
    current: List[int] = []
    last_key = None
    for detail in details:
        key = detail.get("rhyme_key")
        if key and key == last_key:
            current.append(int(detail.get("number") or 0))
        else:
            if len(current) >= 3:
                repeat_runs.append(current[:])
            current = [int(detail.get("number") or 0)] if key else []
            last_key = key
    if len(current) >= 3:
        repeat_runs.append(current)
    for run in repeat_runs[:3]:
        notes.append({
            "title": "Long consecutive rhyme run",
            "detail": "A long repeated-family run creates pressure. Add internal changes or break the family at the fourth line to avoid monotony.",
            "line_numbers": run,
        })
    if transitions:
        turn_pct = sum(1 for row in transitions if row["move"] == "turn") / max(1, len(transitions))
        if turn_pct > 0.82:
            notes.append({
                "title": "Too many rhyme turns",
                "detail": "The scheme turns almost every line. Pair two adjacent lines with a shared family to create a stronger pocket.",
                "line_numbers": [],
            })
        elif turn_pct < 0.28 and len(transitions) >= 6:
            notes.append({
                "title": "Scheme may be too locked",
                "detail": "You repeat families often. Use one slant turn or contrast family every four lines for release.",
                "line_numbers": [],
            })
    if not notes:
        notes.append({
            "title": "Rhyme scheme is balanced",
            "detail": "The draft has a workable blend of repeated families and fresh turns. Improve individual landings and internal echoes.",
            "line_numbers": [],
        })
    return notes[:8]


def _family_ladders_from_details(details: Sequence[Dict[str, Any]], profile: Dict[str, Any]) -> List[Dict[str, Any]]:
    counts = Counter(str(d.get("rhyme_key") or "") for d in details if d.get("rhyme_key"))
    ladders: List[Dict[str, Any]] = []
    for key, count in counts.most_common(8):
        landing_words = unique_preserve([d.get("end_word", "") for d in details if d.get("rhyme_key") == key], 8)
        seed = landing_words[0] if landing_words else key
        report = advanced_rhyme_for_word(seed, profile=profile, limit=10)
        ladders.append({
            "rhyme_key": key,
            "count": count,
            "current_end_words": landing_words,
            "direct_options": (report.get("word_lists") or {}).get("end_rhymes", [])[:8],
            "slant_options": (report.get("word_lists") or {}).get("slant_rhymes", [])[:8],
            "multi_syllable_options": (report.get("word_lists") or {}).get("multi_syllable_endings", [])[:8],
            "internal_echo_options": (report.get("word_lists") or {}).get("internal_echoes", [])[:8],
        })
    return ladders


def build_rhyme_suggestion_lab(
    lyrics: str,
    mode: str = "match",
    active_line: int | None = None,
    profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    profile = profile or get_corpus_profile()
    details = build_line_details(lyrics)
    if not details:
        return {"available": False, "error": "Paste lyrics before running the rhyme lab."}
    end_counts = Counter(d.get("end_word") for d in details if d.get("end_word"))
    rhyme_counts = Counter(d.get("rhyme_key") for d in details if d.get("rhyme_key"))
    word_counts = Counter(w for d in details for w in d.get("content_words", []))
    transitions = _scheme_transitions(details)

    # Active line is nearest editable line.
    line_numbers = [int(d.get("number") or 0) for d in details]
    if active_line and line_numbers:
        chosen = min(line_numbers, key=lambda n: abs(n - int(active_line)))
    else:
        chosen = line_numbers[0] if line_numbers else None

    by_no = {int(d.get("number") or 0): d for d in details}
    line_reports: List[Dict[str, Any]] = []
    for i, detail in enumerate(details):
        prev_d = details[i - 1] if i > 0 else None
        next_d = details[i + 1] if i + 1 < len(details) else None
        report = advanced_rhyme_for_line(detail, profile=profile, mode=mode, end_counts=end_counts, previous_detail=prev_d, next_detail=next_d)
        key = str(detail.get("rhyme_key") or "")
        report["family_count_in_draft"] = int(rhyme_counts.get(key, 0)) if key else 0
        report["exact_end_count_in_draft"] = int(end_counts.get(detail.get("end_word"), 0)) if detail.get("end_word") else 0
        report["active"] = bool(chosen and int(detail.get("number") or 0) == chosen)
        line_reports.append(report)

    active_report = next((row for row in line_reports if row.get("active")), line_reports[0])
    rhyme_entropy = _entropy(rhyme_counts)
    end_entropy = _entropy(end_counts)
    transition_entropy = _entropy(Counter(row["label"] for row in transitions))
    avg_power = _round(sum((row.get("rhyme_power") or {}).get("score", 0) for row in line_reports) / max(1, len(line_reports)), 1)
    weak_lines = [row.get("line_number") for row in line_reports if (row.get("rhyme_power") or {}).get("score", 0) < 52]
    repeated_exact = [word for word, count in end_counts.items() if count > 1]

    # Compare to profile-only reference shape without using raw lyrics.
    profile_top_keys = [row.get("key") for row in profile.get("top_rhymes", [])[:12] if row.get("key")]
    overlap = len(set(rhyme_counts) & set(profile_top_keys)) / max(1, len(set(rhyme_counts)))

    return {
        "available": True,
        "report_type": "advanced_rhyme_suggestion_lab",
        "mode": mode,
        "summary": {
            "lines": len(details),
            "unique_rhyme_families": len(rhyme_counts),
            "repeated_rhyme_families": sum(1 for count in rhyme_counts.values() if count > 1),
            "unique_end_words": len(end_counts),
            "repeated_exact_end_words": len(repeated_exact),
            "avg_rhyme_power": avg_power,
            "weak_rhyme_lines": weak_lines[:12],
            "corpus_rhyme_key_overlap_pct": _round(overlap * 100, 1),
            "rhyme_entropy_bits": rhyme_entropy.get("entropy_bits", 0),
            "rhyme_perplexity": rhyme_entropy.get("perplexity", 0),
        },
        "active_line_number": chosen,
        "active_report": active_report,
        "line_reports": line_reports,
        "scheme": {
            "rhyme_entropy": rhyme_entropy,
            "end_word_entropy": end_entropy,
            "transition_entropy": transition_entropy,
            "transitions": transitions[:80],
            "recommendations": _scheme_recommendations(details, rhyme_counts, end_counts),
        },
        "family_ladders": _family_ladders_from_details(details, profile),
        "top_content_words": [{"word": w, "count": c} for w, c in word_counts.most_common(20)],
        "sections": section_blocks(lyrics),
        "corpus_targets": {
            "top_rhyme_families": profile.get("top_rhymes", [])[:14],
            "signature_rhyme_words": unique_preserve([w for row in profile.get("top_rhymes", [])[:10] for w in row.get("words", [])], 40),
            "note": "Targets are derived from the compiled style profile and do not require raw corpus text in production.",
        },
    }


def compact_word_lists(report: Dict[str, Any], limit: int = 10) -> Dict[str, List[str]]:
    """Convert an advanced line/word report into the simple word-bank shape."""
    lists = report.get("word_lists") or (report.get("word_report", {}).get("word_lists") if report.get("word_report") else {}) or {}
    return {
        "end_rhymes": list(lists.get("end_rhymes") or [])[:limit],
        "near_rhymes": list(lists.get("near_rhymes") or [])[:limit],
        "slant_rhymes": list(lists.get("slant_rhymes") or [])[:limit],
        "assonance_words": list(lists.get("assonance_words") or [])[:limit],
        "consonance_words": list(lists.get("consonance_words") or [])[:limit],
        "internal_echoes": list(lists.get("internal_echoes") or [])[:limit],
        "stress_matched": list(lists.get("stress_matched") or [])[:limit],
        "multi_syllable_endings": list(lists.get("multi_syllable_endings") or [])[:limit],
    }
