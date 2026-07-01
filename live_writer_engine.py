"""Queue-free live writer adapter.

This file is the only code path used by the Live Rhyme Writer routes.  It is
small on purpose: no background jobs, no polling requirement, no heavy static
snapshot build, and no advanced audio/report imports.  Each HTTP request returns
a complete compact payload that the browser can render immediately.
"""
from __future__ import annotations

import re
from typing import Any, Dict

from live_rhyme_core import build_live_rhyme_payload, build_selected_word_payload as _build_selected_word_core

WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _mode(payload: Dict[str, Any]) -> str:
    mode = str(payload.get("coach_mode") or payload.get("mode") or "match")
    return mode if mode in {"match", "polish", "break"} else "match"


def _payload_text(payload: Dict[str, Any]) -> str:
    return str(payload.get("lyrics") or payload.get("text") or payload.get("draft") or payload.get("content") or "")


def _active_line(payload: Dict[str, Any]) -> int:
    return max(1, _int(
        payload.get("active_line")
        or payload.get("line_number")
        or payload.get("line")
        or payload.get("cursor_line")
        or payload.get("source_active_line"),
        1,
    ))


def build_live_writer_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a complete Live Rhyme Writer result.

    The caller may pass a full draft or a clipped context.  If the browser clipped
    context around the cursor, `context_offset_lines` tells the renderer how to map
    relative line numbers back to the original draft.
    """
    payload = payload if isinstance(payload, dict) else {}
    lyrics = _payload_text(payload)
    if len(lyrics.strip().split()) < 3:
        return {
            "available": False,
            "error": "Type at least three words to start the live rhyme sidecar.",
            "engine": "live_writer_engine_v8_core",
            "direct_complete": True,
            "poll_required": False,
            "no_poll_required": True,
        }
    result = build_live_rhyme_payload(
        lyrics,
        mode=_mode(payload),
        active_line=_active_line(payload),
        job_id=payload.get("job_id"),
        context_offset=max(0, _int(payload.get("context_offset_lines") or payload.get("line_offset"), 0)),
        context_clipped=bool(payload.get("client_clipped") or payload.get("context_clipped")),
        total_source_lines=_int(payload.get("total_source_lines"), 0) or None,
        beat_id=str(payload.get("beat_id") or "") or None,
    )
    result.update({
        "engine": "live_writer_engine_v8_core",
        "direct_complete": True,
        "poll_required": False,
        "no_poll_required": True,
        "sync": True,
    })
    return result


def _word_from_payload(payload: Dict[str, Any]) -> str:
    word = str(
        payload.get("word")
        or payload.get("selected_word")
        or payload.get("target")
        or payload.get("highlighted_word")
        or payload.get("selection")
        or ""
    ).strip()
    if not word:
        lyrics = _payload_text(payload)
        start = _int(payload.get("selection_start"), -1)
        end = _int(payload.get("selection_end"), -1)
        if 0 <= start < end <= len(lyrics):
            word = lyrics[start:end]
    match = WORD_RE.search(word)
    return match.group(0) if match else ""


def build_selected_word_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    word = _word_from_payload(payload)
    if not word:
        return {
            "available": False,
            "error": "Highlight or place the cursor inside a word first.",
            "engine": "live_writer_engine_v8_core",
            "direct_complete": True,
            "poll_required": False,
            "no_poll_required": True,
        }
    result = _build_selected_word_core(
        word,
        mode=_mode(payload),
        line_text=str(payload.get("line_text") or payload.get("context") or payload.get("active_line_text") or ""),
        lyrics=_payload_text(payload),
        active_line=_active_line(payload),
        selection_start=_int(payload.get("selection_start"), 0) if payload.get("selection_start") is not None else None,
        selection_end=_int(payload.get("selection_end"), 0) if payload.get("selection_end") is not None else None,
        job_id=payload.get("job_id"),
    )
    result.update({
        "engine": "live_writer_engine_v8_core",
        "direct_complete": True,
        "poll_required": False,
        "no_poll_required": True,
        "sync": True,
    })
    return result
