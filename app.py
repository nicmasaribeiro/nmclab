from __future__ import annotations

import io
import json
import os
import platform
import re
import socket
import sys
import threading
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hmac import compare_digest
from pathlib import Path
from typing import Any, Dict, Tuple

from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename

from beat_engine import ALLOWED_AUDIO_EXTENSIONS, analyze_beat, attach_beat_guidance, beat_backend_status
from song_engine import SUPPORTED_TTS_BACKENDS, VOICE_PRESETS, INTENSITY_PRESETS, available_tts_engines, build_timing_plan, render_song, render_voice_sample
from comparison_engine import build_comparison_report, comparison_summary
from editing_engine import build_editing_lab_result, build_line_fix, build_sentence_sync_feedback, build_static_line_breakdown
from meter_engine import analyze_meter_text, analyze_sentence_meter
from physics_engine import PHYSICAL_ANCHORS, SYMBOL_LEGEND, NOTEBOOK_TEST_PAIRS, build_scansion_physics_report, build_sentence_physics_report
from rhyme_engine import advanced_rhyme_for_word, build_rhyme_suggestion_lab
from live_rhyme_core import build_live_rhyme_payload, build_selected_word_payload as build_selected_word_core_payload, smoke_test as live_rhyme_core_smoke_test
from sentence_pattern_engine import compare_sentence_rhyme_patterns
from score_engine import build_rap_score_report, compare_rap_edits
from report_engine import build_csv_report, build_pdf_report, report_filename
from live_writer_engine import build_live_writer_payload, build_selected_word_payload as build_live_writer_word_payload
from fast_snapshot_engine import build_fast_snapshot_report
from lyric_engine import (
    MODE_LABELS,
    analyze_lyrics,
    clean_rtf_text,
    count_syllables,
    end_word as lyric_end_word,
    get_corpus_profile,
    possible_rhymes_for_word,
    profile_summary,
    rhyme_key as lyric_rhyme_key,
    tokenize as lyric_tokenize,
    to_pretty_json,
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, low: int | None = None, high: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except Exception:
        value = default
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


APP_NAME = os.getenv("APP_NAME", "NMC Live Rhyme Writer Lab")
APP_VERSION = os.getenv("APP_VERSION", "2026.07-snapshot-fast-v9")
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"prod", "production"}


def _detect_pythonanywhere() -> bool:
    probes = [
        os.getenv("PYTHONANYWHERE_DOMAIN"),
        os.getenv("PYTHONANYWHERE_SITE"),
        os.getenv("PYTHONANYWHERE_USERNAME"),
        os.getenv("PYTHONANYWHERE_APP_ROOT"),
        os.getenv("SERVER_SOFTWARE"),
    ]
    try:
        probes.append(socket.gethostname())
    except Exception:
        pass
    joined = " ".join(str(item or "") for item in probes).lower()
    return "pythonanywhere" in joined or "/home/" in str(Path(__file__).resolve()).lower() and "pythonanywhere" in joined


PYTHONANYWHERE_COMPAT = _env_bool("PYTHONANYWHERE_COMPAT", _detect_pythonanywhere())
ASYNC_JOB_MODE = os.getenv("ASYNC_JOB_MODE", "inline" if PYTHONANYWHERE_COMPAT else "thread").strip().lower()
INLINE_GENERAL_ASYNC = True  # Refactor: all writing-analysis routes complete inside the request; no WSGI queue.
# Live rhyme is now direct-by-default. The browser still uses asynchronous fetches,
# but the server returns the completed result in the POST response and never depends
# on a queued in-memory poll cycle for the live writer. This is the most reliable
# mode for PythonAnywhere and other WSGI-only hosts.
LIVE_RHYME_INLINE_JOBS = True
LIVE_RHYME_DIRECT_JOBS = True

NOTEBOOK_MODEL = {
    "available": True,
    "model_name": "Scansion Physics",
    "image_path": "reference/scansion_notebook.jpg",
    "symbol_legend": SYMBOL_LEGEND,
    "physical_anchors": PHYSICAL_ANCHORS,
    "notebook_test_pairs": NOTEBOOK_TEST_PAIRS,
    "pipeline": ["word", "syllables", "stress", "beat phase θ", "force F", "torsion τ", "spin Ω", "cadence delta ΔC", "flow advice"],
}

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
app.secret_key = os.getenv("SECRET_KEY") or ("dev-change-me" if not IS_PRODUCTION else uuid.uuid4().hex)
app.config.update(
    MAX_CONTENT_LENGTH=_env_int("MAX_UPLOAD_MB", 80, low=1, high=500) * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=_env_bool("SESSION_COOKIE_SECURE", IS_PRODUCTION),
    PREFERRED_URL_SCHEME="https" if IS_PRODUCTION else "http",
)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "runtime_uploads"))).expanduser()
if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = BASE_DIR / UPLOAD_DIR
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "runtime_data"))).expanduser()
if not DATA_DIR.is_absolute():
    DATA_DIR = BASE_DIR / DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(DATA_DIR / "renders"))).expanduser()
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = BASE_DIR / OUTPUT_DIR
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TEXT_EXTENSIONS = (".txt", ".md", ".lyrics", ".rtf")
MAX_LYRICS_CHARS = _env_int("MAX_LYRICS_CHARS", 120_000, low=1_000, high=1_000_000)
MAX_SENTENCE_CHARS = _env_int("MAX_SENTENCE_CHARS", 1600, low=120, high=12000)
MAX_TEXT_UPLOAD_BYTES = _env_int("MAX_TEXT_UPLOAD_MB", 5, low=1, high=50) * 1024 * 1024
MAX_BEAT_UPLOAD_BYTES = _env_int("MAX_BEAT_UPLOAD_MB", 80, low=1, high=500) * 1024 * 1024
BETA_ACCESS_CODE = os.getenv("BETA_ACCESS_CODE", "").strip()
ADMIN_TOKEN = os.getenv("BETA_ADMIN_TOKEN", "").strip()
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()
RATE_LIMIT_PER_MINUTE = _env_int("RATE_LIMIT_PER_MINUTE", 90, low=5, high=5000)
JOB_TTL_SECONDS = _env_int("JOB_TTL_SECONDS", 20 * 60, low=60, high=24 * 3600)
BEAT_TTL_SECONDS = _env_int("BEAT_TTL_SECONDS", 60 * 60, low=120, high=24 * 3600)
SONG_TTL_SECONDS = _env_int("SONG_TTL_SECONDS", 2 * 60 * 60, low=300, high=7 * 24 * 3600)
MAX_RENDERS = _env_int("MAX_RENDERS", 40, low=1, high=500)
MAX_RENDER_SECONDS = _env_int("MAX_RENDER_SECONDS", 240, low=10, high=900)
MAX_SONG_RENDER_LINES = _env_int("MAX_SONG_RENDER_LINES", 96, low=1, high=240)
FEEDBACK_PATH = DATA_DIR / os.getenv("FEEDBACK_FILENAME", "beta_feedback.jsonl")

ASYNC_WORKERS = _env_int("ASYNC_WORKERS", 2, low=1, high=8)
EXECUTOR = None if (INLINE_GENERAL_ASYNC and LIVE_RHYME_INLINE_JOBS) else ThreadPoolExecutor(max_workers=ASYNC_WORKERS)
JOBS: Dict[str, Dict[str, Any]] = {}
BEATS: Dict[str, Dict[str, Any]] = {}
RENDERS: Dict[str, Dict[str, Any]] = {}
RATE_BUCKETS: Dict[str, deque[float]] = defaultdict(deque)
STATE_LOCK = threading.Lock()
MAX_JOBS = _env_int("MAX_JOBS", 80, low=10, high=1000)
MAX_BEATS = _env_int("MAX_BEATS", 12, low=1, high=200)
PUBLIC_ENDPOINTS = {"beta_login", "beta_logout", "healthz", "readyz", "robots_txt", "privacy", "terms", "static"}


def _now() -> float:
    return time.time()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json_payload() -> Dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


def _mode(value: Any, default: str = "match") -> str:
    return value if isinstance(value, str) and value in MODE_LABELS else default


def _active_line(value: Any) -> int | None:
    try:
        line = int(value)
        return line if line > 0 else None
    except Exception:
        return None


def _live_rhyme_request_fields(payload: Dict[str, Any]) -> tuple[str, str, int | None]:
    """Normalize all UI/API aliases for the live rhyme writer.

    Older front-end builds used `lyrics` and `active_line`; testers often tried
    `text`, `draft`, `line`, or `line_number`. Accepting those aliases keeps
    the route usable and makes the endpoint resilient for beta users.
    """
    lyrics = payload.get("lyrics")
    if lyrics is None:
        lyrics = payload.get("text")
    if lyrics is None:
        lyrics = payload.get("draft")
    if lyrics is None:
        lyrics = payload.get("content")
    mode = _mode(payload.get("coach_mode", payload.get("mode", "match")))
    active = _active_line(
        payload.get("active_line")
        or payload.get("line_number")
        or payload.get("line")
        or payload.get("cursor_line")
    )
    return str(lyrics or ""), mode, active


def _clip_lyrics_around_line(lyrics: str, active_line: int | None, max_chars: int | None = None) -> tuple[str, int | None, int, bool, int]:
    """Keep live analysis responsive by clipping huge drafts around the active line.

    Static snapshots still analyze the whole draft. Live sidecars should not fail
    just because a beta tester pasted an entire notebook or a long corpus.
    """
    lyrics = str(lyrics or "")
    max_chars = max_chars or max(6000, min(MAX_LYRICS_CHARS, _env_int("LIVE_RHYME_MAX_CHARS", 2600, low=600, high=MAX_LYRICS_CHARS)))
    lines = lyrics.splitlines() or [lyrics]
    total = len(lines)
    radius = _env_int("LIVE_RHYME_CONTEXT_RADIUS", 6, low=2, high=160)
    if len(lyrics) <= max_chars and total <= (radius * 2 + 1):
        return lyrics, active_line, 0, False, total
    if active_line is None:
        active_line = 1
    idx = max(0, min(total - 1, int(active_line) - 1))
    start = max(0, idx - radius)
    end = min(total, idx + radius + 1)
    clipped = "\n".join(lines[start:end])
    while len(clipped) > max_chars and end - start > 12:
        if idx - start > end - idx - 1:
            start += 1
        else:
            end -= 1
        clipped = "\n".join(lines[start:end])
    return clipped, idx - start + 1, start, True, total




