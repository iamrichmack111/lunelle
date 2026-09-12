#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q -r requirements.txt

echo "Checking Lunelle login..."
python app.py --self-test
echo "Starting Lunelle on http://127.0.0.1:5055"
exec python app.py
