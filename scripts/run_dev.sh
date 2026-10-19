#!/usr/bin/env bash
# Bootstrap + run the AI Photo Enhancer dev server.
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "Creating virtual environment (Python 3.12 required)…"
  if command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv .venv
  else
    python3 -m venv .venv
  fi
fi

"$PY" - <<'PY' || { echo "ERROR: Django 5 needs Python 3.10+ (found $("$PY" -V))."; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
PY

echo "Installing dependencies…"
"$PY" -m pip install -q -r requirements.txt

if [ ! -x bin/realesrgan-ncnn-vulkan ] && [ ! -x bin/realesrgan-ncnn-vulkan.exe ]; then
  echo "Downloading Real-ESRGAN engine…"
  "$PY" scripts/setup_realesrgan.py
fi

if [ ! -f db.sqlite3 ]; then
  echo "Running migrations…"
  "$PY" manage.py migrate
fi

echo "Starting http://127.0.0.1:8000/"
exec "$PY" manage.py runserver