def _int_payload(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _live_route_exempt() -> bool:
    """Live-rhyme routes poll frequently while a user types.

    The beta rate limiter is still useful for heavyweight endpoints, but the live
    sidecar should not flash error states just because the browser polled a job
    several times. These endpoints use small clipped contexts and in-memory jobs.
    """
    path = request.path.rstrip("/")
    prefixes = (
        "/api/live-rhyme",
        "/api/rhyme/live",
        "/api/rhyme-word",
        "/api/rhyme/word-job",
        "/api/rhyme/similar",
    )
    return any(path.startswith(prefix) for prefix in prefixes)


def _safe_word_lists(word: str) -> Dict[str, Any]:
    try:
        return possible_rhymes_for_word(word)
    except Exception:
        key = lyric_rhyme_key(word)
        fallback_words = ["sentence", "presence", "essence", "resonance", "diction", "friction", "scripture", "picture", "purpose", "surface"]
        return {
            "word": word,
            "rhyme_key": key,
            "end_rhymes": fallback_words,
            "near_rhymes": fallback_words,
            "internal_echoes": fallback_words,
            "slant_rhymes": fallback_words,
            "multi_syllable_rhymes": fallback_words[:5],
            "phrase_landings": [f"{prefix} {word}" for prefix in ["signal", "pressure", "system", "rhythm"]],
        }


def _fallback_ranked_options(word: str, word_lists: Dict[str, Any], limit: int = 18) -> list[Dict[str, Any]]:
    ranked: list[Dict[str, Any]] = []
    seen: set[str] = set()
    buckets = [
        ("perfect", word_lists.get("strict_rhymes") or word_lists.get("end_rhymes") or []),
        ("family", word_lists.get("end_rhymes") or []),
        ("slant", word_lists.get("slant_rhymes") or word_lists.get("near_rhymes") or []),
        ("internal", word_lists.get("internal_echoes") or []),
        ("multi", word_lists.get("multi_syllable_rhymes") or []),
    ]
    base = 96
    for kind, words in buckets:
        for candidate in words:
            candidate = str(candidate or "").strip()
            if not candidate or candidate.lower() == str(word).lower() or candidate.lower() in seen:
                continue
            seen.add(candidate.lower())
            ranked.append({
                "word": candidate,
                "display": candidate,
                "kind": kind,
                "score": max(45, base - len(ranked) * 3),
                "reasons": [f"{kind} rhyme candidate", f"/{word_lists.get('rhyme_key') or lyric_rhyme_key(word)}/ family"],
            })
            if len(ranked) >= limit:
                return ranked
    return ranked


def _fallback_live_rhyme_result(lyrics: str, mode: str, active_line: int | None, warning: str | None = None) -> Dict[str, Any]:
    lines = [line for line in str(lyrics or "").splitlines()]
    editable = [(idx + 1, line.strip()) for idx, line in enumerate(lines) if line.strip() and not line.strip().startswith("//")]
    if not editable and str(lyrics or "").strip():
        editable = [(1, str(lyrics).strip())]
    active_line = active_line or (editable[0][0] if editable else 1)
    active_text = ""
    for number, text in editable:
        if number == active_line:
            active_text = text
            break
    if not active_text and editable:
        active_line, active_text = editable[min(len(editable) - 1, max(0, active_line - 1))]
    active_end = lyric_end_word(active_text) if active_text else ""
    active_key = lyric_rhyme_key(active_end) if active_end else ""
    word_lists = _safe_word_lists(active_end) if active_end else {}
    ranked = _fallback_ranked_options(active_end, word_lists)
    key_counts: Dict[str, int] = {}
    line_reports = []
    for number, text in editable[:96]:
        ew = lyric_end_word(text)
        key = lyric_rhyme_key(ew) if ew else ""
        if key:
            key_counts[key] = key_counts.get(key, 0) + 1
    for number, text in editable[:96]:
        ew = lyric_end_word(text)
        key = lyric_rhyme_key(ew) if ew else ""
        repeats = key_counts.get(key, 0)
        score = 74 if repeats > 1 else 58
        if number == active_line:
            score += 8
        line_reports.append({
            "line_number": number,
            "text": text,
            "end_word": ew,
            "rhyme_key": key,
            "active": number == active_line,
            "rhyme_power": {"score": min(100, score), "label": "fallback" if warning else "live"},
        })
    active_report = {
        "available": bool(active_text),
        "active": True,
        "line_number": active_line,
        "text": active_text,
        "end_word": active_end,
        "rhyme_key": active_key,
        "rhyme_power": {"score": 72 if active_end else 0, "label": "safe fallback" if warning else "live"},
        "chain_note": f"{key_counts.get(active_key, 0)} line(s) use /{active_key}/" if active_key else "no landing word",
        "word_lists": {
            "end_rhymes": word_lists.get("end_rhymes", [])[:18],
            "near_rhymes": word_lists.get("near_rhymes", [])[:18],
            "internal_echoes": word_lists.get("internal_echoes", [])[:18],
            "slant_rhymes": word_lists.get("slant_rhymes", [])[:18],
            "multi_syllable": word_lists.get("multi_syllable_rhymes", [])[:12],
            "phrase_landings": word_lists.get("phrase_landings", [])[:12],
        },
        "ranked_options": ranked,
        "actions": [
            "Use the ranked landing buttons to test a new final word without leaving the editor.",
            "If the same rhyme family appears only once, answer it within the next two bars.",
            "Add one internal echo before the landing to make the rhyme feel intentional.",
        ],
        "blueprints": [
            "Internal echo → pause → final landing",
            "Repeat the family once, then rotate to a cousin/slant family",
            "Use a two-word landing if the line feels too plain",
        ],
        "patches": [
            {
                "label": f"Swap ending to {row.get('word')}",
                "operation": "replace_end_word",
                "replacement": re.sub(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*([^A-Za-z0-9]*)$", f"{row.get('word')}\\1", active_text) if active_text and row.get("word") else active_text,
                "why": "; ".join(row.get("reasons") or []) or "Rhyme-family repair.",
            }
            for row in ranked[:4]
        ],
    }
    weak_lines = [row["line_number"] for row in line_reports if row["rhyme_power"]["score"] < 65]
    result = {
        "available": True,
        "mode": mode,
        "active_line_number": active_line,
        "active_report": active_report,
        "line_reports": line_reports,
        "summary": {
            "avg_rhyme_power": round(sum((row["rhyme_power"]["score"] for row in line_reports), 0) / max(1, len(line_reports)), 1),
            "unique_rhyme_families": len([key for key in key_counts if key]),
            "weak_rhyme_lines": weak_lines,
            "corpus_rhyme_key_overlap_pct": 0,
        },
        "scheme": {
            "recommendations": [
                {"title": "Answer the active landing", "detail": f"Build another /{active_key}/ or slant cousin within the next two bars.", "line_numbers": [active_line] if active_line else []},
                {"title": "Use highlighted-word mode", "detail": "Highlight a word in the editor to fetch similar rhymes without rerunning the full draft.", "line_numbers": []},
            ],
        },
        "family_ladders": [
            {"key": active_key, "words": [row.get("word") for row in ranked[:12]], "note": "safe fallback ladder"}
        ] if active_key else [],
        "warnings": [warning] if warning else [],
        "fallback_used": bool(warning),
    }
    return result

def _shift_live_result_line_numbers(result: Dict[str, Any], line_offset: int) -> None:
    if not line_offset:
        return
    shifted: set[int] = set()

    def shift_row(row: Any) -> None:
        if not isinstance(row, dict) or id(row) in shifted:
            return
        shifted.add(id(row))
        if row.get("line_number"):
            try:
                row["line_number"] = int(row["line_number"]) + line_offset
            except Exception:
                pass

    if result.get("active_line_number"):
        try:
            result["active_line_number"] = int(result["active_line_number"]) + line_offset
        except Exception:
            pass
    active = result.get("active_report") or {}
    shift_row(active)
    for row in result.get("line_reports", []) or []:
        shift_row(row)
    scheme = result.get("scheme") or {}
    for rec in scheme.get("recommendations", []) or []:
        if isinstance(rec.get("line_numbers"), list):
            rec["line_numbers"] = [int(n) + line_offset if str(n).isdigit() else n for n in rec.get("line_numbers", [])]


def _shift_static_line_payload(row: Any, line_offset: int) -> None:
    """Shift static snapshot line payloads from clipped-context numbering to source numbering."""
    if not isinstance(row, dict) or not line_offset:
        return
    for key in ("line_number",):
        if row.get(key) is not None:
            try:
                row[key] = int(row[key]) + int(line_offset)
            except Exception:
                pass
    section = row.get("section")
    if isinstance(section, dict):
        if section.get("start_line") is not None:
            try: section["start_line"] = int(section["start_line"]) + int(line_offset)
            except Exception: pass
        if section.get("end_line") is not None:
            try: section["end_line"] = int(section["end_line"]) + int(line_offset)
            except Exception: pass


def _build_live_static_line_analysis(
    lyrics: str,
    mode: str,
    active_line: int | None,
    beat: Dict[str, Any] | None = None,
    context_offset: int = 0,
) -> Dict[str, Any]:
    """Build the Static Snapshot line payload for the active live-writer line.

    The live writer uses a clipped context for speed, but the returned rows are
    shifted back to source line numbers so the editor jump/apply controls still
    target the real draft line.
    """
    try:
        source_lines = str(lyrics or "").splitlines() or [str(lyrics or "")]
        active_line = active_line or 1
        static_offset = int(context_offset or 0)
        static_lyrics = lyrics
        static_active_line = active_line
        static_radius = _env_int("LIVE_STATIC_LINE_CONTEXT_RADIUS", 2, low=1, high=40)
        static_max_chars = _env_int("LIVE_STATIC_LINE_MAX_CHARS", 1600, low=400, high=30000)
        if len(source_lines) > (static_radius * 2 + 3) or len(str(lyrics or "")) > static_max_chars:
            idx = max(0, min(len(source_lines) - 1, int(active_line or 1) - 1))
            start = max(0, idx - static_radius)
            end = min(len(source_lines), idx + static_radius + 1)
            static_lyrics = "\n".join(source_lines[start:end])
            static_active_line = idx - start + 1
            static_offset += start
        report = build_static_line_breakdown(static_lyrics, mode=mode, beat=beat)
        rows = list(report.get("line_breakdown") or [])
        active_line = static_active_line or (rows[0].get("line_number") if rows else 1)
        active_row = None
        for row in rows:
            if int(row.get("line_number", -999)) == int(active_line):
                active_row = row
                break
        if active_row is None and rows:
            # If the cursor sits on a blank/comment line, use the closest editable row.
            active_row = min(rows, key=lambda row: abs(int(row.get("line_number", 1)) - int(active_line or 1)))
        nearby = []
        if active_row:
            center = int(active_row.get("line_number", active_line or 1))
            nearby = [row for row in rows if abs(int(row.get("line_number", center)) - center) <= 3]
        if static_offset:
            for row in rows:
                _shift_static_line_payload(row, static_offset)
        if active_row and static_offset:
            # active_row is a reference in rows, already shifted by the loop above.
            pass
        return {
            "available": True,
            "report_type": "live_static_line_analysis",
            "context": "clipped_live_context",
            "context_offset_lines": int(static_offset or 0),
            "static_context_lines": len(source_lines),
            "static_context_clipped": static_lyrics != lyrics,
            "summary": report.get("summary", {}),
            "overview": report.get("overview", {}),
            "information_overview": (report.get("information_theory") or {}).get("overview", {}),
            "information_interpretations": (report.get("information_theory") or {}).get("interpretations", []),
            "meter_summary": (report.get("meter_report") or {}).get("summary", {}),
            "physics_summary": (report.get("physics_report") or {}).get("summary", {}),
            "score_summary": {
                "overall": (report.get("score_report") or {}).get("overall"),
                "grade": (report.get("score_report") or {}).get("grade", {}),
                "headline": (report.get("score_report") or {}).get("headline", ""),
            },
            "comparison_best_match": (report.get("comparison") or {}).get("best_match", {}),
            "active_line": active_row or {},
            "nearby_lines": nearby[:7],
            "snapshot_elements": [
                "metrics", "highlighted_rhymes", "cadence", "sound", "content", "rhyme_instruction",
                "bar_structure", "information_profile", "meter_stress", "scansion_physics", "bar_score",
                "reference_benchmark", "suggestion_actions", "advanced_rhyme", "possible_words",
                "rewrite_options", "applyable_patches", "checklist",
            ],
        }
    except Exception as exc:
        return {
            "available": False,
            "report_type": "live_static_line_analysis",
            "error": str(exc),
            "active_line": {},
            "nearby_lines": [],
        }


def _build_live_rhyme_result(
    lyrics: str,
    mode: str,
    active_line: int | None,
    job_id: str | None = None,
    context_offset: int = 0,
    context_clipped: bool = False,
    total_source_lines: int | None = None,
    beat: Dict[str, Any] | None = None,
    beat_id: str | None = None,
) -> Dict[str, Any]:
    """Fast-core live rhyme result.

    The previous live writer reused the heavyweight static snapshot and advanced
    rhyme lab paths. That produced huge JSON payloads and could make hosted WSGI
    deployments look stuck on queued/polling states. The refactored live writer
    is a compact, deterministic, no-worker endpoint. Full Static Snapshot is
    still available from /api/snapshot; this route returns only the data needed
    by the live sidecar.
    """
    try:
        return build_live_rhyme_payload(
            lyrics,
            mode=mode,
            active_line=active_line,
            job_id=job_id,
            context_offset=context_offset,
            context_clipped=context_clipped,
            total_source_lines=total_source_lines,
            beat_id=beat_id,
        )
    except Exception as exc:
        result = _fallback_live_rhyme_result(lyrics, mode, active_line, warning=str(exc))
        _shift_live_result_line_numbers(result, context_offset)
        result.update({
            "available": True,
            "job_id": job_id,
            "job_type": "live_rhyme_writer",
            "report_type": "live_rhyme_writer_emergency_fallback",
            "engine": "legacy_emergency_fallback",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "context_clipped": bool(context_clipped),
            "context_offset_lines": int(context_offset or 0),
            "total_source_lines": total_source_lines,
            "fallback_used": True,
            "warnings": [str(exc)],
            "live_static_analysis": {"available": False, "error": str(exc), "active_line": {}, "nearby_lines": []},
            "live_writer": {
                "available": True,
                "same_template": True,
                "instruction": "Emergency fallback returned compact rhyme suggestions without queueing.",
                "route_family": "live-rhyme",
                "context_clipped": bool(context_clipped),
                "fallback_used": True,
            },
        })
        return result


def _selected_word_request_fields(payload: Dict[str, Any]) -> tuple[str, str, str, str, int | None, int | None, int | None]:
    lyrics = str(payload.get("lyrics") or payload.get("text") or payload.get("draft") or payload.get("content") or "")
    word = str(
        payload.get("word")
        or payload.get("selected_word")
        or payload.get("target")
        or payload.get("highlighted_word")
        or payload.get("selection")
        or ""
    ).strip()
    selection = payload.get("selection_range") if isinstance(payload.get("selection_range"), dict) else {}
    start = payload.get("selection_start", selection.get("start"))
    end = payload.get("selection_end", selection.get("end"))
    try:
        start_i = int(start) if start is not None else None
        end_i = int(end) if end is not None else None
    except Exception:
        start_i = end_i = None
    if not word and lyrics and start_i is not None and end_i is not None and 0 <= start_i < end_i <= len(lyrics):
        word = lyrics[start_i:end_i]
    match = re.search(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", word)
    word = match.group(0) if match else ""
    mode = _mode(payload.get("coach_mode", payload.get("mode", "match")))
    line_text = str(payload.get("line_text") or payload.get("context") or payload.get("active_line_text") or "")
    active = _active_line(payload.get("active_line") or payload.get("line_number") or payload.get("line") or payload.get("cursor_line"))
    return word, mode, line_text, lyrics, active, start_i, end_i


def _build_selected_word_rhyme_result(
    word: str,
    mode: str,
    line_text: str = "",
    lyrics: str = "",
    active_line: int | None = None,
    selection_start: int | None = None,
    selection_end: int | None = None,
    job_id: str | None = None,
) -> Dict[str, Any]:
    """Compact highlighted-word rhyme result used by the live sidecar."""
    try:
        return build_selected_word_core_payload(
            word,
            mode=mode,
            line_text=line_text,
            lyrics=lyrics,
            active_line=active_line,
            selection_start=selection_start,
            selection_end=selection_end,
            job_id=job_id,
        )
    except Exception as exc:
        clean_word = re.sub(r"[^A-Za-z0-9'’\-]", "", str(word or "")).strip()
        if not clean_word:
            raise ValueError("Highlight or select a word before requesting similar rhymes.") from exc
        basic = _safe_word_lists(clean_word)
        ranked_fallback = _fallback_ranked_options(clean_word, basic, limit=_env_int("RHYME_WORD_LIMIT", 18, low=6, high=80))
        patches = []
        for row in ranked_fallback[:10]:
            candidate = str(row.get("word") or row.get("display") or "").strip()
            if candidate:
                patches.append({
                    "type": "replace_selection",
                    "label": f"Replace highlighted word → {candidate}",
                    "replacement": candidate,
                    "score": row.get("score"),
                    "kind": row.get("kind"),
                    "why": "; ".join(row.get("reasons") or []) or "Similar phonetic landing.",
                })
        return {
            "available": True,
            "job_id": job_id,
            "job_type": "selected_word_rhyme",
            "report_type": "highlighted_word_rhyme_emergency_fallback",
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "selected_word": clean_word,
            "target_word": clean_word,
            "mode": mode,
            "line_text": line_text,
            "active_line": active_line,
            "selection": {"start": selection_start, "end": selection_end},
            "selection_range": {"start": selection_start, "end": selection_end},
            "lyrics_chars": len(lyrics or ""),
            "summary": {
                "rhyme_key": basic.get("rhyme_key") or lyric_rhyme_key(clean_word),
                "syllables": count_syllables(clean_word),
                "stress_signature": "fallback",
                "best_score": ranked_fallback[0].get("score") if ranked_fallback else 0,
                "best_kind": ranked_fallback[0].get("kind") if ranked_fallback else "fallback",
            },
            "word_lists": {
                "end_rhymes": basic.get("end_rhymes", []),
                "near_rhymes": basic.get("near_rhymes", []),
                "slant_rhymes": basic.get("slant_rhymes", []),
                "internal_echoes": basic.get("internal_echoes", []),
                "multi_syllable_endings": basic.get("phrase_landings", []),
            },
            "ranked": ranked_fallback,
            "rhyme_ladder": [{"stage": "safe fallback", "use_when": "fast core was unavailable", "options": [row.get("word") for row in ranked_fallback[:10]]}],
            "similar_rhymes": [{"word": row.get("word"), "category": row.get("kind")} for row in ranked_fallback[:48]],
            "applyable_patches": patches,
            "instruction": "Click a similar rhyme to replace the highlighted word.",
            "warnings": [str(exc)],
            "fallback_used": True,
            "live_writer": {"available": True, "trigger": "highlighted_word", "instruction": "Highlight any word in the editor to fetch compact rhyme suggestions."},
        }


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def _is_public_endpoint() -> bool:
    endpoint = request.endpoint or ""
    return endpoint in PUBLIC_ENDPOINTS or request.path.startswith("/static/")


def _wants_json() -> bool:
    return request.path.startswith("/api/") or "application/json" in (request.headers.get("Accept") or "")


def _safe_next_url(value: str | None) -> str:
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return url_for("index")


def _lyrics_error(lyrics: Any, empty_message: str = "Provide lyrics text.") -> str | None:
    if not isinstance(lyrics, str) or not lyrics.strip():
        return empty_message
    if len(lyrics) > MAX_LYRICS_CHARS:
        return f"Lyrics are too long for this beta. Keep drafts under {MAX_LYRICS_CHARS:,} characters."
    return None


def _rate_limited() -> bool:
    if not request.path.startswith("/api/") or RATE_LIMIT_PER_MINUTE <= 0:
        return False
    if _live_route_exempt():
        return False
    key = _client_ip()
    now = _now()
    with STATE_LOCK:
        bucket = RATE_BUCKETS[key]
        while bucket and now - bucket[0] > 60:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_PER_MINUTE:
            return True
        bucket.append(now)
    return False


def _admin_authorized() -> bool:
    if not ADMIN_TOKEN:
        return False
    provided = request.headers.get("X-Admin-Token") or request.args.get("token") or ""
    return compare_digest(str(provided), ADMIN_TOKEN)


def _cleanup_state() -> None:
    now = _now()
    with STATE_LOCK:
        for job_id, job in list(JOBS.items()):
            if now - float(job.get("created_at", now)) > JOB_TTL_SECONDS:
                JOBS.pop(job_id, None)
        if len(JOBS) > MAX_JOBS:
            ordered = sorted(JOBS.items(), key=lambda item: item[1].get("created_at", 0))
            for job_id, _ in ordered[: max(0, len(JOBS) - MAX_JOBS)]:
                JOBS.pop(job_id, None)
        for beat_id, beat in list(BEATS.items()):
            if now - float(beat.get("uploaded_at", now)) > BEAT_TTL_SECONDS:
                path = beat.get("path")
                if path:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except Exception:
                        pass
                BEATS.pop(beat_id, None)
        if len(BEATS) > MAX_BEATS:
            ordered = sorted(BEATS.items(), key=lambda item: item[1].get("uploaded_at", 0))
            for beat_id, beat in ordered[: max(0, len(BEATS) - MAX_BEATS)]:
                path = beat.get("path")
                if path:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except Exception:
                        pass
                BEATS.pop(beat_id, None)

        for render_id, render in list(RENDERS.items()):
            if now - float(render.get("created_at", now)) > SONG_TTL_SECONDS:
                for path in render.get("paths", []):
                    try:
                        Path(path).unlink(missing_ok=True)
                    except Exception:
                        pass
                RENDERS.pop(render_id, None)
        if len(RENDERS) > MAX_RENDERS:
            ordered = sorted(RENDERS.items(), key=lambda item: item[1].get("created_at", 0))
            for render_id, render in ordered[: max(0, len(RENDERS) - MAX_RENDERS)]:
                for path in render.get("paths", []):
                    try:
                        Path(path).unlink(missing_ok=True)
                    except Exception:
                        pass
                RENDERS.pop(render_id, None)


def _beat_by_id(beat_id: Any) -> Dict[str, Any] | None:
    if not beat_id:
        return None
    with STATE_LOCK:
        beat = BEATS.get(str(beat_id))
        if not beat:
            return None
        return dict(beat.get("analysis") or {})


def _beat_record_by_id(beat_id: Any) -> Dict[str, Any] | None:
    if not beat_id:
        return None
    with STATE_LOCK:
        beat = BEATS.get(str(beat_id))
        if not beat:
            return None
        safe = dict(beat)
        safe["analysis"] = dict(beat.get("analysis") or {})
        return safe


def _extract_active_sentence(lyrics: str, cursor_index: Any = None, sentence_index: Any = None) -> str:
    """Best-effort active sentence extraction for the synchronous side lab."""
    text = str(lyrics or "")
    if not text.strip():
        return ""
    spans = []
    for match in re.finditer(r"[^.!?;\n]+(?:[.!?;]+|$)", text):
        chunk = match.group(0).strip()
        if chunk:
            spans.append((match.start(), match.end(), chunk))
    if not spans:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[0] if lines else text.strip()
    try:
        idx = int(sentence_index)
        if idx >= 1:
            idx -= 1
        if 0 <= idx < len(spans):
            return spans[idx][2]
    except Exception:
        pass
    try:
        cursor = int(cursor_index)
    except Exception:
        cursor = 0
    cursor = max(0, min(len(text), cursor))
    for start, end, chunk in spans:
        if start <= cursor <= end:
            return chunk
    # Fall back to the nearest preceding sentence; useful when the cursor is at a newline.
    before = [row for row in spans if row[0] <= cursor]
    return (before[-1][2] if before else spans[0][2]).strip()


def _read_lyrics_file(uploaded) -> Tuple[str, str | None]:
    if not uploaded or not uploaded.filename:
        return "", "No lyrics file was uploaded."
    filename = uploaded.filename.lower()
    if not filename.endswith(ALLOWED_TEXT_EXTENSIONS):
        return "", "Upload a .txt, .md, .lyrics, or .rtf file."
    raw_bytes = uploaded.read(MAX_TEXT_UPLOAD_BYTES + 1)
    if len(raw_bytes) > MAX_TEXT_UPLOAD_BYTES:
        return "", f"Lyrics file is too large. Keep text uploads under {MAX_TEXT_UPLOAD_BYTES // (1024 * 1024)} MB."
    raw = raw_bytes.decode("utf-8", errors="replace")
    text = clean_rtf_text(raw) if filename.endswith(".rtf") else raw
    error = _lyrics_error(text, "Lyrics file did not contain readable lyric text.")
    if error:
        return "", error
    return text, None


def _save_and_analyze_beat(uploaded) -> Tuple[Dict[str, Any] | None, str | None]:
    if not uploaded or not uploaded.filename:
        return None, "Upload beat_file as multipart/form-data."
    original_name = uploaded.filename
    filename = secure_filename(original_name) or "beat"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        return None, "Upload a beat as WAV, MP3, M4A, AAC, FLAC, OGG, AIFF, or AIF."
    beat_id = uuid.uuid4().hex[:12]
    path = UPLOAD_DIR / f"{beat_id}{suffix}"
    uploaded.save(path)
    if path.stat().st_size > MAX_BEAT_UPLOAD_BYTES:
        path.unlink(missing_ok=True)
        return None, f"Beat upload is too large. Keep beats under {MAX_BEAT_UPLOAD_BYTES // (1024 * 1024)} MB for this beta."
    analysis = analyze_beat(path, original_filename=original_name)
    analysis["beat_id"] = beat_id
    if not analysis.get("available"):
        # Do not keep undecodable uploads in memory or on disk. The response still
        # returns the decoder attempts so the UI can show exactly what failed.
        path.unlink(missing_ok=True)
        return analysis, None
    with STATE_LOCK:
        BEATS[beat_id] = {
            "beat_id": beat_id,
            "filename": original_name,
            "path": str(path),
            "analysis": analysis,
            "uploaded_at": _now(),
        }
    _cleanup_state()
    return analysis, None


def _job_runner(job_id: str, lyrics: str, mode: str, active_line: int | None, beat_id: str | None) -> None:
    with STATE_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update({"status": "running", "started_at": _now()})
    try:
        beat = _beat_by_id(beat_id)
        result = build_editing_lab_result(lyrics, mode=mode, active_line=active_line, beat=beat)
        result["job_id"] = job_id
        result["beat_id"] = beat_id
        result["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with STATE_LOCK:
            if job_id in JOBS:
                JOBS[job_id].update({"status": "complete", "result": result, "finished_at": _now(), "error": None})
    except Exception as exc:
        with STATE_LOCK:
            if job_id in JOBS:
                JOBS[job_id].update({"status": "error", "error": str(exc), "finished_at": _now()})


def _live_rhyme_job_runner(
    job_id: str,
    lyrics: str,
    mode: str,
    active_line: int | None,
    context_offset: int = 0,
    context_clipped: bool = False,
    total_source_lines: int | None = None,
    beat_id: str | None = None,
) -> None:
    """Background worker for the same-template live rhyme writer."""
    with STATE_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update({"status": "running", "started_at": _now()})
    try:
        beat = _beat_by_id(beat_id) if beat_id else None
        result = _build_live_rhyme_result(
            lyrics,
            mode,
            active_line,
            job_id=job_id,
            context_offset=context_offset,
            context_clipped=context_clipped,
            total_source_lines=total_source_lines,
            beat=beat,
            beat_id=beat_id,
        )
        with STATE_LOCK:
            if job_id in JOBS:
                JOBS[job_id].update({"status": "complete", "result": result, "finished_at": _now(), "error": None})
    except Exception as exc:
        with STATE_LOCK:
            if job_id in JOBS:
                JOBS[job_id].update({"status": "error", "error": str(exc), "finished_at": _now()})


def _selected_word_rhyme_job_runner(
    job_id: str,
    word: str,
    mode: str,
    line_text: str,
    lyrics: str,
    active_line: int | None,
    selection_start: int | None,
    selection_end: int | None,
) -> None:
    """Background worker for highlighted/selected word rhyme suggestions."""
    with STATE_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update({"status": "running", "started_at": _now()})
    try:
        result = _build_selected_word_rhyme_result(
            word,
            mode,
            line_text=line_text,
            lyrics=lyrics,
            active_line=active_line,
            selection_start=selection_start,
            selection_end=selection_end,
            job_id=job_id,
        )
        with STATE_LOCK:
            if job_id in JOBS:
                JOBS[job_id].update({"status": "complete", "result": result, "finished_at": _now(), "error": None})
    except Exception as exc:
        with STATE_LOCK:
            if job_id in JOBS:
                JOBS[job_id].update({"status": "error", "error": str(exc), "finished_at": _now()})


def _run_job_or_submit(runner, inline: bool, *args, **kwargs) -> str:
    """Run an API job in a PythonAnywhere-safe way.

    PythonAnywhere's web workers are WSGI/uWSGI processes. Long-lived background
    threads and in-memory job queues can be unreliable across reloads/workers, so
    live-writing jobs default to an inline completion model: the browser still
    posts to an async route and polls, but the job is already complete by the
    time the POST returns.
    """
    engine = "inline" if inline or EXECUTOR is None else "thread"
    job_id = str(args[0]) if args else ""
    if job_id:
        with STATE_LOCK:
            if job_id in JOBS:
                JOBS[job_id]["engine"] = engine
    if engine == "inline":
        runner(*args, **kwargs)
        return engine
    EXECUTOR.submit(runner, *args, **kwargs)
    return engine


def _job_status(job_id: str) -> str:
    with STATE_LOCK:
        return str((JOBS.get(job_id) or {}).get("status") or "missing")


def _job_public_payload(job_id: str, include_complete_result: bool = True) -> Dict[str, Any]:
    with STATE_LOCK:
        job = dict(JOBS.get(job_id) or {})
    payload = {
        "job_id": job_id,
        "status": str(job.get("status") or "missing"),
        "job_type": job.get("job_type"),
        "engine": job.get("engine"),
    }
    if include_complete_result and payload["status"] == "complete" and job.get("result") is not None:
        payload["result"] = job.get("result")
    if job.get("error"):
        payload["error"] = job.get("error")
    return payload


@app.before_request
def beta_gate_and_rate_limit():
    if _rate_limited():
        return jsonify({"error": "Too many beta requests from this browser. Pause briefly, then try again."}), 429
    if not BETA_ACCESS_CODE or _is_public_endpoint():
        return None
    if session.get("beta_ok") is True:
        return None
    if _wants_json():
        return jsonify({"error": "Beta access code required.", "login_url": url_for("beta_login")}), 401
    return redirect(url_for("beta_login", next=request.full_path if request.query_string else request.path))


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'",
    )
    response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    return response


@app.route("/beta/login", methods=["GET", "POST"])
def beta_login():
    next_url = _safe_next_url(request.values.get("next"))
    if not BETA_ACCESS_CODE:
        session["beta_ok"] = True
        return redirect(next_url)
    error = None
    if request.method == "POST":
        access_code = request.form.get("access_code", "").strip()
        if compare_digest(access_code, BETA_ACCESS_CODE):
            session["beta_ok"] = True
            return redirect(next_url)
        error = "That beta access code did not match."
    return render_template("login.html", app_name=APP_NAME, app_version=APP_VERSION, error=error, next_url=next_url)


@app.route("/beta/logout", methods=["GET", "POST"])
def beta_logout():
    session.pop("beta_ok", None)
    return redirect(url_for("beta_login" if BETA_ACCESS_CODE else "index"))


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"ok": True, "app": APP_NAME, "version": APP_VERSION, "environment": APP_ENV})


@app.route("/readyz", methods=["GET"])
def readyz():
    profile = get_corpus_profile()
    refs = comparison_summary()
    return jsonify({
        "ok": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "corpus_lines": profile.get("stats", {}).get("line_count", 0),
        "comparison_profiles": len(refs.get("profiles", [])),
        "jobs_in_memory": len(JOBS),
        "beats_in_memory": len(BEATS),
        "renders_in_memory": len(RENDERS),
        "tts": available_tts_engines(),
        "beat_audio": beat_backend_status(),
        "deployment": {
            "pythonanywhere_compat": PYTHONANYWHERE_COMPAT,
            "async_job_mode": ASYNC_JOB_MODE,
            "inline_general_async": INLINE_GENERAL_ASYNC,
            "live_rhyme_inline_jobs": LIVE_RHYME_INLINE_JOBS,
        "refactor": "queue_free_fast_core_v8",
            "live_rhyme_direct_jobs": LIVE_RHYME_DIRECT_JOBS,
            "executor": "disabled" if EXECUTOR is None else "threadpool",
            "async_workers": ASYNC_WORKERS,
        },
    })


@app.route("/api/pythonanywhere/diagnostics", methods=["GET"])
def pythonanywhere_diagnostics():
    """Deployment diagnostic payload for PythonAnywhere users."""
    imports = {}
    for name in ["flask", "numpy", "pronouncing", "reportlab", "librosa", "soundfile"]:
        try:
            module = __import__(name)
            imports[name] = {"available": True, "version": getattr(module, "__version__", "unknown")}
        except Exception as exc:
            imports[name] = {"available": False, "error": str(exc)}
    return jsonify({
        "ok": True,
        "app": APP_NAME,
        "version": APP_VERSION,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "cwd": os.getcwd(),
        "base_dir": str(BASE_DIR),
        "pythonanywhere_compat": PYTHONANYWHERE_COMPAT,
        "async_job_mode": ASYNC_JOB_MODE,
        "inline_general_async": INLINE_GENERAL_ASYNC,
        "live_rhyme_inline_jobs": LIVE_RHYME_INLINE_JOBS,
        "refactor": "queue_free_fast_core_v8",
        "live_rhyme_direct_jobs": LIVE_RHYME_DIRECT_JOBS,
        "executor": "disabled" if EXECUTOR is None else "threadpool",
        "async_workers": ASYNC_WORKERS,
        "jobs_in_memory": len(JOBS),
        "routes_to_test": [
            "GET /healthz",
            "GET /readyz",
            "GET /api/live-rhyme/health",
            "GET /live-writer",
            "POST /api/live-writer/analyze",
            "POST /api/live-writer/word",
            "POST /api/live-rhyme-job",
            "GET /api/live-rhyme/job/<job_id>",
            "POST /api/rhyme-word-job",
            "GET /api/rhyme-word/job/<job_id>",
        ],
        "imports": imports,
        "beat_audio": beat_backend_status(),
        "advice": [
            "Use the PythonAnywhere Web tab WSGI file to import app as application; do not run app.py as a web server.",
            "Set PYTHONANYWHERE_COMPAT=1 and LIVE_RHYME_INLINE_JOBS=1 in the WSGI file for stable live rhyme polling.",
            "Install requirements-pythonanywhere.txt first. Install optional audio packages only if the account supports them.",
            "Reload the Web app after changing files or environment variables.",
        ],
    })


@app.route("/robots.txt", methods=["GET"])
def robots_txt():
    return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")


@app.route("/privacy", methods=["GET"])
def privacy():
    return render_template("privacy.html", app_name=APP_NAME, app_version=APP_VERSION)


@app.route("/terms", methods=["GET"])
def terms():
    return render_template("terms.html", app_name=APP_NAME, app_version=APP_VERSION)


@app.route("/", methods=["GET"])
def index():
    corpus = profile_summary(get_corpus_profile())
    comparisons = comparison_summary()
    sample_path = BASE_DIR / "sample_lyrics.txt"
    sample_lyrics = sample_path.read_text(encoding="utf-8", errors="replace") if sample_path.exists() else ""
    return render_template(
        "index.html",
        app_name=APP_NAME,
        app_version=APP_VERSION,
        beta_enabled=bool(BETA_ACCESS_CODE),
        max_lyrics_chars=MAX_LYRICS_CHARS,
        max_sentence_chars=MAX_SENTENCE_CHARS,
        notebook_model=NOTEBOOK_MODEL,
        max_beat_upload_mb=MAX_BEAT_UPLOAD_BYTES // (1024 * 1024),
        max_render_seconds=MAX_RENDER_SECONDS,
        max_song_render_lines=MAX_SONG_RENDER_LINES,
        song_render_backends=SUPPORTED_TTS_BACKENDS,
        voice_presets=VOICE_PRESETS,
        intensity_presets=INTENSITY_PRESETS,
        tts=available_tts_engines(),
        corpus=corpus,
        comparisons=comparisons,
        modes=MODE_LABELS,
        selected_mode="match",
        audio_extensions=", ".join(ALLOWED_AUDIO_EXTENSIONS),
        sample_lyrics=sample_lyrics,
    )


@app.route("/api/import-lyrics", methods=["POST"])
def api_import_lyrics():
    text, error = _read_lyrics_file(request.files.get("lyrics_file"))
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"lyrics": text, "characters": len(text), "lines": len(text.splitlines())})




