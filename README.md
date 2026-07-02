# NMC Beta Rap Lab

## Advanced rhyme suggestion upgrade

This build adds a dedicated rhyme engine on top of the existing rhyme highlighting system:

- CMUdict-backed phonetic scoring with deterministic fallback for slang, names, and invented words.
- Perfect/family, slant, assonance, consonance, stress-matched, and multi-syllable rhyme banks.
- Rhyme power scoring for every line.
- Scheme-level repair notes for overused families, single-use families, repeated exact end words, and long consecutive rhyme runs.
- Rhyme ladders that show how to move from a tight family rhyme to a slant turn, multi-syllable ending, or internal setup.
- New JSON endpoints: `GET /api/rhyme/<word>`, `POST /api/rhyme/word`, `POST /api/rhyme/lab`, and `POST /api/rhyme/analyze`.

The real-rapper comparison layer remains publish-safe: it uses derived benchmark statistics and does not bundle raw commercial lyric text.


A beta-ready Flask app for rap lyric editing, rhyme highlighting, beat-aware bar suggestions, static snapshot analysis, synchronous one-sentence feedback, live async line fixing, information-theoretic lyric stats, real-rapper benchmark comparison, beat+lyric song rendering, and tester feedback capture. This build refactors beat decoding/analysis into a separate audio backend layer with transparent diagnostics for failed uploads, and adds sentence meter/stress scansion for rap delivery.

This version is intended for publishing online to a small beta group. It keeps the core creative features from the previous app and adds production entrypoints, invite-code access, upload limits, health checks, privacy pages, and deployment configuration.

## What is new for beta publishing

- Production WSGI entrypoint: `wsgi.py`
- Gunicorn server config: `gunicorn.conf.py`
- Dockerfile for reliable audio dependencies
- `Procfile`, `render.yaml`, and `railway.json`
- Optional invite-code gate with `BETA_ACCESS_CODE`
- Health and readiness routes: `/healthz`, `/readyz`
- Security headers and no-index beta behavior
- Server-side upload and lyric-length limits
- Runtime cleanup for old async jobs and beat uploads
- Derived real-rapper comparison profiles for cadence/rhyme benchmarking
- Synchronous Sentence Lab for fixing one sentence/thought at a time with immediate feedback
- Song Render Lab that overlays real speech TTS vocals on an uploaded beat and outputs downloadable WAV files
- Refactored beat-analysis stack with separate decoder diagnostics for `librosa`, `soundfile`, `ffmpeg`, and basic WAV fallback
- Meter / Stress analysis tab with scansion, likely stressed syllables, weak pickups, dominant foot patterns, pulse-grid placement, and landing-stress diagnostics
- New `/api/beat/diagnostics` endpoint and in-app diagnostics panel for failed beat uploads
- Lightweight per-IP API rate limiting
- In-app beta feedback form
- Feedback storage in `runtime_data/beta_feedback.jsonl`
- Admin feedback export with `BETA_ADMIN_TOKEN`
- Privacy and terms pages
- `.env.example`, `.gitignore`, and `.dockerignore`
- Compiled corpus profile so the beta can run without publishing the raw RTF lyric file

## Core rap editing features

- Static Snapshot first view
- Separate Live Preview view
- Separate Sentence Lab view with immediate `/api/sentence/analyze` feedback
- Rhyme-highlighted lyric source
- Per-line breakdown and suggestions
- One-sentence cadence, meter/stress, rhyme, information, bar-structure, word-bank, rewrite, and reference-benchmark feedback
- Possible word banks per line
- Beat upload and beat-aware bar-structure suggestions
- Explicit beat decoder report: selected backend, attempted backends, waveform preview, sample rate, warnings, and upload guidance
- Beat + lyric rendering: current lyrics + uploaded beat → mix WAV, vocal stem WAV, and timing JSON; Auto refuses to render when real speech TTS is unavailable instead of silently producing buzzy guide audio
- Information-theoretic stats for rhymes, lines, bars, and verses
- Stress-density, meter-consistency, dominant-meter, final-landing-stress, weak-run, and stress-cluster stats
- Corpus DNA from `data/corpus_profile.json`

