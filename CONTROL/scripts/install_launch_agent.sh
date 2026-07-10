#!/usr/bin/env bash
set -Eeuo pipefail

CONTROL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
LOG_ROOT="${DATA_ROOT}/LOGS"
LABEL="com.juice.control"
DEFAULT_PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin:${PATH:-}"

usage() {
  cat <<'USAGE'
Usage:
  install_launch_agent.sh
  install_launch_agent.sh --render-only /path/to/output.plist
  install_launch_agent.sh --uninstall
USAGE
}

mode="install"
plist="${DEFAULT_PLIST}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --render-only)
      [[ $# -ge 2 ]] || { echo "ERROR: --render-only needs a path" >&2; exit 64; }
      mode="render"
      plist="$2"
      shift 2
      ;;
    --uninstall)
      mode="uninstall"
      shift
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

command -v python3 >/dev/null 2>&1 || {
  echo "ERROR: python3 is required to render the LaunchAgent." >&2
  exit 69
}

if [[ "${mode}" == "uninstall" ]]; then
  if [[ "$(uname -s 2>/dev/null || true)" != "Darwin" ]]; then
    echo "ERROR: LaunchAgents are a macOS feature." >&2
    exit 69
  fi
  uid="$(id -u)"
  launchctl bootout "gui/${uid}" "${DEFAULT_PLIST}" 2>/dev/null || \
    launchctl unload "${DEFAULT_PLIST}" 2>/dev/null || true
  rm -f "${DEFAULT_PLIST}"
  echo "Removed ${LABEL}."
  exit 0
fi

mkdir -p "$(dirname "${plist}")" "${LOG_ROOT}"
chmod 700 "${LOG_ROOT}" 2>/dev/null || true

python3 - "${plist}" "${CONTROL_DIR}" "${DATA_ROOT}" "${LOG_ROOT}" "${LABEL}" <<'PY'
import os
import plistlib
import sys
from pathlib import Path

output = Path(sys.argv[1])
control = str(Path(sys.argv[2]).resolve())
data = str(Path(sys.argv[3]).resolve())
logs = str(Path(sys.argv[4]).resolve())
label = sys.argv[5]

payload = {
    "Label": label,
    "ProgramArguments": [
        "/bin/bash",
        str(Path(control) / "scripts" / "run_service.sh"),
    ],
    "WorkingDirectory": control,
    "EnvironmentVariables": {
        "HOME": str(Path.home()),
        "JUICE_CONTROL_ROOT": control,
        "JUICE_DATA_ROOT": data,
        "JUICE_CONTROL_OPEN_BROWSER": "0",
    },
    "RunAtLoad": True,
    # Keep retrying even if a manually launched JUICE instance temporarily owns
    # the port and server.py exits cleanly after detecting it.
    "KeepAlive": True,
    "ThrottleInterval": 30,
    "ProcessType": "Interactive",
    "LimitLoadToSessionType": "Aqua",
    "StandardOutPath": str(Path(logs) / "juice-control.stdout.log"),
    "StandardErrorPath": str(Path(logs) / "juice-control.stderr.log"),
}
output.parent.mkdir(parents=True, exist_ok=True)
temp = output.with_name(f".{output.name}.tmp-{os.getpid()}")
with temp.open("wb") as handle:
    plistlib.dump(payload, handle, fmt=plistlib.FMT_XML, sort_keys=True)
os.replace(temp, output)
PY
chmod 600 "${plist}" 2>/dev/null || true

if [[ "${mode}" == "render" ]]; then
  echo "Rendered LaunchAgent: ${plist}"
  exit 0
fi

if [[ "$(uname -s 2>/dev/null || true)" != "Darwin" ]]; then
  echo "ERROR: LaunchAgents can only be installed on macOS." >&2
  exit 69
fi
command -v launchctl >/dev/null 2>&1 || { echo "ERROR: launchctl is missing" >&2; exit 69; }

uid="$(id -u)"
launchctl bootout "gui/${uid}" "${plist}" 2>/dev/null || \
  launchctl unload "${plist}" 2>/dev/null || true

if launchctl bootstrap "gui/${uid}" "${plist}"; then
  launchctl enable "gui/${uid}/${LABEL}" 2>/dev/null || true
  launchctl kickstart -k "gui/${uid}/${LABEL}"
else
  echo "Modern launchctl bootstrap failed; trying legacy load." >&2
  launchctl load -w "${plist}"
fi

sleep 1
if launchctl print "gui/${uid}/${LABEL}" >/dev/null 2>&1; then
  echo "ROCK SOLID: ${LABEL} is loaded."
else
  echo "ERROR: ${LABEL} did not load. Inspect ${LOG_ROOT}/juice-control.stderr.log" >&2
  exit 70
fi