@app.route("/api/beat/diagnostics", methods=["GET"])
def api_beat_diagnostics():
    """Show which local/server audio decoders are available for beat analysis."""
    status = beat_backend_status()
    status["max_beat_upload_mb"] = MAX_BEAT_UPLOAD_BYTES // (1024 * 1024)
    status["max_analysis_seconds"] = 330
    status["notes"] = [
        "WAV should work even in a minimal Python environment through the basic fallback.",
        "MP3/M4A/AAC usually require ffmpeg or a working librosa/audioread stack.",
        "For hosted beta deployment, prefer the included Dockerfile because it installs ffmpeg and libsndfile.",
    ]
    return jsonify(status)

@app.route("/api/beat/upload", methods=["POST"])
def api_upload_beat():
    beat, error = _save_and_analyze_beat(request.files.get("beat_file"))
    if error:
        return jsonify({"error": error}), 400
    status = 200 if beat and beat.get("available") else 400
    return jsonify(beat), status


@app.route("/api/beat/<beat_id>", methods=["GET"])
def api_get_beat(beat_id: str):
    beat = _beat_by_id(beat_id)
    if not beat:
        return jsonify({"error": "Beat id not found. Upload the beat again."}), 404
    return jsonify(beat)


def _song_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _song_render_options(source: Dict[str, Any]) -> Dict[str, Any]:
    def _float_value(name: str, default: float, low: float, high: float) -> float:
        try:
            return max(low, min(high, float(source.get(name, default))))
        except Exception:
            return default

    backend = str(source.get("tts_backend") or source.get("voice_engine") or "auto").strip().lower()
    if backend == "guide":
        backend = "built_in"
    if backend not in SUPPORTED_TTS_BACKENDS:
        backend = "auto"

    voice_preset = str(source.get("voice_preset") or "neutral").strip().lower()
    if voice_preset not in {"neutral", "low", "bright", "robot"}:
        voice_preset = "neutral"

    intensity = str(source.get("rap_intensity") or source.get("flow_mode") or "balanced").strip().lower()
    if intensity in {"auto", "normal"}:
        intensity = "balanced"
    elif intensity == "double_time":
        intensity = "dense"
    elif intensity == "half_time":
        intensity = "laidback"
    if intensity not in {"laidback", "balanced", "dense"}:
        intensity = "balanced"

    return {
        "tts_backend": backend,
        "voice_preset": voice_preset,
        "rap_intensity": intensity,
        "intro_bars": _float_value("intro_bars", _float_value("start_bar", 0.0, 0.0, 32.0), 0.0, 32.0),
        "outro_bars": _float_value("outro_bars", _float_value("tail_bars", 2.0, 0.0, 32.0), 0.0, 32.0),
        "max_lines": MAX_SONG_RENDER_LINES,
        "beat_gain_db": _float_value("beat_gain_db", -3.5, -30.0, 6.0),
        "vocal_gain_db": _float_value("vocal_gain_db", 1.5, -30.0, 8.0),
        "ducking": _float_value("ducking", 0.18, 0.0, 0.65),
        "loop_beat": _song_bool(source.get("loop_beat"), True),
        "max_render_seconds": MAX_RENDER_SECONDS,
        "title": str(source.get("title") or "nmc_song_render")[:80],
    }


