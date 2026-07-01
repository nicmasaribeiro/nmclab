"""Song render engine for the rap beta app.

The renderer creates a rough demo song by placing TTS-generated rap vocals over
an uploaded beat. It is designed for beta use, not final mastering.

Real TTS backends used when available:
- Linux/Docker: espeak-ng or espeak
- macOS local: say
Important:
- Auto now uses real speech TTS only. It does not silently fall back to the buzzy guide synth.
- The built_in guide synth is still available, but it is explicitly labeled as a timing/pocket check, not vocals.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np

try:
    import soundfile as sf  # type: ignore
except Exception:  # pragma: no cover
    sf = None  # type: ignore

try:
    import librosa  # type: ignore
except Exception:  # pragma: no cover
    librosa = None  # type: ignore

from beat_audio import load_audio_for_analysis
from lyric_engine import count_syllables, is_section_marker, line_syllables, rhyme_key, tokenize

RENDER_SR = 22_050
SUPPORTED_TTS_BACKENDS = ("auto", "espeak", "mac_say", "built_in", "guide_synth")
REAL_TTS_BACKENDS = ("espeak", "mac_say")
MAX_RENDER_LINES = int(os.getenv("MAX_SONG_RENDER_LINES", "96"))
MAX_RENDER_SECONDS = int(os.getenv("MAX_SONG_RENDER_SECONDS", "300"))
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")
VOWEL_RE = re.compile(r"[aeiouy]+", re.I)

VOICE_PRESETS: Dict[str, Dict[str, Any]] = {
    "neutral": {"label": "Neutral rap TTS", "pitch": 116.0, "jitter": 5.5, "gain": 1.0, "espeak_voice": "en-us+m3"},
    "low": {"label": "Low gritty pocket", "pitch": 90.0, "jitter": 4.0, "gain": 1.08, "espeak_voice": "en-us+m5"},
    "bright": {"label": "Bright clear pocket", "pitch": 146.0, "jitter": 8.0, "gain": 0.96, "espeak_voice": "en-us+f3"},
    "robot": {"label": "Robot demo voice", "pitch": 108.0, "jitter": 1.5, "gain": 0.92, "espeak_voice": "en-us+m2"},
}

INTENSITY_PRESETS: Dict[str, Dict[str, Any]] = {
    "laidback": {"label": "Laid-back", "syllables_per_bar": 9, "bar_fill": 0.76, "line_gap": 0.10},
    "balanced": {"label": "Balanced", "syllables_per_bar": 13, "bar_fill": 0.88, "line_gap": 0.045},
    "dense": {"label": "Dense / double-time", "syllables_per_bar": 18, "bar_fill": 0.95, "line_gap": 0.02},
}


def _round(value: Any, digits: int = 3) -> float:
    try:
        n = float(value)
    except Exception:
        n = 0.0
    if not math.isfinite(n):
        return 0.0
    return round(n, digits)


def _duration_label(seconds: float) -> str:
    seconds = max(0, int(round(float(seconds or 0))))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _db_to_amp(db: float) -> float:
    return float(10.0 ** (float(db) / 20.0))


def _normalize_audio(y: np.ndarray, peak: float = 0.95) -> np.ndarray:
    y = np.asarray(y, dtype=np.float32)
    if y.ndim > 1:
        y = y.mean(axis=1)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    cur = float(np.max(np.abs(y))) if y.size else 0.0
    if cur > 0:
        y = y / cur * min(peak, max(cur, 0.12))
    return y.astype(np.float32)


def _resample(y: np.ndarray, source_sr: int, target_sr: int = RENDER_SR) -> np.ndarray:
    y = np.asarray(y, dtype=np.float32)
    if not y.size or int(source_sr) == int(target_sr):
        return y
    if librosa is not None:
        try:
            return librosa.resample(y, orig_sr=int(source_sr), target_sr=int(target_sr)).astype(np.float32)
        except Exception:
            pass
    duration = len(y) / max(1, int(source_sr))
    new_n = max(1, int(round(duration * target_sr)))
    old_x = np.linspace(0.0, 1.0, num=len(y), endpoint=False)
    new_x = np.linspace(0.0, 1.0, num=new_n, endpoint=False)
    return np.interp(new_x, old_x, y).astype(np.float32)


def _read_wav_basic(path: Path, target_sr: int = RENDER_SR, max_seconds: float | None = None) -> Tuple[np.ndarray, int, str]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        sr = wav.getframerate()
        frames = wav.getnframes()
        if max_seconds:
            frames = min(frames, int(max_seconds * sr))
        raw = wav.readframes(frames)
    if width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"Unsupported WAV sample width: {width}")
    if channels > 1 and data.size:
        data = data.reshape(-1, channels).mean(axis=1)
    return _resample(_normalize_audio(data), sr, target_sr), target_sr, "wave fallback"


def load_audio(path: str | Path, target_sr: int = RENDER_SR, max_seconds: float | None = None) -> Tuple[np.ndarray, int, str]:
    """Load beat audio for song rendering through the same factored decoder stack used by beat analysis."""
    try:
        y, sr, report = load_audio_for_analysis(path, target_sr=int(target_sr), max_seconds=float(max_seconds or MAX_RENDER_SECONDS))
        return _normalize_audio(y), int(sr), f"beat_audio:{report.selected_backend}"
    except Exception as exc:
        # Keep a small WAV fallback as an extra safety net for unusual Python environments.
        path = Path(path)
        if path.suffix.lower() in {".wav", ".wave"}:
            try:
                return _read_wav_basic(path, target_sr=target_sr, max_seconds=max_seconds)
            except Exception:
                pass
        raise RuntimeError(f"Could not load the beat for rendering: {exc}") from exc


def _write_wav(path: Path, y: np.ndarray, sr: int = RENDER_SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    y = np.clip(np.asarray(y, dtype=np.float32), -0.999, 0.999)
    if sf is not None:
        sf.write(str(path), y, sr, subtype="PCM_16")
        return
    pcm = (y * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        wav.writeframes(pcm.tobytes())


def _fit_to_samples(y: np.ndarray, target_samples: int) -> np.ndarray:
    target_samples = max(1, int(target_samples))
    y = np.asarray(y, dtype=np.float32)
    if not y.size:
        return np.zeros(target_samples, dtype=np.float32)
    if len(y) == target_samples:
        return y.astype(np.float32)
    # Interpolation is only used for the explicit guide synth. Do not use it
    # on real speech because it can turn TTS into metallic buzzing.
    old_x = np.linspace(0.0, 1.0, num=len(y), endpoint=False)
    new_x = np.linspace(0.0, 1.0, num=target_samples, endpoint=False)
    return np.interp(new_x, old_x, y).astype(np.float32)


def _pad_or_trim_samples(y: np.ndarray, target_samples: int, sr: int = RENDER_SR) -> np.ndarray:
    """Fit real TTS to a bar window without resampling/pitch-shifting it."""
    target_samples = max(1, int(target_samples))
    y = np.asarray(y, dtype=np.float32)
    if not y.size:
        return np.zeros(target_samples, dtype=np.float32)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
    # Trim a little leading/trailing silence from command-line TTS exports.
    nonquiet = np.flatnonzero(np.abs(y) > 0.004)
    if nonquiet.size:
        pad = int(0.035 * sr)
        lo = max(0, int(nonquiet[0]) - pad)
        hi = min(len(y), int(nonquiet[-1]) + pad)
        y = y[lo:hi]
    if len(y) > target_samples:
        y = y[:target_samples].copy()
        fade = min(len(y), int(0.025 * sr))
        if fade > 1:
            y[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
        return y.astype(np.float32)
    if len(y) < target_samples:
        return np.pad(y, (0, target_samples - len(y))).astype(np.float32)
    return y.astype(np.float32)


def _tts_failure_message(errors: Sequence[str]) -> str:
    details = " | ".join(str(e) for e in errors if e)[:900]
    base = (
        "No real speech TTS backend was available, so the app refused to render buzzy fake vocals. "
        "On Mac, select 'macOS system say' and run the app locally. On Linux/beta hosting, use the Dockerfile "
        "or install espeak-ng plus ffmpeg/libsndfile. The built-in guide synth is still available only as an explicit timing check."
    )
    return f"{base} Details: {details}" if details else base


def parse_render_lines(lyrics: str, max_lines: int = MAX_RENDER_LINES) -> Tuple[List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    section = "Body"
    rows: List[Dict[str, Any]] = []
    for raw_idx, raw in enumerate(str(lyrics or "").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if is_section_marker(line) or (line.startswith("//") and len(WORD_RE.findall(line)) <= 4):
            section = re.sub(r"^\s*(?://\s*)?|[\[\]:]", "", line).strip().title() or section
            continue
        words = tokenize(line)
        if not words:
            continue
        rows.append({
            "raw_line_number": raw_idx,
            "render_line_number": len(rows) + 1,
            "section": section,
            "text": line,
            "word_count": len(words),
            "syllables": line_syllables(line),
            "end_word": words[-1],
            "rhyme_key": rhyme_key(words[-1]),
        })
        if len(rows) >= max_lines:
            warnings.append(f"Only the first {max_lines} rap lines were rendered to keep beta jobs bounded.")
            break
    return rows, warnings


def _target_syllables(beat_analysis: Dict[str, Any] | None, intensity: str) -> int:
    preset = INTENSITY_PRESETS.get(intensity, INTENSITY_PRESETS["balanced"])
    target = int(preset["syllables_per_bar"])
    try:
        pockets = (beat_analysis or {}).get("pocket", {}).get("pockets", {})
        key = "dense" if intensity == "dense" else "breath" if intensity == "laidback" else "balanced"
        rng = pockets.get(key, {}).get("range") or []
        if len(rng) >= 2:
            target = int(round((float(rng[0]) + float(rng[1])) / 2.0))
    except Exception:
        pass
    return max(4, target)


def build_timing_plan(lyrics: str, beat_analysis: Dict[str, Any] | None, options: Dict[str, Any] | None = None) -> Dict[str, Any]:
    options = dict(options or {})
    intensity = str(options.get("rap_intensity") or "balanced")
    if intensity not in INTENSITY_PRESETS:
        intensity = "balanced"
    preset = INTENSITY_PRESETS[intensity]
    lines, warnings = parse_render_lines(lyrics, int(options.get("max_lines") or MAX_RENDER_LINES))
    if not lines:
        return {"available": False, "error": "No renderable lyric lines found.", "lines": []}
    rap_bpm = float((beat_analysis or {}).get("rap_grid_bpm") or (beat_analysis or {}).get("detected_bpm") or options.get("bpm") or 90.0)
    if not math.isfinite(rap_bpm) or rap_bpm <= 0:
        rap_bpm = 90.0
    bar_seconds = float((beat_analysis or {}).get("bar_duration_seconds") or (240.0 / max(1.0, rap_bpm)))
    target = _target_syllables(beat_analysis, intensity)
    intro_bars = max(0.0, min(32.0, float(options.get("intro_bars") or 0.0)))
    outro_bars = max(0.0, min(32.0, float(options.get("outro_bars") if options.get("outro_bars") is not None else 2.0)))
    bar_fill = float(preset["bar_fill"])
    line_gap = float(options.get("line_gap_seconds") if options.get("line_gap_seconds") is not None else preset["line_gap"])

    current_bar = intro_bars
    planned: List[Dict[str, Any]] = []
    for row in lines:
        syl = int(row["syllables"] or 0)
        if str(row.get("section", "")).lower().startswith(("hook", "chorus")):
            span = 1 if syl <= target + 4 else max(2, int(math.ceil(syl / max(1, target))))
        else:
            span = max(1, int(math.ceil(syl / max(1, target))))
        span = min(8, span)
        start = current_bar * bar_seconds
        duration = max(0.28, span * bar_seconds * bar_fill - line_gap)
        row = dict(row)
        row.update({
            "bar_start": int(math.floor(current_bar)) + 1,
            "bar_span": span,
            "bar_end": int(math.floor(current_bar)) + span,
            "start_seconds": _round(start, 3),
            "start_time": _duration_label(start),
            "duration_seconds": _round(duration, 3),
            "end_seconds": _round(start + duration, 3),
            "end_time": _duration_label(start + duration),
            "syllables_per_bar": _round(syl / max(1, span), 2),
            "performance_action": _performance_action(syl, span, target),
        })
        planned.append(row)
        current_bar += span
    estimated_vocal_seconds = current_bar * bar_seconds + outro_bars * bar_seconds
    beat_bars = int((beat_analysis or {}).get("estimated_bar_count") or 0)
    bars_needed = int(math.ceil(current_bar + outro_bars))
    if beat_bars and bars_needed > beat_bars:
        warnings.append(f"The lyric plan needs about {bars_needed} bars, but the beat analysis found about {beat_bars}. The renderer can loop the beat, but the arrangement should be shortened or extended.")
    return {
        "available": True,
        "rap_grid_bpm": _round(rap_bpm, 2),
        "bar_duration_seconds": _round(bar_seconds, 3),
        "target_syllables_per_bar": target,
        "rap_intensity": intensity,
        "rap_intensity_label": preset["label"],
        "intro_bars": intro_bars,
        "outro_bars": outro_bars,
        "bars_needed": bars_needed,
        "beat_bars": beat_bars,
        "estimated_vocal_seconds": _round(estimated_vocal_seconds, 2),
        "estimated_vocal_time": _duration_label(estimated_vocal_seconds),
        "warnings": warnings,
        "density_summary": _density_summary(planned, target),
        "lines": planned,
    }


def _performance_action(syllables: int, bar_span: int, target: int) -> str:
    per_bar = syllables / max(1, bar_span)
    if bar_span > 1:
        return f"Split this thought across {bar_span} bars; land the final rhyme at the end of bar {bar_span}."
    if per_bar > target + 3:
        return "Crowded pocket: cut 2-4 syllables or switch this to a two-bar line."
    if per_bar < max(4, target - 4):
        return "Open pocket: leave a rest, repeat a short phrase, or add an ad-lib after the end rhyme."
    return "Balanced one-bar pocket: keep the heaviest stress near beat 4."


def _density_summary(lines: Sequence[Dict[str, Any]], target: int) -> List[str]:
    crowded = [str(row["render_line_number"]) for row in lines if float(row.get("syllables_per_bar") or 0) > target + 3]
    open_rows = [str(row["render_line_number"]) for row in lines if float(row.get("syllables_per_bar") or 0) < max(4, target - 4)]
    multi = [str(row["render_line_number"]) for row in lines if int(row.get("bar_span") or 1) > 1]
    out: List[str] = []
    if crowded:
        out.append(f"Crowded lines: {', '.join(crowded[:10])}. Compress or split these before a final take.")
    if open_rows:
        out.append(f"Open lines: {', '.join(open_rows[:10])}. Add rests, ad-libs, or sustained words.")
    if multi:
        out.append(f"Multi-bar lines: {', '.join(multi[:10])}. The render gives these extra time instead of forcing them into one bar.")
    if not out:
        out.append("Most lines fit the selected beat grid.")
    return out[:4]


def available_tts_engines() -> Dict[str, Any]:
    espeak_path = shutil.which("espeak-ng") or shutil.which("espeak")
    mac_say_path = shutil.which("say") if sys.platform == "darwin" else None
    real = bool(espeak_path or mac_say_path)
    return {
        "backends": SUPPORTED_TTS_BACKENDS,
        "real_tts_backends": REAL_TTS_BACKENDS,
        "voice_presets": VOICE_PRESETS,
        "intensity_presets": INTENSITY_PRESETS,
        "real_tts_available": real,
        "auto_will_render_speech": real,
        "espeak_available": bool(espeak_path),
        "espeak_path": espeak_path or "",
        "mac_say_available": bool(mac_say_path),
        "mac_say_path": mac_say_path or "",
        "guide_synth_available": True,
        "librosa_available": bool(librosa is not None),
        "soundfile_available": bool(sf is not None),
        "warning": "built_in/guide_synth is a buzzy timing guide, not a vocal TTS engine.",
    }


def _envelope(n: int, attack: float = 0.015, release: float = 0.045, sr: int = RENDER_SR) -> np.ndarray:
    n = max(1, int(n))
    env = np.ones(n, dtype=np.float32)
    a = min(n, max(1, int(attack * sr)))
    r = min(n, max(1, int(release * sr)))
    env[:a] *= np.linspace(0, 1, a, dtype=np.float32)
    env[-r:] *= np.linspace(1, 0, r, dtype=np.float32)
    return env


def _word_freq(word: str, base: float) -> float:
    return base * (0.82 + (abs(hash(word.lower())) % 39) / 100.0)


def synthesize_builtin_line(text: str, duration: float, voice_preset: str = "neutral", sr: int = RENDER_SR) -> np.ndarray:
    preset = VOICE_PRESETS.get(voice_preset, VOICE_PRESETS["neutral"])
    words = WORD_RE.findall(text or "")
    total = max(1, int(max(0.12, duration) * sr))
    if not words:
        return np.zeros(total, dtype=np.float32)
    syllables = [max(1, count_syllables(w)) for w in words]
    units = max(1, sum(syllables))
    gap = min(0.035, max(0.004, duration * 0.008))
    body = max(0.08, duration - gap * max(0, len(words) - 1))
    parts: List[np.ndarray] = []
    base_pitch = float(preset["pitch"])
    rng = np.random.default_rng(abs(hash(text)) % (2**32))
    for word, syl in zip(words, syllables):
        dur = max(0.055, body * syl / units)
        n = max(1, int(dur * sr))
        t = np.arange(n, dtype=np.float32) / sr
        freq = _word_freq(word, base_pitch) * (1 + 0.008 * np.sin(2 * np.pi * 4.5 * t))
        phase = 2 * np.pi * np.cumsum(freq) / sr
        vowel = (VOWEL_RE.findall(word) or ["a"])[0][0].lower()
        formant = {"a": 730, "e": 530, "i": 300, "o": 570, "u": 350, "y": 420}.get(vowel, 530)
        y = (0.58 * np.sin(phase) + 0.18 * np.sin(2 * phase) + 0.07 * np.sin(2 * np.pi * formant * t))
        if re.match(r"^[^aeiouy]", word, re.I):
            y[: min(len(y), int(0.018 * sr))] += rng.normal(0, 0.10, min(len(y), int(0.018 * sr)))
        parts.append((y * _envelope(n, sr=sr)).astype(np.float32))
        parts.append(np.zeros(max(0, int(gap * sr)), dtype=np.float32))
    out = np.concatenate(parts) if parts else np.zeros(total, dtype=np.float32)
    out = _fit_to_samples(out, total)
    out = np.tanh(out * 1.55) * float(preset.get("gain", 1.0))
    return out.astype(np.float32)


def _decode_audio_bytes(blob: bytes, target_sr: int = RENDER_SR) -> np.ndarray:
    if sf is not None:
        y, sr = sf.read(io.BytesIO(blob), dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        return _resample(_normalize_audio(y), int(sr), target_sr)
    with wave.open(io.BytesIO(blob), "rb") as wav:
        width = wav.getsampwidth()
        channels = wav.getnchannels()
        sr = wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width == 2:
        y = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        raise RuntimeError("soundfile is needed to decode this TTS output")
    if channels > 1:
        y = y.reshape(-1, channels).mean(axis=1)
    return _resample(_normalize_audio(y), sr, target_sr)


def _try_espeak(text: str, duration: float, voice_preset: str, sr: int = RENDER_SR) -> Tuple[np.ndarray, str]:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("espeak-ng/espeak is not installed")
    preset = VOICE_PRESETS.get(voice_preset, VOICE_PRESETS["neutral"])
    words = max(1, len(WORD_RE.findall(text)))
    wpm = int(max(95, min(420, round(words / max(0.1, duration / 60.0)))))
    voice = str(preset.get("espeak_voice") or "en-us+m3")
    proc = subprocess.run([exe, "--stdout", "-s", str(wpm), "-v", voice, text], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
    if proc.returncode != 0 or not proc.stdout:
        detail = (proc.stderr or b"TTS command failed").decode("utf-8", errors="replace")[:300]
        raise RuntimeError(detail)
    y = _decode_audio_bytes(proc.stdout, target_sr=sr)
    return _pad_or_trim_samples(y, int(duration * sr), sr=sr), f"{Path(exe).name} {voice} {wpm}wpm"


def _try_mac_say(text: str, duration: float, voice_preset: str, sr: int = RENDER_SR) -> Tuple[np.ndarray, str]:
    exe = shutil.which("say")
    if not exe or sys.platform != "darwin":
        raise RuntimeError("macOS say is not available")
    words = max(1, len(WORD_RE.findall(text)))
    wpm = int(max(110, min(420, round(words / max(0.1, duration / 60.0)))))
    attempts: List[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        wav_out = tmp_path / "line.wav"
        aiff_out = tmp_path / "line.aiff"
        commands = [
            [exe, "-r", str(wpm), "--data-format=LEI16@22050", "-o", str(wav_out), text],
            [exe, "-r", str(wpm), "-o", str(wav_out), text],
            [exe, "-r", str(wpm), "-o", str(aiff_out), text],
        ]
        for cmd in commands:
            target = Path(cmd[-2]) if len(cmd) >= 2 and cmd[-3] == "-o" else (wav_out if "line.wav" in " ".join(cmd) else aiff_out)
            try:
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
                if proc.returncode != 0 or not target.exists() or target.stat().st_size < 64:
                    attempts.append((proc.stderr or b"say command failed").decode("utf-8", errors="replace")[:220])
                    continue
                y, _, loader = load_audio(target, target_sr=sr, max_seconds=max(1.0, duration * 4))
                return _pad_or_trim_samples(y, int(duration * sr), sr=sr), f"macOS say {wpm}wpm via {loader}"
            except Exception as exc:
                attempts.append(str(exc)[:220])
        detail = " | ".join(x for x in attempts if x)[:500] or "say command failed"
        raise RuntimeError(detail)


def synthesize_line(text: str, duration: float, *, backend: str = "auto", voice_preset: str = "neutral", sr: int = RENDER_SR) -> Tuple[np.ndarray, str]:
    backend = (backend or "auto").strip().lower()
    if backend == "guide":
        backend = "built_in"
    backend = backend if backend in SUPPORTED_TTS_BACKENDS else "auto"
    if backend in {"built_in", "guide_synth"}:
        y = synthesize_builtin_line(text, duration, voice_preset=voice_preset, sr=sr)
        return y, "built_in buzzy guide synth (timing only, not speech)"

    errors: List[str] = []
    if backend in {"auto", "espeak"}:
        try:
            return _try_espeak(text, duration, voice_preset, sr=sr)
        except Exception as exc:
            errors.append(f"espeak: {exc}")
            if backend == "espeak":
                raise RuntimeError(_tts_failure_message(errors))
    if backend in {"auto", "mac_say"}:
        try:
            return _try_mac_say(text, duration, voice_preset, sr=sr)
        except Exception as exc:
            errors.append(f"mac_say: {exc}")
            if backend == "mac_say":
                raise RuntimeError(_tts_failure_message(errors))
    raise RuntimeError(_tts_failure_message(errors))


def _mix_at(canvas: np.ndarray, clip: np.ndarray, start: int) -> None:
    start = int(start)
    if clip.size == 0 or start >= canvas.size:
        return
    if start < 0:
        clip = clip[abs(start):]
        start = 0
    end = min(canvas.size, start + clip.size)
    if end > start:
        canvas[start:end] += clip[: end - start]


def _loop_or_trim(y: np.ndarray, samples: int) -> np.ndarray:
    samples = max(1, int(samples))
    if not y.size:
        return np.zeros(samples, dtype=np.float32)
    if y.size >= samples:
        return y[:samples].copy()
    loops = int(math.ceil(samples / y.size))
    return np.tile(y, loops)[:samples].astype(np.float32)


def _sidechain(beat: np.ndarray, vocal: np.ndarray, amount: float = 0.18, sr: int = RENDER_SR) -> np.ndarray:
    if not beat.size or not vocal.size or amount <= 0:
        return beat
    win = max(1, int(0.04 * sr))
    env = np.abs(vocal)
    kernel = np.ones(win, dtype=np.float32) / win
    env = np.convolve(env, kernel, mode="same")
    peak = float(np.max(env)) if env.size else 0.0
    if peak > 0:
        env = env / peak
    return beat * (1.0 - amount * np.clip(env, 0.0, 1.0))


def render_song(
    lyrics: str,
    beat_path: str | Path,
    output_dir: str | Path,
    beat_analysis: Dict[str, Any] | None = None,
    options: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    started = time.time()
    options = dict(options or {})
    backend = str(options.get("tts_backend") or options.get("voice_engine") or os.getenv("NMC_TTS_BACKEND", "auto")).strip().lower()
    if backend == "guide":
        backend = "built_in"
    if backend not in SUPPORTED_TTS_BACKENDS:
        backend = "auto"
    voice_preset = str(options.get("voice_preset") or options.get("voice") or "neutral").lower()
    if voice_preset not in VOICE_PRESETS:
        voice_preset = "neutral"
    intensity = str(options.get("rap_intensity") or "balanced")
    if intensity not in INTENSITY_PRESETS:
        intensity = "balanced"
    max_seconds = max(10.0, min(float(options.get("max_render_seconds") or MAX_RENDER_SECONDS), float(MAX_RENDER_SECONDS)))
    plan = build_timing_plan(lyrics, beat_analysis or {}, {**options, "rap_intensity": intensity, "max_lines": MAX_RENDER_LINES})
    if not plan.get("available"):
        return plan
    beat, sr, beat_loader = load_audio(beat_path, target_sr=RENDER_SR, max_seconds=max_seconds)
    if beat.size < sr:
        return {"available": False, "error": "Beat is too short for rendering."}
    beat_seconds = beat.size / sr
    vocal_seconds = float(plan.get("estimated_vocal_seconds") or 0.0)
    loop_beat = bool(options.get("loop_beat", True))
    render_seconds = min(max_seconds, max(beat_seconds if loop_beat else min(beat_seconds, vocal_seconds), vocal_seconds if loop_beat else beat_seconds))
    target_samples = max(1, int(render_seconds * sr))
    beat_bed = _loop_or_trim(beat, target_samples) if loop_beat else np.pad(beat[:target_samples], (0, max(0, target_samples - beat[:target_samples].size)))
    vocal = np.zeros(target_samples, dtype=np.float32)
    warnings: List[str] = list(plan.get("warnings") or [])
    methods: List[str] = []
    rendered = 0
    skipped = 0
    line_meta: List[Dict[str, Any]] = []
    for row in plan.get("lines", []):
        start = int(float(row["start_seconds"]) * sr)
        duration = float(row["duration_seconds"])
        if start >= target_samples:
            skipped += 1
            continue
        duration = min(duration, (target_samples - start) / sr)
        try:
            line_audio, method = synthesize_line(row["text"], duration, backend=backend, voice_preset=voice_preset, sr=sr)
        except Exception as exc:
            return {
                "available": False,
                "error": str(exc),
                "error_type": "tts_backend_unavailable",
                "failed_line_number": row.get("render_line_number"),
                "failed_line_text": row.get("text"),
                "tts_status": available_tts_engines(),
                "plan": plan,
                "warnings": _unique(warnings + [
                    "The old version silently substituted a buzzy guide synth here. This fixed version stops instead so you do not mistake buzz for vocals.",
                    "For a buzzy timing-only render, explicitly select Built-in timing guide synth.",
                ]),
            }
        if method not in methods:
            methods.append(method)
        peak = float(np.max(np.abs(line_audio))) if line_audio.size else 0.0
        if peak > 0:
            line_audio = line_audio / peak * 0.72
        _mix_at(vocal, line_audio.astype(np.float32), start)
        rendered += 1
        line_meta.append({k: row.get(k) for k in ["render_line_number", "raw_line_number", "section", "text", "bar_start", "bar_span", "bar_end", "start_seconds", "end_seconds", "syllables", "syllables_per_bar", "performance_action"]})
    if rendered == 0:
        return {"available": False, "error": "No vocal lines landed inside the render window. Reduce intro bars or increase MAX_SONG_RENDER_SECONDS.", "plan": plan}

    beat_gain_db = float(options.get("beat_gain_db") if options.get("beat_gain_db") is not None else -4.0)
    vocal_gain_db = float(options.get("vocal_gain_db") if options.get("vocal_gain_db") is not None else -1.0)
    ducking = max(0.0, min(0.65, float(options.get("ducking") if options.get("ducking") is not None else 0.18)))
    mix = _sidechain(beat_bed * _db_to_amp(beat_gain_db), vocal, amount=ducking, sr=sr) + vocal * _db_to_amp(vocal_gain_db)
    mix = np.tanh(mix * 1.18).astype(np.float32)
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 0:
        mix = mix / peak * 0.96

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    render_id = uuid.uuid4().hex[:14]
    safe_title = re.sub(r"[^A-Za-z0-9_\-]+", "_", str(options.get("title") or "nmc_song_render")).strip("_")[:60] or "nmc_song_render"
    mix_path = output_dir / f"{render_id}_{safe_title}.wav"
    vocal_path = output_dir / f"{render_id}_{safe_title}_vocal.wav"
    meta_path = output_dir / f"{render_id}_{safe_title}.json"
    _write_wav(mix_path, mix, sr)
    _write_wav(vocal_path, vocal, sr)

    vocal_peak = float(np.max(np.abs(vocal))) if vocal.size else 0.0
    vocal_rms = float(np.sqrt(np.mean(vocal ** 2))) if vocal.size else 0.0
    built_in_used = any("built_in" in m for m in methods)
    if built_in_used and not any(("espeak" in m or "say" in m) for m in methods):
        warnings.append("Built-in timing guide synth was explicitly selected. It will sound buzzy because it is not speech TTS.")
    suggestions = _song_suggestions(plan, line_meta, beat_seconds, vocal_seconds, loop_beat)
    metadata: Dict[str, Any] = {
        "available": True,
        "render_id": render_id,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "filename": mix_path.name,
        "path": str(mix_path),
        "duration_seconds": _round(render_seconds, 2),
        "duration_label": _duration_label(render_seconds),
        "sample_rate": sr,
        "rendered_line_count": rendered,
        "skipped_line_count": skipped,
        "beat_duration_seconds": _round(beat_seconds, 2),
        "beat_looped": bool(loop_beat and render_seconds > beat_seconds + 0.05),
        "beat_loader": beat_loader,
        "vocal_engine": {
            "requested_backend": backend,
            "methods_used": methods,
            "voice_preset": voice_preset,
            "voice_label": VOICE_PRESETS[voice_preset]["label"],
            "rap_intensity": intensity,
            "rap_intensity_label": INTENSITY_PRESETS[intensity]["label"],
        },
        "mix": {"beat_gain_db": _round(beat_gain_db, 2), "vocal_gain_db": _round(vocal_gain_db, 2), "ducking": _round(ducking, 2)},
        "vocal_diagnostics": {"peak": _round(vocal_peak, 4), "rms": _round(vocal_rms, 5), "has_vocal_signal": bool(vocal_peak > 0.01)},
        "summary": {
            "rap_grid_bpm": plan.get("rap_grid_bpm"),
            "bars_needed": plan.get("bars_needed"),
            "target_syllables_per_bar": plan.get("target_syllables_per_bar"),
            "line_count": len(plan.get("lines") or []),
            "rendered_line_count": rendered,
        },
        "alignment_plan": {**{k: v for k, v in plan.items() if k != "lines"}, "lines": line_meta},
        "suggestions": suggestions,
        "warnings": _unique(warnings),
        "created_files": {"mix_filename": mix_path.name, "vocal_filename": vocal_path.name, "timing_filename": meta_path.name},
        "processing_seconds": _round(time.time() - started, 3),
        "notes": [
            "This is a rough beta demo render, not a final mastered vocal.",
            "Use the vocal stem as a guide track, then replace it with a real recorded take for release-quality output.",
        ],
    }
    meta_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return metadata



def render_voice_sample(text: str, output_dir: str | Path, options: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Render a short speech-only WAV so beta users can verify the TTS backend before mixing."""
    options = dict(options or {})
    backend = str(options.get("tts_backend") or options.get("voice_engine") or os.getenv("NMC_TTS_BACKEND", "auto")).strip().lower()
    if backend == "guide":
        backend = "built_in"
    if backend not in SUPPORTED_TTS_BACKENDS:
        backend = "auto"
    voice_preset = str(options.get("voice_preset") or options.get("voice") or "neutral").lower()
    if voice_preset not in VOICE_PRESETS:
        voice_preset = "neutral"
    sample_text = re.sub(r"\s+", " ", str(text or "Every sentence I am inventing has resonance on the beat.")).strip()[:240]
    duration = max(1.5, min(8.0, len(WORD_RE.findall(sample_text)) * 0.34))
    try:
        y, method = synthesize_line(sample_text, duration, backend=backend, voice_preset=voice_preset, sr=RENDER_SR)
    except Exception as exc:
        return {"available": False, "error": str(exc), "error_type": "tts_backend_unavailable", "tts_status": available_tts_engines()}
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0:
        y = y / peak * 0.82
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    render_id = uuid.uuid4().hex[:14]
    sample_path = output_dir / f"{render_id}_voice_test.wav"
    _write_wav(sample_path, y, RENDER_SR)
    return {
        "available": True,
        "render_id": render_id,
        "filename": sample_path.name,
        "path": str(sample_path),
        "duration_seconds": _round(len(y) / RENDER_SR, 2),
        "sample_rate": RENDER_SR,
        "text": sample_text,
        "vocal_engine": {
            "requested_backend": backend,
            "methods_used": [method],
            "voice_preset": voice_preset,
            "voice_label": VOICE_PRESETS[voice_preset]["label"],
        },
        "vocal_diagnostics": {"peak": _round(float(np.max(np.abs(y))) if y.size else 0.0, 4), "rms": _round(float(np.sqrt(np.mean(y ** 2))) if y.size else 0.0, 5)},
        "warnings": ["This is a TTS backend test, not a full song render."] if "built_in" not in method else ["Built-in guide synth is buzzy by design; choose Auto/macOS say/espeak for speech."],
        "created_files": {"voice_test_filename": sample_path.name},
    }


