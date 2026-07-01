from __future__ import annotations

import json
import math
import re
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")
VOWELS = "aeiouy"

DEFAULT_BANK = {
    "signature": ["sentence", "presence", "essence", "resonance", "system", "rhythm", "diction", "friction", "scripture", "picture", "purpose", "surface", "credit", "vector", "signal", "pressure"],
    "images": ["ink", "page", "tongue", "teeth", "breath", "wire", "spark", "static", "mirror", "signal", "engine", "lattice"],
    "actions": ["stitch", "stretch", "anchor", "thread", "measure", "render", "rotate", "sharpen", "compress", "release", "ignite", "sync"],
    "punch": ["impact", "static", "signal", "switch", "spark", "script", "proof", "weight", "edge", "shift", "thread", "cipher"],
}

COMMON_SUFFIX_KEYS = [
    ("tion", "shun"), ("sion", "shun"), ("cion", "shun"), ("xion", "shun"),
    ("tious", "shus"), ("cious", "shus"), ("ence", "ence"), ("ance", "ance"),
    ("ment", "ment"), ("ness", "ness"), ("less", "less"), ("ous", "us"),
    ("ity", "ity"), ("ing", "ing"), ("er", "er"), ("est", "est"),
]


def _load_profile() -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / "data" / "corpus_profile.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


PROFILE = _load_profile()
RHYME_BANK: Dict[str, List[str]] = {
    str(key): [str(w) for w in (value or [])[:32]]
    for key, value in (PROFILE.get("rhyme_bank") or {}).items()
    if isinstance(value, list)
}
ECHO_BANK: Dict[str, List[str]] = {
    str(key): [str(w) for w in (value or [])[:32]]
    for key, value in (PROFILE.get("echo_bank") or {}).items()
    if isinstance(value, list)
}
WORD_BANKS = PROFILE.get("word_banks") if isinstance(PROFILE.get("word_banks"), dict) else {}
CORPUS_WORDS = {str(w).lower() for w in (PROFILE.get("corpus_words_set") or [])}
SIGNATURE_WORDS = [str(row.get("word")) for row in (PROFILE.get("signature_words") or []) if isinstance(row, dict) and row.get("word")][:80]
TOP_RHYME_ROWS = [row for row in (PROFILE.get("top_rhymes") or []) if isinstance(row, dict)]
TOP_RHYME_KEYS = [str(row.get("key")) for row in TOP_RHYME_ROWS if row.get("key")]


def tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall(str(text or ""))


def end_word(text: str) -> str:
    words = tokenize(text)
    return words[-1] if words else ""


def clean_word(word: str) -> str:
    match = TOKEN_RE.search(str(word or ""))
    return match.group(0) if match else ""


def rhyme_key(word: str) -> str:
    w = clean_word(word).lower().strip("'’-")
    if not w:
        return ""
    for suffix, key in COMMON_SUFFIX_KEYS:
        if w.endswith(suffix) and len(w) > len(suffix) + 1:
            return key
    # Use the final vowel nucleus through the end. This is crude but very stable.
    for i in range(len(w) - 1, -1, -1):
        if w[i] in VOWELS:
            start = i
            while start > 0 and w[start - 1] in VOWELS:
                start -= 1
            key = w[start:]
            return key[-6:]
    return w[-4:]


def syllables(word: str) -> int:
    w = clean_word(word).lower()
    if not w:
        return 0
    groups = re.findall(r"[aeiouy]+", w)
    count = len(groups)
    if w.endswith("e") and count > 1 and not w.endswith(("le", "ye")):
        count -= 1
    if w.endswith(("tion", "sion")):
        count = max(count, 2)
    return max(1, count)


def line_syllables(text: str) -> int:
    return sum(syllables(w) for w in tokenize(text))


def grade_for_score(score: int) -> Dict[str, str]:
    if score >= 90:
        return {"letter": "A", "label": "release-ready"}
    if score >= 82:
        return {"letter": "B+", "label": "strong pocket"}
    if score >= 72:
        return {"letter": "B", "label": "usable"}
    if score >= 60:
        return {"letter": "C+", "label": "needs tightening"}
    return {"letter": "C", "label": "needs revision"}


