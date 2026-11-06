#!/bin/bash
set -eu
cd "$(dirname "$0")"
PYTHON="$PWD/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  python3 -m venv .venv
  "$PYTHON" -m pip install -r requirements.txt
fi
"$PYTHON" -m coverage run -m pytest -q
"$PYTHON" -m coverage report -m
printf '\nНажмите Enter, чтобы закрыть окно...'
read -r reply