def _song_suggestions(plan: Dict[str, Any], line_meta: Sequence[Dict[str, Any]], beat_seconds: float, vocal_seconds: float, loop_beat: bool) -> List[str]:
    target = int(plan.get("target_syllables_per_bar") or 13)
    suggestions: List[str] = []
    crowded = [row for row in line_meta if float(row.get("syllables_per_bar") or 0) > target + 3]
    open_rows = [row for row in line_meta if float(row.get("syllables_per_bar") or 0) < max(4, target - 4)]
    if crowded:
        nums = ", ".join(str(row.get("render_line_number")) for row in crowded[:8])
        suggestions.append(f"Lines {nums} sound rushed against the beat grid; split them into two bars or cut filler syllables.")
    if open_rows:
        nums = ", ".join(str(row.get("render_line_number")) for row in open_rows[:8])
        suggestions.append(f"Lines {nums} leave open beat space; add ad-libs, repeat a title phrase, or hold the end word.")
    if loop_beat and vocal_seconds > beat_seconds + 1:
        suggestions.append("The renderer looped the beat to fit the full lyric. For a better beta demo, extend the instrumental or shorten the section layout.")
    if not suggestions:
        suggestions.append("The lyric density fits the selected grid; focus on performance energy and clearer end-rhyme landings.")
    return suggestions[:5]


def _unique(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for item in items:
        text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