## Run locally on Mac

```bash
unzip nmc_meter_stress_lab.zip
cd rap_meter_stress_lab
./run_mac.sh
```

Or manually:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## Local beta-gate test

```bash
cp .env.example .env
```

Edit `.env` and set at least:

```text
APP_ENV=production
SECRET_KEY=a-long-random-secret
BETA_ACCESS_CODE=test-code-123
BETA_ADMIN_TOKEN=another-random-admin-token
```

Then export the variables before running, for example:

```bash
set -a
source .env
set +a
python app.py
```

## Production environment variables

Required for a private beta:

```text
APP_ENV=production
SECRET_KEY=<long random value>
BETA_ACCESS_CODE=<invite code for testers>
```

Recommended:

```text
BETA_ADMIN_TOKEN=<admin token for feedback export>
PUBLIC_BASE_URL=https://your-public-beta-url
MAX_UPLOAD_MB=80
MAX_TEXT_UPLOAD_MB=5
MAX_BEAT_UPLOAD_MB=80
MAX_LYRICS_CHARS=120000
MAX_SENTENCE_CHARS=1600
MAX_RENDER_SECONDS=240
MAX_SONG_RENDER_LINES=96
SONG_TTL_SECONDS=7200
MAX_RENDERS=40
OUTPUT_DIR=runtime_renders
NMC_TTS_BACKEND=auto  # auto = real speech only; built_in = buzzy timing guide only
RATE_LIMIT_PER_MINUTE=90
WEB_CONCURRENCY=1
GUNICORN_THREADS=4
GUNICORN_TIMEOUT=180
NMC_PROFILE_PATH=data/corpus_profile.json
NMC_EXPOSE_CORPUS_SAMPLES=0
```

## Start command for most hosts

```bash
gunicorn wsgi:app --config gunicorn.conf.py
```

The beta uses in-memory jobs, beat IDs, and render IDs. Keep `WEB_CONCURRENCY=1` unless you move job/beat/render state to Redis or a database.

## Docker

Build:

```bash
docker build -t nmc-beta-rap-lab .
```

Run:

```bash
docker run --rm -p 5000:5000 \
  -e APP_ENV=production \
  -e SECRET_KEY='replace-me-with-a-long-secret' \
  -e BETA_ACCESS_CODE='test-code-123' \
  nmc-beta-rap-lab
```

Open:

```text
http://127.0.0.1:5000
```

## Render deployment

This package includes a Docker-based `render.yaml`. The Docker build installs `ffmpeg`, `libsndfile1`, and `espeak-ng`, which helps with MP3/M4A/FLAC beat analysis and Linux server-side TTS rendering.

1. Push this folder to GitHub.
2. Create a new Render Blueprint from the repository, or create a Web Service from the repo and let Render use the Dockerfile.
3. Set `BETA_ACCESS_CODE` and `BETA_ADMIN_TOKEN` as secret environment variables.
4. Deploy.
5. Check:

```text
https://your-app.onrender.com/healthz
https://your-app.onrender.com/readyz
```

## Railway deployment

1. Push this folder to GitHub.
2. Create a Railway project from the repo.
3. Railway can use the included Dockerfile and `railway.json`.
4. Add the production environment variables.
5. Verify `/healthz` after deployment.

## Feedback collection

Tester feedback is stored here:

```text
runtime_data/beta_feedback.jsonl
```

Post feedback:

```http
POST /api/feedback
POST /api/beta/feedback
```

Export latest feedback as admin:

```bash
curl -H "X-Admin-Token: $BETA_ADMIN_TOKEN" https://your-app.example/api/admin/feedback
```


## Live Rhyme Writer repair

This build fixes the live rhyme sidecar and adds route diagnostics. The issue in the previous build was a front-end state bug: `liveRhymeSequence` was not initialized, so browser polling treated every async result as stale and never rendered the returned rhyme payload.

The editor now has:

