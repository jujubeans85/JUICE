#!/usr/bin/env bash
set -Eeuo pipefail

CONTROL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "${CONTROL_DIR}/.." && pwd -P)"
DATA_ROOT="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
STATE_ROOT="${DATA_ROOT}/ADMIN"
STATE_FILE="${STATE_ROOT}/last-verify.json"
REQUESTED_PASS="all"

usage() {
  cat <<'USAGE'
Usage:
  verify.sh
  verify.sh --pass shell|python|tests|plist|secrets|repo

Without --pass, all six verification passes run in order.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pass)
      [[ $# -ge 2 ]] || { echo "ERROR: --pass needs a value" >&2; exit 64; }
      REQUESTED_PASS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin:${PATH:-}"
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required" >&2; exit 69; }
mkdir -p "${STATE_ROOT}"

passes=0
current_label="not started"

run_pass() {
  local label="$1"
  shift
  current_label="${label}"
  echo
  echo "=== ${label} ==="
  "$@"
  passes=$((passes + 1))
  echo "PASS: ${label}"
}

record_state() {
  local status="$1"
  local message="$2"
  python3 - "${STATE_FILE}" "${status}" "${message}" "${passes}" <<'PY'
import datetime as dt
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = {
    "format": "juice-verification-state-v1",
    "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "status": sys.argv[2],
    "message": sys.argv[3],
    "passes_completed": int(sys.argv[4]),
}
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(tmp, path)
PY
}

on_error() {
  local code=$?
  set +e
  record_state "failed" "Verification failed in ${current_label}"
  exit "${code}"
}
trap on_error ERR

shell_syntax() {
  local bad=0
  while IFS= read -r script; do
    echo "bash -n ${script#${REPO_ROOT}/}"
    if ! bash -n "${script}"; then
      bad=1
    fi
  done < <(find "${CONTROL_DIR}" -type f \( -name '*.sh' -o -name '*.command' \) -print | sort)
  [[ ${bad} -eq 0 ]]
}

python_compile() {
  python3 -m py_compile \
    "${CONTROL_DIR}/server.py" \
    "${CONTROL_DIR}/scripts/verify_backup.py"
}

unit_and_integration() {
  (
    cd "${CONTROL_DIR}"
    python3 -m unittest discover -s tests -v
  )
}

launch_agent_lint() {
  local temp
  temp="$(mktemp -d "${TMPDIR:-/tmp}/juice-plist.XXXXXX")"
  bash "${CONTROL_DIR}/scripts/install_launch_agent.sh" --render-only "${temp}/com.juice.control.plist"
  if command -v plutil >/dev/null 2>&1; then
    plutil -lint "${temp}/com.juice.control.plist"
  else
    python3 - "${temp}/com.juice.control.plist" <<'PY'
import plistlib
import sys
with open(sys.argv[1], "rb") as handle:
    plistlib.load(handle)
print("plist parse passed")
PY
  fi
  rm -rf "${temp}"
}

secret_scan() {
  python3 - "${REPO_ROOT}" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
patterns = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "AWS access key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
}
skip_parts = {".git", "__pycache__"}
hits = []
for path in root.rglob("*"):
    if not path.is_file() or skip_parts.intersection(path.parts):
        continue
    try:
        if path.stat().st_size > 2_000_000:
            continue
        data = path.read_bytes()
    except OSError:
        continue
    for label, pattern in patterns.items():
        if pattern.search(data):
            hits.append(f"{label}: {path.relative_to(root)}")
if hits:
    print("\n".join(hits), file=sys.stderr)
    raise SystemExit(1)
print("high-confidence secret patterns: none")
PY
}

repository_checks() {
  if command -v git >/dev/null 2>&1 && [[ -d "${REPO_ROOT}/.git" ]]; then
    git -C "${REPO_ROOT}" diff --check
    git -C "${REPO_ROOT}" diff --cached --check
  else
    echo "No Git worktree available; diff check skipped."
  fi
  [[ -f "${REPO_ROOT}/.gitignore" ]]
  grep -q '\.env' "${REPO_ROOT}/.gitignore"
  grep -q '\*\.log' "${REPO_ROOT}/.gitignore"
}

run_named_pass() {
  case "$1" in
    shell)   run_pass "1/6 shell syntax" shell_syntax ;;
    python)  run_pass "2/6 Python compilation" python_compile ;;
    tests)   run_pass "3/6 unit, integration, backup round-trip and tamper tests" unit_and_integration ;;
    plist)   run_pass "4/6 LaunchAgent rendering and plist parsing" launch_agent_lint ;;
    secrets) run_pass "5/6 high-confidence secret scan" secret_scan ;;
    repo)    run_pass "6/6 repository consistency" repository_checks ;;
    *)
      echo "ERROR: unknown verification pass: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
}

if [[ "${REQUESTED_PASS}" == "all" ]]; then
  for pass_name in shell python tests plist secrets repo; do
    run_named_pass "${pass_name}"
  done
  record_state "success" "All ${passes} verification passes completed"
  result_message="all ${passes} verification passes completed"
else
  run_named_pass "${REQUESTED_PASS}"
  record_state "success" "Verification pass ${REQUESTED_PASS} completed"
  result_message="verification pass ${REQUESTED_PASS} completed"
fi

trap - ERR

echo
echo "ROCK SOLID: ${result_message}."
