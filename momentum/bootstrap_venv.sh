#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=python3.12
VENV="$APP_DIR/.venv"

echo "[bootstrap] Using APP_DIR=$APP_DIR"

# 0) sanity: correct user?
if [[ "$(id -un)" != "snapdiscounts" ]]; then
  echo "[bootstrap] ERROR: run this as user 'snapdiscounts' (not root)"
  exit 1
fi

# 1) check python version
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "[bootstrap] ERROR: $PY not found. Ask root to: apt update && apt install -y python3.12-venv python3.12-dev build-essential"
  exit 1
fi

# 2) (re)create venv if missing
if [[ ! -x "$VENV/bin/python" ]]; then
  echo "[bootstrap] Creating venv at $VENV"
  "$PY" -m venv "$VENV"
fi

# 3) activate
# shellcheck disable=SC1090
source "$VENV/bin/activate"

# 4) upgrade toolchain
python -m pip install -U pip setuptools wheel build

# 5) install runtime deps (explicit) then the package editable
echo "[bootstrap] Installing runtime requirements"
python -m pip install -r "$APP_DIR/requirements.txt"

echo "[bootstrap] Editable install of momentum"
python -m pip install -e "$APP_DIR"

# 6) freeze full lock for reproducibility
echo "[bootstrap] Writing requirements.lock.txt"
python -m pip freeze > "$APP_DIR/requirements.lock.txt"

# 7) smoke test
echo "[bootstrap] Running probe"
python -m momentum.l4_cli.probe_env || true

echo "[bootstrap] Done."
