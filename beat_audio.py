"""Audio loading and beat-analysis diagnostics.

This module is intentionally isolated from the musical-analysis code.  The app
can now explain *which* decoder failed instead of collapsing the whole beat
workflow into a generic upload error.
"""
from __future__ import annotations

import importlib
import math
import shutil
import subprocess
import wave
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

DEFAULT_ANALYSIS_SR = 22_050
MAX_ANALYSIS_SECONDS = 330

AUDIO_EXTENSIONS = (".wav", ".wave", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".aif", ".aiff")


@dataclass
class BackendAttempt:
    backend: str
    ok: bool
    message: str


@dataclass
class AudioLoadReport:
    selected_backend: str
    sample_rate: int
    duration_seconds: float
    channels: int
    attempts: List[BackendAttempt]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["attempts"] = [asdict(item) for item in self.attempts]
        data["duration_seconds"] = round(float(self.duration_seconds), 3)
        return data


class AudioLoadError(RuntimeError):
    """Raised when no audio backend can decode a beat."""

    def __init__(self, message: str, attempts: List[BackendAttempt] | None = None):
        super().__init__(message)
        self.attempts = attempts or []

    def to_dict(self) -> Dict[str, Any]:
        return {"error": str(self), "attempts": [asdict(item) for item in self.attempts]}


def _module_status(name: str) -> Dict[str, Any]:
    try:
        module = importlib.import_module(name)
        return {"available": True, "version": getattr(module, "__version__", "unknown")}
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"available": False, "error": str(exc)}


def ffmpeg_status() -> Dict[str, Any]:
    exe = shutil.which("ffmpeg")
    if not exe:
        return {"available": False, "path": None, "version": None}
    try:
        proc = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=4)
        first = (proc.stdout or proc.stderr or "").splitlines()[0] if (proc.stdout or proc.stderr) else "ffmpeg present"
        return {"available": proc.returncode == 0, "path": exe, "version": first}
    except Exception as exc:  # pragma: no cover - environment dependent
        return {"available": False, "path": exe, "error": str(exc)}


def audio_backend_status() -> Dict[str, Any]:
    """Return deployment diagnostics used by /api/beat/diagnostics."""
    return {
        "ok": True,
        "recommended_for_beta": "ffmpeg + librosa + soundfile",
        "allowed_extensions": list(AUDIO_EXTENSIONS),
        "basic_wav_fallback": True,
        "librosa": _module_status("librosa"),
        "soundfile": _module_status("soundfile"),
        "ffmpeg": ffmpeg_status(),
    }


def _normalize_audio(y: np.ndarray) -> np.ndarray:
    y = np.asarray(y, dtype=np.float32)
    if y.ndim > 1:
        y = np.mean(y, axis=1)
    if y.size == 0:
        return y.astype(np.float32)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 1.0:
        y = y / peak
    # Remove DC offset so onset/RMS analysis is not skewed by malformed exports.
    y = y - float(np.mean(y))
    return np.clip(y, -1.0, 1.0).astype(np.float32)


def _linear_resample(y: np.ndarray, src_sr: int, target_sr: int) -> np.ndarray:
    if int(src_sr) == int(target_sr) or y.size == 0:
        return y.astype(np.float32)
    duration = y.size / float(max(1, src_sr))
    target_len = max(1, int(round(duration * target_sr)))
    old_x = np.linspace(0.0, duration, num=y.size, endpoint=False)
    new_x = np.linspace(0.0, duration, num=target_len, endpoint=False)
    return np.interp(new_x, old_x, y).astype(np.float32)


def _trim_seconds(y: np.ndarray, sr: int, max_seconds: float) -> np.ndarray:
    max_samples = int(max(1.0, max_seconds) * sr)
    if y.size > max_samples:
        return y[:max_samples]
    return y


def _load_librosa(path: Path, target_sr: int, max_seconds: float) -> Tuple[np.ndarray, int, int]:
    librosa = importlib.import_module("librosa")
    y, sr = librosa.load(str(path), sr=target_sr, mono=True, duration=max_seconds)
    return _normalize_audio(np.asarray(y, dtype=np.float32)), int(sr), 1


def _load_soundfile(path: Path, target_sr: int, max_seconds: float) -> Tuple[np.ndarray, int, int]:
    sf = importlib.import_module("soundfile")
    info = sf.info(str(path))
    frames = min(int(info.frames), int(max_seconds * int(info.samplerate)))
    data, sr = sf.read(str(path), frames=frames, always_2d=True, dtype="float32")
    channels = int(data.shape[1]) if data.ndim == 2 else 1
    y = np.mean(data, axis=1) if data.ndim == 2 else data
    y = _linear_resample(_normalize_audio(y), int(sr), target_sr)
    return _normalize_audio(y), int(target_sr), channels


def _decode_24bit_pcm(frames: bytes) -> np.ndarray:
    # Convert packed signed little-endian 24-bit PCM into int32.
    raw = np.frombuffer(frames, dtype=np.uint8)
    usable = (raw.size // 3) * 3
    raw = raw[:usable].reshape(-1, 3)
    out = (raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16))
    sign = out & 0x800000
    out = out - (sign << 1)
    return out.astype(np.float32) / 8388608.0


