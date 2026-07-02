"""PythonAnywhere WSGI template for NMC Live Rhyme Writer.

Copy the contents of this file into the WSGI file linked from the
PythonAnywhere Web tab, then replace YOURUSERNAME with your PythonAnywhere
username and adjust PROJECT_DIR if you uploaded the app somewhere else.
"""
import os
import sys

USERNAME = "YOURUSERNAME"
PROJECT_DIR = f"/home/{USERNAME}/rap_score_compare_lab"

# PythonAnywhere-safe live mode: the browser still posts to async routes and
# does not poll for live rhyme output; live rhyme requests return completed
# results in the initial response so they do not depend on background threads.
os.environ.setdefault("APP_ENV", "production")
os.environ.setdefault("PYTHONANYWHERE_COMPAT", "1")
os.environ.setdefault("LIVE_RHYME_INLINE_JOBS", "1")
os.environ.setdefault("LIVE_RHYME_DIRECT_JOBS", "1")
os.environ.setdefault("ASYNC_JOB_MODE", "inline")
os.environ.setdefault("INLINE_GENERAL_ASYNC", "1")
os.environ.setdefault("MAX_UPLOAD_MB", "25")
os.environ.setdefault("MAX_BEAT_UPLOAD_MB", "25")
os.environ.setdefault("MAX_LYRICS_CHARS", "30000")
os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")
# Optional: set a private beta code. Leave blank for no gate.
# os.environ.setdefault("BETA_ACCESS_CODE", "your-beta-code")
# Keep SECRET_KEY stable so login sessions remain valid.
os.environ.setdefault("RAP_DB_PATH", f"/home/{USERNAME}/rap_score_compare_lab/runtime_data/user_raps.sqlite")
# os.environ.setdefault("SECRET_KEY", "replace-with-a-long-random-string")

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from app import app as application  # noqa: E402
