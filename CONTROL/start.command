#!/usr/bin/env bash
set -Eeuo pipefail

CONTROL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$CONTROL_DIR"
export JUICE_CONTROL_ROOT="${JUICE_CONTROL_ROOT:-${CONTROL_DIR}}"

# Finder-launched .command files do not always inherit the user's shell PATH.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin:${PATH:-}"

DATA_DIR="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
mkdir -p \
  "${DATA_DIR}/CREATIVE" \
  "${DATA_DIR}/BUILD/Repos" \
  "${DATA_DIR}/CAPTURE"

chmod +x "${CONTROL_DIR}/server.py" "${CONTROL_DIR}"/scripts/*.sh 2>/dev/null || true

if ! command -v python3 >/dev/null 2>&1; then
  printf 'JUICE Control needs python3. Install Command Line Tools or Homebrew Python, then run this again.\n' >&2
  exit 127
fi

exec python3 "${CONTROL_DIR}/server.py"
