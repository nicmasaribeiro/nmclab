"""Beat analysis and beat-aware bar-structure coaching.

The functions in this module are deliberately local/offline. If librosa is
installed, the app can analyze common beat formats such as WAV, MP3, M4A, FLAC,
AIFF, and OGG. If librosa is missing, the app still starts and can perform a
basic WAV-only analysis using Python's standard library plus NumPy.
"""
from __future__ import annotations

import math
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np

try:  # Optional but recommended for MP3/M4A/FLAC and better tempo analysis.
    import librosa  # type: ignore
except Exception:  # pragma: no cover - app should still run without it.
    librosa = None  # type: ignore

from beat_audio import AUDIO_EXTENSIONS, AudioLoadError, audio_backend_status, compact_waveform, load_audio_for_analysis
from lyric_engine import count_syllables, tokenize, unique_preserve

ALLOWED_AUDIO_EXTENSIONS = AUDIO_EXTENSIONS
MAX_ANALYSIS_SECONDS = 330
DEFAULT_SR = 22_050
HOP_LENGTH = 512


def _round(value: float, digits: int = 2) -> float:
    if value is None or not math.isfinite(float(value)):
        return 0.0
    return round(float(value), digits)


def _duration_label(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _pct(value: float) -> int:
    if value is None or not math.isfinite(float(value)):
        return 0
    return max(0, min(100, int(round(value))))


def _safe_percentile(values: Sequence[float], percentile: float, fallback: float = 0.0) -> float:
    arr = np.asarray([v for v in values if math.isfinite(float(v))], dtype=float)
    if arr.size == 0:
        return fallback
    return float(np.percentile(arr, percentile))


def beat_backend_status() -> Dict[str, Any]:
    """Expose decoder availability and deployment diagnostics for the UI/API."""
    return audio_backend_status()


def _load_audio(path: Path) -> Tuple[np.ndarray, int, Dict[str, Any]]:
    y, sr, report = load_audio_for_analysis(path, target_sr=DEFAULT_SR, max_seconds=MAX_ANALYSIS_SECONDS)
    return y, sr, report.to_dict()


def _rms_envelope(y: np.ndarray, frame_length: int = 2048, hop_length: int = HOP_LENGTH) -> Tuple[np.ndarray, np.ndarray]:
    if y.size < frame_length:
        pad = np.pad(y, (0, max(0, frame_length - y.size)))
    else:
        pad = y
    frame_count = max(1, 1 + (len(pad) - frame_length) // hop_length)
    rms = np.zeros(frame_count, dtype=float)
    for i in range(frame_count):
        start = i * hop_length
        frame = pad[start:start + frame_length]
        if frame.size == 0:
            continue
        rms[i] = float(np.sqrt(np.mean(np.square(frame))))
    times = np.arange(frame_count, dtype=float) * hop_length
    return rms, times


def _onset_env_basic(rms: np.ndarray) -> np.ndarray:
    if rms.size == 0:
        return np.array([], dtype=float)
    diff = np.diff(rms, prepend=rms[0])
    diff[diff < 0] = 0
    if np.max(diff) > 0:
        diff = diff / np.max(diff)
    return diff


def _autocorr_tempo(onset_env: np.ndarray, frame_rate: float, min_bpm: int = 60, max_bpm: int = 190) -> float:
    env = np.asarray(onset_env, dtype=float)
    if env.size < 8 or frame_rate <= 0:
        return 90.0
    env = env - float(np.mean(env))
    corr = np.correlate(env, env, mode="full")[env.size - 1:]
    min_lag = max(1, int(round(frame_rate * 60.0 / max_bpm)))
    max_lag = min(len(corr) - 1, int(round(frame_rate * 60.0 / min_bpm)))
    if max_lag <= min_lag:
        return 90.0
    search = corr[min_lag:max_lag + 1]
    if search.size == 0 or float(np.max(search)) <= 0:
        return 90.0
    lag = int(np.argmax(search)) + min_lag
    bpm = 60.0 * frame_rate / max(1, lag)
    while bpm < 60:
        bpm *= 2
    while bpm > 190:
        bpm /= 2
    return float(bpm)


def _detect_peaks(values: np.ndarray, times: np.ndarray, percentile: float = 75.0, min_gap_seconds: float = 0.16) -> List[float]:
    if values.size < 3:
        return []
    threshold = _safe_percentile(values, percentile, fallback=float(np.mean(values)))
    peaks: List[float] = []
    last = -999.0
    for i in range(1, len(values) - 1):
        if values[i] >= threshold and values[i] >= values[i - 1] and values[i] >= values[i + 1]:
            t = float(times[i])
            if t - last >= min_gap_seconds:
                peaks.append(t)
                last = t
    return peaks


def _tempo_and_beats(y: np.ndarray, sr: int) -> Tuple[float, List[float], np.ndarray, np.ndarray, List[float], str]:
    frame_times = np.arange(max(1, len(y) // HOP_LENGTH + 1), dtype=float) * HOP_LENGTH / sr
    if librosa is not None:
        try:
            onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP_LENGTH)
            tempo_raw, beat_frames = librosa.beat.beat_track(y=y, sr=sr, onset_envelope=onset_env, hop_length=HOP_LENGTH, trim=False)
            tempo = float(np.asarray(tempo_raw).reshape(-1)[0])
            beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP_LENGTH).astype(float).tolist()
            onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=HOP_LENGTH, backtrack=False)
            onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=HOP_LENGTH).astype(float).tolist()
            frame_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr, hop_length=HOP_LENGTH)
            if len(beat_times) >= 4 and 45 <= tempo <= 220:
                return tempo, beat_times, np.asarray(onset_env, dtype=float), np.asarray(frame_times, dtype=float), onset_times, "librosa beat tracker"
        except Exception:
            pass

    rms, sample_times = _rms_envelope(y, hop_length=HOP_LENGTH)
    times = sample_times / max(1, sr)
    onset_env = _onset_env_basic(rms)
    frame_rate = sr / HOP_LENGTH
    tempo = _autocorr_tempo(onset_env, frame_rate)
    duration = len(y) / max(1, sr)
    interval = 60.0 / max(1.0, tempo)
    first_peak = _detect_peaks(onset_env, times, percentile=82, min_gap_seconds=interval * 0.5)
    offset = first_peak[0] if first_peak and first_peak[0] < interval * 1.5 else 0.0
    beat_times = list(np.arange(offset, max(offset + interval, duration), interval, dtype=float))
    onset_times = _detect_peaks(onset_env, times, percentile=78, min_gap_seconds=0.12)
    return tempo, beat_times, onset_env, times, onset_times, "autocorrelation fallback"


