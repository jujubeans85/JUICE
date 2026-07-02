#!/usr/bin/env bash
set -Eeuo pipefail

CONTROL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$CONTROL_DIR"

# Finder-launched .command files do not always inherit the user's shell PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin:${PATH:-}"

mkdir -p \
  "${HOME}/JUICE_DATA/CREATIVE" \
  "${HOME}/JUICE_DATA/BUILD/Repos" \
  "${HOME}/JUICE_DATA/CAPTURE"

chmod +x "${CONTROL_DIR}/server.py" "${CONTROL_DIR}"/scripts/*.sh 2>/dev/null || true

HOST="${JUICE_CONTROL_HOST:-127.0.0.1}"
PORT="${JUICE_CONTROL_PORT:-8765}"
URL="http://${HOST}:${PORT}/"

if command -v curl >/dev/null 2>&1 && curl -fsS "${URL}health" >/dev/null 2>&1; then
  open "${URL}" >/dev/null 2>&1 || true
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  printf 'JUICE Control needs python3. Install Command Line Tools or Homebrew Python, then run this again.\n' >&2
  exit 127
fi

exec python3 "${CONTROL_DIR}/server.py"