- an async rhyme sidecar inside the same writing template
- a manual **Run async rhyme** button
- a **Sync fallback** button that returns rhyme suggestions immediately if async polling fails
- a **Test routes** button that checks the live-rhyme route manifest
- active-line rhyme diagnostics
- a line-by-line rhyme map with clickable line tiles
- ranked landing buttons that can replace the active line ending

Live rhyme routes:

```http
POST /api/live-rhyme-job
POST /api/rhyme/live-job
GET  /api/live-rhyme/job/<job_id>
GET  /api/rhyme/live-job/<job_id>
GET  /api/live-rhyme/status/<job_id>
POST /api/live-rhyme/sync
POST /api/live-rhyme
POST /api/rhyme/live
GET  /api/live-rhyme/routes
```

The route accepts `lyrics`, `text`, `draft`, or `content` for the draft body and `active_line`, `line_number`, `line`, or `cursor_line` for the active row.

## API routes

```http
GET  /healthz
GET  /readyz
GET  /privacy
GET  /terms
GET  /api/meta
POST /api/snapshot
POST /api/information-theory
POST /api/static-breakdown
POST /api/sentence/analyze
POST /api/sentence
GET  /api/song/tts-status
POST /api/song/test-voice
POST /api/song/timing
POST /api/song/render
POST /api/render-song
GET  /renders/<filename>
POST /api/suggest-job
GET  /api/job/<job_id>
POST /api/live-rhyme-job
POST /api/rhyme/live-job
GET  /api/live-rhyme/job/<job_id>
POST /api/live-rhyme/sync
GET  /api/live-rhyme/routes
POST /api/line-fix
POST /api/beat/upload
GET  /api/beat/<beat_id>
GET  /api/beat/diagnostics
POST /api/meter/analyze
POST /api/meter/sentence
POST /api/analyze
GET  /api/corpus
GET  /api/comparison/profiles
POST /api/comparison
GET  /api/rhyme/<word>
POST /api/feedback
GET  /api/admin/feedback
```

## Beat analysis diagnostics

The beat-analysis path is now factored into:

- `beat_audio.py`: audio loading, decoder attempts, backend status, waveform preview
- `beat_engine.py`: BPM/grid detection, energy bars, drop windows, and lyric-to-bar guidance
- `song_engine.py`: song rendering now reuses the same beat-audio loader so rendering and analysis agree on decoder behavior

Use the **Run decoder diagnostics** button in the **Beat + Bars** tab, or call:

```http
GET /api/beat/diagnostics
```

If MP3/M4A uploads fail locally, install `ffmpeg` or upload a WAV export. For hosted beta deployment, use the included Dockerfile because it installs `ffmpeg`, `libsndfile1`, and `espeak-ng`.

## Song Render Lab

The Song Render Lab creates rough beta audio from the current lyric draft and the uploaded beat:

```http
GET  /api/song/tts-status
POST /api/song/test-voice
POST /api/song/timing
POST /api/song/render
POST /api/render-song
GET  /renders/<filename>
```

Render output includes:

- a mixed WAV with beat + generated vocal
- a vocal-stem WAV
- a timing JSON file showing line-to-bar placement

Available TTS backends:

- `auto`: real speech only. It tries `espeak-ng` / `espeak`, then macOS `say`; if neither works, it returns an error instead of making buzz.
- `espeak`: uses `espeak-ng` / `espeak` when installed, useful for Linux Docker hosting.
- `mac_say`: uses macOS `say` when running locally on a Mac.
- `built_in`: explicit synthetic timing guide. It is buzzy by design and is not speech.

Use **Test speech voice** in the Song Render tab before rendering a full mix. If that voice test fails on a hosted beta, deploy with the included Dockerfile or install `espeak-ng`, `ffmpeg`, and `libsndfile1` on the host.

The rendered vocal is a beta guide track for pocket, line length, and rhyme landing. It is not meant to clone or impersonate real artists and should be replaced with a recorded vocal for release-quality songs. The fixed renderer no longer hides TTS failures behind the built-in buzzy oscillator.