def _beat_stability(beat_times: Sequence[float], tempo: float) -> int:
    if len(beat_times) < 5:
        return 35
    intervals = np.diff(np.asarray(beat_times, dtype=float))
    intervals = intervals[(intervals > 0.1) & (intervals < 3.0)]
    if intervals.size < 3:
        return 40
    expected = 60.0 / max(1.0, tempo)
    jitter = float(np.median(np.abs(intervals - expected))) / max(0.001, expected)
    return _pct(100 - jitter * 220)


def _rap_grid_from_tempo(tempo: float) -> Tuple[float, str, List[Dict[str, Any]]]:
    tempo = float(tempo or 90.0)
    options: List[Dict[str, Any]] = []
    options.append({"name": "detected", "bpm": _round(tempo, 2), "bar_seconds": _round(240.0 / max(1.0, tempo), 3)})
    if tempo >= 118:
        half = tempo / 2.0
        options.append({"name": "half-time rap feel", "bpm": _round(half, 2), "bar_seconds": _round(240.0 / half, 3)})
        return half, "Detected tempo is fast, so the app uses a half-time rap grid for bar-structure suggestions while preserving the detected BPM as audio data.", options
    if tempo <= 78:
        double = tempo * 2.0
        options.append({"name": "double-time option", "bpm": _round(double, 2), "bar_seconds": _round(240.0 / double, 3)})
        return tempo, "Detected tempo is slow; suggestions use the slow grid but include double-time as an option for faster flows.", options
    return tempo, "Detected tempo is within a normal rap-counting range; suggestions use the detected grid.", options


