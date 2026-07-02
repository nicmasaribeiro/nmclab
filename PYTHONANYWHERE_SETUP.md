# PythonAnywhere setup for NMC Live Rhyme Writer

This build includes a PythonAnywhere-safe live-rhyme mode. The browser now uses direct asynchronous fetches for the Live Rhyme Writer, so no live-rhyme job should remain queued. The old job aliases still exist, but they also complete inside the initial POST response.

## 1. Upload and unzip

Upload the ZIP to PythonAnywhere, open a Bash console, then run:

```bash
cd ~
unzip nmc_pythonanywhere_live_rhyme_lab.zip
cd rap_score_compare_lab
```

## 2. Create a virtualenv

Use the same Python version that you select in the Web tab.

```bash
mkvirtualenv --python=/usr/bin/python3.13 nmc-rhyme-env
pip install -r requirements-pythonanywhere.txt
```

If your account cannot install `reportlab`, remove it from `requirements-pythonanywhere.txt`; only PDF export will be affected. Beat upload and song rendering require optional audio dependencies and may not work on every PythonAnywhere account.

## 3. Create the Web app

In the PythonAnywhere **Web** tab:

1. Add a new web app.
2. Choose **Manual configuration**.
3. Choose the same Python version you used for the virtualenv.
4. Set the virtualenv to something like:

```text
/home/YOURUSERNAME/.virtualenvs/nmc-rhyme-env
```

## 4. Configure the WSGI file

Open the WSGI file linked in the Web tab. Replace its Flask section with the contents of `pythonanywhere_wsgi.py`, then change:

```python
USERNAME = "YOURUSERNAME"
```

to your PythonAnywhere username.

The critical settings are:

```python
os.environ.setdefault("PYTHONANYWHERE_COMPAT", "1")
os.environ.setdefault("LIVE_RHYME_INLINE_JOBS", "1")
os.environ.setdefault("LIVE_RHYME_DIRECT_JOBS", "1")
os.environ.setdefault("ASYNC_JOB_MODE", "inline")
os.environ.setdefault("INLINE_GENERAL_ASYNC", "1")
```

## 5. Static files

In the Web tab, add this static file mapping:

```text
URL:       /static/
Directory: /home/YOURUSERNAME/rap_score_compare_lab/static
```

## 6. Reload and test

Click **Reload** in the Web tab, then visit:

```text
https://YOURUSERNAME.pythonanywhere.com/healthz
https://YOURUSERNAME.pythonanywhere.com/readyz
https://YOURUSERNAME.pythonanywhere.com/api/pythonanywhere/diagnostics
https://YOURUSERNAME.pythonanywhere.com/api/live-rhyme/health
```

In the app, open **Live Rhyme Writer**, click **PythonAnywhere check**, then click **Run async rhyme**.

## 7. Common fixes

### 502 / 504

Check the PythonAnywhere error log. The most common causes are an incorrect project path in the WSGI file, the wrong virtualenv, or missing dependencies.

### CSS/JS missing

Add the `/static/` mapping in the Web tab and reload the web app.

### Live rhyme job starts but poll says job not found

Make sure these are set in the WSGI file:

```python
os.environ.setdefault("LIVE_RHYME_INLINE_JOBS", "1")
os.environ.setdefault("LIVE_RHYME_DIRECT_JOBS", "1")
os.environ.setdefault("ASYNC_JOB_MODE", "inline")
```

This build uses `/api/live-rhyme/sync` for the live sidecar and returns completed results; the UI no longer depends on polling hitting the same worker process.

### Beat/song render not working

PythonAnywhere may not have ffmpeg/libsndfile/espeak installed. The lyric/rhyme analysis will still work. Use `optional_audio_requirements.txt` only if your account supports the native audio stack.


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

## Important: use the refactored writer page

After uploading this build and reloading the Web app, open:

```text
https://YOURUSERNAME.pythonanywhere.com/live-writer
```

This page is the queue-free writer. It uses inline JavaScript and direct request/response endpoints, so it avoids PythonAnywhere worker/queue issues and browser caching of old static JavaScript.

Quick tests after reload:

```text
/api/live-writer/health
/api/live-rhyme/health
/api/live-rhyme/routes
```

If the old full lab still shows a queued state, it is usually the browser serving cached static files. The `/live-writer` page avoids that problem.

## Login and saved raps on PythonAnywhere

This build stores accounts and saved raps in SQLite, so no external database is required for beta use.

Recommended environment variables in the PythonAnywhere Web tab or WSGI file:

```python
import os
os.environ.setdefault("SECRET_KEY", "replace-with-a-long-random-secret")
os.environ.setdefault("RAP_DB_PATH", "/home/YOURUSERNAME/rap_score_compare_lab/runtime_data/user_raps.sqlite")
os.environ.setdefault("LOGIN_REQUIRED_TO_SAVE", "1")
```

Make sure the directory exists and is writable:

```bash
mkdir -p /home/YOURUSERNAME/rap_score_compare_lab/runtime_data
```

After reload, open the app, go to **Account / Saved Raps**, create an account, then test:

```text
/api/account/diagnostics
/api/auth/me
```

Keep `SECRET_KEY` stable. If you change it, existing login sessions are invalidated, but saved raps remain in the SQLite database.


## Saved rap database

The saved-rap suite stores accounts, saved raps, tags, notes, pins, archives, and version history in SQLite. Use a persistent path:

```python
os.environ.setdefault("RAP_DB_PATH", "/home/YOURUSERNAME/rap_score_compare_lab/runtime_data/user_raps.sqlite")
os.environ.setdefault("SECRET_KEY", "replace-with-a-long-random-secret")
```

Create the folder from a PythonAnywhere Bash console:

```bash
mkdir -p /home/YOURUSERNAME/rap_score_compare_lab/runtime_data
```

After upload, reload the Web app and check:

```text
/api/account/diagnostics
```
