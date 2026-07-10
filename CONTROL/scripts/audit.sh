#!/usr/bin/env bash
set -u

CONTROL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
ADMIN_ROOT="${DATA_ROOT}/ADMIN"
AUDIT_ROOT="${ADMIN_ROOT}/audits"
PORT="${JUICE_CONTROL_PORT:-8765}"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin:${PATH:-}"

mkdir -p "${AUDIT_ROOT}"
report="${AUDIT_ROOT}/mac-home-audit-$(date '+%Y%m%d-%H%M%S').txt"
touch "${report}"
chmod 600 "${report}" 2>/dev/null || true

section() {
  printf '\n=== %s ===\n' "$1"
}

run_if_present() {
  local command_name="$1"
  shift
  if command -v "${command_name}" >/dev/null 2>&1; then
    "$@" 2>&1 || true
  else
    echo "UNAVAILABLE: ${command_name}"
  fi
}

{
  section "AUDIT IDENTITY"
  date
  printf 'user: %s\n' "$(id -un 2>/dev/null || echo unknown)"
  printf 'host: %s\n' "$(hostname 2>/dev/null || echo unknown)"
  printf 'home: %s\n' "${HOME}"
  printf 'control: %s\n' "${CONTROL_DIR}"
  printf 'data: %s\n' "${DATA_ROOT}"

  section "OPERATING SYSTEM"
  run_if_present sw_vers sw_vers
  uname -a 2>&1 || true

  section "INTERNAL STORAGE"
  df -h "${HOME}" 2>&1 || true
  if command -v diskutil >/dev/null 2>&1; then
    diskutil info "${HOME}" 2>/dev/null | grep -E \
      'Device Node|Volume Name|File System Personality|Disk Size|Volume Free Space|Solid State|Encrypted|FileVault' \
      || true
  fi

  section "FILEVAULT"
  run_if_present fdesetup fdesetup status

  section "POWER AND RESTART"
  run_if_present pmset pmset -g
  if command -v pmset >/dev/null 2>&1; then
    pmset -g custom 2>&1 || true
  fi

  section "NETWORK"
  if command -v scutil >/dev/null 2>&1; then
    scutil --get ComputerName 2>&1 || true
    scutil --get LocalHostName 2>&1 || true
  else
    echo "UNAVAILABLE: scutil"
  fi
  if command -v networksetup >/dev/null 2>&1; then
    networksetup -listallhardwareports 2>&1 || true
  else
    echo "UNAVAILABLE: networksetup"
  fi

  section "REQUIRED TOOLS"
  for tool in git python3 curl shasum rsync open osascript launchctl; do
    if command -v "${tool}" >/dev/null 2>&1; then
      printf '%-12s %s\n' "${tool}" "$(command -v "${tool}")"
    else
      printf '%-12s MISSING\n' "${tool}"
    fi
  done
  python3 --version 2>&1 || true
  git --version 2>&1 || true

  section "ZED"
  for app in \
    "/Applications/Zed.app" \
    "${HOME}/Applications/Zed.app" \
    "/Applications/Zed Preview.app" \
    "${HOME}/Applications/Zed Preview.app"; do
    [[ -d "${app}" ]] && echo "${app}"
  done
  if [[ -f "${CONTROL_DIR}/scripts/open_in_zed.sh" ]]; then
    bash "${CONTROL_DIR}/scripts/open_in_zed.sh" --status 2>&1 || true
  else
    echo "MISSING: scripts/open_in_zed.sh"
  fi

  section "JUICE REPOSITORY"
  repo_root="$(cd "${CONTROL_DIR}/.." 2>/dev/null && pwd -P)"
  if [[ -d "${repo_root}/.git" ]] && command -v git >/dev/null 2>&1; then
    git -C "${repo_root}" status --short --branch 2>&1 || true
    git -C "${repo_root}" log -1 --date=iso --format='commit: %H%nwhen: %ad%nsubject: %s' 2>&1 || true
    printf 'remotes: '
    git -C "${repo_root}" remote 2>/dev/null | paste -sd, - || true
    echo
  else
    echo "No Git repository detected at ${repo_root}"
  fi

  section "JUICE LAYOUT"
  for path in \
    "${HOME}/JUICE" \
    "${HOME}/JUICE/CONTROL" \
    "${DATA_ROOT}" \
    "${DATA_ROOT}/CREATIVE" \
    "${DATA_ROOT}/BUILD/Repos" \
    "${DATA_ROOT}/CAPTURE" \
    "${DATA_ROOT}/ADMIN" \
    "${DATA_ROOT}/LOGS"; do
    if [[ -d "${path}" ]]; then
      printf 'OK      %s\n' "${path}"
    else
      printf 'MISSING %s\n' "${path}"
    fi
  done

  section "EXTERNAL VOLUMES"
  if [[ -d /Volumes ]]; then
    find /Volumes -mindepth 1 -maxdepth 1 -print 2>/dev/null | sort || true
  else
    echo "UNAVAILABLE: /Volumes"
  fi
  if command -v diskutil >/dev/null 2>&1; then
    diskutil list external physical 2>&1 || true
  fi

  section "BACKUP CONFIGURATION"
  config="${JUICE_BACKUP_CONFIG:-${ADMIN_ROOT}/backup.env}"
  if [[ -f "${config}" ]]; then
    echo "Configured: ${config}"
    # Do not print the whole config. Only show the configured volume safely.
    (
      # shellcheck disable=SC1090
      source "${config}"
      printf 'volume: %s\n' "${JUICE_BACKUP_VOLUME:-unset}"
      printf 'mounted: %s\n' "$([[ -d "${JUICE_BACKUP_VOLUME:-}" ]] && echo yes || echo no)"
    ) 2>&1 || true
  else
    echo "NOT CONFIGURED"
  fi
  if [[ -f "${ADMIN_ROOT}/last-backup.json" ]]; then
    python3 -m json.tool "${ADMIN_ROOT}/last-backup.json" 2>&1 || cat "${ADMIN_ROOT}/last-backup.json"
  else
    echo "No JUICE backup state recorded."
  fi

  section "TIME MACHINE"
  run_if_present tmutil tmutil destinationinfo
  run_if_present tmutil tmutil latestbackup

  section "LAUNCH AGENT"
  plist="${HOME}/Library/LaunchAgents/com.juice.control.plist"
  [[ -f "${plist}" ]] && echo "plist: ${plist}" || echo "plist: MISSING"
  if command -v launchctl >/dev/null 2>&1; then
    launchctl print "gui/$(id -u)/com.juice.control" 2>&1 | head -n 80 || true
  fi

  section "JUICE CONTROL PORT"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 2 "http://127.0.0.1:${PORT}/health" 2>&1 || echo "No healthy JUICE Control response on port ${PORT}"
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN 2>&1 || true
  fi

  section "AUDIT COMPLETE"
  echo "This report observes state. It does not claim that physical-Mac acceptance tests passed."
} | tee "${report}"

printf '\nAudit saved to: %s\n' "${report}"