def _pocket_ranges(rap_bpm: float) -> Dict[str, Any]:
    bar_seconds = 240.0 / max(1.0, rap_bpm)
    # Ranges assume a one-bar line. Dense rap often lives above the balanced range,
    # especially when the artist is comfortable with consonant-heavy internal rhyme.
    easy_mid = bar_seconds * 3.1
    balanced_mid = bar_seconds * 4.25
    dense_mid = bar_seconds * 5.55
    def rng(mid: float, spread: float) -> List[int]:
        return [max(3, int(math.floor(mid - spread))), max(4, int(math.ceil(mid + spread)))]
    pockets = {
        "breath": {"range": rng(easy_mid, 1.6), "description": "room for rests, ad-libs, and vowel stretch"},
        "balanced": {"range": rng(balanced_mid, 2.0), "description": "clean one-bar rap pocket"},
        "dense": {"range": rng(dense_mid, 2.8), "description": "fast internal-rhyme pocket"},
    }
    return {
        "rap_grid_bpm": _round(rap_bpm, 2),
        "beat_seconds": _round(60.0 / max(1.0, rap_bpm), 3),
        "bar_seconds": _round(bar_seconds, 3),
        "pockets": pockets,
        "default_pocket": "balanced",
    }


def _bar_energy(
    duration: float,
    rap_bpm: float,
    rms: np.ndarray,
    rms_times: np.ndarray,
    onset_times: Sequence[float],
    max_bars: int = 192,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    bar_seconds = 240.0 / max(1.0, rap_bpm)
    if bar_seconds <= 0:
        bar_seconds = 2.5
    bar_count = max(1, int(math.ceil(duration / bar_seconds)))
    shown_bars = min(bar_count, max_bars)
    energies: List[float] = []
    onset_counts: List[int] = []
    raw_rows: List[Dict[str, Any]] = []
    rms = np.asarray(rms, dtype=float)
    rms_times = np.asarray(rms_times, dtype=float)
    for idx in range(shown_bars):
        start = idx * bar_seconds
        end = min(duration, start + bar_seconds)
        mask = (rms_times >= start) & (rms_times < end)
        energy = float(np.mean(rms[mask])) if np.any(mask) else 0.0
        onsets = len([t for t in onset_times if start <= t < end])
        energies.append(energy)
        onset_counts.append(onsets)
        raw_rows.append({"bar": idx + 1, "start": start, "end": end, "energy_raw": energy, "onsets": onsets})
    lo = _safe_percentile(energies, 10, 0.0)
    hi = _safe_percentile(energies, 95, max(energies) if energies else 1.0)
    span = max(1e-9, hi - lo)
    q35 = _safe_percentile(energies, 35, 0.0)
    q70 = _safe_percentile(energies, 70, 0.0)
    max_onsets = max(1, max(onset_counts) if onset_counts else 1)

    bars: List[Dict[str, Any]] = []
    for row in raw_rows:
        score = _pct((row["energy_raw"] - lo) / span * 100)
        if row["energy_raw"] >= q70:
            label = "high"
        elif row["energy_raw"] <= q35:
            label = "low"
        else:
            label = "medium"
        density = _pct(row["onsets"] / max_onsets * 100)
        bars.append({
            "bar": row["bar"],
            "start": _round(row["start"], 2),
            "end": _round(row["end"], 2),
            "time": f"{_duration_label(row['start'])}-{_duration_label(row['end'])}",
            "energy": score,
            "onset_density": density,
            "label": label,
        })

    windows: List[Dict[str, Any]] = []
    for start_idx in range(0, len(bars), 4):
        chunk = bars[start_idx:start_idx + 4]
        if not chunk:
            continue
        avg_energy = int(round(mean([b["energy"] for b in chunk])))
        avg_density = int(round(mean([b["onset_density"] for b in chunk])))
        label = "hook/drop" if avg_energy >= 70 else "breakdown" if avg_energy <= 35 else "verse pocket"
        windows.append({
            "window": len(windows) + 1,
            "bars": f"{chunk[0]['bar']}-{chunk[-1]['bar']}",
            "start_bar": chunk[0]["bar"],
            "end_bar": chunk[-1]["bar"],
            "start": chunk[0]["start"],
            "end": chunk[-1]["end"],
            "time": f"{chunk[0]['time'].split('-')[0]}-{chunk[-1]['time'].split('-')[-1]}",
            "energy": avg_energy,
            "onset_density": avg_density,
            "label": label,
        })

    drops: List[Dict[str, Any]] = []
    for prev, cur in zip(windows, windows[1:]):
        jump = cur["energy"] - prev["energy"]
        if jump >= 16 or (cur["energy"] >= 70 and jump >= 10):
            drops.append({
                "bar": cur["start_bar"],
                "time": _duration_label(float(cur["start"])),
                "energy_jump": jump,
                "suggestion": "Place a hook entrance, title phrase, or strongest punchline here.",
            })
    drops = sorted(drops, key=lambda row: (-row["energy_jump"], row["bar"]))[:8]

    sections = _section_suggestions(windows, len(bars))
    return bars, windows, drops, sections


def _section_suggestions(windows: Sequence[Dict[str, Any]], bar_count: int) -> List[Dict[str, Any]]:
    if not windows:
        return []
    suggestions: List[Dict[str, Any]] = []
    first = windows[0]
    if first["energy"] <= 45 and first["start_bar"] <= 5:
        suggestions.append({"section": "Intro / pickup", "bars": first["bars"], "time": first["time"], "reason": "lower opening energy; good for a half-volume entrance or spoken tag"})
    high_windows = sorted([w for w in windows if w["energy"] >= 68], key=lambda w: (-w["energy"], w["start_bar"]))[:3]
    for w in high_windows:
        suggestions.append({"section": "Hook or drop", "bars": w["bars"], "time": w["time"], "reason": "highest four-bar energy; use shorter repeatable lines and stronger end-rhyme landings"})
    mid_windows = [w for w in windows if 38 <= w["energy"] < 68]
    if mid_windows:
        w = mid_windows[0]
        suggestions.append({"section": "Verse pocket", "bars": w["bars"], "time": w["time"], "reason": "medium energy leaves room for dense multisyllabic writing"})
    low_windows = sorted([w for w in windows if w["energy"] <= 35], key=lambda w: (w["energy"], w["start_bar"]))[:2]
    for w in low_windows:
        suggestions.append({"section": "Bridge / breath reset", "bars": w["bars"], "time": w["time"], "reason": "low energy zone; useful for space, shorter bars, or emotional contrast"})
    if bar_count >= 32:
        suggestions.append({"section": "Standard rap blueprint", "bars": "1-4 intro · 5-20 verse · 21-28 hook · 29-44 verse/hook", "time": "full beat", "reason": "enough estimated bars for a 4/16/8/16 style arrangement"})
    return unique_sections(suggestions, 8)


def unique_sections(items: Iterable[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for item in items:
        key = (item.get("section"), item.get("bars"))
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _feature_curves(y: np.ndarray, sr: int) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    if librosa is not None:
        try:
            rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP_LENGTH)[0]
            centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=HOP_LENGTH)[0]
            times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=HOP_LENGTH)
            return np.asarray(rms, dtype=float), np.asarray(times, dtype=float), np.asarray(centroid, dtype=float)
        except Exception:
            pass
    rms, sample_times = _rms_envelope(y, hop_length=HOP_LENGTH)
    return rms, sample_times / max(1, sr), np.zeros_like(rms)