def _song_beat_record_from_request() -> Tuple[Dict[str, Any] | None, str | None]:
    if request.files.get("beat_file"):
        beat, error = _save_and_analyze_beat(request.files.get("beat_file"))
        if error:
            return None, error
        return _beat_record_by_id(beat.get("beat_id")), None
    if request.is_json:
        beat_id = _json_payload().get("beat_id")
    else:
        beat_id = request.form.get("beat_id")
    record = _beat_record_by_id(beat_id) if beat_id else None
    if not record:
        return None, "Upload a beat_file or reuse an existing beat_id before rendering a song."
    return record, None


@app.route("/api/song/tts-status", methods=["GET"])
def api_song_tts_status():
    return jsonify(available_tts_engines())


@app.route("/api/song/test-voice", methods=["POST"])
def api_song_test_voice():
    payload = _json_payload() if request.is_json else request.form.to_dict()
    options = _song_render_options(payload)
    text = payload.get("text") or payload.get("lyrics") or "Every sentence I am inventing has resonance on the beat."
    result = render_voice_sample(text, OUTPUT_DIR, options)
    if not result.get("available"):
        return jsonify(result), 400
    files = result.get("created_files", {})
    result["download_urls"] = {
        "voice_test": url_for("download_render", filename=files.get("voice_test_filename", ""), download=1),
    }
    result["audio_url"] = url_for("download_render", filename=files.get("voice_test_filename", ""))
    with STATE_LOCK:
        RENDERS[result["render_id"]] = {
            "render_id": result["render_id"],
            "created_at": _now(),
            "paths": [str(OUTPUT_DIR / files.get("voice_test_filename", ""))],
            "download_urls": result["download_urls"],
            "summary": {"type": "voice_test"},
        }
    _cleanup_state()
    return jsonify(result)


