#!/usr/bin/env bash
# AI Photo Enhancer — one-command setup & start (macOS / Linux)
# Usage:  ./start.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "==> AI Photo Enhancer"

# Always use the project venv (Python 3.12), never the system/shell python.
if [ ! -x .venv/bin/python ]; then
  echo "==> Creating .venv with Python 3.12…"
  if [ -x /opt/homebrew/bin/python3.12 ]; then
    /opt/homebrew/bin/python3.12 -m venv .venv
  elif command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv .venv
  else
    echo "ERROR: Python 3.12 not found. Install it:  brew install python@3.12"; exit 1
  fi
fi

PY=.venv/bin/python
echo "==> Using $($PY -V)"

"$PY" - <<'PY' || { echo "ERROR: need Python 3.10+ (Django 5)."; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
PY

echo "==> Installing dependencies…"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt

if [ ! -x bin/realesrgan-ncnn-vulkan ]; then
  echo "==> Downloading Real-ESRGAN engine…"
  "$PY" scripts/setup_realesrgan.py
fi

if [ ! -f .env ]; then
  echo "==> Creating .env…"
  cp .env.example .env
fi

echo "==> Applying migrations…"
"$PY" manage.py migrate --noinput

echo "==> Starting http://127.0.0.1:8000/   (Ctrl+C to stop)"
exec "$PY" manage.py runserver