def analyze_beat(path: str | Path, original_filename: str | None = None) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"available": False, "error": "Beat file was not found."}
    if path.suffix.lower() not in ALLOWED_AUDIO_EXTENSIONS:
        return {"available": False, "error": f"Unsupported beat format: {path.suffix}. Use WAV, MP3, M4A, FLAC, OGG, AIFF, or AAC."}
    try:
        y, sr, load_report = _load_audio(path)
        duration = len(y) / max(1, sr)
        if duration < 2.0:
            return {"available": False, "error": "Beat is too short to analyze. Upload at least a few seconds of audio."}
        tempo, beat_times, onset_env, onset_frame_times, onset_times, beat_method = _tempo_and_beats(y, sr)
        if not math.isfinite(tempo) or tempo <= 0:
            tempo = 90.0
        # Normalize extreme tempo readings into a musically useful range.
        while tempo < 55:
            tempo *= 2
        while tempo > 210:
            tempo /= 2
        rap_bpm, grid_note, tempo_options = _rap_grid_from_tempo(tempo)
        pocket = _pocket_ranges(rap_bpm)
        rms, rms_times, centroid = _feature_curves(y, sr)
        bars, windows, drops, sections = _bar_energy(duration, rap_bpm, rms, rms_times, onset_times)
        beat_stability = _beat_stability(beat_times, tempo)
        brightness = _pct((float(np.median(centroid)) if centroid.size else 0.0) / 4500 * 100)
        avg_energy = _pct(float(np.mean(rms)) / max(1e-9, _safe_percentile(rms, 95, 1.0)) * 100) if rms.size else 0
        bar_seconds = 240.0 / max(1.0, rap_bpm)
        return {
            "available": True,
            "filename": original_filename or path.name,
            "load_method": load_report.get("selected_backend", "unknown"),
            "load_report": load_report,
            "audio_diagnostics": {
                "backend": load_report.get("selected_backend", "unknown"),
                "sample_rate": load_report.get("sample_rate", sr),
                "channels": load_report.get("channels", 1),
                "attempts": load_report.get("attempts", []),
                "warnings": load_report.get("warnings", []),
                "waveform_preview": compact_waveform(y, sr, buckets=96),
            },
            "beat_method": beat_method,
            "duration_seconds": _round(duration, 2),
            "duration_label": _duration_label(duration),
            "analyzed_seconds": min(_round(duration, 2), MAX_ANALYSIS_SECONDS),
            "detected_bpm": _round(tempo, 2),
            "rap_grid_bpm": _round(rap_bpm, 2),
            "grid_note": grid_note,
            "tempo_options": tempo_options,
            "beat_stability": beat_stability,
            "beats_detected": len(beat_times),
            "beat_interval_seconds": _round(60.0 / max(1.0, rap_bpm), 3),
            "bar_duration_seconds": _round(bar_seconds, 3),
            "estimated_bar_count": max(1, int(math.ceil(duration / bar_seconds))),
            "average_energy": avg_energy,
            "brightness": brightness,
            "pocket": pocket,
            "energy_bars": bars,
            "four_bar_windows": windows,
            "drop_moments": drops,
            "section_suggestions": sections,
        }
    except AudioLoadError as exc:
        return {
            "available": False,
            "filename": original_filename or path.name,
            "error": str(exc),
            "audio_diagnostics": exc.to_dict(),
            "backend_status": beat_backend_status(),
        }
    except Exception as exc:
        return {
            "available": False,
            "filename": original_filename or path.name,
            "error": str(exc),
            "backend_status": beat_backend_status(),
        }


