#!/usr/bin/env bash
set -u

CONTROL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "${CONTROL_DIR}/.." 2>/dev/null && pwd -P)"
DATA_ROOT="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
ADMIN_ROOT="${DATA_ROOT}/ADMIN"
PORT="${JUICE_CONTROL_PORT:-8765}"
strict=0
deep=0
allow_no_backup=0
allow_no_launch_agent=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --strict) strict=1 ;;
    --deep) deep=1 ;;
    --allow-no-backup) allow_no_backup=1 ;;
    --allow-no-launch-agent) allow_no_launch_agent=1 ;;
    -h|--help)
      echo "Usage: doctor.sh [--strict] [--deep] [--allow-no-backup] [--allow-no-launch-agent]"
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      exit 64
      ;;
  esac
  shift
done

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin:${PATH:-}"

passes=0
warnings=0
failures=0

pass() { printf 'PASS  %s\n' "$1"; passes=$((passes + 1)); }
warn() { printf 'WARN  %s\n' "$1"; warnings=$((warnings + 1)); }
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }
note() { printf 'NOTE  %s\n' "$1"; }

if command -v python3 >/dev/null 2>&1; then
  pass "python3 available: $(python3 --version 2>&1)"
  if python3 -m py_compile "${CONTROL_DIR}/server.py" "${CONTROL_DIR}/scripts/verify_backup.py" >/dev/null 2>&1; then
    pass "Python files compile"
  else
    fail "Python compilation failed"
  fi
else
  fail "python3 is missing"
fi

syntax_bad=0
while IFS= read -r script; do
  if ! bash -n "${script}" >/dev/null 2>&1; then
    echo "      syntax error: ${script}"
    syntax_bad=1
  fi
done < <(find "${CONTROL_DIR}" -type f \( -name '*.sh' -o -name '*.command' \) -print 2>/dev/null)
[[ ${syntax_bad} -eq 0 ]] && pass "shell scripts parse" || fail "one or more shell scripts have syntax errors"

if [[ -f "${CONTROL_DIR}/scripts/open_in_zed.sh" ]] && \
   bash "${CONTROL_DIR}/scripts/open_in_zed.sh" --status >/dev/null 2>&1; then
  pass "Zed is reachable"
else
  fail "Zed is not reachable; install Zed or its CLI"
fi

for path in \
  "${HOME}/JUICE" \
  "${HOME}/JUICE/CONTROL" \
  "${DATA_ROOT}/CREATIVE" \
  "${DATA_ROOT}/BUILD/Repos" \
  "${DATA_ROOT}/CAPTURE" \
  "${ADMIN_ROOT}" \
  "${DATA_ROOT}/LOGS"; do
  [[ -d "${path}" ]] && pass "directory exists: ${path}" || fail "missing directory: ${path}"
done

if [[ -f "${REPO_ROOT}/.gitignore" ]]; then
  if grep -q '\.env' "${REPO_ROOT}/.gitignore" && grep -q '\*\.log' "${REPO_ROOT}/.gitignore"; then
    pass "repository privacy ignores are present"
  else
    warn ".gitignore exists but privacy patterns look incomplete"
  fi
else
  fail "repository .gitignore is missing"
fi

health=""
if command -v curl >/dev/null 2>&1; then
  health="$(curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/health" 2>/dev/null || true)"
fi
if printf '%s' "${health}" | grep -q '"service": "juice-control"'; then
  pass "JUICE Control health endpoint is live on port ${PORT}"
elif command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  fail "port ${PORT} is occupied by a non-JUICE listener"
else
  warn "JUICE Control is not currently listening on port ${PORT}"
fi

if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]]; then
  plist="${HOME}/Library/LaunchAgents/com.juice.control.plist"
  if [[ -f "${plist}" ]]; then
    pass "LaunchAgent plist exists"
    if launchctl print "gui/$(id -u)/com.juice.control" >/dev/null 2>&1; then
      pass "LaunchAgent is loaded"
    else
      fail "LaunchAgent plist exists but is not loaded"
    fi
  else
    if [[ ${allow_no_launch_agent} -eq 1 ]]; then
      note "LaunchAgent absence allowed by explicit setup mode"
    else
      fail "LaunchAgent is not installed"
    fi
  fi
else
  note "LaunchAgent check skipped outside macOS"
fi

config="${JUICE_BACKUP_CONFIG:-${ADMIN_ROOT}/backup.env}"
backup_volume=""
allow_unencrypted="0"
if [[ -f "${config}" ]]; then
  # shellcheck disable=SC1090
  source "${config}"
  backup_volume="${JUICE_BACKUP_VOLUME:-}"
  allow_unencrypted="${JUICE_ALLOW_UNENCRYPTED_BACKUP:-0}"
  pass "external backup configuration exists"
