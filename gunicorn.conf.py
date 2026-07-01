"""Gunicorn config for the NMC beta Flask app.

The app uses in-memory async jobs and beat IDs, so the beta profile intentionally
uses one worker process with multiple threads. Move jobs/beats to Redis or a
database before scaling past one process.
"""
import multiprocessing
import os

bind = f"0.0.0.0:{os.getenv('PORT', '5000')}"
workers = int(os.getenv("WEB_CONCURRENCY", "1"))
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "180"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
preload_app = False

# Safety guard: this app stores jobs/uploads in memory during beta.
if workers > 1 and os.getenv("ALLOW_MULTI_WORKER", "0") != "1":
    workers = 1