def _choose_pocket(avg_syllables: float, beat: Dict[str, Any]) -> Tuple[str, List[int]]:
    pockets = beat.get("pocket", {}).get("pockets", {})
    if not pockets:
        return "balanced", [10, 16]
    balanced = pockets.get("balanced", {}).get("range", [10, 16])
    dense = pockets.get("dense", {}).get("range", [14, 22])
    breath = pockets.get("breath", {}).get("range", [6, 11])
    if avg_syllables >= dense[0] - 1:
        return "dense", dense
    if avg_syllables <= breath[1] + 1:
        return "breath", breath
    return "balanced", balanced


def _split_after_word(words: Sequence[str], target_syllables: int) -> Tuple[int, str, str]:
    if not words:
        return 0, "", ""
    running = 0
    best_idx = 1
    best_dist = 999
    for idx, word in enumerate(words, start=1):
        running += count_syllables(word)
        dist = abs(running - target_syllables)
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    left = " ".join(words[:best_idx])
    right = " ".join(words[best_idx:])
    return best_idx, left, right


def _bar_energy_lookup(beat: Dict[str, Any], start_bar: int, span: int) -> Dict[str, Any]:
    bars = beat.get("energy_bars") or []
    chunk = [b for b in bars if start_bar <= int(b.get("bar", 0)) < start_bar + span]
    if not chunk:
        return {"energy": 50, "onset_density": 50, "label": "unknown", "time": "not mapped"}
    return {
        "energy": int(round(mean([int(b.get("energy", 50)) for b in chunk]))),
        "onset_density": int(round(mean([int(b.get("onset_density", 50)) for b in chunk]))),
        "label": max([str(b.get("label", "medium")) for b in chunk], key=[str(b.get("label", "medium")) for b in chunk].count),
        "time": f"{chunk[0].get('time', '').split('-')[0]}-{chunk[-1].get('time', '').split('-')[-1]}",
    }


