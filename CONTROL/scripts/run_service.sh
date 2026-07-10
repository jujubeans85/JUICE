#!/usr/bin/env bash
set -Eeuo pipefail

CONTROL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin:${PATH:-}"
export JUICE_CONTROL_ROOT="${JUICE_CONTROL_ROOT:-${CONTROL_DIR}}"
export JUICE_DATA_ROOT="${DATA_ROOT}"
export JUICE_CONTROL_OPEN_BROWSER="${JUICE_CONTROL_OPEN_BROWSER:-0}"

mkdir -p \
  "${JUICE_DATA_ROOT}/CREATIVE" \
  "${JUICE_DATA_ROOT}/BUILD/Repos" \
  "${JUICE_DATA_ROOT}/CAPTURE" \
  "${JUICE_DATA_ROOT}/ADMIN" \
  "${JUICE_DATA_ROOT}/LOGS"

command -v python3 >/dev/null 2>&1 || {
  echo "JUICE Control needs python3." >&2
  exit 127
}

exec python3 "${CONTROL_DIR}/server.py"