Example after a beat upload returns `beat_id`:

```json
{
  "lyrics": "Core to surface, I convert the verse",
  "beat_id": "uploaded-beat-id",
  "tts_backend": "auto",
  "voice_preset": "neutral",
  "rap_intensity": "balanced",
  "intro_bars": 1,
  "outro_bars": 1,
  "beat_gain_db": -3.5,
  "vocal_gain_db": 1.5,
  "ducking": 0.18,
  "loop_beat": true
}
```

## Meter / Stress analysis

The app now analyzes sentence meter and likely stress placement in two places:

- The **Sentence Lab** shows syllable-level stress marks for the active sentence, word-level stress anchors, dominant foot tendency, weak pickups, final landing strength, and a four-beat pulse grid.
- The **Static Snapshot** and **Meter / Stress** tab summarize the entire draft with stress density, meter consistency, final-landing stress percentage, long weak runs, stress clusters, and line-by-line stress patterns.

New endpoints:

```http
POST /api/meter/analyze
POST /api/meter/sentence
```

Example:

```json
{
  "sentence": "Every sentence I am inventing has resonance on the beat",
  "beat_id": "optional-uploaded-beat-id"
}
```

The meter engine uses the optional `pronouncing`/CMUdict package when installed and falls back to a deterministic rap-focused heuristic when it is unavailable. This is a performance guide, not a perfect linguistic scansion model. Always verify the final stress pattern by rapping along to the beat.


## Synchronous Sentence Lab

The Sentence Lab is separate from the async live editor. It is meant for one active thought at a time:

```http
POST /api/sentence/analyze
POST /api/sentence
```

Example JSON body:

```json
{
  "sentence": "The sentence is present with resonance in the system",
  "coach_mode": "match",
  "beat_id": "optional-uploaded-beat-id"
}
```

It returns immediate feedback with sentence metrics, syllable/bar fit, meter/stress scansion, rhyme key, rhyme highlights, internal echoes, corpus-information bits, reference-benchmark guidance, word banks, rewrite options, and applyable patches. You can also pass `lyrics` plus `cursor_index` instead of `sentence`; the server extracts the active sentence synchronously.


## Important beta notes

- Runtime uploads and feedback are local to the server unless your host provides persistent disk storage.
- Beat detection is approximate. Confirm the BPM/bar grid in your DAW before recording.
- The app does not call an external AI API. Suggestions are generated by local deterministic Python logic and the compiled corpus profile.
- Do not commit `.env`, `runtime_uploads/`, `runtime_data/`, or raw private lyric files to GitHub.


## Reference benchmark profiles

This beta includes `data/comparison_profiles.json`, generated from the supplied comparison file as derived statistics only. It stores cadence windows, rhyme entropy, rhyme-key distributions, internal-rhyme density, and benchmark coaching moves. It does **not** include raw reference lyric lines.

New endpoints:

```text
GET  /api/comparison/profiles
POST /api/comparison
```

Use these profiles to compare a user draft against measurable reference styles, not to reproduce or imitate copyrighted lyrics.

To rebuild comparison profiles from private source files, create a manifest JSON outside the public repo and run:

```bash
python tools/build_comparison_profiles.py --manifest /secure/private/comparison_manifest.json --output data/comparison_profiles.json
```

The builder reads private text files and writes only derived statistics into the app package.

## Scansion Physics Lab

This build adds a notebook-derived **Scansion Physics** layer. The uploaded notebook image is included at `static/reference/scansion_notebook.jpg` and its interpreted model is stored at `data/notebook_scansion_model.json`.

New analysis concepts:

- `ΔC` — cadence delta from the previous line: syllable change, stress change, bar-span change, and rhyme-family change.
- `F` — accent force: stress weight plus content-word and rhyme-landing weight.
- `τ` — torsion/syncopation: how far stressed syllables twist from the strong-beat grid.
- `Ω` — spin: repeated phonetic motion from internal rhyme, alliteration, and repeated rhyme-family pressure.
- `θ` — beat phase inside the `1 e & a 2 e & a 3 e & a 4 e & a` grid.
- `β` — assigned bar or bar range.
- `γ` — rhyme family.
- `σ` — syllable event.