def _line_beat_moves(
    detail: Dict[str, Any],
    line_card: Dict[str, Any],
    target_range: Sequence[int],
    bar_span: int,
    energy: Dict[str, Any],
    beat: Dict[str, Any],
) -> List[str]:
    syllables = int(detail.get("syllables", 0))
    low, high = int(target_range[0]), int(target_range[1])
    moves: List[str] = []
    per_bar = syllables / max(1, bar_span)
    if bar_span == 1 and syllables > high:
        moves.append(f"Compress this to {high} syllables or split it into two bars; it is {syllables - high} syllables above the one-bar pocket.")
    elif bar_span > 1:
        moves.append(f"Treat this as a {bar_span}-bar thought. Split the syntax so each bar carries about {low}-{high} syllables.")
    elif syllables < low:
        moves.append(f"This is under the beat pocket by about {low - syllables} syllables; either add an image phrase or leave a deliberate rest.")
    else:
        moves.append("Length fits the beat pocket; focus on where the stress lands, not on adding words.")

    label = energy.get("label", "medium")
    density = int(energy.get("onset_density", 50))
    if label == "high":
        moves.append("High-energy bar: use a cleaner hook-like landing. Put the title word or hardest end rhyme on beat 4.")
    elif label == "low":
        moves.append("Low-energy bar: leave more breath after the punchline or use a quieter setup line before the next dense bar.")
    else:
        moves.append("Medium-energy bar: good for your dense technical style; keep one internal echo before the final rhyme.")
    if density >= 72:
        moves.append("Busy percussion detected here; cut filler and avoid cramming extra unstressed syllables between beats 2 and 3.")
    elif density <= 34:
        moves.append("Sparse percussion detected here; you can stretch vowels, use a pickup, or add an ad-lib without fighting the beat.")

    end_word = detail.get("end_word") or "final word"
    moves.append(f"Performance grid: stress beat 1 with the setup, echo near beat 2-and, then land “{end_word}” near beat 4.")
    return unique_preserve(moves, 6)