@app.route("/api/song/timing", methods=["POST"])
def api_song_timing():
    payload = _json_payload() if request.is_json else request.form.to_dict()
    lyrics = payload.get("lyrics", "")
    error = _lyrics_error(lyrics, "Provide lyrics text before building a song timing plan.")
    if error:
        return jsonify({"error": error}), 400
    beat = _beat_by_id(payload.get("beat_id")) if payload.get("beat_id") else None
    options = _song_render_options(payload)
    timing = build_timing_plan(lyrics, beat, options)
    status = 200 if timing.get("available") else 400
    return jsonify(timing), status


@app.route("/api/song/render", methods=["POST"])
@app.route("/api/render-song", methods=["POST"])
def api_song_render():
    if request.is_json:
        payload = _json_payload()
        lyrics = payload.get("lyrics", "")
        option_source = payload
    else:
        lyrics = request.form.get("lyrics", "")
        option_source = request.form.to_dict()
    error = _lyrics_error(lyrics, "Provide lyrics text before rendering a song.")
    if error:
        return jsonify({"error": error}), 400
    beat_record, beat_error = _song_beat_record_from_request()
    if beat_error or not beat_record:
        return jsonify({"error": beat_error or "Beat not found."}), 400
    beat_path = beat_record.get("path")
    if not beat_path:
        return jsonify({"error": "Beat path is missing. Upload the beat again."}), 404
    options = _song_render_options(option_source)
    try:
        result = render_song(lyrics, beat_path, OUTPUT_DIR, beat_record.get("analysis"), options)
    except Exception as exc:
        return jsonify({"available": False, "error": str(exc)}), 400
    if not result.get("available"):
        return jsonify(result), 400

    files = result.get("created_files", {})
    result["download_urls"] = {
        "mix": url_for("download_render", filename=files.get("mix_filename", ""), download=1),
        "vocal_stem": url_for("download_render", filename=files.get("vocal_filename", ""), download=1),
        "timing_json": url_for("download_render", filename=files.get("timing_filename", ""), download=1),
    }
    result["audio_url"] = url_for("download_render", filename=files.get("mix_filename", ""))
    result["vocal_stem_url"] = url_for("download_render", filename=files.get("vocal_filename", ""))
    result["timing_json_url"] = url_for("download_render", filename=files.get("timing_filename", ""), download=1)
    paths = [str(OUTPUT_DIR / name) for name in files.values() if name]
    with STATE_LOCK:
        RENDERS[result["render_id"]] = {
            "render_id": result["render_id"],
            "created_at": _now(),
            "paths": paths,
            "download_urls": result["download_urls"],
            "summary": result.get("summary", {}),
        }
    _cleanup_state()
    return jsonify(result)


@app.route("/renders/<path:filename>", methods=["GET"])
def download_render(filename: str):
    safe_name = secure_filename(Path(filename).name)
    if not safe_name:
        return jsonify({"error": "Missing render filename."}), 404
    target = OUTPUT_DIR / safe_name
    if not target.exists():
        return jsonify({"error": "Rendered file not found or expired."}), 404
    return send_from_directory(OUTPUT_DIR, safe_name, as_attachment=_song_bool(request.args.get("download"), False))


@app.route("/live-writer", methods=["GET"])
def live_writer_standalone():
    """Standalone queue-free writer. Uses inline JS to avoid stale app.js cache."""
    return render_template(
        "live_writer.html",
        app_name=APP_NAME,
        app_version=APP_VERSION,
        modes=MODE_LABELS,
        selected_mode="match",
    )


@app.route("/api/live-writer/analyze", methods=["POST"])
def api_live_writer_analyze():
    payload = _json_payload()
    try:
        result = build_live_writer_payload(payload)
        status = 200 if result.get("available") else 400
        return jsonify(result), status
    except Exception as exc:
        return jsonify({
            "available": False,
            "error": str(exc),
            "engine": "live_writer_engine_direct_noqueue",
            "direct_complete": True,
            "poll_required": False,
            "no_poll_required": True,
        }), 500


@app.route("/api/live-writer/word", methods=["POST"])
def api_live_writer_word():
    payload = _json_payload()
    try:
        result = build_live_writer_word_payload(payload)
        status = 200 if result.get("available") else 400
        return jsonify(result), status
    except Exception as exc:
        return jsonify({
            "available": False,
            "error": str(exc),
            "engine": "live_writer_engine_direct_noqueue",
            "direct_complete": True,
            "poll_required": False,
            "no_poll_required": True,
        }), 500


@app.route("/api/suggest-job", methods=["POST"])
def api_suggest_job():
    """Direct-complete general live coaching.

    Older builds returned queued jobs here. This refactor keeps the same route
    but completes inside the POST request so PythonAnywhere cannot strand the UI
    on a pending in-memory job.
    """
    payload = _json_payload()
    lyrics = payload.get("lyrics", "")
    error = _lyrics_error(lyrics, "Provide lyrics text before requesting suggestions.")
    if error:
        return jsonify({"error": error}), 400
    mode = _mode(payload.get("coach_mode", "match"))
    active = _active_line(payload.get("active_line"))
    beat_id = str(payload.get("beat_id")) if payload.get("beat_id") else None
    beat = _beat_by_id(beat_id) if beat_id else None
    job_id = uuid.uuid4().hex[:16]
    try:
        result = build_editing_lab_result(lyrics, mode=mode, active_line=active, beat=beat)
        result["job_id"] = job_id
        result["beat_id"] = beat_id
        result["generated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        status = "complete"
        error_text = None
    except Exception as exc:
        return jsonify({"error": str(exc), "status": "error", "job_id": job_id}), 500
    with STATE_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "job_type": "editing_lab_direct",
            "status": status,
            "engine": "direct",
            "created_at": _now(),
            "started_at": _now(),
            "finished_at": _now(),
            "mode": mode,
            "active_line": active,
            "beat_id": beat_id,
            "error": error_text,
            "result": result,
        }
    _cleanup_state()
    return jsonify({
        "job_id": job_id,
        "job_type": "editing_lab_direct",
        "status": "complete",
        "engine": "direct",
        "result": result,
        "direct_complete": True,
        "poll_required": False,
        "no_poll_required": True,
    })

@app.route("/api/live-rhyme-job", methods=["POST"])
@app.route("/api/live-rhyme-job/", methods=["POST"])
@app.route("/api/rhyme/live-job", methods=["POST"])
@app.route("/api/rhyme/live-job/", methods=["POST"])
def api_live_rhyme_job():
    """Compatibility alias for the queue-free live writer.

    The response is complete. Clients must not wait for a queue/poll cycle.
    """
    payload = _json_payload()
    job_id = uuid.uuid4().hex[:16]
    result = build_live_writer_payload(payload)
    result["job_id"] = job_id
    with STATE_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "job_type": "live_rhyme_writer",
            "status": "complete",
            "engine": "direct_refactor",
            "created_at": _now(),
            "started_at": _now(),
            "finished_at": _now(),
            "error": None if result.get("available") else result.get("error"),
            "result": result,
        }
    _cleanup_state()
    return jsonify({
        "job_id": job_id,
        "status": "complete",
        "engine": "direct_refactor",
        "job_type": "live_rhyme_writer",
        "result": result,
        "direct_complete": True,
        "poll_required": False,
        "no_poll_required": True,
        "poll_url": url_for("api_live_rhyme_job_lookup", job_id=job_id),
        "generic_poll_url": url_for("api_job", job_id=job_id),
    }), (200 if result.get("available") else 400)