else
  if [[ ${allow_no_backup} -eq 1 ]]; then
    note "external backup absence allowed by explicit recovery/setup mode"
  else
    fail "external backup is not configured"
  fi
fi

if [[ -n "${backup_volume}" ]]; then
  if [[ -d "${backup_volume}" ]]; then
    pass "configured backup volume is mounted: ${backup_volume}"
    if [[ -f "${backup_volume}/.juice-backup-volume" ]] && \
       [[ "$(head -n 1 "${backup_volume}/.juice-backup-volume" 2>/dev/null || true)" == "JUICE_BACKUP_VOLUME_V1" ]]; then
      pass "backup-volume sentinel is valid"
    else
      fail "backup-volume sentinel is missing or invalid"
    fi

    if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]] && command -v diskutil >/dev/null 2>&1; then
      if diskutil info "${backup_volume}" 2>/dev/null | grep -Eq '^[[:space:]]*(Encrypted|FileVault):[[:space:]]*Yes'; then
        pass "backup volume is encrypted"
      elif [[ "${allow_unencrypted}" == "1" ]]; then
        note "backup volume is unencrypted by explicit override"
      else
        fail "backup volume does not appear encrypted"
      fi
    fi
  else
    fail "configured backup volume is not mounted: ${backup_volume}"
  fi
fi

state="${ADMIN_ROOT}/last-backup.json"
snapshot=""
if [[ -f "${state}" ]] && command -v python3 >/dev/null 2>&1; then
  state_values="$(python3 - "${state}" <<'PY'
import datetime as dt
import json
import sys
from pathlib import Path
try:
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    updated = data.get("updated_at") or ""
    age_days = ""
    if updated:
        stamp = dt.datetime.fromisoformat(updated.replace("Z", "+00:00"))
        now = dt.datetime.now(dt.timezone.utc)
        age_days = str(max(0, (now - stamp).days))
    print(data.get("status") or "")
    print(data.get("snapshot") or "")
    print(age_days)
except Exception:
    print("")
    print("")
    print("")
PY
)"
  status="$(printf '%s\n' "${state_values}" | sed -n '1p')"
  snapshot="$(printf '%s\n' "${state_values}" | sed -n '2p')"
  age_days="$(printf '%s\n' "${state_values}" | sed -n '3p')"
  if [[ "${status}" == "success" ]]; then
    pass "last JUICE backup recorded success"
  else
    fail "last JUICE backup status is ${status:-unreadable}"
  fi
  if [[ -n "${age_days}" && "${age_days}" -le 7 ]]; then
    pass "last backup state is ${age_days} day(s) old"
  elif [[ -n "${age_days}" ]]; then
    warn "last backup state is ${age_days} day(s) old"
  fi
else
  if [[ ${allow_no_backup} -eq 1 ]]; then
    note "backup state absence allowed by explicit recovery/setup mode"
  else
    fail "no readable JUICE backup state exists"
  fi
fi

if [[ -n "${snapshot}" ]]; then
  [[ -f "${snapshot}/COMPLETED.json" ]] && pass "backup completion marker exists" || fail "backup completion marker missing"
  [[ -f "${snapshot}/MANIFEST.json" ]] && pass "backup manifest exists" || fail "backup manifest missing"
  if [[ ${deep} -eq 1 && -f "${snapshot}/MANIFEST.json" && -f "${CONTROL_DIR}/scripts/verify_backup.py" ]]; then
    if python3 "${CONTROL_DIR}/scripts/verify_backup.py" verify \
      --manifest "${snapshot}/MANIFEST.json" \
      --backup-root "${snapshot}" >/dev/null; then
      pass "deep backup manifest verification passed"
    else
      fail "deep backup manifest verification failed"
    fi
  fi
fi

if command -v tmutil >/dev/null 2>&1; then
  if tmutil destinationinfo >/dev/null 2>&1; then
    note "Time Machine destination is configured"
  else
    note "Time Machine is not configured; JUICE external backup remains separate"
  fi
fi

if command -v git >/dev/null 2>&1 && [[ -d "${REPO_ROOT}/.git" ]]; then
  if [[ -z "$(git -C "${REPO_ROOT}" status --porcelain 2>/dev/null)" ]]; then
    pass "JUICE repository working tree is clean"
  else
    warn "JUICE repository has local changes"
  fi
fi

printf '\nChecks: %s pass; %s warning; %s fail\n' "${passes}" "${warnings}" "${failures}"
if [[ ${failures} -gt 0 ]]; then
  exit 1
fi
if [[ ${strict} -eq 1 && ${warnings} -gt 0 ]]; then
  exit 2
fi
exit 0