New endpoints:

```http
POST /api/physics/analyze
POST /api/physics/sentence
```

The static snapshot, live preview, and sentence lab now include scansion physics data. The Scansion Physics tab renders the notebook reference image, symbol legend, force/torsion/spin summary, cadence-delta map, compression/release sequences, phonetic skeleton matches, and line-by-line phase grids.


## System-wide scoring and edit comparison

This build adds a deterministic score engine for the entire rap, every section, and every bar/line. The score combines corpus style match, rhyme power, cadence fit, beat-aware bar structure, meter/stress strength, Scansion Physics force/torsion/spin, content clarity, and derived reference-benchmark fit.

New endpoints:

```http
POST /api/score
POST /api/score/rap
POST /api/score/compare-edits
POST /api/compare-edits
```

The **Scores / Edit Compare** tab lets beta users capture a baseline draft, score the current draft, and compare edits bar by bar. The comparison report shows global score delta, component deltas, changed bars, top gains, top losses, and a keep/revise recommendation. Static Snapshot and Live Preview now also surface the system-wide rap score and individual bar scores.

## Visualization, export, and revision-diff tools

This build adds the full visualization/export layer:

- Chart.js-powered radar and bar/timeline charts, with SVG/CSS fallbacks when the CDN is unavailable.
- Bar-by-bar timeline views for static snapshots and score reports.
- Edit-delta timeline charts for baseline-vs-edit comparisons.
- Downloadable CSV reports for snapshots, scores, and edit comparisons.
- Downloadable PDF reports generated server-side with ReportLab.
- Highlighted before/after lyric diff view, including added, deleted, changed, and unchanged lines.

New endpoints:

```http
POST /api/report/pdf
POST /api/report/csv
```

Examples:

```json
{
  "kind": "score",
  "lyrics": "your draft here",
  "coach_mode": "match",
  "beat_id": "optional-uploaded-beat-id"
}
```

```json
{
  "kind": "compare",
  "original_lyrics": "baseline draft",
  "edited_lyrics": "edited draft",
  "coach_mode": "match"
}
```

PDF export requires `reportlab`, which is included in `requirements.txt`.

## Sentence Pattern Compare Lab

This build adds a separate sentence-level rhyme-structure comparison workspace. Put each sentence or candidate bar on its own line, then run **Compare patterns**. The app now compares:

- end-rhyme family similarity,
- internal rhyme/echo placement,
- tail stress compatibility,
- alliteration and consonance density,
- syllable-shape distance,
- pairwise sentence-pattern similarity.

New endpoints:

```http
POST /api/sentence/compare-patterns
POST /api/sentence-patterns
POST /api/patterns/sentences
```

Example payload:

```json
{
  "text": "Every sentence I invent has resonance\nThe method in the message bends with evidence",
  "coach_mode": "match",
  "max_sentences": 16
}
```

The response includes `sentences`, `pairwise`, `best_pairs`, `pattern_blueprints`, and sentence-level `rewrite_suggestions`. The feature uses compiled corpus/profile data and does not require shipping raw reference lyrics.

## Live Rhyme Writer

This build adds a same-template live writing environment inside the main editor. As the user types, the editor submits a lightweight background rhyme job to `/api/live-rhyme-job`; the sidebar polls `/api/live-rhyme/job/<job_id>` and refreshes active-line rhyme banks, ranked rhyme options, scheme repairs, and applyable rhyme patches without blocking the text box.

The live rhyme sidecar uses the existing compiled corpus profile and the advanced rhyme engine, so it can suggest perfect rhymes, slants, assonance, consonance, stress-matched words, multi-syllable landings, internal echoes, and draft-level scheme repair while the user keeps writing.

### Fixed live-rhyme async + highlighted-word rhyme search

This build hardens the live rhyme sidecar in two ways:

1. Long drafts are clipped around the active line for live analysis, so the async sidecar stays responsive even when the full notebook draft is large. Static Snapshot still analyzes the full draft.
2. Highlight or double-click any word in the editor, then click **Analyze highlighted word**. The app starts a separate async job for similar rhymes and renders family rhymes, slants, stress matches, internal echoes, and multi-syllable landing phrases in the same live-writing sidebar.

New selected-word endpoints:

```http
POST /api/rhyme-word-job
POST /api/rhyme/word-job
POST /api/live-rhyme/word-job
GET  /api/rhyme-word/job/<job_id>
GET  /api/rhyme/word-job/<job_id>
GET  /api/live-rhyme/word/status/<job_id>
POST /api/rhyme-word/sync
POST /api/live-rhyme/word
GET  /api/rhyme-word/routes
```

Example selected-word async payload:

```json
{
  "word": "diction",
  "line_text": "The expression is in the direction of the diction",
  "lyrics": "The expression is in the direction of the diction\nThe present presence corrects the sentence",
  "active_line": 1,
  "coach_mode": "match",
  "selection_start": 43,
  "selection_end": 50
}
```

## Live Rhyme Writer stable v3

This build hardens the same-template live rhyme writer so it should not keep flashing error states while the user types.

Changes:

- The live sidecar now analyzes a clipped context around the cursor instead of posting an entire long draft on every keystroke.
- Live-rhyme polling routes are exempt from the broad beta API rate limiter because they poll frequently by design.
- `/api/live-rhyme/sync` and `/api/live-rhyme-job` now use a safe fallback result if the advanced rhyme engine throws an exception.
- The broad live coaching job no longer auto-runs on every keystroke; full live coaching is manual, while rhyme suggestions stay async.
- The UI parses non-JSON route failures safely and falls back to synchronous rhyme analysis instead of leaving the sidecar in an error state.
- A new health check route verifies the live rhyme engine quickly:

```http
GET /api/live-rhyme/health
```

Highlighted-word workflow:

1. Highlight or double-click a word inside the editor.
2. The app starts an async selected-word rhyme job.
3. The side panel shows similar rhymes, slants, stress-compatible options, and multi-syllable landings.
4. Click a suggestion to replace the highlighted word in the editor.

Highlighted-word routes:

```http
POST /api/rhyme-word-job
GET  /api/rhyme-word/job/<job_id>
POST /api/rhyme-word/sync
POST /api/live-rhyme/word
```

Live-rhyme routes:

```http
POST /api/live-rhyme-job
GET  /api/live-rhyme/job/<job_id>
POST /api/live-rhyme/sync
GET  /api/live-rhyme/routes
GET  /api/live-rhyme/health
```

## Live Rhyme Writer static-line-analysis upgrade

This build upgrades the same-template Live Rhyme Writer so the active-line panel now carries the same major line-analysis elements used by Static Snapshot, while still running asynchronously in the sidebar.

New live sidecar content:

- active-line Static Snapshot payload under `live_static_analysis.active_line`
- rhyme-highlighted line rendering
- syllables, word count, end word, rhyme key, information bits, rhyme surprise
- cadence, sound, content, rhyme, and bar-structure diagnosis
- meter/stress scansion and suggestions
- Scansion Physics force/torsion/spin/ΔC data
- bar score, grade, issues, and advice
- reference-benchmark line note
- action steps and checklist
- advanced rhyme options
- possible word banks
- applyable rewrites and patches
- nearby line context from the clipped live window

To keep the live writer stable, the full Static Snapshot view still analyzes the complete draft on demand. The live sidecar analyzes a small cursor-centered context and builds a static-style active-line payload from that context, then shifts line numbers back to the source draft so jump/apply buttons target the correct line.

The live rhyme response now includes:

```json
{
  "live_static_analysis": {
    "available": true,
    "report_type": "live_static_line_analysis",
    "active_line": {},
    "nearby_lines": [],
    "snapshot_elements": []
  },
  "active_report": {
    "static_line_analysis": {}
  }
}
```

Useful tuning variables for hosted beta:

