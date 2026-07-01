# Beta Deployment Checklist

## Before pushing to GitHub

```bash
python -m py_compile app.py lyric_engine.py editing_engine.py beat_audio.py beat_engine.py comparison_engine.py song_engine.py wsgi.py
python tests/smoke_test.py
```

Confirm these files are present:

```text
requirements.txt
wsgi.py
gunicorn.conf.py
Procfile
render.yaml
railway.json
Dockerfile
.env.example
.gitignore
.dockerignore
data/corpus_profile.json
data/comparison_profiles.json
```

## Required production secrets

Never commit these values:

```text
SECRET_KEY
BETA_ACCESS_CODE
BETA_ADMIN_TOKEN
```

Set them in your hosting provider's environment-variable dashboard.

## Recommended launch flow

1. Deploy privately with `BETA_ACCESS_CODE` turned on.
2. Open `/healthz`, `/readyz`, and `/api/beat/diagnostics`.
3. Test the invite-code login.
4. Paste a short lyric draft.
5. Generate a Static Snapshot.
6. Open Sentence Lab and analyze one sentence synchronously.
7. Upload a small WAV or MP3 beat. If it fails, use **Run decoder diagnostics** in the Beat + Bars tab and capture the attempted backend report.
8. Open Song Render and click **Test speech voice**. This must produce intelligible speech before a full mix.
9. Preview the timing map and render a short WAV mix.
10. Submit one feedback form entry.
11. Export feedback with `/api/admin/feedback` and `X-Admin-Token`.
12. Send testers the public URL and the invite code separately.

## Suggested beta tester prompt

Ask testers to try these tasks:

- Paste 8 to 16 bars and refresh the Static Snapshot.
- Use Sentence Lab to pull the active sentence, analyze it, and apply one rewrite back to the editor.
- Click rhyme-family chips and check if highlighted rhymes make sense.
- Upload a beat and compare the bar-structure advice to their own flow.
- Click **Test speech voice** first; if it fails, report the TTS status shown in the Song Render panel.
- Render a short song mix and check whether the vocal exposes bar-length problems.
- Try applying one rewrite patch.
- Submit feedback with the current draft excerpt included only when comfortable.

## Corpus and comparison privacy

This beta package uses compiled profile files: `data/corpus_profile.json` for the private NMC style corpus and `data/comparison_profiles.json` for real-rapper benchmark statistics. Raw uploaded RTF files, private lyric text, and raw commercial reference lyrics are not required for deployment. Keep raw corpus files outside public repositories unless you intentionally want to publish them and have the rights to do so.

## Known limitations

- Uploaded beats use server CPU and memory; keep beta uploads short. Beat decoding is factored into `beat_audio.py`, but MP3/M4A still require a working `ffmpeg`, `librosa`, or `soundfile` backend.
- Free/low-tier cloud instances may sleep or be slow with audio analysis and song rendering.
- Feedback JSONL is local unless the host has persistent disk enabled.
- This is not a full user-account system. The beta gate is an invite-code gate, not full authentication.
- In-memory jobs, beat IDs, and render IDs work best with one Gunicorn worker process during beta. Sentence Lab itself is synchronous and does not need the background job queue.
- Online Linux deployments should use the included Dockerfile so `espeak-ng` is available for server-side TTS. macOS system TTS works only when running the app locally on macOS.
- The Song Render tab no longer silently falls back to the built-in oscillator when real TTS is missing. Auto returns a clear error instead of producing a buzz track. The `built_in` backend is only for timing tests.


## Reference benchmark data

The beta package includes `data/comparison_profiles.json`, a derived profile-only file. Do not commit or deploy raw commercial lyrics or unlicensed reference corpora. The comparison feature works from the compiled JSON profile.

## Rebuilding comparison profiles privately

Keep raw reference lyrics outside the repo. Build a manifest that points to private text files, then run:

```bash
python tools/build_comparison_profiles.py --manifest /secure/private/comparison_manifest.json --output data/comparison_profiles.json
```

The resulting JSON stores only derived cadence, rhyme, entropy, and line-length statistics.