def overlap_score(a: str, b: str) -> int:
    a = str(a or "")
    b = str(b or "")
    if not a or not b:
        return 0
    if a == b:
        return 100
    best = 0
    for n in range(1, min(len(a), len(b)) + 1):
        if a[-n:] == b[-n:]:
            best = n
    return int(100 * best / max(len(a), len(b), 1))


def unique_keep(items: Iterable[Any], limit: int = 24, exclude: str | None = None) -> List[str]:
    out: List[str] = []
    seen = set()
    ex = (exclude or "").lower()
    for item in items:
        word = str(item or "").strip()
        if not word:
            continue
        low = word.lower()
        if low == ex or low in seen:
            continue
        seen.add(low)
        out.append(word)
        if len(out) >= limit:
            break
    return out


def words_for_key(key: str, target: str = "", limit: int = 24) -> List[str]:
    key = str(key or "")
    exact = RHYME_BANK.get(key, []) + ECHO_BANK.get(key, [])
    if exact:
        return unique_keep(exact, limit, exclude=target)
    scored: List[Tuple[int, str]] = []
    for bank_key, words in RHYME_BANK.items():
        score = overlap_score(key, bank_key)
        if score >= 34:
            for word in words[:8]:
                scored.append((score, word))
    if not scored:
        for row in TOP_RHYME_ROWS[:6]:
            for word in row.get("words", [])[:5]:
                scored.append((20, word))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return unique_keep([w for _, w in scored], limit, exclude=target)


def near_words_for_key(key: str, target: str = "", limit: int = 24) -> List[str]:
    scored: List[Tuple[int, str]] = []
    for bank_key, words in RHYME_BANK.items():
        score = overlap_score(key, bank_key)
        if 18 <= score < 100:
            for word in words[:6]:
                scored.append((score, word))
    if not scored:
        scored = [(10, word) for word in DEFAULT_BANK["signature"]]
    scored.sort(key=lambda x: (-x[0], x[1]))
    return unique_keep([w for _, w in scored], limit, exclude=target)


def phrase_landings(target_key: str, target_word: str, candidates: List[str]) -> List[str]:
    stems = ["measured", "coded", "threaded", "hidden", "present", "rhythmic", "signal", "system"]
    base = candidates[:8] or [target_word]
    phrases = []
    for stem, word in zip(stems, base + base):
        if word:
            phrases.append(f"{stem} {word}")
    return unique_keep(phrases, 10)


def word_lists_for(word: str) -> Dict[str, List[str]]:
    key = rhyme_key(word)
    exact = words_for_key(key, word, 24)
    near = near_words_for_key(key, word, 24)
    signature = unique_keep(SIGNATURE_WORDS + DEFAULT_BANK["signature"], 16, exclude=word)
    images = unique_keep((WORD_BANKS.get("images") or []) + DEFAULT_BANK["images"], 16, exclude=word)
    actions = unique_keep((WORD_BANKS.get("actions") or []) + DEFAULT_BANK["actions"], 16, exclude=word)
    punch = unique_keep((WORD_BANKS.get("punch") or []) + DEFAULT_BANK["punch"], 16, exclude=word)
    return {
        "end_rhymes": exact[:16],
        "near_rhymes": near[:16],
        "slant_rhymes": near[:16],
        "assonance_words": unique_keep(exact + near, 16, exclude=word),
        "consonance_words": unique_keep(near + exact, 16, exclude=word),
        "stress_matched": unique_keep(exact[:8] + near[:8], 16, exclude=word),
        "multi_syllable_endings": phrase_landings(key, word, exact + near),
        "internal_echoes": unique_keep(exact[:10] + signature[:8], 18, exclude=word),
        "signature_words": signature,
        "images": images,
        "verbs": actions,
        "punch_words": punch,
        "cut_words": ["very", "really", "just", "that", "maybe", "actually", "basically", "stuff"],
    }