def _load_basic_wav(path: Path, target_sr: int, max_seconds: float) -> Tuple[np.ndarray, int, int]:
    if path.suffix.lower() not in {".wav", ".wave"}:
        raise RuntimeError("basic WAV fallback only supports .wav/.wave files")
    with wave.open(str(path), "rb") as wav:
        channels = int(wav.getnchannels())
        sample_width = int(wav.getsampwidth())
        sr = int(wav.getframerate())
        max_frames = min(int(wav.getnframes()), int(max_seconds * sr))
        frames = wav.readframes(max_frames)
    if sample_width == 1:
        data = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        data = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 3:
        data = _decode_24bit_pcm(frames)
    elif sample_width == 4:
        data = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise RuntimeError(f"unsupported WAV sample width: {sample_width} bytes")
    if channels > 1:
        usable = (data.size // channels) * channels
        data = data[:usable].reshape(-1, channels).mean(axis=1)
    y = _linear_resample(_normalize_audio(data), sr, target_sr)
    return _normalize_audio(y), int(target_sr), channels


def _load_ffmpeg(path: Path, target_sr: int, max_seconds: float) -> Tuple[np.ndarray, int, int]:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg executable not found")
    cmd = [
        exe,
        "-v", "error",
        "-nostdin",
        "-t", str(float(max_seconds)),
        "-i", str(path),
        "-f", "f32le",
        "-acodec", "pcm_f32le",
        "-ac", "1",
        "-ar", str(int(target_sr)),
        "pipe:1",
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=max(20, min(180, int(max_seconds / 3) + 20)))
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="replace").strip() or "ffmpeg decode failed"
        raise RuntimeError(err[-600:])
    y = np.frombuffer(proc.stdout, dtype=np.float32)
    if y.size == 0:
        raise RuntimeError("ffmpeg decoded zero samples")
    return _normalize_audio(y), int(target_sr), 1


def load_audio_for_analysis(
    path: str | Path,
    target_sr: int = DEFAULT_ANALYSIS_SR,
    max_seconds: float = MAX_ANALYSIS_SECONDS,
) -> Tuple[np.ndarray, int, AudioLoadReport]:
    """Decode audio with multiple backends and return a transparent report."""
    audio_path = Path(path)
    attempts: List[BackendAttempt] = []
    warnings: List[str] = []
    if not audio_path.exists():
        raise AudioLoadError("Beat file was not found.", attempts)
    if audio_path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise AudioLoadError(f"Unsupported beat format: {audio_path.suffix}", attempts)

    # Order matters: librosa gives the most stable tempo features when present;
    # soundfile handles WAV/FLAC/OGG cleanly; ffmpeg rescues most web/mobile exports;
    # the stdlib WAV path keeps the app usable in minimal environments.
    loaders = [
        ("librosa", _load_librosa),
        ("soundfile", _load_soundfile),
        ("ffmpeg", _load_ffmpeg),
        ("basic_wav", _load_basic_wav),
    ]
    last_error = "No decoder attempted."
    for name, loader in loaders:
        try:
            y, sr, channels = loader(audio_path, int(target_sr), float(max_seconds))
            y = _trim_seconds(_normalize_audio(y), int(sr), float(max_seconds))
            duration = y.size / float(max(1, sr))
            if y.size < int(sr * 0.35):
                raise RuntimeError("decoded audio is too short or empty")
            if float(np.max(np.abs(y))) < 1e-5:
                raise RuntimeError("decoded audio is near-silent")
            attempts.append(BackendAttempt(name, True, f"decoded {duration:.2f}s at {sr} Hz"))
            if duration >= max_seconds - 0.5:
                warnings.append(f"Analysis was capped at {int(max_seconds)} seconds for performance.")
            report = AudioLoadReport(
                selected_backend=name,
                sample_rate=int(sr),
                duration_seconds=float(duration),
                channels=int(channels),
                attempts=attempts,
                warnings=warnings,
            )
            return y, int(sr), report
        except Exception as exc:
            last_error = str(exc)
            attempts.append(BackendAttempt(name, False, last_error[-800:]))

    helpful = (
        "No audio decoder could open this beat. For local Mac beta runs, install ffmpeg "
        "or upload a WAV export. For hosted deployment, use the included Dockerfile so ffmpeg/libsndfile are present."
    )
    raise AudioLoadError(f"{helpful} Last error: {last_error}", attempts)


def compact_waveform(y: np.ndarray, sr: int, buckets: int = 96) -> List[float]:
    """Small waveform preview for diagnostics/UI; values are normalized RMS buckets."""
    y = np.asarray(y, dtype=np.float32)
    if y.size == 0:
        return []
    buckets = max(8, min(512, int(buckets)))
    chunk = max(1, int(math.ceil(y.size / buckets)))
    values: List[float] = []
    for start in range(0, y.size, chunk):
        frame = y[start:start + chunk]
        if frame.size:
            values.append(float(np.sqrt(np.mean(frame * frame))))
    peak = max(values) if values else 1.0
    if peak <= 0:
        return [0.0 for _ in values]
    return [round(v / peak, 4) for v in values[:buckets]]