def attach_beat_guidance(analysis: Dict[str, Any], beat: Dict[str, Any]) -> Dict[str, Any]:
    """Add beat-aware bar suggestions to an existing lyric analysis dict."""
    if not beat or not beat.get("available"):
        analysis["beat_analysis"] = beat or {"available": False}
        analysis["beat_alignment"] = {"available": False, "summary": "No usable beat uploaded."}
        return analysis

    details = analysis.get("raw_line_details") or []
    line_cards = {int(card.get("number", -1)): card for card in analysis.get("line_suggestions", [])}
    avg_syllables = float(analysis.get("stats", {}).get("avg_syllables") or 0.0)
    pocket_name, target_range = _choose_pocket(avg_syllables, beat)
    low, high = int(target_range[0]), int(target_range[1])
    bar_seconds = float(beat.get("bar_duration_seconds") or 2.5)
    beat_seconds = float(beat.get("beat_interval_seconds") or bar_seconds / 4)
    total_available = int(beat.get("estimated_bar_count") or 0)

    current_bar = 1
    per_line: List[Dict[str, Any]] = []
    split_count = 0
    compress_count = 0
    extend_count = 0
    locked_count = 0
    for detail in details:
        line_no = int(detail.get("number", 0))
        syllables = int(detail.get("syllables", 0))
        if syllables <= high + 2:
            span = 1
        else:
            span = max(2, min(4, int(math.ceil(syllables / max(1, high)))))
        if syllables < low - 1:
            extend_count += 1
        elif span > 1:
            split_count += 1
        elif syllables > high:
            compress_count += 1
        else:
            locked_count += 1

        start = (current_bar - 1) * bar_seconds
        end = start + span * bar_seconds
        landing = max(start, end - beat_seconds * 0.35)
        energy = _bar_energy_lookup(beat, current_bar, span)
        words = detail.get("words") or tokenize(detail.get("text", ""))
        split_idx, split_left, split_right = _split_after_word(words, max(low, min(high, int(round(syllables / max(1, span))))))
        line_card = line_cards.get(line_no, {})
        possible_words = line_card.get("possible_words", {}) if isinstance(line_card, dict) else {}
        add_words = unique_preserve(
            list(possible_words.get("signature_motif_words", []))
            + list(possible_words.get("internal_echo_words", []))
            + list(possible_words.get("concrete_image_words", [])),
            12,
        )
        cut_words = unique_preserve(list(detail.get("cut_candidates", [])) + list(possible_words.get("cut_or_replace", [])), 12)
        if not cut_words and words:
            # Suggest trimming short connective words first.
            cut_words = unique_preserve([w for w in words if len(w) <= 3], 8)
        density_per_beat = syllables / max(1, span * 4)
        if density_per_beat >= 4.3:
            density_label = "very dense"
        elif density_per_beat >= 3.2:
            density_label = "dense"
        elif density_per_beat <= 1.65:
            density_label = "open"
        else:
            density_label = "balanced"
        plan = {
            "line_number": line_no,
            "text": detail.get("text", ""),
            "assigned_bars": f"{current_bar}" if span == 1 else f"{current_bar}-{current_bar + span - 1}",
            "bar_start": current_bar,
            "bar_span": span,
            "time_window": f"{_duration_label(start)}-{_duration_label(end)}",
            "landing_time": _duration_label(landing),
            "syllables": syllables,
            "target_syllables_per_bar": [low, high],
            "syllables_per_beat": _round(density_per_beat, 2),
            "density_label": density_label,
            "energy_context": energy,
            "split_after_word": split_idx,
            "split_preview": {"bar_1": split_left, "bar_2_plus": split_right} if span > 1 else {},
            "beat_moves": _line_beat_moves(detail, line_card, target_range, span, energy, beat),
            "bar_structure_options": _bar_structure_options(syllables, target_range, span),
            "words_to_add_for_pocket": add_words,
            "words_to_cut_for_pocket": cut_words,
        }
        per_line.append(plan)
        if line_no in line_cards:
            line_cards[line_no]["beat_guidance"] = plan
        current_bar += span

    bars_needed = current_bar - 1
    fit_gap = total_available - bars_needed if total_available else 0
    if total_available and bars_needed > total_available:
        fit_status = f"Lyrics need about {bars_needed} bars, which is {abs(fit_gap)} bars longer than the analyzed beat grid. Compress sections, cut repeated lines, or switch more long lines to double-time."
    elif total_available:
        fit_status = f"Lyrics need about {bars_needed} bars, leaving roughly {fit_gap} bars for intro, hook repeats, ad-libs, or outro."
    else:
        fit_status = f"Lyrics need about {bars_needed} bars on the estimated grid."

    beat_actions = [
        {"title": "Use the beat pocket, not only the corpus median", "detail": f"Your lyric average is {avg_syllables} syllables/line. Against this beat, the recommended {pocket_name} pocket is {low}-{high} syllables per one-bar line."},
        {"title": "Split long technical lines", "detail": f"{split_count} line(s) are better treated as multi-bar thoughts. Split after the suggested word and make each bar land separately."},
        {"title": "Protect the bar-4 landing", "detail": "Move the hardest noun, title word, or rhyme-family word to the final quarter of each assigned bar span."},
    ]
    if beat.get("drop_moments"):
        first_drop = beat["drop_moments"][0]
        beat_actions.append({"title": "Write toward the first drop", "detail": f"The strongest detected energy jump starts near bar {first_drop['bar']} at {first_drop['time']}. Place a hook entrance or punchline there."})
    if beat.get("beat_stability", 100) < 62:
        beat_actions.append({"title": "Loose beat grid warning", "detail": "Tempo stability is moderate/low. Use the suggestions as a pocket guide, then verify by rapping along to the actual beat."})

    analysis["beat_analysis"] = beat
    analysis["beat_alignment"] = {
        "available": True,
        "recommended_pocket": pocket_name,
        "target_syllables_per_bar": [low, high],
        "bars_needed_by_lyrics": bars_needed,
        "beat_bars_available": total_available,
        "fit_status": fit_status,
        "locked_lines": locked_count,
        "compress_lines": compress_count,
        "split_lines": split_count,
        "extend_or_rest_lines": extend_count,
        "global_actions": beat_actions,
        "per_line": per_line,
    }
    return analysis


def _bar_structure_options(syllables: int, target_range: Sequence[int], span: int) -> List[str]:
    low, high = int(target_range[0]), int(target_range[1])
    options: List[str] = []
    if span > 1:
        options.append(f"Two-bar split: first clause {low}-{high} syllables, second clause {low}-{high} syllables, separate end-rhyme landings.")
        options.append("Call-and-response split: bar 1 sets the concept; bar 2 answers with the punch word.")
    if syllables > high:
        options.append(f"Compression pass: remove {max(1, syllables - high)} syllable(s) to make it a one-bar line.")
    if syllables < low:
        options.append(f"Expansion pass: add {max(1, low - syllables)} syllable(s), or leave that space as a breath before the next line.")
    options.append("16th-note grid: 4 beats × 4 slots; keep the last slot open enough for the rhyme to breathe.")
    return options[:4]