@app.route("/api/live-rhyme", methods=["POST"])
@app.route("/api/live-rhyme/", methods=["POST"])
@app.route("/api/live-rhyme/sync", methods=["POST"])
@app.route("/api/live-rhyme/sync/", methods=["POST"])
@app.route("/api/rhyme/live", methods=["POST"])
@app.route("/api/rhyme/live/", methods=["POST"])
def api_live_rhyme_sync():
    payload = _json_payload()
    result = build_live_writer_payload(payload)
    result["sync"] = True
    result["direct_complete"] = True
    result["poll_required"] = False
    result["no_poll_required"] = True
    return jsonify(result), (200 if result.get("available") else 400)

@app.route("/api/rhyme-word-job", methods=["POST"])
@app.route("/api/rhyme-word-job/", methods=["POST"])
@app.route("/api/rhyme/word-job", methods=["POST"])
@app.route("/api/rhyme/word-job/", methods=["POST"])
@app.route("/api/live-rhyme/word-job", methods=["POST"])
@app.route("/api/live-rhyme/word-job/", methods=["POST"])
@app.route("/api/rhyme/similar-job", methods=["POST"])
def api_selected_word_rhyme_job():
    """Compatibility alias for queue-free highlighted-word suggestions."""
    payload = _json_payload()
    job_id = uuid.uuid4().hex[:16]
    result = build_live_writer_word_payload(payload)
    result["job_id"] = job_id
    with STATE_LOCK:
        JOBS[job_id] = {
            "job_id": job_id,
            "job_type": "selected_word_rhyme",
            "status": "complete",
            "engine": "direct_refactor",
            "created_at": _now(),
            "started_at": _now(),
            "finished_at": _now(),
            "error": None if result.get("available") else result.get("error"),
            "result": result,
        }
    _cleanup_state()
    return jsonify({
        "job_id": job_id,
        "status": "complete",
        "engine": "direct_refactor",
        "job_type": "selected_word_rhyme",
        "result": result,
        "direct_complete": True,
        "poll_required": False,
        "no_poll_required": True,
        "poll_url": url_for("api_selected_word_rhyme_job_lookup", job_id=job_id),
    }), (200 if result.get("available") else 400)


@app.route("/api/rhyme-word/sync", methods=["POST"])
@app.route("/api/rhyme-word", methods=["POST"])
@app.route("/api/rhyme/word", methods=["POST"])
@app.route("/api/rhyme/similar", methods=["POST"])
@app.route("/api/live-rhyme/word", methods=["POST"])
def api_selected_word_rhyme_sync():
    payload = _json_payload()
    result = build_live_writer_word_payload(payload)
    result["sync"] = True
    result["direct_complete"] = True
    result["poll_required"] = False
    result["no_poll_required"] = True
    return jsonify(result), (200 if result.get("available") else 400)

@app.route("/api/rhyme-word/job/<job_id>", methods=["GET"])
@app.route("/api/rhyme/word-job/<job_id>", methods=["GET"])
@app.route("/api/live-rhyme/word-job/<job_id>", methods=["GET"])
@app.route("/api/live-rhyme/word/status/<job_id>", methods=["GET"])
@app.route("/api/rhyme/similar/status/<job_id>", methods=["GET"])
def api_selected_word_rhyme_job_lookup(job_id: str):
    return api_job(job_id)


@app.route("/api/rhyme-word/routes", methods=["GET"])
@app.route("/api/rhyme/word-routes", methods=["GET"])
def api_selected_word_rhyme_routes():
    with STATE_LOCK:
        word_jobs = sum(1 for job in JOBS.values() if job.get("job_type") == "selected_word_rhyme")
    return jsonify({
        "available": True,
        "job_type": "selected_word_rhyme",
        "start_async": ["POST /api/rhyme-word-job", "POST /api/rhyme/word-job", "POST /api/live-rhyme/word-job"],
        "poll_async": ["not required in direct mode", "GET /api/rhyme-word/job/<job_id> still works for completed jobs"],
        "sync_fallback": ["POST /api/rhyme-word/sync", "POST /api/live-rhyme/word"],
        "payload_aliases": {"word": ["word", "target", "selected_word", "highlighted_word", "selection"], "context": ["line_text", "context", "active_line_text"]},
        "jobs_in_memory": word_jobs,
        "now": _iso_now(),
    })



@app.route("/api/live-rhyme/health", methods=["GET"])
@app.route("/api/rhyme/live/health", methods=["GET"])
def api_live_rhyme_health():
    sample = "The expression is in the direction of the diction\nThe present presence corrects the sentence"
    try:
        result = build_live_writer_payload({"lyrics": sample, "active_line": 1, "coach_mode": "match"})
        return jsonify({
            "available": True,
            "ok": True,
            "active_end_word": (result.get("active_report") or {}).get("end_word"),
            "fallback_used": result.get("fallback_used", False),
            "pythonanywhere_compat": PYTHONANYWHERE_COMPAT,
            "live_rhyme_inline_jobs": LIVE_RHYME_INLINE_JOBS,
            "refactor": "queue_free_fast_core_v8",
            "engine": result.get("engine"),
            "payload_bytes_est": len(json.dumps(result)),
            "live_rhyme_direct_jobs": LIVE_RHYME_DIRECT_JOBS,
            "async_job_mode": ASYNC_JOB_MODE,
            "executor": "disabled" if EXECUTOR is None else "threadpool",
            "now": _iso_now(),
        })
    except Exception as exc:
        return jsonify({"available": False, "ok": False, "error": str(exc), "now": _iso_now()}), 500

@app.route("/api/live-writer/health", methods=["GET"])
def api_live_writer_health():
    try:
        smoke = live_rhyme_core_smoke_test()
        return jsonify({"available": True, "ok": True, "engine": "live_writer_engine_v8_core", "smoke": smoke, "now": _iso_now()})
    except Exception as exc:
        return jsonify({"available": False, "ok": False, "error": str(exc), "now": _iso_now()}), 500


@app.route("/api/live-rhyme/routes", methods=["GET"])
@app.route("/api/rhyme/live/routes", methods=["GET"])
def api_live_rhyme_routes():
    with STATE_LOCK:
        live_jobs = sum(1 for job in JOBS.values() if job.get("job_type") == "live_rhyme_writer")
    return jsonify({
        "available": True,
        "job_type": "live_rhyme_writer",
        "start_async": ["POST /api/live-rhyme-job", "POST /api/rhyme/live-job"],
        "poll_async": ["not required in direct mode", "GET /api/live-rhyme/job/<job_id> still works for completed jobs"],
        "sync_fallback": ["POST /api/live-rhyme", "POST /api/live-rhyme/sync", "POST /api/rhyme/live"],
        "health": ["GET /api/live-rhyme/health", "GET /api/live-writer/health"],
        "direct_refactor_page": "GET /live-writer",
        "direct_refactor_api": ["POST /api/live-writer/analyze", "POST /api/live-writer/word"],
        "highlighted_word_async": ["POST /api/rhyme-word-job", "GET /api/rhyme-word/job/<job_id>", "POST /api/rhyme-word/sync"],
        "payload_aliases": {"lyrics": ["lyrics", "text", "draft", "content"], "active_line": ["active_line", "line_number", "line", "cursor_line"]},
        "jobs_in_memory": live_jobs,
        "pythonanywhere_diagnostics": "GET /api/pythonanywhere/diagnostics",
        "pythonanywhere_compat": PYTHONANYWHERE_COMPAT,
        "live_rhyme_inline_jobs": LIVE_RHYME_INLINE_JOBS,
        "refactor": "queue_free_fast_core_v8",
        "live_rhyme_direct_jobs": LIVE_RHYME_DIRECT_JOBS,
        "async_job_mode": ASYNC_JOB_MODE,
        "executor": "disabled" if EXECUTOR is None else "threadpool",
        "async_workers": ASYNC_WORKERS,
        "now": _iso_now(),
    })


@app.route("/api/live-rhyme/job/<job_id>", methods=["GET"])
@app.route("/api/rhyme/live-job/<job_id>", methods=["GET"])
@app.route("/api/live-rhyme/status/<job_id>", methods=["GET"])
@app.route("/api/rhyme/live/status/<job_id>", methods=["GET"])
def api_live_rhyme_job_lookup(job_id: str):
    return api_job(job_id)


@app.route("/api/job/<job_id>", methods=["GET"])
def api_job(job_id: str):
    with STATE_LOCK:
        job = JOBS.get(job_id)
        safe = dict(job) if job else None
    if not safe:
        # Old cached JavaScript may still poll. Return a complete soft-failure
        # object instead of a 404 so the UI never stays queued forever.
        return jsonify({
            "job_id": job_id,
            "status": "complete",
            "engine": "direct_refactor_missing_job_guard",
            "result": {
                "available": False,
                "error": "This queued job id is not available in this worker. The refactored live writer uses direct endpoints; refresh and use /live-writer or run live rhyme again.",
                "direct_complete": True,
                "poll_required": False,
                "no_poll_required": True,
            },
            "direct_complete": True,
            "poll_required": False,
            "no_poll_required": True,
        })
    if safe.get("status") in {"queued", "running"}:
        safe["status"] = "complete"
        safe["result"] = safe.get("result") or {
            "available": False,
            "error": "This route has been refactored to direct mode. Refresh the page and retry the live writer.",
            "direct_complete": True,
            "poll_required": False,
            "no_poll_required": True,
        }
    return jsonify(safe)

@app.route("/api/line-fix", methods=["POST"])
def api_line_fix():
    payload = _json_payload()
    lyrics = payload.get("lyrics", "")
    error = _lyrics_error(lyrics)
    if error:
        return jsonify({"error": error}), 400
    mode = _mode(payload.get("coach_mode", "match"))
    line_number = _active_line(payload.get("line_number")) or 1
    beat = _beat_by_id(payload.get("beat_id"))
    return jsonify(build_line_fix(lyrics, line_number=line_number, mode=mode, beat=beat))


@app.route("/api/sentence/analyze", methods=["POST"])
@app.route("/api/sentence", methods=["POST"])
def api_sentence_analyze():
    payload = _json_payload()
    sentence = str(payload.get("sentence") or "").strip()
    lyrics = str(payload.get("lyrics") or "")
    if not sentence and lyrics:
        sentence = _extract_active_sentence(lyrics, payload.get("cursor_index"), payload.get("sentence_index"))
    if not sentence:
        return jsonify({"error": "Provide one sentence, or pass lyrics plus cursor_index to extract the active sentence."}), 400
    if len(sentence) > MAX_SENTENCE_CHARS:
        return jsonify({"error": f"Sentence is too long for synchronous feedback. Keep it under {MAX_SENTENCE_CHARS:,} characters."}), 400
    mode = _mode(payload.get("coach_mode", "match"))
    beat_id = str(payload.get("beat_id")) if payload.get("beat_id") else None
    beat = _beat_by_id(beat_id) if beat_id else None
    if beat_id and not beat:
        return jsonify({"error": "Beat id not found. Upload the beat again."}), 404
    return jsonify(build_sentence_sync_feedback(sentence, mode=mode, beat=beat, context_lyrics=lyrics))


