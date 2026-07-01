#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "Note: ffmpeg is not installed. WAV beat uploads should work; MP3/M4A may fail unless librosa/audioread can decode them."
  echo "On macOS, install with: brew install ffmpeg"
fi
python app.py
