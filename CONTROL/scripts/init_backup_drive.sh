#!/usr/bin/env bash
set -Eeuo pipefail

CONTROL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
ADMIN_ROOT="${DATA_ROOT}/ADMIN"
CONFIG_FILE="${JUICE_BACKUP_CONFIG:-${ADMIN_ROOT}/backup.env}"
SENTINEL_NAME=".juice-backup-volume"
MAGIC="JUICE_BACKUP_VOLUME_V1"

usage() {
  cat <<'USAGE'
Usage:
  init_backup_drive.sh /Volumes/DRIVE [--yes] [--allow-unencrypted]

This does not erase or format the drive. It writes a small sentinel file and
a private local configuration file so later backups cannot silently target
the wrong disk.
USAGE
}

volume=""
yes=0
allow_unencrypted=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes)
      yes=1
      shift
      ;;
    --allow-unencrypted)
      allow_unencrypted=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 64
      ;;
    *)
      if [[ -n "${volume}" ]]; then
        echo "ERROR: only one volume path is accepted" >&2
        exit 64
      fi
      volume="$1"
      shift
      ;;
  esac
done

[[ -n "${volume}" ]] || { usage >&2; exit 64; }
[[ -d "${volume}" ]] || { echo "ERROR: volume is not mounted: ${volume}" >&2; exit 66; }
volume="$(cd "${volume}" && pwd -P)"

if [[ "${JUICE_ALLOW_NON_VOLUME_BACKUP:-0}" != "1" ]]; then
  case "${volume}" in
    /Volumes/*) ;;
    *)
      echo "ERROR: refusing to initialise a destination outside /Volumes: ${volume}" >&2
      exit 65
      ;;
  esac
  home_device="$(df -P "${HOME}" | awk 'END {print $1}')"
  volume_device="$(df -P "${volume}" | awk 'END {print $1}')"
  if [[ -n "${home_device}" && "${home_device}" == "${volume_device}" ]]; then
    echo "ERROR: ${volume} is on the same filesystem as HOME, so it is not an external backup." >&2
    exit 65
  fi
  if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]] && command -v diskutil >/dev/null 2>&1; then
    disk_info="$(diskutil info "${volume}" 2>/dev/null || true)"
    if printf '%s\n' "${disk_info}" | grep -Eq '^[[:space:]]*Virtual:[[:space:]]*Yes'; then
      echo "ERROR: ${volume} is a virtual disk, not a physical external drive." >&2
      exit 65
    fi
    if ! printf '%s\n' "${disk_info}" | grep -Eq '^[[:space:]]*(Device Location:[[:space:]]*External|Internal:[[:space:]]*No)'; then
      echo "ERROR: diskutil does not identify ${volume} as external." >&2
      exit 65
    fi
  fi
fi

probe="${volume}/.juice-init-write-test.$$"
( umask 077; printf 'JUICE\n' > "${probe}" ) || {
  echo "ERROR: destination is not writable: ${volume}" >&2
  exit 73
}
rm -f "${probe}"

encryption="unknown"
if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]] && command -v diskutil >/dev/null 2>&1; then
  if diskutil info "${volume}" 2>/dev/null | grep -Eq '^[[:space:]]*(Encrypted|FileVault):[[:space:]]*Yes'; then
    encryption="yes"
  else
    encryption="no"
  fi
fi

if [[ "${encryption}" == "no" && ${allow_unencrypted} -ne 1 ]]; then
  cat >&2 <<EOF
ERROR: ${volume} does not appear encrypted.
Private family data should not be copied to a loose unencrypted disk.
Use Disk Utility to create an encrypted APFS volume, or make the risk explicit
with --allow-unencrypted.
EOF
  exit 77
fi

echo "Initialise JUICE external backup destination"
echo "  volume:      ${volume}"
echo "  encryption:  ${encryption}"
echo "  writes:      ${volume}/${SENTINEL_NAME}"
echo "  local config:${CONFIG_FILE}"
echo "This does not erase or format the drive."

if [[ ${yes} -ne 1 ]]; then
  printf 'Type INITIALISE to continue: '
  read -r answer
  [[ "${answer}" == "INITIALISE" ]] || { echo "Cancelled."; exit 1; }
fi

mkdir -p "${ADMIN_ROOT}" "${volume}/JUICE_BACKUPS"
chmod 700 "${ADMIN_ROOT}" "${volume}/JUICE_BACKUPS" 2>/dev/null || true

sentinel="${volume}/${SENTINEL_NAME}"
if [[ -e "${sentinel}" ]] && [[ "$(head -n 1 "${sentinel}" 2>/dev/null || true)" != "${MAGIC}" ]]; then
  echo "ERROR: refusing to overwrite an unfamiliar sentinel: ${sentinel}" >&2
  exit 65
fi

umask 077
cat > "${sentinel}" <<EOF
${MAGIC}
created_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
created_by=$(id -un 2>/dev/null || echo unknown)
host=$(hostname 2>/dev/null || echo unknown)
EOF

{
  printf '# Created by JUICE Control. Private local configuration.\n'
  printf 'JUICE_BACKUP_VOLUME=%q\n' "${volume}"
  printf 'JUICE_ALLOW_UNENCRYPTED_BACKUP=%q\n' "${allow_unencrypted}"
} > "${CONFIG_FILE}"
chmod 600 "${CONFIG_FILE}" "${sentinel}" 2>/dev/null || true

echo "ROCK SOLID: backup destination initialised."
echo "Next: bash \"${CONTROL_DIR}/scripts/backup_external.sh\""