@app.route("/api/sentence/compare-patterns", methods=["POST"])
@app.route("/api/sentence-patterns", methods=["POST"])
@app.route("/api/patterns/sentences", methods=["POST"])
def api_sentence_compare_patterns():
    payload = _json_payload()
    raw_sentences = payload.get("sentences")
    if isinstance(raw_sentences, list):
        text_source = [str(item) for item in raw_sentences]
        total_chars = sum(len(item) for item in text_source)
    else:
        text_source = str(payload.get("text") or payload.get("lyrics") or payload.get("sentence_text") or "")
        total_chars = len(text_source)
    if not text_source or (isinstance(text_source, str) and not text_source.strip()):
        return jsonify({"error": "Provide sentences, text, or lyrics to compare rhyme patterns."}), 400
    if total_chars > MAX_LYRICS_CHARS:
        return jsonify({"error": f"Sentence comparison input is too long. Keep it under {MAX_LYRICS_CHARS:,} characters."}), 400
    mode = _mode(payload.get("coach_mode", "match"))
    try:
        max_sentences = int(payload.get("max_sentences") or 16)
    except Exception:
        max_sentences = 16
    max_sentences = max(1, min(32, max_sentences))
    return jsonify(compare_sentence_rhyme_patterns(text_source, mode=mode, max_sentences=max_sentences))


@app.route("/api/meter/analyze", methods=["POST"])
@app.route("/api/meter/sentence", methods=["POST"])
def api_meter_analyze():
    payload = _json_payload()
    text = str(payload.get("sentence") or payload.get("text") or payload.get("lyrics") or "").strip()
    if not text:
        return jsonify({"error": "Provide a sentence, text, or lyrics value for meter analysis."}), 400
    if len(text) > MAX_LYRICS_CHARS:
        return jsonify({"error": f"Text is too long for this beta. Keep it under {MAX_LYRICS_CHARS:,} characters."}), 400
    beat_id = str(payload.get("beat_id")) if payload.get("beat_id") else None
    beat = _beat_by_id(beat_id) if beat_id else None
    if beat_id and not beat:
        return jsonify({"error": "Beat id not found. Upload the beat again."}), 404
    one_sentence = bool(payload.get("one_sentence")) or request.path.endswith("/sentence") or bool(payload.get("sentence"))
    if one_sentence:
        if len(text) > MAX_SENTENCE_CHARS and bool(payload.get("sentence")):
            return jsonify({"error": f"Sentence is too long. Keep one-sentence meter checks under {MAX_SENTENCE_CHARS:,} characters."}), 400
        return jsonify(analyze_sentence_meter(text, beat=beat))
    return jsonify(analyze_meter_text(text, beat=beat))


@app.route("/api/physics/analyze", methods=["POST"])
def api_physics_analyze():
    payload = _json_payload()
    lyrics = str(payload.get("lyrics") or payload.get("text") or "")
    error = _lyrics_error(lyrics, "Provide lyrics text for scansion physics analysis.")
    if error:
        return jsonify({"error": error}), 400
    mode = _mode(payload.get("coach_mode", "match"))
    beat_id = str(payload.get("beat_id")) if payload.get("beat_id") else None
    beat = _beat_by_id(beat_id) if beat_id else None
    if beat_id and not beat:
        return jsonify({"error": "Beat id not found. Upload the beat again."}), 404
    return jsonify(build_scansion_physics_report(lyrics, mode=mode, beat=beat))


@app.route("/api/physics/sentence", methods=["POST"])
def api_physics_sentence():
    payload = _json_payload()
    sentence = str(payload.get("sentence") or payload.get("text") or "").strip()
    lyrics = str(payload.get("lyrics") or "")
    if not sentence and lyrics:
        sentence = _extract_active_sentence(lyrics, payload.get("cursor_index"), payload.get("sentence_index"))
    if not sentence:
        return jsonify({"error": "Provide one sentence, or pass lyrics plus cursor_index."}), 400
    if len(sentence) > MAX_SENTENCE_CHARS:
        return jsonify({"error": f"Sentence is too long. Keep physics checks under {MAX_SENTENCE_CHARS:,} characters."}), 400
    mode = _mode(payload.get("coach_mode", "match"))
    beat_id = str(payload.get("beat_id")) if payload.get("beat_id") else None
    beat = _beat_by_id(beat_id) if beat_id else None
    if beat_id and not beat:
        return jsonify({"error": "Beat id not found. Upload the beat again."}), 404
    return jsonify(build_sentence_physics_report(sentence, beat=beat, mode=mode))


@app.route("/api/scansion/physics", methods=["POST"])
def api_scansion_physics_alias():
    """Backward-compatible alias for older beta clients."""
    payload = _json_payload()
    text = str(payload.get("lyrics") or payload.get("text") or payload.get("sentence") or "").strip()
    if not text:
        return jsonify({"error": "Provide lyrics, text, or one sentence for scansion physics."}), 400
    if len(text) > MAX_LYRICS_CHARS:
        return jsonify({"error": f"Text is too long for this beta. Keep it under {MAX_LYRICS_CHARS:,} characters."}), 400
    beat_id = str(payload.get("beat_id")) if payload.get("beat_id") else None
    beat = _beat_by_id(beat_id) if beat_id else None
    if beat_id and not beat:
        return jsonify({"error": "Beat id not found. Upload the beat again."}), 404
    mode = _mode(payload.get("coach_mode", "match"))
    if bool(payload.get("one_sentence") or payload.get("sentence")):
        if len(text) > MAX_SENTENCE_CHARS and payload.get("sentence"):
            return jsonify({"error": f"Sentence is too long. Keep one-sentence physics checks under {MAX_SENTENCE_CHARS:,} characters."}), 400
        return jsonify(build_sentence_physics_report(text, beat=beat, mode=mode))
    return jsonify(build_scansion_physics_report(text, mode=mode, beat=beat))


@app.route("/api/scansion/skeleton", methods=["POST"])
def api_scansion_skeleton():
    payload = _json_payload()
    left = str(payload.get("left") or payload.get("phrase_a") or "").strip()
    right = str(payload.get("right") or payload.get("phrase_b") or "").strip()
    if not left or not right:
        return jsonify({"error": "Provide left and right phrase values for phonetic skeleton comparison."}), 400
    if len(left) > MAX_SENTENCE_CHARS or len(right) > MAX_SENTENCE_CHARS:
        return jsonify({"error": "Phrase comparison inputs are too long for this beta."}), 400
    report = build_scansion_physics_report(f"{left}\n{right}")
    pairs = report.get("phonetic_skeletons", {}).get("top_pairs", [])
    match = pairs[0].get("match", {}) if pairs else {}
    return jsonify({"available": True, "left": left, "right": right, "match": match, "report": report.get("phonetic_skeletons", {})})


@app.route("/api/scansion/model", methods=["GET"])
def api_scansion_model():
    return jsonify({
        "available": True,
        "model_name": "Scansion Physics",
        "image_url": url_for("static", filename="reference/scansion_notebook.jpg"),
        "symbol_legend": SYMBOL_LEGEND,
        "physical_anchors": PHYSICAL_ANCHORS,
        "notebook_test_pairs": NOTEBOOK_TEST_PAIRS,
        "pipeline": ["word", "syllables", "stress", "beat phase θ", "force F", "torsion τ", "spin Ω", "cadence delta ΔC", "flow advice"],
    })




@app.route("/api/score", methods=["POST"])
@app.route("/api/score/rap", methods=["POST"])
def api_rap_score():
    payload = _json_payload()
    lyrics = payload.get("lyrics", "")
    error = _lyrics_error(lyrics, "Provide lyrics text before scoring the rap.")
    if error:
        return jsonify({"error": error}), 400
    mode = _mode(payload.get("coach_mode", "match"))
    beat = _beat_by_id(payload.get("beat_id"))
    return jsonify(build_rap_score_report(lyrics, mode=mode, beat=beat))


@app.route("/api/score/compare-edits", methods=["POST"])
@app.route("/api/compare-edits", methods=["POST"])
def api_compare_edits():
    payload = _json_payload()
    original = payload.get("original_lyrics", payload.get("baseline_lyrics", ""))
    edited = payload.get("edited_lyrics", payload.get("lyrics", ""))
    if _lyrics_error(original, "Provide original/baseline lyrics before comparing edits."):
        return jsonify({"error": "Provide original/baseline lyrics before comparing edits."}), 400
    if _lyrics_error(edited, "Provide edited lyrics before comparing edits."):
        return jsonify({"error": "Provide edited lyrics before comparing edits."}), 400
    mode = _mode(payload.get("coach_mode", "match"))
    beat = _beat_by_id(payload.get("beat_id"))
    return jsonify(compare_rap_edits(original, edited, mode=mode, beat=beat))

def _snapshot_request_fields() -> tuple[str, str, Dict[str, Any] | None, bool]:
    """Normalize snapshot request inputs and decide fast vs full mode.

    Hosted deployments such as PythonAnywhere can time out on the original deep
    snapshot because it runs comparison, meter, physics, rhyme, and scoring over
    the whole draft. The default route now returns a fast schema-compatible
    snapshot. Use `full=true`, `/api/snapshot/full`, or `/api/static-breakdown/full`
    for the old exhaustive local report.
    """
    if request.is_json:
        payload = _json_payload()
        lyrics = payload.get("lyrics", payload.get("text", payload.get("draft", "")))
        mode = _mode(payload.get("coach_mode", payload.get("mode", "match")))
        beat = _beat_by_id(payload.get("beat_id"))
        full = str(payload.get("full", payload.get("deep", ""))).strip().lower() in {"1", "true", "yes", "on", "full", "deep"}
    else:
        lyrics = request.form.get("lyrics", request.form.get("text", ""))
        mode = _mode(request.form.get("coach_mode", request.form.get("mode", "match")))
        beat = None
        full = str(request.form.get("full", request.form.get("deep", ""))).strip().lower() in {"1", "true", "yes", "on", "full", "deep"}
        if request.files.get("beat_file"):
            beat, error = _save_and_analyze_beat(request.files.get("beat_file"))
            if error:
                raise ValueError(error)
    return str(lyrics or ""), mode, beat, full


def _snapshot_response(force_full: bool = False):
    try:
        lyrics, mode, beat, requested_full = _snapshot_request_fields()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    error = _lyrics_error(lyrics, "Provide lyrics text before generating the static line breakdown.")
    if error:
        return jsonify({"error": error}), 400
    full = bool(force_full or requested_full)
    if full:
        try:
            data = build_static_line_breakdown(lyrics, mode=mode, beat=beat)
            data["snapshot_mode"] = "full_deep"
            return jsonify(data)
        except Exception as exc:
            # Never leave the first view blank. If the deep pass fails, fall back
            # to the fast hosted snapshot and expose the reason to the UI.
            data = build_fast_snapshot_report(lyrics, mode=mode, beat=beat)
            data["snapshot_mode"] = "fast_fallback_after_full_error"
            data.setdefault("warnings", []).append(f"Full snapshot failed, fast snapshot shown instead: {exc}")
            return jsonify(data)
    data = build_fast_snapshot_report(lyrics, mode=mode, beat=beat)
    data["snapshot_mode"] = "fast_hosted_safe"
    return jsonify(data)


@app.route("/api/static-breakdown", methods=["POST"])
def api_static_breakdown():
    return _snapshot_response(force_full=False)


@app.route("/api/snapshot", methods=["POST"])
def api_snapshot():
    return _snapshot_response(force_full=False)


@app.route("/api/static-breakdown/full", methods=["POST"])
@app.route("/api/snapshot/full", methods=["POST"])
def api_snapshot_full():
    return _snapshot_response(force_full=True)


