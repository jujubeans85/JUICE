#!/usr/bin/env bash
set -Eeuo pipefail
CONTROL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${CONTROL_DIR}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin:${PATH:-}"

ok=0
fail=0
check() {
  local label="$1"
  shift
  if "$@" >/tmp/juice-control-check.$$ 2>&1; then
    printf 'ok: %s\n' "${label}"
    ok=$((ok + 1))
  else
    printf 'fail: %s\n' "${label}"
    sed 's/^/  /' /tmp/juice-control-check.$$ || true
    fail=$((fail + 1))
  fi
  rm -f /tmp/juice-control-check.$$
}

check "python3 is available" command -v python3
check "server and intake compile" python3 -m py_compile "${CONTROL_DIR}/server.py" "${CONTROL_DIR}/audio_intake.py"
check "intake browser assets exist" test -f "${CONTROL_DIR}/intake.js"
check "intake markup exists" test -f "${CONTROL_DIR}/intake.html"
check "Zed can be reached" "${CONTROL_DIR}/scripts/open_in_zed.sh" --status
DATA_DIR="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
check "CREATIVE data folder exists" test -d "${DATA_DIR}/CREATIVE"
check "BUILD repos folder exists" test -d "${DATA_DIR}/BUILD/Repos"
check "CAPTURE data folder exists" test -d "${DATA_DIR}/CAPTURE"

PORT="${JUICE_CONTROL_PORT:-8765}"
if command -v lsof >/dev/null 2>&1; then
  if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    printf 'note: Port %s already has a listener. start.command reuses only this exact Control version. Run scripts/identify-jc.sh before restarting it.\n' "${PORT}"
  else
    printf 'ok: Port %s is free\n' "${PORT}"
  fi
fi

printf '\nChecks passed: %s; failed: %s\n' "${ok}" "${fail}"
exit "${fail}"
