"""Corpus-driven lyric analysis engine for the Flask app.

This module builds a style profile from the user's uploaded rap corpus and uses
that profile to give catalog-aware, line-level rewrite advice. It is intentionally
local/offline: no API key, no database, no internet connection.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from statistics import median
from typing import Any, Dict, Iterable, List, Sequence, Tuple

BASE_DIR = Path(__file__).resolve().parent

def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


DEFAULT_CORPUS_PATH = _path_from_env("NMC_CORPUS_PATH", BASE_DIR / "data" / "rap_corpus.txt")
DEFAULT_PROFILE_PATH = _path_from_env("NMC_PROFILE_PATH", BASE_DIR / "data" / "corpus_profile.json")
EXPOSE_CORPUS_SAMPLES = _env_bool("NMC_EXPOSE_CORPUS_SAMPLES", False)

WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")
VOWEL_RE = re.compile(r"[aeiouy]+", re.I)
SECTION_RE = re.compile(
    r"^\s*(?://\s*)?\[?\s*(intro|verse|pre[- ]?chorus|chorus|hook|bridge|outro|refrain)\s*(\d+)?\s*\]?\s*:??\s*$",
    re.I,
)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by",
    "can", "could", "did", "do", "does", "for", "from", "had", "has", "have",
    "he", "her", "hers", "him", "his", "i", "if", "in", "into", "is", "it",
    "its", "it's", "just", "me", "my", "of", "on", "or", "our", "ours", "she",
    "so", "that", "the", "their", "them", "then", "there", "they", "this", "to",
    "too", "up", "was", "we", "were", "what", "when", "where", "who", "will",
    "with", "would", "every", "each", "yet", "also", "you", "your", "yours", "im", "i'm", "ive", "i've", "dont",
    "don't", "cant", "can't", "wont", "won't", "ain", "aint", "again", "still",
    "yes", "no", "not", "all", "one", "some", "any", "than", "through", "within",
}

FILLER_WORDS = {
    "just", "really", "very", "like", "kinda", "sorta", "maybe", "basically",
    "actually", "literally", "yeah", "uh", "um", "okay", "ok", "gotta", "wanna",
    "gonna", "thing", "stuff", "something", "nothing", "seemingly", "somehow",
}

WEAK_END_WORDS = {
    "i", "me", "you", "it", "that", "this", "they", "them", "he", "she", "we",
    "us", "to", "of", "in", "on", "at", "for", "and", "but", "so", "then", "just",
    "like", "thing", "stuff", "now", "again", "with", "from", "while", "because",
}

ABSTRACT_WORDS = {
    "love", "pain", "life", "dream", "dreams", "heart", "soul", "mind", "time",
    "truth", "trust", "hate", "fear", "hope", "peace", "war", "energy", "destiny",
    "fate", "feel", "feeling", "feelings", "lonely", "alone", "broken", "real",
    "fake", "struggle", "grind", "change", "memory", "memories", "purpose",
    "presence", "essence", "distance", "system", "method", "faith", "vision",
}

CONCRETE_IMAGE_WORDS = {
    "mic", "stage", "pen", "paper", "ticket", "engine", "script", "letter", "letters",
    "sentence", "verse", "screen", "phone", "sky", "ocean", "surface", "core", "earth",
    "thread", "stitch", "circuit", "vector", "matrix", "canvas", "signal", "code",
    "bits", "digits", "curtain", "door", "entrance", "exit", "sweater", "weapon",
    "skeleton", "medicine", "cabinet", "stadium", "cranium", "lattice", "ozone",
    "mortgage", "rocket", "target", "reactor", "dice", "coin", "radians", "calculator",
    "basement", "hallway", "voicemail", "receipt", "mirror", "scar", "breath", "blood",
}

CORE_VERBS = {
    "anchor", "convert", "reverse", "stitch", "thread", "measure", "derive", "etch",
    "register", "rehearse", "observe", "determine", "preserve", "ignite", "inspire",
    "stretch", "compress", "connect", "transmit", "signal", "decode", "audit", "polish",
    "demolish", "synchronize", "maximize", "refine", "construct", "project", "resolve",
}

PUNCH_WORDS = {
    "resonance", "venom", "evidence", "script", "system", "signal", "medicine",
    "consonance", "dominance", "confidence", "monuments", "universe", "surface",
    "purpose", "service", "investment", "credit", "debt", "vector", "method",
    "signature", "sentence", "infinite", "intimate", "significant", "frontier",
    "oxymoron", "nuisance", "paradise", "entropy", "transformers", "schematics",
}

MOTIF_CLUSTERS: Dict[str, List[str]] = {
    "language craft": [
        "sentence", "sentences", "lyric", "lyrics", "verse", "verses", "rhyme", "rhymes",
        "rhythm", "rhythmic", "cadence", "bar", "bars", "pen", "script", "scripts", "words",
        "letters", "text", "texts", "method", "message", "notes", "flow", "mic", "music",
    ],
    "systems / code": [
        "system", "systems", "data", "vector", "vectors", "matrix", "algorithm", "digital",
        "code", "bits", "digits", "python", "transformers", "markov", "stochastic", "signal",
        "protocol", "logic", "queries", "embeddings", "semantic", "schema", "widgets",
    ],
    "finance / power": [
        "fed", "debt", "credit", "invest", "investment", "investor", "stock", "bond", "assets",
        "yield", "spread", "market", "payment", "cash", "prices", "options", "private", "deficit",
        "inflation", "equity", "stimulus", "companies", "business", "revenue",
    ],
    "science / math": [
        "atoms", "radians", "calculus", "distribution", "dependence", "entropy", "logical",
        "mathematics", "integrals", "physics", "decibels", "hexadecimals", "degree", "degrees",
        "percentage", "digits", "oxygen", "ozone", "radius", "spectrum", "vectors",
    ],
    "spiritual / myth": [
        "heaven", "heavenly", "satan", "devil", "christian", "jesus", "egyptian", "scripture",
        "church", "religion", "faith", "prayer", "pagan", "paradise", "vengeance", "sinners",
    ],
    "performance / confidence": [
        "mc", "rap", "rapper", "beat", "bass", "stage", "record", "track", "hook", "chorus",
        "flow", "consonants", "consonance", "dominance", "confidence", "practice", "rehearsal",
        "studio", "signature", "classic", "fantastic", "talent", "frontier",
    ],
    "struggle / reflection": [
        "pain", "anger", "fear", "dream", "dreams", "forgive", "courage", "frontier", "torment",
        "lament", "worries", "bully", "cruelty", "trust", "paranoia", "vices", "nicotine", "repent",
    ],
}

MODE_LABELS = {
    "match": "Match my corpus",
    "polish": "Polish + clarify",
    "break": "Break the pattern",
}


def clean_rtf_text(raw: str) -> str:
    """Best-effort conversion for the Apple/RTF style produced by TextEdit."""
    raw = re.sub(
        r"\\'([0-9a-fA-F]{2})",
        lambda m: bytes.fromhex(m.group(1)).decode("cp1252", errors="replace"),
        raw,
    )
    raw = raw.replace("\\\n", "\n")
    idx_candidates = [raw.find("// Chorus"), raw.find("// CHORUS"), raw.find("// Verse"), raw.find("// VERSE")]
    idx_candidates = [idx for idx in idx_candidates if idx >= 0]
    if idx_candidates:
        raw = raw[min(idx_candidates):]
    raw = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", raw)
    raw = raw.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\")
    raw = raw.replace("{", "").replace("}", "")
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def normalize_word(word: str) -> str:
    word = word.lower().replace("’", "'").replace("‘", "'")
    word = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", word)
    return word


def tokenize(text: str) -> List[str]:
    return [normalize_word(match.group(0)) for match in WORD_RE.finditer(text) if normalize_word(match.group(0))]


def content_words(words: Sequence[str]) -> List[str]:
    return [word for word in words if len(word) > 2 and word not in STOPWORDS]


def is_section_marker(line: str) -> bool:
    return bool(SECTION_RE.match(line.strip()))


def lyric_lines(text: str, include_markers: bool = False) -> List[str]:
    lines = []
    for raw in text.splitlines():
        clean = raw.strip()
        if not clean:
            continue
        if not include_markers and is_section_marker(clean):
            continue
        lines.append(clean)
    return lines


def count_syllables(word: str) -> int:
    word = normalize_word(word)
    if not word:
        return 0
    if len(word) <= 3:
        return 1
    word = re.sub(r"(?:e|es|ed)$", "", word)
    groups = VOWEL_RE.findall(word)
    count = len(groups)
    if word.endswith("le") and len(word) > 3 and word[-3] not in "aeiouy":
        count += 1
    return max(1, count)


def line_syllables(line: str) -> int:
    return sum(count_syllables(word) for word in tokenize(line))


def end_word(line: str) -> str:
    words = tokenize(line)
    return words[-1] if words else ""


def rhyme_key(word: str) -> str:
    word = normalize_word(word)
    if not word:
        return ""
    word = re.sub(r"'(s|m|re|ve|ll|d)$", "", word)
    if len(word) > 5:
        word = re.sub(r"(?:ing|ers|er|ed|es|s)$", "", word)
    if word.endswith("tion") or word.endswith("sion"):
        return "shun"
    if word.endswith("ance") or word.endswith("ence"):
        return "ence"
    if word.endswith("ment"):
        return "ment"
    if word.endswith("ness"):
        return "ness"
    if word.endswith("ics"):
        return "ics"
    match = re.search(r"[aeiouy][a-z]*$", word)
    if match:
        key = match.group(0)
    else:
        key = word[-3:]
    if len(key) > 5:
        key = key[-5:]
    return key


def ngrams(items: Sequence[str], n: int) -> Iterable[Tuple[str, ...]]:
    for i in range(0, max(0, len(items) - n + 1)):
        yield tuple(items[i : i + n])


def unique_preserve(items: Iterable[str], limit: int | None = None) -> List[str]:
    output: List[str] = []
    seen = set()
    for item in items:
        if item is None:
            continue
        text = str(item).strip(" ,.;:!?\"'“”‘’")
        if not text:
            continue
        key = normalize_word(text) or text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
        if limit is not None and len(output) >= limit:
            break
    return output


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def pct(value: float) -> int:
    return int(round(clamp(value)))


def section_blocks(text: str) -> List[Dict[str, Any]]:
    sections: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    auto_idx = 1

    def close_current() -> None:
        nonlocal current
        if current and current["lines"]:
            current["end_line"] = current["lines"][-1]["number"]
            sections.append(current)
        current = None

    for idx, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        marker = SECTION_RE.match(line)
        if marker:
            close_current()
            kind = marker.group(1).lower().replace(" ", "-")
            number = marker.group(2) or ""
            label = f"{kind.title()} {number}".strip()
            current = {"label": label, "type": kind, "start_line": idx, "end_line": idx, "lines": []}
            continue
        if current is None:
            current = {"label": f"Section {auto_idx}", "type": "section", "start_line": idx, "end_line": idx, "lines": []}
            auto_idx += 1
        current["lines"].append({"number": idx, "text": line})
    close_current()
    return sections


def internal_rhyme_hits(words: Sequence[str]) -> List[Dict[str, Any]]:
    keys: Dict[str, List[str]] = defaultdict(list)
    for word in words:
        key = rhyme_key(word)
        if key and len(key) >= 2:
            keys[key].append(word)
    hits = []
    for key, vals in keys.items():
        uniq = unique_preserve(vals)
        if len(uniq) >= 2:
            hits.append({"key": key, "words": uniq[:8], "count": len(vals)})
    hits.sort(key=lambda x: (-x["count"], x["key"]))
    return hits[:6]


def alliteration_hits(words: Sequence[str]) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[str]] = defaultdict(list)
    for word in words:
        w = normalize_word(word)
        if len(w) > 2 and w[0].isalpha():
            buckets[w[0]].append(w)
    hits = []
    for key, vals in buckets.items():
        uniq = unique_preserve(vals)
        if len(uniq) >= 2:
            hits.append({"letter": key, "words": uniq[:8], "count": len(vals)})
    hits.sort(key=lambda x: (-x["count"], x["letter"]))
    return hits[:5]


def motif_hits_for_words(words: Sequence[str]) -> Dict[str, List[str]]:
    word_set = set(words)
    hits: Dict[str, List[str]] = {}
    for cluster, cluster_words in MOTIF_CLUSTERS.items():
        found = [w for w in cluster_words if normalize_word(w) in word_set]
        if found:
            hits[cluster] = unique_preserve(found, 8)
    return hits


def top_ngrams(cw: Sequence[str], n: int, limit: int = 20) -> List[Dict[str, Any]]:
    counts = Counter(ngrams(cw, n))
    rows = []
    for phrase, count in counts.items():
        if count > 1:
            rows.append({"phrase": " ".join(phrase), "count": count})
    rows.sort(key=lambda item: (-item["count"], item["phrase"]))
    return rows[:limit]


def build_corpus_profile(corpus_text: str) -> Dict[str, Any]:
    lines = lyric_lines(corpus_text)
    marker_lines = [line for line in corpus_text.splitlines() if is_section_marker(line.strip())]
    sections = section_blocks(corpus_text)
    words = tokenize("\n".join(lines))
    cw = content_words(words)
    word_counter = Counter(words)
    content_counter = Counter(cw)

    line_details = []
    for idx, line in enumerate(lines, start=1):
        w = tokenize(line)
        c = content_words(w)
        ew = end_word(line)
        rk = rhyme_key(ew)
        sylls = line_syllables(line)
        line_details.append(
            {
                "number": idx,
                "text": line,
                "words": w,
                "content_words": c,
                "word_count": len(w),
                "syllables": sylls,
                "end_word": ew,
                "rhyme_key": rk,
                "motif_hits": motif_hits_for_words(c),
            }
        )

    syllables = [d["syllables"] for d in line_details if d["syllables"]]
    word_counts = [d["word_count"] for d in line_details if d["word_count"]]
    end_words = [d["end_word"] for d in line_details if d["end_word"]]
    rhyme_keys = [d["rhyme_key"] for d in line_details if d["rhyme_key"]]
    end_counter = Counter(end_words)
    rhyme_counter = Counter(rhyme_keys)

    rhyme_bank: Dict[str, Counter] = defaultdict(Counter)
    echo_bank: Dict[str, Counter] = defaultdict(Counter)
    for detail in line_details:
        if detail["rhyme_key"]:
            rhyme_bank[detail["rhyme_key"]].update([detail["end_word"]])
        for word in detail["content_words"]:
            key = rhyme_key(word)
            if key:
                echo_bank[key].update([word])

    motif_cluster_rows = []
    for name, cluster_words in MOTIF_CLUSTERS.items():
        count = sum(content_counter.get(normalize_word(word), 0) for word in cluster_words)
        found = [word for word in cluster_words if content_counter.get(normalize_word(word), 0) > 0]
        motif_cluster_rows.append(
            {
                "name": name,
                "count": count,
                "score": pct((count / max(1, len(cw))) * 500),
                "words": unique_preserve(found, 12),
            }
        )
    motif_cluster_rows.sort(key=lambda row: (-row["count"], row["name"]))

    section_counts = Counter()
    for section in sections:
        section_counts[section["type"]] += 1

    signature_words = [
        {"word": word, "count": count}
        for word, count in content_counter.most_common(80)
        if len(word) > 2
    ]

    top_rhymes = []
    for key, count in rhyme_counter.most_common(24):
        words_for_key = [word for word, _ in rhyme_bank[key].most_common(12)]
        top_rhymes.append({"key": key, "count": count, "words": words_for_key})

    phrase_rows = top_ngrams(cw, 2, 18) + top_ngrams(cw, 3, 18)
    phrase_rows.sort(key=lambda item: (-item["count"], len(item["phrase"])))
    phrase_rows = phrase_rows[:24]

    all_corpus_words = unique_preserve([word for word, _ in content_counter.most_common(500)], 500)
    image_words = [w for w in all_corpus_words if w in CONCRETE_IMAGE_WORDS]
    action_words = [w for w in all_corpus_words if w in CORE_VERBS]
    punch_words = [w for w in all_corpus_words if w in PUNCH_WORDS]

    # Sample lines are selected from distinct motifs so the corpus browser has useful examples.
    sample_lines = []
    seen_sample = set()
    for cluster in motif_cluster_rows[:6]:
        cluster_vocab = set(normalize_word(w) for w in cluster["words"])
        for detail in line_details:
            if set(detail["content_words"]) & cluster_vocab:
                text = detail["text"]
                key = text.lower()
                if key not in seen_sample and len(text.split()) >= 4:
                    seen_sample.add(key)
                    sample_lines.append(
                        {
                            "line": text,
                            "cluster": cluster["name"],
                            "rhyme_key": detail["rhyme_key"],
                            "syllables": detail["syllables"],
                        }
                    )
                    break
    for detail in line_details:
        if len(sample_lines) >= 18:
            break
        if detail["rhyme_key"] in {r["key"] for r in top_rhymes[:6]}:
            key = detail["text"].lower()
            if key not in seen_sample and len(detail["text"].split()) >= 4:
                seen_sample.add(key)
                sample_lines.append(
                    {
                        "line": detail["text"],
                        "cluster": "rhyme DNA",
                        "rhyme_key": detail["rhyme_key"],
                        "syllables": detail["syllables"],
                    }
                )

    stats = {
        "line_count": len(lines),
        "word_count": len(words),
        "unique_words": len(set(words)),
        "content_words": len(cw),
        "sections": len(sections),
        "section_markers": len(marker_lines),
        "median_syllables": round(float(median(syllables)), 1) if syllables else 0,
        "avg_syllables": round(sum(syllables) / len(syllables), 1) if syllables else 0,
        "median_words": round(float(median(word_counts)), 1) if word_counts else 0,
        "avg_words": round(sum(word_counts) / len(word_counts), 1) if word_counts else 0,
        "rhyme_families": len(set(rhyme_keys)),
        "unique_end_words": len(set(end_words)),
        "top_rhyme_key": top_rhymes[0]["key"] if top_rhymes else "",
        "top_signature_word": signature_words[0]["word"] if signature_words else "",
    }

    return {
        "stats": stats,
        "section_counts": dict(section_counts),
        "signature_words": signature_words,
        "top_rhymes": top_rhymes,
        "motif_clusters": motif_cluster_rows,
        "phrases": phrase_rows,
        "sample_lines": sample_lines,
        "rhyme_bank": {
            key: [word for word, _ in counter.most_common(30)] for key, counter in rhyme_bank.items()
        },
        "echo_bank": {
            key: [word for word, _ in counter.most_common(40)] for key, counter in echo_bank.items()
        },
        "word_banks": {
            "signature": [row["word"] for row in signature_words[:80]],
            "images": image_words[:48],
            "actions": action_words[:48],
            "punch": punch_words[:48],
            "all": all_corpus_words,
        },
        "corpus_words_set": sorted(set(all_corpus_words)),
    }


@lru_cache(maxsize=1)
def get_corpus_profile() -> Dict[str, Any]:
    """Return the style DNA profile used by the lyric coach.

    Beta deployments prefer a precomputed JSON profile so the public repository
    does not need to contain the user's raw lyrics. Set NMC_CORPUS_PATH to build
    from a private corpus file, or NMC_PROFILE_PATH to point at a compiled
    profile generated from that corpus.
    """
    if DEFAULT_PROFILE_PATH.exists():
        try:
            return json.loads(DEFAULT_PROFILE_PATH.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    if DEFAULT_CORPUS_PATH.exists():
        corpus_text = DEFAULT_CORPUS_PATH.read_text(encoding="utf-8", errors="replace")
    else:
        corpus_text = ""
    return build_corpus_profile(corpus_text)


def profile_summary(profile: Dict[str, Any] | None = None) -> Dict[str, Any]:
    profile = profile or get_corpus_profile()
    return {
        "stats": profile["stats"],
        "section_counts": profile["section_counts"],
        "signature_words": profile["signature_words"][:36],
        "top_rhymes": profile["top_rhymes"][:18],
        "motif_clusters": profile["motif_clusters"][:8],
        "phrases": profile["phrases"][:18] if EXPOSE_CORPUS_SAMPLES else [],
        "sample_lines": profile["sample_lines"][:18] if EXPOSE_CORPUS_SAMPLES else [],
        "mode_labels": MODE_LABELS,
    }


def component_scores(input_details: Sequence[Dict[str, Any]], input_content: Sequence[str], profile: Dict[str, Any]) -> Dict[str, Any]:
    corpus_word_set = set(profile["corpus_words_set"])
    signature_set = set(profile["word_banks"]["signature"][:40])
    input_content_set = set(input_content)
    top_rhyme_keys = {row["key"] for row in profile["top_rhymes"][:24]}
    input_rhyme_keys = [d["rhyme_key"] for d in input_details if d["rhyme_key"]]

    vocab_overlap = len([word for word in input_content if word in corpus_word_set]) / max(1, len(input_content))
    signature_presence = len(input_content_set & signature_set) / max(1, min(len(signature_set), max(1, len(input_content_set))))
    rhyme_overlap = len([key for key in input_rhyme_keys if key in top_rhyme_keys]) / max(1, len(input_rhyme_keys))

    input_syllables = [d["syllables"] for d in input_details if d["syllables"]]
    target_median = profile["stats"].get("median_syllables") or 12
    input_avg = sum(input_syllables) / len(input_syllables) if input_syllables else 0
    cadence_similarity = clamp(100 - (abs(input_avg - target_median) / max(1, target_median)) * 100)

    motif_counts = Counter()
    for detail in input_details:
        for motif in detail["motif_hits"].keys():
            motif_counts[motif] += 1
    strong_profile_motifs = {row["name"] for row in profile["motif_clusters"][:5]}
    motif_match = len(set(motif_counts.keys()) & strong_profile_motifs) / max(1, len(strong_profile_motifs))

    internal_rate = sum(1 for d in input_details if d["internal_rhymes"]) / max(1, len(input_details))
    corpus_internal_baseline = 0.52
    internal_density_score = clamp((internal_rate / corpus_internal_baseline) * 100)

    components = {
        "Vocabulary overlap": pct(vocab_overlap * 100),
        "Signature motif use": pct(signature_presence * 100),
        "Rhyme-family match": pct(rhyme_overlap * 100),
        "Cadence match": pct(cadence_similarity),
        "Internal-rhyme density": pct(internal_density_score),
        "Topic-cluster match": pct(motif_match * 100),
    }
    overall = pct(
        components["Vocabulary overlap"] * 0.18
        + components["Signature motif use"] * 0.16
        + components["Rhyme-family match"] * 0.18
        + components["Cadence match"] * 0.18
        + components["Internal-rhyme density"] * 0.16
        + components["Topic-cluster match"] * 0.14
    )
    return {
        "score": overall,
        "components": [{"name": name, "score": score} for name, score in components.items()],
        "input_avg_syllables": round(input_avg, 1),
        "target_median_syllables": target_median,
        "rhyme_keys_used": sorted(set(input_rhyme_keys)),
        "motifs_used": [{"name": name, "count": count} for name, count in motif_counts.most_common()],
    }


def _vowel_tail(word: str) -> str:
    word = normalize_word(word)
    groups = VOWEL_RE.findall(word)
    return groups[-1].lower() if groups else ""


def _consonant_tail(word: str) -> str:
    word = normalize_word(word)
    frame = re.sub(r"[aeiouy]+", "", word)
    frame = re.sub(r"(.)\1+", r"\1", frame)
    return frame[-3:]


def possible_rhymes_for_word(word: str, profile: Dict[str, Any] | None = None, limit: int = 18) -> Dict[str, Any]:
    profile = profile or get_corpus_profile()
    normalized = normalize_word(word)
    key = rhyme_key(normalized)
    bank = profile["rhyme_bank"].get(key, [])
    echo = profile["echo_bank"].get(key, [])

    # Looser fallback: match the last 2 chars of the rhyme key, share the last
    # vowel color, or share a clipped consonant frame. These extra categories
    # make the app's rhyme banks more useful for rap, where slant rhyme,
    # assonance, consonance, and internal echoes often matter more than exact
    # dictionary rhyme.
    near: List[str] = []
    assonance: List[str] = []
    consonance: List[str] = []
    multi_syllable: List[str] = []
    family_rotations: List[str] = []
    all_candidates = profile["word_banks"].get("all", [])
    target_vowel = _vowel_tail(normalized)
    target_consonants = _consonant_tail(normalized)
    if len(key) >= 2:
        tail = key[-2:]
        for candidate in all_candidates:
            c_norm = normalize_word(candidate)
            if not c_norm or c_norm == normalized:
                continue
            ck = rhyme_key(c_norm)
            if ck == key:
                family_rotations.append(c_norm)
            if ck.endswith(tail) or tail in ck[-3:]:
                near.append(c_norm)
            if target_vowel and _vowel_tail(c_norm) == target_vowel:
                assonance.append(c_norm)
            if target_consonants and _consonant_tail(c_norm) == target_consonants:
                consonance.append(c_norm)
            if count_syllables(c_norm) >= 3 and (ck == key or ck.endswith(tail) or (target_vowel and _vowel_tail(c_norm) == target_vowel)):
                multi_syllable.append(c_norm)

    phrase_landings: List[str] = []
    phrase_seed_words = unique_preserve(list(bank) + family_rotations + near + assonance, 16)
    phrase_prefixes = unique_preserve(
        profile["word_banks"].get("actions", [])[:8]
        + profile["word_banks"].get("images", [])[:8]
        + ["hidden", "written", "coded", "threaded", "rhythmic", "digital", "signal", "pressure"],
        20,
    )
    for end in phrase_seed_words:
        for prefix in phrase_prefixes:
            p_norm = normalize_word(prefix)
            if not p_norm or p_norm == end:
                continue
            phrase = f"{prefix} {end}"
            if sum(count_syllables(w) for w in tokenize(phrase)) <= 7:
                phrase_landings.append(phrase)
                break
        if len(phrase_landings) >= limit:
            break

    pivot_families = []
    for row in profile.get("top_rhymes", [])[:12]:
        pivot_key = row.get("key", "")
        if pivot_key and pivot_key != key:
            pivot_families.append({
                "rhyme_key": pivot_key,
                "words": unique_preserve(row.get("words", []), 8),
            })

    end_rhymes = unique_preserve([w for w in bank if w != normalized], limit)
    internal_echoes = unique_preserve([w for w in echo if w != normalized], limit)
    near_rhymes = unique_preserve(near, limit)
    return {
        "word": normalized,
        "rhyme_key": key,
        "end_rhymes": end_rhymes,
        "internal_echoes": internal_echoes,
        "near_rhymes": near_rhymes,
        "strict_rhymes": end_rhymes,
        "family_rotations": unique_preserve(family_rotations, limit),
        "slant_rhymes": near_rhymes,
        "assonance_rhymes": unique_preserve(assonance, limit),
        "consonance_rhymes": unique_preserve(consonance, limit),
        "multi_syllable_rhymes": unique_preserve(multi_syllable, limit),
        "phrase_landings": unique_preserve(phrase_landings, limit),
        "pivot_families": pivot_families[:8],
    }


def cut_candidates(words: Sequence[str]) -> List[str]:
    counts = Counter(words)
    candidates: List[str] = []
    candidates.extend([w for w in words if w in FILLER_WORDS])
    candidates.extend([w for w in words if w in STOPWORDS and w not in {"i", "me", "my", "you", "your", "we", "us"}])
    candidates.extend([w for w, count in counts.items() if count > 1 and len(w) > 3])
    return unique_preserve(candidates, 10)


def motif_words_for_line(detail: Dict[str, Any], profile: Dict[str, Any], mode: str) -> List[str]:
    current = set(detail["content_words"])
    candidates: List[str] = []
    if detail["motif_hits"]:
        for cluster in detail["motif_hits"].keys():
            candidates.extend(MOTIF_CLUSTERS.get(cluster, []))
    else:
        for cluster in profile["motif_clusters"][:3]:
            candidates.extend(cluster["words"])
    candidates.extend(profile["word_banks"]["signature"][:30])
    if mode == "break":
        # For break mode, avoid the top-most default words and prefer less-used corpus terms.
        candidates = profile["word_banks"]["all"][60:160] + candidates
    return unique_preserve([w for w in candidates if normalize_word(w) not in current and len(normalize_word(w)) > 2], 14)


def image_words_for_line(detail: Dict[str, Any], profile: Dict[str, Any], mode: str) -> List[str]:
    current = set(detail["content_words"])
    corpus_images = profile["word_banks"].get("images", [])
    fallback = [
        "mic", "stage", "ticket", "signal", "canvas", "mirror", "receipt", "engine",
        "skeleton", "circuit", "surface", "core", "thread", "script", "paper", "ocean",
        "sky", "door", "entrance", "exit", "vector", "dice", "rocket", "target",
    ]
    if mode == "polish":
        fallback = ["mirror", "receipt", "door", "phone", "breath", "scar", "notebook", "streetlight"] + fallback
    return unique_preserve([w for w in corpus_images + fallback if normalize_word(w) not in current], 12)


def action_words_for_line(detail: Dict[str, Any], profile: Dict[str, Any], mode: str) -> List[str]:
    current = set(detail["content_words"])
    corpus_actions = profile["word_banks"].get("actions", [])
    fallback = [
        "anchor", "convert", "reverse", "stitch", "thread", "measure", "derive", "etch",
        "register", "rehearse", "observe", "determine", "preserve", "ignite", "inspire",
        "stretch", "compress", "decode", "synchronize", "maximize", "refine",
    ]
    if mode == "break":
        fallback = ["collide", "fracture", "swerve", "subtract", "mutate", "rupture"] + fallback
    return unique_preserve([w for w in corpus_actions + fallback if normalize_word(w) not in current], 12)


def phrase_sparks_for_line(detail: Dict[str, Any], profile: Dict[str, Any]) -> List[str]:
    current = set(detail["content_words"])
    phrases = []
    for row in profile["phrases"]:
        parts = row["phrase"].split()
        if not (set(parts) & current):
            continue
        phrases.append(row["phrase"])
    if not phrases:
        phrases = [row["phrase"] for row in profile["phrases"][:10]]
    return unique_preserve(phrases, 8)


def build_line_details(text: str) -> List[Dict[str, Any]]:
    details = []
    raw_lines = text.splitlines()
    for idx, raw in enumerate(raw_lines, start=1):
        clean = raw.strip()
        if not clean or is_section_marker(clean):
            continue
        words = tokenize(clean)
        cw = content_words(words)
        ew = end_word(clean)
        rk = rhyme_key(ew)
        details.append(
            {
                "number": idx,
                "text": clean,
                "words": words,
                "content_words": cw,
                "word_count": len(words),
                "syllables": line_syllables(clean),
                "end_word": ew,
                "rhyme_key": rk,
                "internal_rhymes": internal_rhyme_hits(cw),
                "alliteration": alliteration_hits(cw),
                "motif_hits": motif_hits_for_words(cw),
                "abstract_words": [w for w in cw if w in ABSTRACT_WORDS],
                "image_words": [w for w in cw if w in CONCRETE_IMAGE_WORDS],
                "filler_words": [w for w in words if w in FILLER_WORDS],
                "cut_candidates": cut_candidates(words),
            }
        )
    return details


def line_suggestion(detail: Dict[str, Any], profile: Dict[str, Any], mode: str, input_end_counts: Counter) -> Dict[str, Any]:
    mode = mode if mode in MODE_LABELS else "match"
    target_median = profile["stats"].get("median_syllables") or 12
    tolerance = 4 if mode != "polish" else 3
    issues: List[Dict[str, str]] = []
    moves: List[str] = []

    syll_delta = detail["syllables"] - target_median
    if syll_delta > tolerance:
        issues.append({"type": "cadence", "message": f"Long against your catalog median by about {round(syll_delta, 1)} syllables."})
        moves.append(f"Trim {max(1, round(syll_delta))} syllable(s); keep the strongest noun and the end-rhyme position.")
    elif syll_delta < -tolerance:
        issues.append({"type": "cadence", "message": f"Short against your catalog median by about {abs(round(syll_delta, 1))} syllables."})
        moves.append(f"Add {max(1, round(abs(syll_delta)))} syllable(s) with one technical image before the final word.")
    else:
        moves.append("Cadence is near your corpus pocket; revise for punch, not length.")

    if detail["end_word"] in WEAK_END_WORDS:
        issues.append({"type": "end word", "message": "The final word is a weak landing spot."})
        moves.append("Move a harder noun or concept to the end of the line so the rhyme lands with weight.")

    if input_end_counts[detail["end_word"]] > 1 and detail["end_word"]:
        issues.append({"type": "repetition", "message": f"The end word “{detail['end_word']}” repeats in this draft."})
        moves.append("Keep the rhyme family, but rotate the actual end word to avoid a flat repeat.")

    if detail["word_count"] >= 8 and not detail["internal_rhymes"]:
        issues.append({"type": "internal rhyme", "message": "Dense line, but no strong internal echo detected."})
        moves.append("Add one mid-line echo before the comma/turn; your corpus often stacks sound inside the bar.")

    if len(detail["abstract_words"]) >= 2 and not detail["image_words"]:
        issues.append({"type": "imagery", "message": "Abstract-heavy line without a visible object."})
        moves.append("Translate one abstract idea into a concrete object: mic, ticket, vector, mirror, signal, engine, etc.")

    if mode == "match" and not detail["motif_hits"]:
        issues.append({"type": "style DNA", "message": "This line is low on your signature corpus motifs."})
        moves.append("Inject one recurring motif from your catalog—system, sentence, rhythm, method, evidence, vector, credit, or surface.")

    if mode == "break" and len(detail["motif_hits"]) >= 2:
        issues.append({"type": "freshness", "message": "This line leans heavily on existing corpus motifs."})
        moves.append("Keep the cadence, but replace one familiar motif with a new physical scene or character action.")

    rhyme_options = possible_rhymes_for_word(detail["end_word"], profile, 18)
    motif_options = motif_words_for_line(detail, profile, mode)
    image_options = image_words_for_line(detail, profile, mode)
    action_options = action_words_for_line(detail, profile, mode)
    phrase_options = phrase_sparks_for_line(detail, profile)
    punch_options = unique_preserve(profile["word_banks"].get("punch", []) + list(PUNCH_WORDS), 12)
    advanced_rhyme: Dict[str, Any]
    try:
        from rhyme_engine import advanced_rhyme_for_line, compact_word_lists
        advanced_rhyme = advanced_rhyme_for_line(detail, profile=profile, mode=mode, end_counts=input_end_counts)
        advanced_lists = compact_word_lists(advanced_rhyme, 18)
    except Exception as exc:
        advanced_rhyme = {"available": False, "error": str(exc)}
        advanced_lists = {}

    if not issues:
        issues.append({"type": "fine tune", "message": "No major issue detected; polish the line for a sharper turn or more surprise."})

    formulas = []
    if rhyme_options["end_rhymes"]:
        formulas.append(
            f"Keep the setup, add an internal echo, then land on “{rhyme_options['end_rhymes'][0]}” instead of “{detail['end_word']}”."
        )
    if advanced_rhyme.get("available") and advanced_rhyme.get("actions"):
        formulas.append(str(advanced_rhyme["actions"][0]))
    if motif_options and image_options:
        formulas.append(f"Build it as: {motif_options[0]} → {image_options[0]} → action verb → punch end.")
    if detail["abstract_words"] and image_options:
        formulas.append(f"Replace “{detail['abstract_words'][0]}” with a scene/object like “{image_options[0]}”.")
    formulas.append("Revision frame: setup the concept, compress the middle, then make the final word carry the rhyme and meaning.")

    sample_matches = []
    key = detail["rhyme_key"]
    for sample in profile["sample_lines"]:
        if sample["rhyme_key"] == key or (sample["cluster"] in detail["motif_hits"]):
            sample_matches.append(sample)
        if len(sample_matches) >= 2:
            break

    return {
        "number": detail["number"],
        "text": detail["text"],
        "metrics": {
            "words": detail["word_count"],
            "syllables": detail["syllables"],
            "target_syllables": target_median,
            "end_word": detail["end_word"],
            "rhyme_key": detail["rhyme_key"],
            "internal_rhyme_groups": len(detail["internal_rhymes"]),
            "alliteration_groups": len(detail["alliteration"]),
        },
        "issues": issues,
        "specific_moves": unique_preserve(moves, 8),
        "possible_words": {
            "end_rhymes_from_your_corpus": unique_preserve(rhyme_options["end_rhymes"] + advanced_lists.get("end_rhymes", []), 18),
            "near_rhymes_from_your_corpus": unique_preserve(rhyme_options["near_rhymes"] + advanced_lists.get("near_rhymes", []), 18),
            "internal_echo_words": unique_preserve(rhyme_options["internal_echoes"] + advanced_lists.get("internal_echoes", []), 18),
            "slant_rhyme_words": advanced_lists.get("slant_rhymes", [])[:14],
            "assonance_words": advanced_lists.get("assonance_words", [])[:14],
            "consonance_words": advanced_lists.get("consonance_words", [])[:14],
            "stress_matched_words": advanced_lists.get("stress_matched", [])[:14],
            "multi_syllable_endings": advanced_lists.get("multi_syllable_endings", [])[:14],
            "signature_motif_words": motif_options,
            "concrete_image_words": image_options,
            "stronger_verbs": action_options,
            "punch_words": punch_options,
            "phrase_sparks": phrase_options,
            "cut_or_replace": detail["cut_candidates"],
        },
        "advanced_rhyme": advanced_rhyme,
        "sound_hits": {
            "internal_rhymes": detail["internal_rhymes"],
            "alliteration": detail["alliteration"],
        },
        "motif_hits": detail["motif_hits"],
        "rewrite_formulas": unique_preserve(formulas, 4),
        "nearby_corpus_lines": sample_matches,
    }


def rhyme_scheme(details: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    keys = [d["rhyme_key"] for d in details if d["rhyme_key"]]
    key_to_letter: Dict[str, str] = {}
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    scheme = []
    for detail in details:
        key = detail["rhyme_key"]
        if not key:
            scheme.append("-")
            continue
        if key not in key_to_letter:
            idx = len(key_to_letter)
            if idx < len(letters):
                key_to_letter[key] = letters[idx]
            else:
                key_to_letter[key] = f"R{idx+1}"
        scheme.append(key_to_letter[key])
    groups = []
    by_key = defaultdict(list)
    for detail in details:
        if detail["rhyme_key"]:
            by_key[detail["rhyme_key"]].append(detail)
    for key, rows in by_key.items():
        if len(rows) > 1:
            groups.append(
                {
                    "key": key,
                    "letter": key_to_letter.get(key, ""),
                    "count": len(rows),
                    "end_words": unique_preserve([row["end_word"] for row in rows], 12),
                    "line_numbers": [row["number"] for row in rows],
                }
            )
    groups.sort(key=lambda item: (-item["count"], item["key"]))
    density = len([key for key in Counter(keys).values() if key > 1]) / max(1, len(set(keys)))
    return {"scheme": " ".join(scheme), "groups": groups[:18], "density": pct(density * 100)}


def priority_actions(analysis: Dict[str, Any], mode: str) -> List[Dict[str, str]]:
    actions: List[Dict[str, str]] = []
    style = analysis["style_match"]
    stats = analysis["stats"]
    components = {item["name"]: item["score"] for item in style["components"]}
    if components.get("Cadence match", 100) < 72:
        actions.append({"title": "Fix cadence first", "detail": f"Your average line is {style['input_avg_syllables']} syllables against a corpus target near {style['target_median_syllables']}."})
    if components.get("Rhyme-family match", 100) < 55 and mode == "match":
        actions.append({"title": "Use more corpus rhyme families", "detail": "Lean into your strongest endings: -ence, -ist, -ice, -ight, -ing, -ation, and -ment families when they fit."})
    if components.get("Internal-rhyme density", 100) < 60:
        actions.append({"title": "Add mid-bar sound", "detail": "Many lines in your corpus stack echoes before the end word; add one internal rhyme in longer lines."})
    if stats["abstract_ratio"] > 28:
        actions.append({"title": "Make abstractions visible", "detail": "Turn purpose/presence/system/method into physical images like ticket, vector, mic, engine, surface, or circuit."})
    if mode == "break":
        actions.append({"title": "Break signature habits intentionally", "detail": "Keep the dense cadence, but replace one default motif per four lines with a new scene, character, or object."})
    if not actions:
        actions.append({"title": "Draft is structurally healthy", "detail": "Focus on punch endings, title choice, and one memorable image per section."})
    return actions[:5]


def title_candidates(details: Sequence[Dict[str, Any]], input_content: Sequence[str], profile: Dict[str, Any]) -> List[str]:
    counts = Counter(input_content)
    candidates: List[str] = []
    # Short input lines often make good titles.
    for detail in details:
        if 2 <= detail["word_count"] <= 7:
            candidates.append(detail["text"].strip(" ,.;:!?\"'“”‘’"))
    for word, _ in counts.most_common(8):
        if len(word) > 4:
            candidates.append(word)
    for motif in profile["motif_clusters"][:4]:
        if motif["words"]:
            candidates.append(f"{motif['words'][0]} protocol")
    for rhyme in profile["top_rhymes"][:4]:
        if rhyme["words"]:
            candidates.append(f"{rhyme['words'][0]} resonance")
    clean = []
    for item in unique_preserve(candidates, 10):
        item = " ".join(word.capitalize() for word in item.split())
        if 2 <= len(item) <= 60:
            clean.append(item)
    return unique_preserve(clean, 8)


def analyze_lyrics(lyrics: str, mode: str = "match") -> Dict[str, Any]:
    mode = mode if mode in MODE_LABELS else "match"
    profile = get_corpus_profile()
    details = build_line_details(lyrics)
    all_words = tokenize(lyrics)
    all_content = content_words(all_words)
    syllables = [d["syllables"] for d in details]
    end_counts = Counter(d["end_word"] for d in details if d["end_word"])
    style = component_scores(details, all_content, profile)
    scheme = rhyme_scheme(details)

    abstract_count = sum(len(d["abstract_words"]) for d in details)
    image_count = sum(len(d["image_words"]) for d in details)
    internal_count = sum(len(d["internal_rhymes"]) for d in details)
    motif_counter = Counter()
    for detail in details:
        for motif in detail["motif_hits"].keys():
            motif_counter[motif] += 1

    line_cards = [line_suggestion(detail, profile, mode, end_counts) for detail in details]

    stats = {
        "lines": len(details),
        "words": len(all_words),
        "unique_words": len(set(all_words)),
        "content_words": len(all_content),
        "avg_syllables": round(sum(syllables) / len(syllables), 1) if syllables else 0,
        "median_syllables": round(float(median(syllables)), 1) if syllables else 0,
        "rhyme_density": scheme["density"],
        "internal_rhyme_lines": sum(1 for d in details if d["internal_rhymes"]),
        "internal_rhyme_groups": internal_count,
        "abstract_ratio": pct((abstract_count / max(1, len(all_content))) * 100),
        "image_ratio": pct((image_count / max(1, len(all_content))) * 100),
        "style_match": style["score"],
    }

    analysis: Dict[str, Any] = {
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "stats": stats,
        "style_match": style,
        "rhyme_scheme": scheme,
        "top_input_words": [{"word": w, "count": c} for w, c in Counter(all_content).most_common(24)],
        "motifs_used": [{"name": name, "count": count} for name, count in motif_counter.most_common()],
        "line_suggestions": line_cards,
        "sections": section_blocks(lyrics),
        "title_candidates": title_candidates(details, all_content, profile),
        "corpus_profile": profile_summary(profile),
        "raw_line_details": details,
    }
    analysis["priority_actions"] = priority_actions(analysis, mode)
    return analysis


def to_pretty_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)