@app.route("/api/information-theory", methods=["POST"])
def api_information_theory():
    response = api_static_breakdown()
    if isinstance(response, tuple):
        return response
    data = response.get_json(silent=True) or {}
    return jsonify({"available": bool(data.get("available")), "summary": data.get("summary", {}), "information_theory": data.get("information_theory", {})})


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    if request.is_json:
        payload = _json_payload()
        lyrics = payload.get("lyrics", "")
        mode = _mode(payload.get("coach_mode", "match"))
        active = _active_line(payload.get("active_line"))
        beat = _beat_by_id(payload.get("beat_id"))
    else:
        lyrics = request.form.get("lyrics", "")
        mode = _mode(request.form.get("coach_mode", "match"))
        active = _active_line(request.form.get("active_line"))
        beat = None
        if request.files.get("beat_file"):
            beat, error = _save_and_analyze_beat(request.files.get("beat_file"))
            if error:
                return jsonify({"error": error}), 400
    error = _lyrics_error(lyrics)
    if error:
        return jsonify({"error": error}), 400
    return jsonify(build_editing_lab_result(lyrics, mode=mode, active_line=active, beat=beat))


@app.route("/api/legacy-lyric-analysis", methods=["POST"])
def api_legacy_analysis():
    payload = _json_payload()
    lyrics = payload.get("lyrics", "")
    error = _lyrics_error(lyrics)
    if error:
        return jsonify({"error": error}), 400
    mode = _mode(payload.get("coach_mode", "match"))
    analysis = analyze_lyrics(lyrics, mode)
    beat = _beat_by_id(payload.get("beat_id"))
    if beat:
        analysis = attach_beat_guidance(analysis, beat)
    analysis["comparison"] = build_comparison_report(lyrics, analysis)
    return jsonify(analysis)


@app.route("/api/beat", methods=["POST"])
def api_beat_alias():
    return api_upload_beat()


@app.route("/api/corpus", methods=["GET"])
def api_corpus():
    return jsonify(profile_summary(get_corpus_profile()))


@app.route("/api/comparison/profiles", methods=["GET"])
@app.route("/api/comparison-profiles", methods=["GET"])
@app.route("/api/references", methods=["GET"])
def api_comparison_profiles():
    return jsonify(comparison_summary())


@app.route("/api/comparison", methods=["POST"])
@app.route("/api/compare", methods=["POST"])
def api_comparison():
    payload = _json_payload()
    lyrics = payload.get("lyrics", "")
    error = _lyrics_error(lyrics, "Provide lyrics text before comparing to reference profiles.")
    if error:
        return jsonify({"error": error}), 400
    analysis = analyze_lyrics(lyrics, _mode(payload.get("coach_mode", "match")))
    return jsonify(build_comparison_report(lyrics, analysis))


@app.route("/api/rhyme/<word>", methods=["GET"])
def api_rhyme(word: str):
    # Backward-compatible route, now powered by the advanced rhyme engine.
    mode = _mode(request.args.get("coach_mode", "match"))
    basic = possible_rhymes_for_word(word)
    advanced = advanced_rhyme_for_word(word, mode=mode, limit=_env_int("RHYME_WORD_LIMIT", 18, low=6, high=80))
    return jsonify({**basic, "advanced": advanced, "word_lists": advanced.get("word_lists", {})})


@app.route("/api/rhyme/word", methods=["POST"])
def api_rhyme_word():
    payload = _json_payload()
    word = str(payload.get("word") or "").strip()
    if not word:
        return jsonify({"error": "Provide a word to analyze."}), 400
    return jsonify(advanced_rhyme_for_word(
        word,
        line_text=str(payload.get("line_text") or payload.get("context") or ""),
        mode=_mode(payload.get("coach_mode", "match")),
        limit=_env_int("RHYME_WORD_LIMIT", 18, low=6, high=80),
    ))


@app.route("/api/rhyme/analyze", methods=["POST"])
@app.route("/api/rhyme/lab", methods=["POST"])
def api_rhyme_lab():
    payload = _json_payload()
    lyrics = payload.get("lyrics", "")
    error = _lyrics_error(lyrics, "Provide lyrics text before running the rhyme lab.")
    if error:
        return jsonify({"error": error}), 400
    mode = _mode(payload.get("coach_mode", "match"))
    active = _active_line(payload.get("active_line"))
    return jsonify(build_rhyme_suggestion_lab(lyrics, mode=mode, active_line=active))


@app.route("/api/export-json", methods=["POST"])
def api_export_json():
    payload = _json_payload()
    lyrics = payload.get("lyrics", "")
    mode = _mode(payload.get("coach_mode", "match"))
    active = _active_line(payload.get("active_line"))
    beat = _beat_by_id(payload.get("beat_id"))
    error = _lyrics_error(lyrics)
    if error:
        return jsonify({"error": error}), 400
    result = build_editing_lab_result(lyrics, mode=mode, active_line=active, beat=beat)
    return jsonify({"json": to_pretty_json(result)})



def _build_report_from_payload(payload: Dict[str, Any]) -> tuple[str, Dict[str, Any], Dict[str, Any], int | None]:
    kind = str(payload.get("kind") or payload.get("report_type") or "snapshot").strip().lower()
    mode = _mode(payload.get("coach_mode", "match"))
    beat = _beat_by_id(payload.get("beat_id"))
    if kind in {"compare", "comparison", "edit_compare", "edit-comparison"}:
        kind = "compare"
        original = payload.get("original_lyrics", payload.get("baseline_lyrics", ""))
        edited = payload.get("edited_lyrics", payload.get("lyrics", ""))
        if _lyrics_error(original, ""):
            return kind, {}, {"error": "Provide original/baseline lyrics before exporting an edit comparison."}, 400
        if _lyrics_error(edited, ""):
            return kind, {}, {"error": "Provide edited lyrics before exporting an edit comparison."}, 400
        report = compare_rap_edits(original, edited, mode=mode, beat=beat)
        meta = {"kind": kind, "mode": mode, "original_lyrics": original, "edited_lyrics": edited}
        return kind, report, meta, None

    lyrics = payload.get("lyrics", "")
    error = _lyrics_error(lyrics, "Provide lyrics text before exporting a report.")
    if error:
        return kind, {}, {"error": error}, 400
    if kind in {"score", "scores", "rap_score", "rap-score"}:
        kind = "score"
        report = build_rap_score_report(lyrics, mode=mode, beat=beat)
    else:
        kind = "snapshot"
        report = build_static_line_breakdown(lyrics, mode=mode, beat=beat)
    meta = {"kind": kind, "mode": mode, "lyrics": lyrics}
    return kind, report, meta, None


@app.route("/api/report/csv", methods=["POST"])
def api_report_csv():
    payload = _json_payload()
    kind, report, meta, status = _build_report_from_payload(payload)
    if status:
        return jsonify(meta), status
    csv_text = build_csv_report(kind, report, meta)
    filename = report_filename(kind, "csv")
    return Response(
        csv_text,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/api/report/pdf", methods=["POST"])
def api_report_pdf():
    payload = _json_payload()
    kind, report, meta, status = _build_report_from_payload(payload)
    if status:
        return jsonify(meta), status
    try:
        pdf_bytes = build_pdf_report(kind, report, meta)
    except Exception as exc:
        return jsonify({
            "error": "PDF export failed. Make sure reportlab is installed from requirements.txt.",
            "detail": str(exc),
        }), 500
    filename = report_filename(kind, "pdf")
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
        max_age=0,
    )


@app.route("/api/meta", methods=["GET"])
def api_meta():
    return jsonify({
        "app": APP_NAME,
        "version": APP_VERSION,
        "environment": APP_ENV,
        "beta_gated": bool(BETA_ACCESS_CODE),
        "max_lyrics_chars": MAX_LYRICS_CHARS,
        "max_sentence_chars": MAX_SENTENCE_CHARS,
        "max_text_upload_mb": MAX_TEXT_UPLOAD_BYTES // (1024 * 1024),
        "max_beat_upload_mb": MAX_BEAT_UPLOAD_BYTES // (1024 * 1024),
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
        "audio_extensions": ALLOWED_AUDIO_EXTENSIONS,
        "max_render_seconds": MAX_RENDER_SECONDS,
        "song_render_backends": SUPPORTED_TTS_BACKENDS,
        "voice_presets": list(VOICE_PRESETS.keys()),
        "intensity_presets": list(INTENSITY_PRESETS.keys()),
        "max_song_render_lines": MAX_SONG_RENDER_LINES,
        "song_render_ttl_seconds": SONG_TTL_SECONDS,
        "tts": available_tts_engines(),
        "meter_stress_analysis": True,
        "meter_stress_backend": "cmudict_optional_with_heuristic_fallback",
        "scansion_physics": True,
        "scansion_physics_endpoints": ["/api/physics/analyze", "/api/physics/sentence"],
        "advanced_rhyme_suggestions": True,
        "advanced_rhyme_endpoints": ["/api/rhyme/<word>", "/api/rhyme/word", "/api/rhyme/lab", "/api/rhyme/analyze", "/api/live-rhyme-job", "/api/rhyme/live-job", "/api/live-rhyme/sync", "/api/live-rhyme/routes", "/api/rhyme-word-job", "/api/rhyme-word/sync", "/api/rhyme-word/routes"],
        "report_export": True,
        "report_export_endpoints": ["/api/report/pdf", "/api/report/csv"],
        "charting": "Chart.js with built-in SVG fallback",
        "comparison_profiles": len(comparison_summary().get("profiles", [])),
        "comparison_profile_policy": comparison_summary().get("metadata", {}).get("copyright_handling", "derived_profile_only_no_raw_lyrics"),
        "privacy": url_for("privacy"),
        "terms": url_for("terms"),
        "public_base_url": PUBLIC_BASE_URL,
    })


@app.route("/api/feedback", methods=["POST"])
def api_feedback():
    payload = _json_payload()
    message = str(payload.get("message", "")).strip()
    if len(message) < 3:
        return jsonify({"error": "Add at least a short note before sending feedback."}), 400
    if len(message) > 3000:
        return jsonify({"error": "Feedback is too long. Keep it under 3,000 characters."}), 400
    rating = payload.get("rating")
    try:
        rating = int(rating) if rating not in (None, "") else None
    except Exception:
        rating = None
    if rating is not None and not (1 <= rating <= 5):
        return jsonify({"error": "Rating must be between 1 and 5."}), 400
    record = {
        "id": uuid.uuid4().hex[:12],
        "created_at": _iso_now(),
        "kind": str(payload.get("kind", "general"))[:40],
        "rating": rating,
        "email": str(payload.get("email", "")).strip()[:200],
        "message": message,
        "draft_excerpt": str(payload.get("draft_excerpt", ""))[:1500],
        "page": str(payload.get("page", ""))[:120],
        "app_version": APP_VERSION,
        "user_agent": (request.headers.get("User-Agent") or "")[:300],
    }
    with FEEDBACK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return jsonify({"ok": True, "feedback_id": record["id"]})


@app.route("/api/beta/feedback", methods=["POST"])
def api_beta_feedback_alias():
    return api_feedback()


@app.route("/api/admin/feedback", methods=["GET"])
def api_admin_feedback():
    if not _admin_authorized():
        return jsonify({"error": "Admin token required. Set BETA_ADMIN_TOKEN and pass X-Admin-Token."}), 403
    if not FEEDBACK_PATH.exists():
        return jsonify({"feedback": [], "count": 0})
    rows = []
    for line in FEEDBACK_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-250:]:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return jsonify({"feedback": rows, "count": len(rows)})


@app.errorhandler(413)
def file_too_large(_error):
    return jsonify({"error": f"That upload is too large. Keep the combined request under {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB."}), 413


@app.errorhandler(404)
def not_found(_error):
    if _wants_json():
        return jsonify({"error": "Route not found."}), 404
    return render_template("error.html", app_name=APP_NAME, code=404, message="Page not found."), 404


@app.errorhandler(500)
def server_error(_error):
    if _wants_json():
        return jsonify({"error": "Unexpected server error."}), 500
    return render_template("error.html", app_name=APP_NAME, code=500, message="Unexpected server error."), 500


if __name__ == "__main__":
    debug = _env_bool("FLASK_DEBUG", False)
    host = os.getenv("HOST", "127.0.0.1")
    port = _env_int("PORT", 5000, low=1, high=65535)
    app.run(host=host, port=port, debug=debug, use_reloader=False, threaded=True)