def ranked_options_for(word: str, limit: int = 18) -> List[Dict[str, Any]]:
    banks = word_lists_for(word)
    buckets = [
        ("family", banks["end_rhymes"], 96),
        ("slant", banks["slant_rhymes"], 84),
        ("internal", banks["internal_echoes"], 76),
        ("multi", banks["multi_syllable_endings"], 72),
    ]
    out: List[Dict[str, Any]] = []
    seen = set()
    key = rhyme_key(word)
    for kind, words, base in buckets:
        for idx, candidate in enumerate(words):
            display = str(candidate or "").strip()
            if not display or display.lower() in seen or display.lower() == str(word).lower():
                continue
            seen.add(display.lower())
            out.append({
                "word": display.split()[-1],
                "display": display,
                "kind": kind,
                "score": max(44, base - idx * 3 - len(out)),
                "rhyme_key": key,
                "reasons": [f"/{key}/ family" if key else "same landing texture", f"{kind} option for the active line"],
            })
            if len(out) >= limit:
                return out
    return out


def replace_line_ending(line: str, replacement: str) -> str:
    replacement = str(replacement or "").strip()
    if not replacement:
        return line
    if TOKEN_RE.search(line or ""):
        return re.sub(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*([^A-Za-z0-9]*)$", replacement + r"\1", str(line))
    return f"{line} {replacement}".strip()


def highlight_for_line(line: str, key_counts: Dict[str, int], line_number: int, family_lines: Dict[str, List[int]]) -> Dict[str, Any]:
    ew = end_word(line)
    key = rhyme_key(ew)
    class_num = (abs(hash(key)) % 12) + 1 if key else 1
    tokens = []
    pos = 0
    for match in re.finditer(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|\s+|[^A-Za-z0-9\s]+", line or ""):
        text = match.group(0)
        if TOKEN_RE.fullmatch(text):
            wk = rhyme_key(text)
            is_end = text.lower() == ew.lower() and match.end() >= len(line.rstrip()) - len(text)
            is_echo = bool(key and wk == key and (key_counts.get(key, 0) > 1 or is_end))
            tokens.append({
                "text": text,
                "highlight": bool(is_echo),
                "role": "end" if is_end else "internal",
                "rhyme_key": wk,
                "rhyme_class": class_num,
                "title": f"/{wk}/ rhyme" if wk else "word",
            })
        else:
            tokens.append({"text": text, "highlight": False})
        pos = match.end()
    return {
        "line_number": line_number,
        "line_rhyme_key": key,
        "line_rhyme_class": class_num,
        "line_rhyme_letter": chr(65 + (class_num - 1) % 26),
        "end_word": ew,
        "line_family_count": key_counts.get(key, 0) if key else 0,
        "line_family_lines": family_lines.get(key, [])[:12],
        "highlighted_word_count": sum(1 for t in tokens if t.get("highlight")),
        "tokens": tokens,
    }


def stress_ratio(words: List[str]) -> int:
    if not words:
        return 0
    # Rap-focused heuristic: content words with 2+ syllables and hard consonant starts tend to carry stress.
    stressed = 0
    for w in words:
        lw = w.lower()
        if len(lw) >= 6 or syllables(lw) >= 2 or lw[0] in "ptkbdgfvszcr":
            stressed += 1
    return int(round(100 * stressed / max(1, len(words))))


def line_power(text: str, key_counts: Dict[str, int], previous_syllables: int | None = None) -> Tuple[int, Dict[str, int]]:
    words = tokenize(text)
    ew = end_word(text)
    key = rhyme_key(ew)
    syl = line_syllables(text)
    repeats = key_counts.get(key, 0) if key else 0
    internal = sum(1 for w in words[:-1] if rhyme_key(w) == key and key)
    allit = 0
    initials = Counter(w[0].lower() for w in words if w)
    if initials:
        allit = max(initials.values()) - 1
    cadence_fit = max(0, 100 - abs(syl - 12) * 7)
    rhyme = 42 + min(28, repeats * 14) + min(18, internal * 9)
    sound = min(100, 50 + internal * 12 + allit * 6)
    clarity = max(48, 100 - max(0, len(words) - 18) * 4)
    score = int(round(0.34 * min(100, rhyme) + 0.24 * cadence_fit + 0.2 * sound + 0.22 * clarity))
    delta = 0 if previous_syllables is None else syl - previous_syllables
    return max(0, min(100, score)), {"syllables": syl, "internal": internal, "allit": allit, "delta_syllables": delta, "cadence_fit": cadence_fit, "rhyme": min(100, rhyme), "sound": sound, "clarity": clarity}


def build_live_static(active: Dict[str, Any], line_reports: List[Dict[str, Any]], mode: str) -> Dict[str, Any]:
    if not active:
        return {"available": False, "error": "No active line."}
    text = active.get("text", "")
    words = tokenize(text)
    syl = active.get("syllables", line_syllables(text))
    key = active.get("rhyme_key", "")
    ew = active.get("end_word", "")
    score = int(active.get("rhyme_power", {}).get("score", active.get("score", 0)) or 0)
    info_bits = round(sum(4.0 if w.lower() in CORPUS_WORDS else 8.0 for w in words), 2)
    stress_pct = stress_ratio(words)
    force = min(100, 40 + stress_pct // 2 + min(20, active.get("internal_count", 0) * 8))
    torsion = min(100, abs(active.get("cadence_delta", 0)) * 10 + max(0, syl - 16) * 3)
    spin = min(100, 35 + active.get("internal_count", 0) * 16 + active.get("alliteration_count", 0) * 7)
    bar_note = "Fits one bar cleanly." if 8 <= syl <= 14 else ("Consider splitting across two bars." if syl > 16 else "Short punch line; leave a rest after it.")
    actions = []
    if score < 64:
        actions.append("Add one internal echo before the end word, then land the rhyme harder.")
    if syl > 16:
        actions.append("Split after the strongest comma or phrase break to reduce bar overload.")
    if syl < 7:
        actions.append("Use this as a punch/reset or add 2–4 syllables before the landing.")
    if not actions:
        actions.append("Keep the landing; test one stronger internal echo before it.")
    possible = word_lists_for(ew)
    ranked = ranked_options_for(ew, 6)
    rewrites = []
    if ranked:
        rewrites.append({
            "name": "Swap ending",
            "text": replace_line_ending(text, ranked[0]["display"]),
            "syllables": line_syllables(replace_line_ending(text, ranked[0]["display"])),
            "why": "Tests a stronger rhyme landing without rewriting the whole thought.",
        })
    if possible.get("internal_echoes"):
        echo = possible["internal_echoes"][0]
        rewrites.append({
            "name": "Add internal echo",
            "text": f"{echo} in the {text}" if not text.lower().startswith(echo.lower()) else text,
            "syllables": line_syllables(f"{echo} in the {text}"),
            "why": "Adds a sound loop before the final landing.",
        })
    active_line = {
        "available": True,
        "line_number": active.get("line_number"),
        "relative_line_number": active.get("relative_line_number"),
        "text": text,
        "role": "active live line",
        "section": {"label": "Live context"},
        "metrics": {"words": len(words), "syllables": syl, "end_word": ew, "rhyme_key": key},
        "rhyme_highlight": active.get("rhyme_highlight"),
        "breakdown": {
            "cadence": f"{syl} syllables. {bar_note}",
            "sound": f"/{key}/ landing with {active.get('internal_count', 0)} internal echo(s) and {active.get('alliteration_count', 0)} alliteration hit(s).",
            "content": "Live mode keeps the line readable: preserve the meaning, then change only the landing or one internal word.",
            "rhyme": active.get("chain_note", "Single rhyme family in the current context."),
            "bar_structure": {"available": True, "assigned_bars": active.get("assigned_bars", "1 bar"), "note": bar_note},
        },
        "information": {
            "line_self_information_bits": info_bits,
            "bits_per_word": round(info_bits / max(1, len(words)), 2),
            "interpretation": "Higher bits mean the line uses rarer words relative to the local corpus profile.",
            "rarest_words": [{"word": w, "bits": 8 if w.lower() not in CORPUS_WORDS else 4} for w in words if len(w) > 4][:5],
        },
        "meter": {
            "available": True,
            "summary": {"stress_ratio_pct": stress_pct, "dominant_meter": "mixed rap pulse", "final_landing_stressed": syllables(ew) >= 1},
            "suggestions": ["Land the strongest stress on the final content word.", "Avoid three weak filler words before the rhyme."],
        },
        "physics": {
            "available": True,
            "force_pct": force,
            "torsion_pct": torsion,
            "spin_pct": spin,
            "cadence_delta": {"available": True, "delta_syllables": active.get("cadence_delta", 0)},
            "actions": ["Use force for punch, torsion for surprise, and spin for internal rhyme motion."],
        },
        "bar_score": {
            "overall": score,
            "grade": grade_for_score(score),
            "diagnosis": {"issues": [] if score >= 70 else ["weak rhyme landing or cadence imbalance"], "advice": actions[:3]},
        },
        "comparison_guidance": {"available": True, "note": "Use this line as a live bar-level diagnostic, then rescore the full draft in Static Snapshot.", "rhyme_note": f"Current family /{key}/."},
        "advanced_rhyme": {"available": True, "summary": {"target_word": ew, "rhyme_key": key}, "ranked_options": ranked[:6]},
        "possible_words": possible,
        "rewrite_options": rewrites,
        "applyable_patches": [{"label": r["name"], "replacement": r["text"], "why": r["why"]} for r in rewrites],
        "suggestion": {
            "operation_label": "Live polish",
            "action_steps": actions,
            "checklist": ["Keep the meaning", "Choose one stronger landing", "Add one internal echo", "Refresh live rhyme"],
        },
    }
    idx = next((i for i, row in enumerate(line_reports) if row.get("line_number") == active.get("line_number")), 0)
    nearby = line_reports[max(0, idx - 3): idx + 4]
    return {
        "available": True,
        "report_type": "live_static_line_analysis_fast_core",
        "active_line": active_line,
        "nearby_lines": nearby,
        "overview": {"actions": actions, "headline": "Fast live static-style line analysis ready."},
        "snapshot_elements": ["metrics", "cadence", "sound", "content", "rhyme_instruction", "bar_structure", "information_profile", "meter_stress", "scansion_physics", "bar_score", "possible_words", "rewrite_options", "applyable_patches", "checklist"],
    }


def editable_lines(lyrics: str, context_offset: int = 0) -> List[Tuple[int, int, str]]:
    raw_lines = str(lyrics or "").splitlines()
    if not raw_lines and str(lyrics or "").strip():
        raw_lines = [str(lyrics).strip()]
    rows = []
    for idx, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        rows.append((idx, idx + context_offset, stripped))
    return rows


def build_live_rhyme_payload(
    lyrics: str,
    mode: str = "match",
    active_line: int | None = None,
    job_id: str | None = None,
    context_offset: int = 0,
    context_clipped: bool = False,
    total_source_lines: int | None = None,
    beat_id: str | None = None,
) -> Dict[str, Any]:
    rows = editable_lines(lyrics, context_offset=context_offset)
    if not rows:
        return {"available": False, "error": "Type at least three words to start the live rhyme sidecar.", "job_id": job_id}
    active_line = active_line or rows[0][0]
    # Choose exact relative line if possible, otherwise nearest editable line.
    active_tuple = min(rows, key=lambda row: abs(row[0] - active_line))
    key_counts: Dict[str, int] = Counter(rhyme_key(end_word(text)) for _, _, text in rows if end_word(text))
    family_lines: Dict[str, List[int]] = defaultdict(list)
    for _, source_no, text in rows:
        key = rhyme_key(end_word(text))
        if key:
            family_lines[key].append(source_no)
    line_reports: List[Dict[str, Any]] = []
    previous_syl = None
    for rel_no, source_no, text in rows[:80]:
        ew = end_word(text)
        key = rhyme_key(ew)
        score, stats = line_power(text, key_counts, previous_syllables=previous_syl)
        previous_syl = stats["syllables"]
        report = {
            "available": True,
            "relative_line_number": rel_no,
            "line_number": source_no,
            "text": text,
            "end_word": ew,
            "rhyme_key": key,
            "rhyme_power": {"score": score, "label": grade_for_score(score)["label"]},
            "score": score,
            "syllables": stats["syllables"],
            "cadence_delta": stats["delta_syllables"],
            "internal_count": stats["internal"],
            "alliteration_count": stats["allit"],
            "chain_note": f"/{key}/ appears on {key_counts.get(key, 0)} line(s) in this live context." if key else "No end-rhyme family detected.",
            "active": rel_no == active_tuple[0],
            "rhyme_highlight": highlight_for_line(text, key_counts, source_no, family_lines),
            "assigned_bars": "1 bar" if 7 <= stats["syllables"] <= 15 else ("2 bars" if stats["syllables"] > 15 else "half-bar/punch"),
        }
        line_reports.append(report)
    active_report = next((row for row in line_reports if row["relative_line_number"] == active_tuple[0]), line_reports[0])
    active_word = active_report.get("end_word", "")
    active_banks = word_lists_for(active_word)
    ranked = ranked_options_for(active_word)
    patches = []
    for option in ranked[:4]:
        candidate = option.get("display") or option.get("word")
        patches.append({
            "label": f"Swap ending → {candidate}",
            "operation": "replace_line_ending",
            "replacement": replace_line_ending(active_report.get("text", ""), str(candidate).split()[-1]),
            "why": f"Tests a {option.get('kind')} landing in /{active_report.get('rhyme_key')}/ family.",
        })
    if active_banks.get("internal_echoes"):
        echo = active_banks["internal_echoes"][0]
        patches.append({
            "label": f"Add echo → {echo}",
            "operation": "prepend_internal_echo",
            "replacement": f"{echo} in the {active_report.get('text', '')}",
            "why": "Adds an internal rhyme before the landing.",
        })
    actions = []
    score = int(active_report.get("score", 0))
    if score < 64:
        actions.append("Strengthen this bar: choose one ranked landing or add an internal echo before the end word.")
    else:
        actions.append("The landing is usable. Keep the rhyme family and test one sharper internal echo.")
    if active_report.get("syllables", 0) > 16:
        actions.append("Split this line across two bars or cut one prepositional phrase.")
    if key_counts.get(active_report.get("rhyme_key"), 0) < 2:
        actions.append("Give this rhyme family an answer on a nearby line so it does not feel orphaned.")
    active_report.update({
        "word_lists": active_banks,
        "ranked_options": ranked,
        "patches": patches,
        "actions": actions,
        "blueprints": [
            "Anchor-chain couplet: repeat this rhyme family on the next line with a different image.",
            "Internal ladder: place one echo in the first half of the bar, then land the end rhyme.",
            "Slant-turn release: keep the vowel family but rotate the final consonant for surprise.",
        ],
    })
    scores = [int(row.get("score", 0)) for row in line_reports]
    weak = [row.get("line_number") for row in line_reports if int(row.get("score", 0)) < 62]
    corpus_overlap = 0
    if TOP_RHYME_KEYS:
        corpus_overlap = int(round(100 * sum(1 for k in key_counts if k in TOP_RHYME_KEYS) / max(1, len(key_counts))))
    recs = []
    if weak:
        recs.append({"title": "Fix weak rhyme lines first", "detail": "Use ranked landings on these bars before changing the whole verse.", "line_numbers": weak[:8]})
    orphan = [row.get("line_number") for row in line_reports if key_counts.get(row.get("rhyme_key"), 0) == 1]
    if orphan:
        recs.append({"title": "Answer orphan rhyme families", "detail": "Repeat or slant-answer single-use rhyme keys within two lines.", "line_numbers": orphan[:8]})
    if not recs:
        recs.append({"title": "Preserve the chain", "detail": "The live context has enough rhyme linkage; focus on cadence and stress now.", "line_numbers": [active_report.get("line_number")]})
    family_ladders = []
    for key, count in key_counts.most_common(4):
        family_ladders.append({"key": key, "rhyme_key": key, "words": words_for_key(key, active_word, 10), "note": f"/{key}/ appears {count} time(s)."})
    live_static = build_live_static(active_report, line_reports, mode)
    line_reports_public = []
    for row in line_reports[:40]:
        line_reports_public.append({k: row.get(k) for k in ["available", "relative_line_number", "line_number", "text", "end_word", "rhyme_key", "rhyme_power", "score", "syllables", "cadence_delta", "internal_count", "alliteration_count", "chain_note", "active", "assigned_bars"]})
    return {
        "available": True,
        "job_id": job_id,
        "job_type": "live_rhyme_writer",
        "report_type": "live_rhyme_writer_fast_core",
        "engine": "live_rhyme_core_v1",
        "mode": mode,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "active_line_number": active_report.get("line_number"),
        "active_report": active_report,
        "line_reports": line_reports_public,
        "summary": {
            "avg_rhyme_power": int(round(sum(scores) / max(1, len(scores)))),
            "unique_rhyme_families": len([k for k in key_counts if k]),
            "weak_rhyme_lines": weak[:12],
            "corpus_rhyme_key_overlap_pct": corpus_overlap,
            "lines_analyzed": len(line_reports),
        },
        "scheme": {"recommendations": recs},
        "family_ladders": family_ladders,
        "live_static_analysis": live_static,
        "live_writer": {
            "available": True,
            "same_template": True,
            "active_line_number": active_report.get("line_number"),
            "instruction": "Direct fast-core live analysis; no queue, no polling, no worker dependency.",
            "primary_landing": active_report.get("end_word"),
            "primary_rhyme_key": active_report.get("rhyme_key"),
            "primary_rhyme_power": active_report.get("score"),
            "route_family": "live-rhyme",
            "context_clipped": bool(context_clipped),
            "fallback_used": False,
            "static_line_analysis": True,
            "beat_id": beat_id,
        },
        "context_clipped": bool(context_clipped),
        "context_offset_lines": int(context_offset or 0),
        "total_source_lines": total_source_lines,
        "payload_size_hint": "compact",
    }


def build_selected_word_payload(
    word: str,
    mode: str = "match",
    line_text: str = "",
    lyrics: str = "",
    active_line: int | None = None,
    selection_start: int | None = None,
    selection_end: int | None = None,
    job_id: str | None = None,
) -> Dict[str, Any]:
    target = clean_word(word)
    if not target:
        raise ValueError("Highlight or select a word before requesting similar rhymes.")
    key = rhyme_key(target)
    banks = word_lists_for(target)
    ranked = ranked_options_for(target, 24)
    patches = []
    for option in ranked[:12]:
        candidate = option.get("display") or option.get("word")
        patches.append({
            "type": "replace_selection",
            "label": f"Replace highlighted word → {candidate}",
            "replacement": str(candidate).split()[-1],
            "score": option.get("score"),
            "kind": option.get("kind"),
            "why": "; ".join(option.get("reasons") or []),
        })
    similar = []
    for category, words in banks.items():
        for item in words[:10]:
            similar.append({"word": item, "category": category.replace("_", " ")})
    return {
        "available": True,
        "job_id": job_id,
        "job_type": "selected_word_rhyme",
        "report_type": "highlighted_word_rhyme_fast_core",
        "engine": "live_rhyme_core_v1",
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
            "rhyme_key": key,
            "syllables": syllables(target),
            "stress_signature": "rap-heuristic",
            "best_score": ranked[0].get("score") if ranked else 0,
            "best_kind": ranked[0].get("kind") if ranked else "none",
        },
        "word_lists": banks,
        "ranked": ranked,
        "rhyme_ladder": [
            {"stage": "perfect/family", "use_when": "You want a clean landing.", "options": banks.get("end_rhymes", [])[:8]},
            {"stage": "slant turn", "use_when": "You want surprise without breaking the pocket.", "options": banks.get("slant_rhymes", [])[:8]},
            {"stage": "internal echo", "use_when": "You want more motion before the end rhyme.", "options": banks.get("internal_echoes", [])[:8]},
        ],
        "similar_rhymes": similar[:60],
        "applyable_patches": patches,
        "instruction": "Click a similar rhyme to replace the highlighted word, or use it as a landing option.",
        "fallback_used": False,
        "live_writer": {"available": True, "trigger": "highlighted_word", "instruction": "Highlight a word to fetch compact direct rhyme suggestions."},
    }


def smoke_test() -> Dict[str, Any]:
    sample = "The expression is in the direction of the diction\nThe present presence corrects the sentence"
    live = build_live_rhyme_payload(sample, active_line=1)
    word = build_selected_word_payload("diction", line_text=sample.splitlines()[0])
    return {"live_available": live.get("available"), "word_available": word.get("available"), "live_bytes_est": len(json.dumps(live)), "word_bytes_est": len(json.dumps(word))}
