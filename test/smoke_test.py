from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "500")

from app import app  # noqa: E402


def main() -> int:
    client = app.test_client()

    health = client.get("/healthz")
    assert health.status_code == 200, health.data
    assert health.get_json()["ok"] is True

    ready = client.get("/readyz")
    assert ready.status_code == 200, ready.data
    assert ready.get_json().get("comparison_profiles", 0) >= 1

    index = client.get("/")
    assert index.status_code == 200, index.data[:500]
    assert b"Beta Rap Editing Lab" in index.data

    payload = {"lyrics": "My sentence keeps stretching with system precision\nThe rhythm is written with hidden decisions", "coach_mode": "match"}
    snapshot = client.post("/api/snapshot", data=json.dumps(payload), content_type="application/json")
    assert snapshot.status_code == 200, snapshot.data[:500]
    data = snapshot.get_json()
    assert data.get("available") is True
    assert data.get("rhyme_highlights") is not None
    assert data.get("comparison", {}).get("available") is True
    assert data.get("meter_report", {}).get("available") is True
    assert data.get("physics_report", {}).get("available") is True
    assert data.get("line_breakdown", [])[0].get("meter", {}).get("available") is True
    assert data.get("line_breakdown", [])[0].get("physics", {}).get("available") is True
    assert data.get("line_breakdown", [])[0].get("comparison_guidance", {}).get("available") is True

    comparison_profiles = client.get("/api/comparison/profiles")
    assert comparison_profiles.status_code == 200, comparison_profiles.data
    assert len(comparison_profiles.get_json().get("profiles", [])) >= 1

    comparison = client.post("/api/comparison", data=json.dumps(payload), content_type="application/json")
    assert comparison.status_code == 200, comparison.data[:500]
    assert comparison.get_json().get("best_match", {}).get("score", 0) >= 0

    score = client.post("/api/score", json=payload)
    assert score.status_code == 200, score.data[:500]
    score_data = score.get_json()
    assert score_data.get("available") is True
    assert score_data.get("overall", 0) >= 0
    assert score_data.get("bar_scores")
    assert score_data.get("bar_scores", [])[0].get("overall", 0) >= 0

    edit_compare = client.post("/api/score/compare-edits", json={
        "original_lyrics": payload["lyrics"],
        "edited_lyrics": payload["lyrics"] + "\nEvery bar lands with clearer system resonance",
        "coach_mode": "match",
    })
    assert edit_compare.status_code == 200, edit_compare.data[:500]
    edit_data = edit_compare.get_json()
    assert edit_data.get("available") is True
    assert edit_data.get("summary", {}).get("edited_score", 0) >= 0
    assert edit_data.get("bar_deltas")

    sentence = client.post("/api/sentence/analyze", json={"sentence": "My sentence keeps stretching with system precision", "coach_mode": "match"})
    assert sentence.status_code == 200, sentence.data[:500]
    sentence_data = sentence.get_json()
    assert sentence_data.get("available") is True
    assert sentence_data.get("report_type") == "synchronous_sentence_feedback"
    assert sentence_data.get("possible_words") is not None
    assert sentence_data.get("meter", {}).get("available") is True
    assert sentence_data.get("physics", {}).get("available") is True
    assert sentence_data.get("metrics", {}).get("dominant_meter")
    assert sentence_data.get("bar_plan", {}).get("available") is True

    pattern_compare = client.post("/api/sentence/compare-patterns", json={
        "text": "Every sentence I invent has resonance\nThe method in the message bends with evidence\nThe rhythm in the system keeps a vivid sentence",
        "coach_mode": "match",
    })
    assert pattern_compare.status_code == 200, pattern_compare.data[:500]
    pattern_data = pattern_compare.get_json()
    assert pattern_data.get("available") is True
    assert pattern_data.get("report_type") == "sentence_rhyme_pattern_comparison"
    assert pattern_data.get("sentences")
    assert pattern_data.get("pattern_blueprints")
    assert pattern_data.get("pairwise")

    live_payload = {
        "lyrics": "The expression is in the direction of the diction\nThe present presence corrects the sentence",
        "active_line": 1,
        "coach_mode": "match",
    }
    live_routes = client.get("/api/live-rhyme/routes")
    assert live_routes.status_code == 200, live_routes.data[:500]
    assert live_routes.get_json().get("available") is True

    live_health = client.get("/api/live-rhyme/health")
    assert live_health.status_code == 200, live_health.data[:500]
    assert live_health.get_json().get("ok") is True

    clipped_sync = client.post("/api/live-rhyme/sync", json={
        "lyrics": "The present presence corrects the sentence",
        "active_line": 1,
        "context_offset_lines": 4,
        "total_source_lines": 8,
    })
    assert clipped_sync.status_code == 200, clipped_sync.data[:500]
    assert clipped_sync.get_json().get("active_report", {}).get("line_number") == 5

    live_sync = client.post("/api/live-rhyme/sync", json=live_payload)
    assert live_sync.status_code == 200, live_sync.data[:500]
    assert live_sync.get_json().get("available") is True
    assert live_sync.get_json().get("active_report", {}).get("ranked_options")

    live_rhyme = client.post("/api/live-rhyme-job", json=live_payload)
    assert live_rhyme.status_code == 200, live_rhyme.data[:500]
    live_rhyme_data = live_rhyme.get_json()
    assert live_rhyme_data.get("job_type") == "live_rhyme_writer"
    assert live_rhyme_data.get("job_id")
    assert live_rhyme_data.get("status") == "complete"
    assert live_rhyme_data.get("result", {}).get("available") is True
    assert live_rhyme_data.get("poll_required") is False
    # Poll aliases still work, but the live sidecar no longer depends on them.
    poll = client.get(f"/api/live-rhyme/job/{live_rhyme_data['job_id']}")
    assert poll.status_code == 200, poll.data[:500]
    assert poll.get_json().get("status") == "complete"

    word_routes = client.get("/api/rhyme-word/routes")
    assert word_routes.status_code == 200, word_routes.data[:500]
    assert word_routes.get_json().get("available") is True

    word_payload = {
        "word": "diction",
        "line_text": "The expression is in the direction of the diction",
        "lyrics": live_payload["lyrics"],
        "active_line": 1,
        "coach_mode": "match",
        "selection_start": 43,
        "selection_end": 50,
    }
    word_sync = client.post("/api/rhyme-word/sync", json=word_payload)
    assert word_sync.status_code == 200, word_sync.data[:500]
    assert word_sync.get_json().get("available") is True
    assert word_sync.get_json().get("target_word") == "diction"

    word_job = client.post("/api/rhyme-word-job", json=word_payload)
    assert word_job.status_code == 200, word_job.data[:500]
    assert word_job.get_json().get("job_type") == "selected_word_rhyme"
    assert word_job.get_json().get("status") == "complete"
    assert word_job.get_json().get("result", {}).get("available") is True
    assert word_job.get_json().get("poll_required") is False
    word_poll = client.get(f"/api/rhyme-word/job/{word_job.get_json()['job_id']}")
    assert word_poll.status_code == 200, word_poll.data[:500]
    assert word_poll.get_json().get("status") == "complete"

    meter = client.post("/api/meter/sentence", json={"sentence": "My sentence keeps stretching with system precision"})
    assert meter.status_code == 200, meter.data[:500]
    assert meter.get_json().get("available") is True
    assert meter.get_json().get("summary", {}).get("stressed_syllables", 0) >= 1

    physics = client.post("/api/physics/analyze", json=payload)
    assert physics.status_code == 200, physics.data[:500]
    assert physics.get_json().get("available") is True
    assert physics.get_json().get("summary", {}).get("avg_force_pct", 0) >= 0

    physics_sentence = client.post("/api/physics/sentence", json={"sentence": "My sentence keeps stretching with system precision"})
    assert physics_sentence.status_code == 200, physics_sentence.data[:500]
    assert physics_sentence.get_json().get("available") is True

    extracted = client.post("/api/sentence", json={"lyrics": "First sentence. Second sentence with system resonance.", "cursor_index": 25})
    assert extracted.status_code == 200, extracted.data[:500]
    assert extracted.get_json().get("sentence", "").startswith("Second sentence")

    beat_diag = client.get("/api/beat/diagnostics")
    assert beat_diag.status_code == 200, beat_diag.data[:500]
    assert beat_diag.get_json().get("basic_wav_fallback") is True

    beat_path = ROOT / "data" / "sample_beat.wav"
    with beat_path.open("rb") as f:
        beat_upload = client.post("/api/beat/upload", data={"beat_file": (f, "sample_beat.wav")}, content_type="multipart/form-data")
    assert beat_upload.status_code == 200, beat_upload.data[:500]
    beat_json = beat_upload.get_json()
    assert beat_json.get("audio_diagnostics", {}).get("attempts")
    beat_id = beat_json.get("beat_id")
    assert beat_id

    timing = client.post("/api/song/timing", json={"lyrics": payload["lyrics"], "beat_id": beat_id, "voice_engine": "guide"})
    assert timing.status_code == 200, timing.data[:500]
    assert timing.get_json().get("available") is True

    render = client.post("/api/song/render", json={"lyrics": payload["lyrics"], "beat_id": beat_id, "voice_engine": "guide", "outro_bars": 0})
    assert render.status_code == 200, render.data[:500]
    render_data = render.get_json()
    assert render_data.get("available") is True
    assert render_data.get("download_urls", {}).get("mix")
    mix = client.get(render_data["download_urls"]["mix"])
    assert mix.status_code == 200, mix.data[:20]


    beat_path = ROOT / "data" / "sample_beat.wav"
    with beat_path.open("rb") as f:
        beat_upload = client.post("/api/beat/upload", data={"beat_file": (f, "sample_beat.wav")}, content_type="multipart/form-data")
    assert beat_upload.status_code == 200, beat_upload.data[:500]
    beat_id = beat_upload.get_json().get("beat_id")

    song_payload = {
        "lyrics": "My sentence keeps stretching with system precision\nThe rhythm is written with hidden decisions",
        "beat_id": beat_id,
        "tts_backend": "built_in",
        "voice_preset": "robot",
        "rap_intensity": "balanced",
        "start_bar": 0,
        "tail_bars": 0,
        "loop_beat": True,
        "title": "smoke_song",
    }
    timing = client.post("/api/song/timing", json=song_payload)
    assert timing.status_code == 200, timing.data[:500]
    assert timing.get_json().get("available") is True

    song = client.post("/api/song/render", json=song_payload)
    assert song.status_code == 200, song.data[:500]
    song_data = song.get_json()
    assert song_data.get("available") is True
    assert song_data.get("download_urls", {}).get("mix")
    audio = client.get(song_data.get("audio_url"))
    assert audio.status_code == 200, audio.status_code
    assert len(audio.data) > 1000

    feedback = client.post("/api/beta/feedback", json={"message": "Smoke test feedback", "rating": 5, "kind": "test"})
    assert feedback.status_code == 200, feedback.data
    assert feedback.get_json()["ok"] is True

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