```text
LIVE_RHYME_MAX_CHARS=2600
LIVE_RHYME_CONTEXT_RADIUS=6
LIVE_STATIC_LINE_CONTEXT_RADIUS=2
LIVE_STATIC_LINE_MAX_CHARS=1600
```


## PythonAnywhere quick deploy

Use `requirements-pythonanywhere.txt` and copy `pythonanywhere_wsgi.py` into the WSGI file in the PythonAnywhere Web tab. This build defaults the Live Rhyme Writer to an inline-complete async model on PythonAnywhere so the UI no longer depends on background threads or a poll request hitting the same worker process. Full instructions are in `PYTHONANYWHERE_SETUP.md`.

Health and diagnostic routes:

```http
GET /healthz
GET /readyz
GET /api/pythonanywhere/diagnostics
GET /api/live-rhyme/health
```


## Live Rhyme Writer direct mode

This build uses direct live mode for the Live Rhyme Writer. The browser still sends asynchronous `fetch()` requests while the user types, but the server completes `/api/live-rhyme-job` and `/api/rhyme-word-job` inside the initial POST response. The UI no longer needs polling to get a result, which prevents PythonAnywhere/WSGI deployments from getting stuck on `queued`.

Useful checks after deployment:

```text
/api/live-rhyme/health
/api/live-rhyme/routes
/api/live-rhyme-job
/api/rhyme-word-job
```

A successful `/api/live-rhyme-job` response should have:

```json
{ "status": "complete", "engine": "direct", "no_poll_required": true, "result": { "available": true } }
```


## Live Rhyme Writer refactor v8

The Live Rhyme Writer has been refactored to use a queue-free fast core. The most reliable page is:

```text
/live-writer
```

That standalone route uses only these direct endpoints and does not depend on background workers, thread pools, in-memory queues, or polling:

```http
POST /api/live-writer/analyze
POST /api/live-writer/word
GET  /api/live-writer/health
```

The older compatibility routes still exist, but they now complete inside the request:

```http
POST /api/live-rhyme/sync
POST /api/live-rhyme-job
POST /api/rhyme-word/sync
POST /api/rhyme-word-job
```

On PythonAnywhere, after uploading this build, click **Reload** in the Web tab and hard-refresh the browser. If the main app still shows stale queue messages, open `/live-writer`; it ships with inline JavaScript so it cannot use an old cached `static/app.js`.

## Queue-free Live Rhyme Writer refactor

This build includes a refactored Live Rhyme Writer that avoids PythonAnywhere queue/polling problems.

Use this page first on hosted deployments:

```text
/live-writer
```

The page uses inline JavaScript and direct endpoints, so it does not rely on stale cached `app.js`, background threads, in-memory job queues, or cross-worker polling.

Direct routes:

```http
POST /api/live-writer/analyze
POST /api/live-writer/word
GET  /api/live-writer/health
```

Compatibility routes still exist but now complete immediately:

```http
POST /api/live-rhyme/sync
POST /api/live-rhyme-job
GET  /api/live-rhyme/job/<job_id>
POST /api/rhyme-word/sync
POST /api/rhyme-word-job
GET  /api/rhyme-word/job/<job_id>
```

Every compatibility POST returns `status: complete`, `poll_required: false`, and `no_poll_required: true` when applicable.

## User accounts and saved raps

This build includes built-in login, registration, and saved rap storage.

Routes:

```http
GET  /login
POST /login
GET  /register
POST /register
POST /logout
GET  /api/auth/me
POST /api/auth/login
POST /api/auth/register
POST /api/auth/logout
GET  /api/raps
POST /api/raps
GET  /api/raps/<rap_id>
PATCH /api/raps/<rap_id>
DELETE /api/raps/<rap_id>
POST /api/raps/<rap_id>/duplicate
GET  /api/account/diagnostics
```

The account system uses SQLite through `user_store.py`. By default the database is created at:

```text
runtime_data/user_raps.sqlite
```

Set this environment variable to move it:

