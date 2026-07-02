"""Strict highlighted-word rhyme suggestions for the live writer.

This module fixes the selected/highlighted-word rhyme panel by separating true
phonetic rhymes from looser rap texture matches. It intentionally avoids the old
"same suffix key = rhyme" shortcut that could put words like ``projects`` next to
``bits`` or ``father`` next to ``bar`` as if they were clean rhymes.
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

try:
    import cmudict  # type: ignore
except Exception:  # pragma: no cover
    cmudict = None  # type: ignore

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")
VOWELS = set("AEIOUY")
PHONE_STRESS_RE = re.compile(r"\d")
LETTER_VOWELS = "aeiouy"

# High-value rap/style slant families from the user's corpus. These are allowed
# only when the phonetic score passes the gate, and they are labeled as style
# slants rather than clean perfect rhymes.
STYLE_NEIGHBORS: Dict[str, List[str]] = {
    "surface": ["service", "purpose", "purchase", "circus", "nervous", "surplus", "verses", "universe", "reverse", "rehearse", "curse"],
    "service": ["surface", "purpose", "purchase", "circus", "nervous", "surplus", "verses", "universe", "reverse", "rehearse", "curse"],
    "purpose": ["surface", "service", "purchase", "circus", "nervous", "surplus", "verses", "universe", "reverse", "rehearse", "curse"],
    "purchase": ["surface", "service", "purpose", "circus", "nervous", "surplus", "verses", "universe", "reverse", "rehearse", "curse"],
    "music": ["cubic", "acoustic", "amuses", "excuses", "uses", "crucial", "lyric", "lyrics", "physics", "critics", "civic", "clinic", "logic", "rhythmic"],
    "lyric": ["lyrics", "physics", "critics", "civic", "clinic", "logic", "rhythmic", "specific", "music"],
    "lyrics": ["lyric", "physics", "critics", "civic", "clinic", "logic", "rhythmic", "specific", "music"],
    "diction": ["friction", "restriction", "direction", "description", "definition", "precision", "decision", "vision", "section", "action", "attention", "expression", "reflection", "projection"],
    "sentence": ["presence", "essence", "resonance", "evidence", "confidence", "dominance", "distance", "instance", "entrance", "patience"],
    "presence": ["sentence", "essence", "resonance", "evidence", "confidence", "dominance", "distance", "instance", "entrance", "patience"],
    "confidence": ["consonance", "dominance", "prominence", "providence", "evidence", "residence", "resonance", "ordinance"],
    "dominance": ["consonance", "confidence", "prominence", "providence", "evidence", "residence", "resonance", "ordinance"],
    "moron": ["oxymoron", "boron", "florin", "foreign", "warren"],
}


# Broader rap-family groups. These are intentionally wider than perfect
# dictionary rhymes: they model how rappers chain assonance, consonance,
# suffix texture, and recurring motif families.  They are never displayed as
# "perfect" rhymes; the UI labels them as broad family/style slant so the user
# can decide whether the looseness fits the pocket.
BROAD_RHYME_FAMILIES: Dict[str, List[str]] = {
    "sentence / presence / resonance": [
        "sentence", "sentences", "presence", "essence", "resonance", "evidence", "confidence",
        "dominance", "consonance", "prominence", "providence", "ordinance", "relevance",
        "reticence", "decadence", "eloquence", "diligence", "intimate", "infinite",
    ],
    "surface / purpose / universe": [
        "surface", "service", "purpose", "purchase", "circus", "surplus", "nervous",
        "verse", "verses", "curse", "curses", "reverse", "rehearse", "universe", "substance",
        "numbers", "covers", "sum", "sums", "works", "earth", "dirt", "search",
    ],
    "diction / direction / precision": [
        "diction", "friction", "fiction", "restriction", "prediction", "conviction", "depiction",
        "description", "definition", "direction", "section", "reflection", "projection", "selection",
        "correction", "perfection", "attention", "intention", "precision", "decision", "vision",
        "mission", "submission", "expression", "impression", "intermission",
    ],
    "music / lyrics / physics": [
        "music", "amuses", "amusing", "uses", "excuses", "confusing", "allusion", "solution",
        "conclusion", "motion", "emotion", "smoothly", "soothes", "lyric", "lyrics", "physics",
        "critics", "specific", "civic", "clinic", "logic", "rhythmic", "schematics", "mathematics",
        "acoustic", "cubic",
    ],
    "system / rhythm / hidden": [
        "system", "rhythm", "wisdom", "christen", "glisten", "listen", "written", "hidden",
        "digits", "tickets", "clinic", "specific", "minute", "infinite", "intimate",
        "mission", "submission", "tradition", "edition", "condition",
    ],
    "credit / edit / threaded": [
        "credit", "debit", "edit", "reddit", "method", "merit", "inherit", "embedded",
        "threaded", "vetted", "tested", "rested", "registered", "deficit", "benefit",
    ],
    "paradise / price / disguise": [
        "ice", "dice", "price", "precise", "device", "advice", "twice", "slice", "spice",
        "paradise", "sacrifice", "disguise", "surprise", "rise", "skies", "eyes", "wise",
    ],
    "recipe / destiny / energy": [
        "recipe", "destiny", "energy", "legacy", "company", "melody", "fantasy", "gravity",
        "mentally", "carefully", "heavily", "steadily", "readily", "pedigree", "bravery", "savory",
    ],
    "walking / talking / consonance": [
        "walking", "talking", "stalking", "polishing", "demolishing", "auditing",
        "promises", "monuments", "confidence", "consonants", "consonance", "dominance",
    ],
    "projects / context / complex": [
        "projects", "objects", "subjects", "prospect", "object", "project", "complex",
        "context", "pretext", "perplexed", "contest", "process", "progress", "logic",
    ],
    "moron / oxymoron / nuisance": [
        "moron", "oxymoron", "boron", "foreign", "foregone", "father", "bother", "author",
        "dollars", "scholars", "nuisance", "influence", "intrusive", "confusion", "conclusion",
    ],
}

BROAD_FAMILY_LOOKUP: Dict[str, str] = {}
for _family_name, _family_words in BROAD_RHYME_FAMILIES.items():
    for _family_word in _family_words:
        BROAD_FAMILY_LOOKUP.setdefault(_family_word, _family_name)


def _broad_family_name(target: str, candidate: str) -> str:
    t = normalize_word(target)
    c = normalize_word(candidate)
    if not t or not c:
        return ""
    if BROAD_FAMILY_LOOKUP.get(t) and BROAD_FAMILY_LOOKUP.get(t) == BROAD_FAMILY_LOOKUP.get(c):
        return BROAD_FAMILY_LOOKUP[t]
    # Multisyllable/suffix heuristic for invented or corpus-specific words that
    # are not explicitly listed above. This is intentionally conservative: it
    # requires a shared final vowel-ish spelling chunk of at least 4 characters.
    for size in (7, 6, 5, 4):
        if len(t) >= size and len(c) >= size and t[-size:] == c[-size:]:
            return f"suffix family /{t[-size:]}/"
    return ""


def broad_family_candidates(target: str) -> List[str]:
    target = normalize_word(target)
    family = BROAD_FAMILY_LOOKUP.get(target, "")
    if not family:
        return []
    return [w for w in BROAD_RHYME_FAMILIES.get(family, []) if normalize_word(w) != target]


COMMON_FALLBACKS = [
    "sentence", "presence", "essence", "resonance", "evidence", "medicine", "venom", "system",
    "rhythm", "signal", "script", "surface", "purpose", "service", "universe", "reverse",
    "credit", "method", "vector", "texture", "pressure", "precision", "signature", "structure",
    "picture", "scripture", "mixture", "friction", "diction", "direction", "projection", "reflection",
    "dominance", "consonance", "confidence", "monuments", "documents", "elements", "delicate",
    "intricate", "infinite", "intimate", "significant", "digital", "physical", "criminal", "critical",
    "lyrics", "physics", "schematics", "mathematics", "paradise", "device", "price", "dice",
    "spark", "dark", "mark", "heart", "start", "part", "art", "cards",
    "thread", "spread", "debt", "fed", "vetted", "embedded", "tested", "rested",
    "clear", "near", "fear", "sphere", "frontier", "career", "engineer", "pioneer",
    "bother", "father", "farther", "rather", "gather", "weather", "other",
    "objects", "projects", "subjects", "context", "complex", "prospect", "contest",
]

# Curated common endings keep the selected-word panel useful without exposing
# obscure CMU names as the top results.  The keys are ARPABET rhyming tails after
# stress digits are stripped.
COMMON_TAIL_RHYMES: Dict[str, List[str]] = {
    "AY S": ["ice", "dice", "nice", "price", "slice", "spice", "twice", "vice", "advice", "device", "precise", "paradise", "sacrifice", "entice"],
    "AY Z": ["rise", "wise", "eyes", "skies", "tries", "lies", "surprise", "disguise", "demise", "advise", "revise", "emphasize"],
    "IH R": ["clear", "near", "fear", "hear", "dear", "sphere", "appear", "career", "frontier", "sincere", "engineer", "pioneer", "interfere"],
    "IY M Z": ["dreams", "beams", "seems", "schemes", "streams", "teams", "themes", "regimes"],
    "IY M": ["dream", "beam", "seem", "scheme", "stream", "team", "theme", "regime"],
    "IH NG": ["king", "ring", "sing", "bring", "thing", "sting", "wing", "swing", "spring", "string"],
    "OW L D": ["gold", "old", "bold", "cold", "fold", "hold", "mold", "sold", "told", "rolled"],
    "AA DH ER": ["father", "bother"],
    "AA R DH ER": ["farther", "father", "harder", "starter", "martyr"],
    "AA JH EH K T S": ["projects", "objects", "subjects"],
    "AA B JH EH K T S": ["objects", "projects", "subjects"],
    "IH K SH AH N": ["fiction", "friction", "diction", "prediction", "addiction", "depiction", "conviction", "restriction"],
    "EH K SH AH N": ["section", "direction", "reflection", "projection", "connection", "selection", "correction", "perfection"],
    "EH N T AH N S": ["sentence", "repentance"],
    "EH Z AH N S": ["presence", "resonance"],
    "EH S AH N S": ["essence"],
    "ER F AH S": ["surface", "resurface"],
    "ER V AH S": ["service"],
    "ER P AH S": ["purpose", "multipurpose"],
    "UW Z IH K": ["music"],
    "AO R AA N": ["moron", "boron", "oxymoron"],
}

COMMON_WORDS = set(COMMON_FALLBACKS)
for _vals in COMMON_TAIL_RHYMES.values():
    COMMON_WORDS.update(_vals)
for _vals in STYLE_NEIGHBORS.values():
    COMMON_WORDS.update(_vals)
for _vals in BROAD_RHYME_FAMILIES.values():
    COMMON_WORDS.update(_vals)

BAD_SUGGESTIONS = {
    "a", "i", "the", "and", "or", "but", "to", "of", "in", "on", "for", "with", "that", "this",
    "your", "you", "me", "my", "it", "its", "is", "are", "was", "were", "be", "been",
}


def normalize_word(word: str) -> str:
    word = str(word or "").lower().replace("’", "'").replace("‘", "'")
    word = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", word)
    return word


def tokenize(text: str) -> List[str]:
    return [normalize_word(m.group(0)) for m in TOKEN_RE.finditer(str(text or "")) if normalize_word(m.group(0))]


def _load_profile() -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / "data" / "corpus_profile.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


@lru_cache(maxsize=1)
def profile() -> Dict[str, Any]:
    return _load_profile()


def unique_keep(items: Iterable[Any], limit: int = 24, exclude: str | None = None) -> List[str]:
    seen = set()
    out: List[str] = []
    ex = normalize_word(exclude or "")
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        # Keep phrases but compare normalized tail/whole phrase for uniqueness.
        key = normalize_word(text) or " ".join(tokenize(text))
        if not key or key == ex or key in seen or key in BAD_SUGGESTIONS:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


@lru_cache(maxsize=1)
def cmu_dictionary() -> Dict[str, List[List[str]]]:
    if cmudict is None:
        return {}
    try:
        return {str(k).lower(): [list(p) for p in v] for k, v in cmudict.dict().items()}
    except Exception:
        return {}


def _strip_stress(phone: str) -> str:
    return PHONE_STRESS_RE.sub("", str(phone or ""))


def _is_vowel(phone: str) -> bool:
    bare = _strip_stress(phone)
    return bool(bare) and bare[0] in VOWELS and any(ch.isdigit() for ch in str(phone))


def _fallback_phones(word: str) -> List[str]:
    word = normalize_word(word)
    if not word:
        return []
    # Suffix-aware fallbacks for common rap endings.
    suffix_map = [
        ("tion", ["SH", "AH1", "N"]), ("sion", ["ZH", "AH1", "N"]),
        ("ence", ["AH1", "N", "S"]), ("ance", ["AH1", "N", "S"]),
        ("ics", ["IH1", "K", "S"]), ("ic", ["IH1", "K"]),
        ("ing", ["IH1", "NG"]), ("ight", ["AY1", "T"]), ("ice", ["AY1", "S"]),
        ("ise", ["AY1", "Z"]), ("ize", ["AY1", "Z"]), ("ear", ["IH1", "R"]),
        ("eer", ["IH1", "R"]), ("air", ["EH1", "R"]), ("are", ["EH1", "R"]),
        ("old", ["OW1", "L", "D"]), ("ame", ["EY1", "M"]), ("ime", ["AY1", "M"]),
    ]
    for suffix, phones in suffix_map:
        if word.endswith(suffix):
            return phones
    chunks = re.findall(r"[aeiouy]+|[^aeiouy]+", word)
    phones: List[str] = []
    for chunk in chunks:
        if re.fullmatch(r"[aeiouy]+", chunk):
            vowel = chunk[-1]
            vowel_phone = {
                "a": "AE1", "e": "EH1", "i": "IH1", "o": "OW1", "u": "UW1", "y": "IY1",
            }.get(vowel, "AH1")
            phones.append(vowel_phone)
        else:
            phones.extend([ch.upper() for ch in chunk if ch.isalpha()])
    return phones or [word.upper() + "1"]


def candidate_keys(word: str) -> List[str]:
    word = normalize_word(word)
    keys = [word]
    if word.endswith("s") and len(word) > 4:
        keys.append(word[:-1])
    if word.endswith("es") and len(word) > 5:
        keys.append(word[:-2])
    if word.endswith("ed") and len(word) > 5:
        keys.append(word[:-2])
    if word.endswith("in'"):
        keys.append(word[:-3] + "ing")
    if "-" in word:
        keys.extend(part for part in word.split("-") if part)
    return unique_keep(keys, 8)


def phones_for_word(word: str) -> Tuple[List[str], str]:
    cmu = cmu_dictionary()
    for key in candidate_keys(word):
        entries = cmu.get(key)
        if entries:
            # Prefer entries with more syllables/stress marks; that usually keeps
            # noun/verb variants useful for rap endings.
            phones = max(entries, key=lambda p: sum(1 for ph in p if any(ch.isdigit() for ch in ph)))
            return list(phones), "cmudict"
    return _fallback_phones(word), "heuristic"


def _vowel_indexes(phones: Sequence[str]) -> List[int]:
    return [i for i, ph in enumerate(phones) if _is_vowel(ph)]


def _last_stressed_vowel_idx(phones: Sequence[str]) -> int:
    vowels = _vowel_indexes(phones)
    if not vowels:
        return max(0, len(phones) - 1)
    # For rap/rhyme endings, the final stressed vowel should drive the landing.
    # CMU often marks words such as "paradise" as P EH1 R AH0 D AY2 S; using
    # only primary stress would incorrectly rhyme on "EH R AH D AY S" instead
    # of the actual final landing "AY S".
    stressed = [i for i in vowels if "1" in str(phones[i]) or "2" in str(phones[i])]
    if stressed:
        return stressed[-1]
    return vowels[-1]


def _bare(phones: Sequence[str]) -> List[str]:
    return [_strip_stress(p) for p in phones]


def _rhyming_tail(phones: Sequence[str]) -> Tuple[str, ...]:
    if not phones:
        return tuple()
    idx = _last_stressed_vowel_idx(phones)
    return tuple(_bare(phones[idx:]))


def _last_vowel(phones: Sequence[str]) -> str:
    vowels = [_strip_stress(phones[i]) for i in _vowel_indexes(phones)]
    return vowels[-1] if vowels else ""


def _last_two_vowels(phones: Sequence[str]) -> Tuple[str, ...]:
    vowels = [_strip_stress(phones[i]) for i in _vowel_indexes(phones)]
    return tuple(vowels[-2:])


def _post_vowel_consonants(phones: Sequence[str]) -> Tuple[str, ...]:
    if not phones:
        return tuple()
    last_vowels = _vowel_indexes(phones)
    start = last_vowels[-1] + 1 if last_vowels else 0
    return tuple(_strip_stress(p) for p in phones[start:] if not _is_vowel(p))


def _syllables_from_phones(phones: Sequence[str], word: str) -> int:
    count = len(_vowel_indexes(phones))
    if count:
        return count
    groups = re.findall(r"[aeiouy]+", normalize_word(word))
    return max(1, len(groups))


def word_signature(word: str) -> Dict[str, Any]:
    norm = normalize_word(word)
    phones, source = phones_for_word(norm)
    tail = _rhyming_tail(phones)
    return {
        "word": norm,
        "phones": phones,
        "phones_plain": _bare(phones),
        "source": source,
        "rhyming_tail": list(tail),
        "rhyming_tail_key": " ".join(tail),
        "last_vowel": _last_vowel(phones),
        "last_two_vowels": list(_last_two_vowels(phones)),
        "post_vowel_consonants": list(_post_vowel_consonants(phones)),
        "syllables": _syllables_from_phones(phones, norm),
        "letter_tail": norm[-5:],
    }


def _common_suffix_len(a: Sequence[Any], b: Sequence[Any]) -> int:
    total = 0
    for x, y in zip(reversed(list(a)), reversed(list(b))):
        if x == y:
            total += 1
        else:
            break
    return total


def _letter_suffix_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    suffix = 0
    for x, y in zip(reversed(a), reversed(b)):
        if x == y:
            suffix += 1
        else:
            break
    return min(1.0, suffix / 5.0)


def _style_neighbor(target: str, candidate: str) -> bool:
    t = normalize_word(target)
    c = normalize_word(candidate)
    return c in {normalize_word(w) for w in STYLE_NEIGHBORS.get(t, [])}


def rhyme_score(target_sig: Dict[str, Any], candidate_word: str) -> Dict[str, Any]:
    target = normalize_word(target_sig.get("word", ""))
    cand = normalize_word(candidate_word)
    if not target or not cand or target == cand or cand in BAD_SUGGESTIONS:
        return {"score": 0, "kind": "reject", "reasons": ["same/empty/weak word"]}
    cand_sig = word_signature(cand)
    a_tail = tuple(target_sig.get("rhyming_tail") or [])
    b_tail = tuple(cand_sig.get("rhyming_tail") or [])
    a_plain = list(target_sig.get("phones_plain") or [])
    b_plain = list(cand_sig.get("phones_plain") or [])
    exact_tail = bool(a_tail and a_tail == b_tail)
    suffix = _common_suffix_len(a_plain, b_plain)
    suffix_ratio = suffix / max(1, min(len(a_plain), len(b_plain)))
    last_vowel_match = bool(target_sig.get("last_vowel") and target_sig.get("last_vowel") == cand_sig.get("last_vowel"))
    last_two_vowels_match = bool(target_sig.get("last_two_vowels") and target_sig.get("last_two_vowels") == cand_sig.get("last_two_vowels"))
    a_cons = tuple(target_sig.get("post_vowel_consonants") or [])
    b_cons = tuple(cand_sig.get("post_vowel_consonants") or [])
    final_cons_match = bool(a_cons and b_cons and a_cons[-1:] == b_cons[-1:])
    cons_suffix = _common_suffix_len(a_cons, b_cons) / max(1, min(len(a_cons), len(b_cons)) or 1)
    syllable_close = abs(int(target_sig.get("syllables") or 1) - int(cand_sig.get("syllables") or 1)) <= 1
    letter_ratio = _letter_suffix_ratio(target, cand)
    style = _style_neighbor(target, cand)
    broad_family = _broad_family_name(target, cand)

    score = 0.0
    reasons: List[str] = []
    if exact_tail:
        score += 74
        reasons.append("same stressed vowel tail")
    if suffix_ratio >= 0.45:
        score += 18 * suffix_ratio
        reasons.append("matching final phone sequence")
    if last_vowel_match:
        score += 14
        reasons.append("matching last vowel sound")
    if last_two_vowels_match:
        score += 7
        reasons.append("matching vowel motion")
    if final_cons_match:
        score += 10
        reasons.append("matching final consonant")
    if cons_suffix >= 0.5:
        score += 8 * cons_suffix
        reasons.append("matching consonant tail")
    if syllable_close:
        score += 4
        reasons.append("compatible syllable size")
    if letter_ratio >= 0.4:
        score += 5 * letter_ratio
        reasons.append("matching spelling tail")
    if style and (last_vowel_match or final_cons_match or suffix_ratio >= 0.35):
        score += 8
        reasons.append("corpus style-neighbor slant")
    if broad_family and (last_vowel_match or final_cons_match or suffix_ratio >= 0.25 or letter_ratio >= 0.25):
        score += 12
        reasons.append(f"broad rap family: {broad_family}")

    score_int = int(round(max(0.0, min(100.0, score))))

    # Hard gates: do not let mere final consonant overlap masquerade as rhyme.
    if not exact_tail and not last_vowel_match and suffix_ratio < 0.42 and not broad_family:
        score_int = min(score_int, 42)
    if not exact_tail and last_vowel_match and not final_cons_match and suffix_ratio < 0.38 and not broad_family:
        score_int = min(score_int, 55)

    if exact_tail and score_int >= 84:
        kind = "perfect"
    elif exact_tail or score_int >= 76:
        kind = "family"
    elif style and score_int >= 50:
        kind = "style slant"
    elif broad_family and score_int >= 45:
        kind = "broad family"
    elif score_int >= 62:
        kind = "near"
    elif score_int >= 52:
        kind = "slant"
    elif last_vowel_match and score_int >= 45:
        kind = "assonance"
    elif final_cons_match and score_int >= 45:
        kind = "consonance"
    else:
        kind = "reject"

    return {
        "score": score_int,
        "kind": kind,
        "reasons": unique_keep(reasons, 5),
        "candidate_signature": cand_sig,
        "components": {
            "exact_tail": exact_tail,
            "phone_suffix_ratio": round(suffix_ratio, 3),
            "last_vowel_match": last_vowel_match,
            "last_two_vowels_match": last_two_vowels_match,
            "final_consonant_match": final_cons_match,
            "consonant_suffix_ratio": round(cons_suffix, 3),
            "style_neighbor": style,
            "broad_family": broad_family,
        },
    }


@lru_cache(maxsize=256)
def exact_cmu_rhymes(word: str, limit: int = 80) -> Tuple[str, ...]:
    target = normalize_word(word)
    target_sig = word_signature(target)
    tail = tuple(target_sig.get("rhyming_tail") or [])
    if not tail:
        return tuple()
    tail_key = " ".join(tail)
    corpus = {normalize_word(w) for w in (profile().get("corpus_words_set") or [])}
    approved = set(COMMON_TAIL_RHYMES.get(tail_key, [])) | corpus | COMMON_WORDS
    rows: List[str] = []
    # Start from curated/common endings so the panel does not lead with obscure
    # CMU surname entries.
    rows.extend(COMMON_TAIL_RHYMES.get(tail_key, []))
    cmu = cmu_dictionary()
    for cand, pronuns in cmu.items():
        cand_norm = normalize_word(cand)
        if cand_norm == target or not re.fullmatch(r"[a-z][a-z'\-]{1,18}", cand_norm):
            continue
        if cand_norm not in approved:
            continue
        for phones in pronuns[:2]:
            if _rhyming_tail(phones) == tail:
                rows.append(cand_norm)
                break
    rows = sorted(set(rows), key=lambda w: (0 if w in corpus or w in COMMON_TAIL_RHYMES.get(tail_key, []) else 1, abs(len(w) - len(target)), len(w), w))
    return tuple(unique_keep(rows, limit, exclude=target))


def profile_word_pool() -> List[str]:
    p = profile()
    words: List[str] = []
    banks = p.get("word_banks") if isinstance(p.get("word_banks"), dict) else {}
    for key in ("signature", "punch", "images", "actions", "all"):
        words.extend(banks.get(key, []) or [])
    for row in p.get("top_rhymes", []) or []:
        if isinstance(row, dict):
            words.extend(row.get("words", []) or [])
    for bank_name in ("rhyme_bank", "echo_bank"):
        bank = p.get(bank_name) if isinstance(p.get(bank_name), dict) else {}
        for vals in bank.values():
            words.extend(vals or [])
    words.extend(COMMON_FALLBACKS)
    return unique_keep([normalize_word(w) for w in words], 3500)


def candidate_words(target: str) -> List[str]:
    target = normalize_word(target)
    exact = list(exact_cmu_rhymes(target, 80))
    style = STYLE_NEIGHBORS.get(target, [])
    broad = broad_family_candidates(target)
    return unique_keep(exact + style + broad + profile_word_pool(), 3000, exclude=target)


def ranked_rhymes(word: str, limit: int = 40) -> List[Dict[str, Any]]:
    target = normalize_word(word)
    sig = word_signature(target)
    rows: List[Dict[str, Any]] = []
    for cand in candidate_words(target):
        sim = rhyme_score(sig, cand)
        score = int(sim.get("score") or 0)
        if score < 45 or sim.get("kind") == "reject":
            continue
        # Low-scoring corpus words are often topical/style neighbors rather than
        # actual rhymes.  Keep loose matches only when they are an explicit
        # style-neighbor for the target; otherwise they create the "doesn't
        # rhyme" problem in the highlighted-word panel.
        if score < 60 and not ((sim.get("components") or {}).get("style_neighbor") or (sim.get("components") or {}).get("broad_family")):
            continue
        csig = sim.get("candidate_signature") or word_signature(cand)
        rows.append({
            "word": cand,
            "display": cand,
            "score": score,
            "kind": sim.get("kind"),
            "quality_label": "clean" if score >= 84 else "usable" if score >= 62 else "loose",
            "rhyme_tail": csig.get("rhyming_tail_key"),
            "phones": " ".join(csig.get("phones_plain") or []),
            "syllables": csig.get("syllables"),
            "reasons": sim.get("reasons") or [],
            "components": sim.get("components") or {},
        })
    kind_order = {"perfect": 0, "family": 1, "style slant": 2, "broad family": 3, "near": 4, "slant": 5, "assonance": 6, "consonance": 7}
    rows.sort(key=lambda r: (-int(r.get("score") or 0), kind_order.get(str(r.get("kind")), 9), len(str(r.get("word"))), str(r.get("word"))))
    # Enforce uniqueness after sorting.
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in rows:
        key = normalize_word(row.get("word"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def phrase_landings(target: str, rows: Sequence[Dict[str, Any]], limit: int = 12) -> List[str]:
    prefixes = ["hidden", "written", "rhythmic", "coded", "threaded", "measured", "pressure", "signal", "system", "precise", "vivid", "steady"]
    phrases: List[str] = []
    for prefix, row in zip(prefixes * 2, rows):
        word = str(row.get("word") or "").strip()
        if word and normalize_word(prefix) != normalize_word(word):
            phrases.append(f"{prefix} {word}")
    return unique_keep(phrases, limit, exclude=target)


def group_word_lists(rows: Sequence[Dict[str, Any]], target: str) -> Dict[str, List[str]]:
    exact = [r["word"] for r in rows if r.get("kind") in {"perfect", "family"} and int(r.get("score") or 0) >= 76]
    style = [r["word"] for r in rows if r.get("kind") == "style slant"]
    broad = [r["word"] for r in rows if r.get("kind") == "broad family"]
    near = [r["word"] for r in rows if r.get("kind") in {"near", "slant"} and int(r.get("score") or 0) >= 55]
    assonance = [r["word"] for r in rows if r.get("kind") == "assonance"]
    consonance = [r["word"] for r in rows if r.get("kind") == "consonance"]
    stress = [r["word"] for r in rows if abs(int(r.get("syllables") or 1) - int(word_signature(target).get("syllables") or 1)) == 0]
    internal = unique_keep([r["word"] for r in rows if int(r.get("score") or 0) >= 52], 18, exclude=target)
    return {
        "end_rhymes": unique_keep(exact, 16, exclude=target),
        "style_slants": unique_keep(style, 16, exclude=target),
        "broad_family": unique_keep(broad, 18, exclude=target),
        "near_rhymes": unique_keep(near + broad + style, 18, exclude=target),
        "slant_rhymes": unique_keep(style + broad + near, 18, exclude=target),
        "assonance_words": unique_keep(assonance, 16, exclude=target),
        "consonance_words": unique_keep(consonance, 16, exclude=target),
        "stress_matched": unique_keep(stress, 16, exclude=target),
        "multi_syllable_endings": phrase_landings(target, rows, 12),
        "internal_echoes": internal,
    }


def _phrase_tokens(phrase: str) -> List[str]:
    return tokenize(phrase)


def _phrase_shape(words: Sequence[str]) -> Dict[str, Any]:
    sigs = [word_signature(w) for w in words]
    return {
        "token_count": len(words),
        "syllables": sum(int(s.get("syllables") or 1) for s in sigs),
        "tail_word": words[-1] if words else "",
        "tail_rhyme_key": (sigs[-1].get("rhyming_tail_key") if sigs else ""),
        "internal_rhyme_keys": [s.get("rhyming_tail_key") for s in sigs[:-1] if s.get("rhyming_tail_key")],
        "stress_family": "-".join(str(s.get("syllables") or 1) for s in sigs),
        "vowel_motion": [s.get("last_vowel") for s in sigs if s.get("last_vowel")],
    }


def _replace_phrase_landing(original_phrase: str, new_landing: str) -> str:
    matches = list(TOKEN_RE.finditer(str(original_phrase or "")))
    if not matches:
        return str(new_landing or "").strip()
    last = matches[-1]
    return f"{original_phrase[:last.start()]}{new_landing}{original_phrase[last.end():]}".strip()


def _phrase_family_templates(phrase: str, landing_rows: Sequence[Dict[str, Any]], limit: int = 24) -> List[Dict[str, Any]]:
    words = _phrase_tokens(phrase)
    if not words:
        return []
    target = words[-1]
    prefix = " ".join(words[:-1]).strip()
    templates: List[Dict[str, Any]] = []
    # Preserve the user's selected phrase rhythm; just rotate the landing.
    for row in landing_rows[:14]:
        cand = str(row.get("word") or "").strip()
        if not cand:
            continue
        templates.append({
            "word": _replace_phrase_landing(phrase, cand),
            "display": _replace_phrase_landing(phrase, cand),
            "kind": f"phrase {row.get('kind')}",
            "score": max(0, int(row.get("score") or 0) - 2),
            "source_landing": cand,
            "pattern": "same phrase frame, rotated landing",
        })
    # Corpus-style phrase frames based on recurring motifs in the user's writing.
    frames = [
        "core to {w}", "curse with a {w}", "reversed in the {w}", "service with {w}",
        "sentence with {w}", "presence of {w}", "rhythm in {w}", "system of {w}",
        "threaded with {w}", "written in {w}", "signal through {w}", "pressure into {w}",
    ]
    for row in landing_rows[:12]:
        cand = str(row.get("word") or "").strip()
        if not cand:
            continue
        for frame in frames[:4]:
            # Avoid absurd articles before plurals or phrases; keep it simple.
            phr = frame.format(w=cand).replace(" a universe", " universe").replace(" a evidence", " evidence")
            templates.append({
                "word": phr,
                "display": phr,
                "kind": "suggestive phrase family",
                "score": max(45, int(row.get("score") or 0) - 10),
                "source_landing": cand,
                "pattern": "corpus phrase frame",
            })
    # If the selected phrase has at least two meaningful words, also answer the
    # last two-word cadence.
    if len(words) >= 2:
        lead = words[-2]
        for row in landing_rows[:10]:
            cand = str(row.get("word") or "").strip()
            if cand:
                templates.append({
                    "word": f"{lead} {cand}",
                    "display": f"{lead} {cand}",
                    "kind": "two-word tail answer",
                    "score": max(42, int(row.get("score") or 0) - 8),
                    "source_landing": cand,
                    "pattern": "preserve penultimate word, rotate landing",
                })
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in templates:
        key = " ".join(tokenize(row.get("word", "")))
        if not key or key in seen or key == " ".join(words):
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def build_highlighted_phrase_report(
    phrase: str,
    mode: str = "match",
    line_text: str = "",
    lyrics: str = "",
    active_line: int | None = None,
    selection_start: int | None = None,
    selection_end: int | None = None,
    job_id: str | None = None,
    limit: int = 36,
) -> Dict[str, Any]:
    raw_phrase = str(phrase or "").strip()
    words = _phrase_tokens(raw_phrase)
    if len(words) <= 1:
        return build_highlighted_word_report(
            words[0] if words else raw_phrase,
            mode=mode,
            line_text=line_text,
            lyrics=lyrics,
            active_line=active_line,
            selection_start=selection_start,
            selection_end=selection_end,
            job_id=job_id,
            limit=limit,
        )
    target = words[-1]
    landing_rows = ranked_rhymes(target, limit=max(50, limit))
    phrase_rows = _phrase_family_templates(raw_phrase, landing_rows, limit=limit)
    target_sig = word_signature(target)
    shape = _phrase_shape(words)
    word_banks = group_word_lists(landing_rows, target)
    word_banks.update({
        "phrase_rhymes": [r["word"] for r in phrase_rows[:18]],
        "pattern_preserving_phrases": [r["word"] for r in phrase_rows if r.get("pattern") == "same phrase frame, rotated landing"][:12],
        "suggestive_phrase_families": [r["word"] for r in phrase_rows if r.get("pattern") != "same phrase frame, rotated landing"][:12],
    })
    patches = []
    for row in phrase_rows[:14]:
        patches.append({
            "type": "replace_selection",
            "label": f"Replace highlighted phrase → {row.get('word')}",
            "replacement": row.get("word"),
            "score": row.get("score"),
            "kind": row.get("kind"),
            "why": row.get("pattern"),
        })
    return {
        "available": True,
        "job_id": job_id,
        "job_type": "selected_phrase_rhyme",
        "report_type": "highlighted_phrase_rhyme_broad_family",
        "engine": "highlighted_rhyme_engine_v3_broad_phrase",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "phrase_mode": True,
        "selected_phrase": raw_phrase,
        "selected_word": raw_phrase,
        "target_word": target,
        "mode": mode,
        "line_text": line_text,
        "active_line": active_line,
        "selection": {"start": selection_start, "end": selection_end},
        "selection_range": {"start": selection_start, "end": selection_end},
        "lyrics_chars": len(lyrics or ""),
        "summary": {
            "rhyme_key": target_sig.get("rhyming_tail_key") or target_sig.get("letter_tail"),
            "rhyme_tail": target_sig.get("rhyming_tail_key"),
            "phones": " ".join(target_sig.get("phones_plain") or []),
            "source": target_sig.get("source"),
            "syllables": shape.get("syllables"),
            "target_syllables": target_sig.get("syllables"),
            "stress_signature": shape.get("stress_family"),
            "candidate_count": len(phrase_rows),
            "best_score": phrase_rows[0].get("score", 0) if phrase_rows else 0,
            "best_kind": phrase_rows[0].get("kind", "none") if phrase_rows else "none",
        },
        "target_signature": target_sig,
        "phrase_shape": shape,
        "word_lists": word_banks,
        "ranked": phrase_rows[:limit],
        "target_landing_ranked": landing_rows[:limit],
        "perfect_or_family": [r for r in landing_rows if r.get("kind") in {"perfect", "family"}][:16],
        "style_slants": [r for r in landing_rows if r.get("kind") == "style slant"][:16],
        "broad_family": [r for r in landing_rows if r.get("kind") == "broad family"][:16],
        "slant": [r for r in landing_rows if r.get("kind") in {"near", "slant"}][:16],
        "rhyme_ladder": [
            {"stage": "1. Preserve phrase frame", "use_when": "Keep the selected phrase shape and rotate only the landing.", "options": word_banks.get("pattern_preserving_phrases", [])[:8]},
            {"stage": "2. Broad family phrase", "use_when": "Use a looser rap-family phrase that shares vowel/consonant/motif motion.", "options": word_banks.get("suggestive_phrase_families", [])[:8]},
            {"stage": "3. Clean landing words", "use_when": "Use these if the phrase should end with a clearer rhyme.", "options": word_banks.get("end_rhymes", [])[:8]},
            {"stage": "4. Internal setup", "use_when": "Place these inside the bar before the phrase landing.", "options": word_banks.get("internal_echoes", [])[:8]},
        ],
        "similar_rhymes": [{"word": r.get("word"), "category": r.get("kind"), "score": r.get("score"), "quality_label": "phrase"} for r in phrase_rows[:60]],
        "applyable_patches": patches,
        "instruction": "Phrase mode: suggestions preserve or answer the highlighted phrase shape, then classify the landing as clean, style slant, broad family, near, or internal echo.",
        "fallback_used": False,
        "strict_filtering": False,
        "broad_family_mode": True,
        "classification_legend": RHYME_CLASSIFICATION_LEGEND,
        "live_writer": {"available": True, "trigger": "highlighted_phrase", "instruction": "Highlight one or more words to fetch phrase-aware rhyme suggestions."},
    }


RHYME_CLASSIFICATION_LEGEND = [
    {"kind": "perfect", "meaning": "Same stressed vowel and same phonetic tail; safest end-rhyme landing."},
    {"kind": "family", "meaning": "Strong shared phonetic tail or very high score; still clean enough for bar endings."},
    {"kind": "style slant", "meaning": "Corpus-learned rap slant from your style neighborhoods."},
    {"kind": "broad family", "meaning": "Broader rap-family link: shared vowel/consonant/motif/suffix movement, useful for chains and internals."},
    {"kind": "near/slant", "meaning": "Usable rap rhyme when cadence and delivery carry it."},
    {"kind": "assonance", "meaning": "Vowel color match; best used inside a line."},
    {"kind": "consonance", "meaning": "Consonant texture match; best used as internal percussion."},
]


def build_highlighted_word_report(
    word: str,
    mode: str = "match",
    line_text: str = "",
    lyrics: str = "",
    active_line: int | None = None,
    selection_start: int | None = None,
    selection_end: int | None = None,
    job_id: str | None = None,
    limit: int = 36,
) -> Dict[str, Any]:
    phrase_tokens = _phrase_tokens(str(word or ""))
    if len(phrase_tokens) > 1:
        return build_highlighted_phrase_report(
            str(word or ""),
            mode=mode,
            line_text=line_text,
            lyrics=lyrics,
            active_line=active_line,
            selection_start=selection_start,
            selection_end=selection_end,
            job_id=job_id,
            limit=limit,
        )
    target = normalize_word(phrase_tokens[0] if phrase_tokens else word)
    if not target:
        return {"available": False, "error": "Highlight or select a word or phrase before requesting similar rhymes."}
    sig = word_signature(target)
    rows = ranked_rhymes(target, limit=limit)
    banks = group_word_lists(rows, target)
    best = rows[0] if rows else {}
    patches = []
    for row in rows[:12]:
        replacement = str(row.get("word") or "").strip()
        if not replacement:
            continue
        patches.append({
            "type": "replace_selection",
            "label": f"Replace highlighted word → {replacement}",
            "replacement": replacement,
            "score": row.get("score"),
            "kind": row.get("kind"),
            "why": "; ".join(row.get("reasons") or []),
        })
    similar = [
        {"word": row.get("word"), "category": row.get("kind"), "score": row.get("score"), "quality_label": row.get("quality_label")}
        for row in rows[:60]
    ]
    if not rows:
        instruction = "No reliable phonetic rhymes found. Try highlighting a longer content word or use the static snapshot word banks."
    else:
        instruction = "Suggestions are phonetic-scored. Use clean/family rhymes for landings; use style slants for internal motion."
    return {
        "available": True,
        "job_id": job_id,
        "job_type": "selected_word_rhyme",
        "report_type": "highlighted_word_rhyme_broad_classified",
        "engine": "highlighted_rhyme_engine_v3_broad_phrase",
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "selected_word": target,
        "target_word": target,
        "mode": mode,
        "line_text": line_text,
        "active_line": active_line,
        "selection": {"start": selection_start, "end": selection_end},
        "selection_range": {"start": selection_start, "end": selection_end},
        "lyrics_chars": len(lyrics or ""),
        "summary": {
            "rhyme_key": sig.get("rhyming_tail_key") or sig.get("letter_tail"),
            "rhyme_tail": sig.get("rhyming_tail_key"),
            "phones": " ".join(sig.get("phones_plain") or []),
            "source": sig.get("source"),
            "syllables": sig.get("syllables"),
            "stress_signature": "phonetic-tail",
            "candidate_count": len(rows),
            "best_score": best.get("score", 0),
            "best_kind": best.get("kind", "none"),
        },
        "target_signature": sig,
        "word_lists": banks,
        "ranked": rows[:limit],
        "perfect_or_family": [r for r in rows if r.get("kind") in {"perfect", "family"}][:16],
        "style_slants": [r for r in rows if r.get("kind") == "style slant"][:16],
        "broad_family": [r for r in rows if r.get("kind") == "broad family"][:16],
        "slant": [r for r in rows if r.get("kind") in {"near", "slant"}][:16],
        "assonance": [r for r in rows if r.get("kind") == "assonance"][:16],
        "consonance": [r for r in rows if r.get("kind") == "consonance"][:16],
        "rhyme_ladder": [
            {"stage": "1. Clean landing", "use_when": "Use this for an obvious end rhyme.", "options": banks.get("end_rhymes", [])[:8]},
            {"stage": "2. Style slant", "use_when": "Use this for your surface/purpose/music-style corpus chains.", "options": banks.get("style_slants", [])[:8]},
            {"stage": "3. Broad rap family", "use_when": "Use this for wider assonance/consonance/motif-family movement.", "options": banks.get("broad_family", [])[:8]},
            {"stage": "4. Near/slant turn", "use_when": "Use this when you want the rhyme to move instead of lock.", "options": banks.get("near_rhymes", [])[:8]},
            {"stage": "5. Internal setup", "use_when": "Place these before the landing to strengthen the bar.", "options": banks.get("internal_echoes", [])[:8]},
        ],
        "similar_rhymes": similar,
        "applyable_patches": patches,
        "instruction": instruction,
        "fallback_used": False,
        "strict_filtering": False,
        "broad_family_mode": True,
        "minimum_display_score": 45,
        "classification_legend": RHYME_CLASSIFICATION_LEGEND,
        "live_writer": {"available": True, "trigger": "highlighted_word", "instruction": "Highlight a word to fetch strict phonetic rhyme suggestions."},
    }


if __name__ == "__main__":  # pragma: no cover
    for sample in ["father", "projects", "dreams", "frontier", "surface", "music", "paradise", "diction", "sentence"]:
        report = build_highlighted_word_report(sample)
        print(sample, report["summary"])
        print([f"{r['word']}:{r['kind']}:{r['score']}" for r in report["ranked"][:10]])