```bash
export RAP_DB_PATH=/home/YOURUSERNAME/rap_score_compare_lab/runtime_data/user_raps.sqlite
```

For production hosting, set a stable `SECRET_KEY`. Changing `SECRET_KEY` logs users out because Flask session cookies can no longer be verified.

```bash
export SECRET_KEY="replace-with-a-long-random-secret"
```

The UI has an **Account / Saved Raps** tab. Users can create an account, save the current editor draft, update a selected saved rap, load a saved rap back into the editor, duplicate a saved rap, and delete a saved rap.

## 2026.07 highlighted-word rhyme fix

This build fixes the highlighted-word rhyme workflow in the main editor and the standalone `/live-writer` page.

- The selected/highlighted word range is now the source of truth for the rhyme request.
- If the user accidentally highlights punctuation or multiple words, the app chooses the best word token inside the selection.
- Clicking a highlighted rhyme token in the Static Snapshot or Live Rhyme sidecar now opens the same highlighted-word suggestion panel.
- Clicking a suggested rhyme now replaces the highlighted word, not the whole line ending, in the standalone live writer.
- The selected-word endpoints return a helpful JSON message instead of a hard HTTP error when no word is selected.
- The rhyme key logic now uses corpus/profile suffix neighborhoods, improving suggestions for families like surface/service/purpose/universe, diction/friction/direction, and music/lyric.


## Saved Rap Suite v12

The account system now supports a full saved-rap library:

- User registration, login, and logout.
- Save as new, update selected rap, and manual checkpoints.
- Automatic version history for each saved rap.
- Restore any saved version back into the editor.
- Tags, notes, pinned raps, and archived raps.
- Library stats: total saved raps, versions, words, lines, and top tags.
- Search and sorting by recent update, creation date, title, score, or length.
- JSON export/import of the user's library.
- Compare a saved rap against the current editor draft.

Important routes:

```http
GET  /api/raps
POST /api/raps
GET  /api/raps/stats
GET  /api/raps/export
POST /api/raps/import
GET  /api/raps/<rap_id>/versions
POST /api/raps/<rap_id>/versions
GET  /api/raps/<rap_id>/versions/<version_id>
POST /api/raps/<rap_id>/versions/<version_id>/restore
POST /api/raps/<rap_id>/pin
POST /api/raps/<rap_id>/archive
```

On PythonAnywhere, keep `RAP_DB_PATH` pointed at a persistent path, for example:

```bash
export RAP_DB_PATH=/home/YOURUSERNAME/rap_score_compare_lab/runtime_data/user_raps.sqlite
mkdir -p /home/YOURUSERNAME/rap_score_compare_lab/runtime_data
```

## Highlighted-word rhyme fix

This build includes a stricter highlighted-word rhyme engine (`highlighted_rhyme_engine.py`). The selected-word panel no longer treats a loose spelling suffix as a rhyme. It now scores the highlighted word against candidate words by phonetic tail, final vowel, final consonant, syllable fit, and corpus-style slant families.

The highlighted-word panel separates:

- clean family / end rhymes
- corpus style slants
- near / slant rhymes
- multi-syllable landings
- internal echoes

The main route is still:

```http
POST /api/live-writer/word
```

Compatibility routes also use the strict engine:

```http
POST /api/rhyme-word/sync
POST /api/live-rhyme/word
POST /api/rhyme-word-job
```


## Broad rhyme families and highlighted phrase rhymes

The Live Rhyme Writer now supports both highlighted words and highlighted phrases.

New/updated routes:

```http
POST /api/live-writer/word
POST /api/live-writer/phrase
POST /api/rhyme-phrase/sync
POST /api/live-rhyme/phrase
```

The rhyme classifier separates suggestions into:

- perfect / clean family rhymes
- corpus style slants
- broad rap families
- near/slant rhymes
- assonance and consonance
- phrase-preserving replacements
- suggestive phrase-family rewrites

Highlighting a phrase such as `core to surface` returns phrase-level replacements like frame-preserving landings and broader phrase-family responses, while still showing the target landing word and its phonetic rhyme classification.
