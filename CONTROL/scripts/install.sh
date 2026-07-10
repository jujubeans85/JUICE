#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE_REPO="$(cd "${SOURCE_DIR}/.." && pwd -P)"
TARGET_DIR="${JUICE_CONTROL_INSTALL_DIR:-${HOME}/JUICE/CONTROL}"
TARGET_REPO="$(cd "$(dirname "${TARGET_DIR}")" 2>/dev/null && pwd -P || dirname "${TARGET_DIR}")"
DATA_ROOT="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
BACKUP_ROOT="${DATA_ROOT}/ADMIN/control-backups"

mkdir -p "$(dirname "${TARGET_DIR}")" "${BACKUP_ROOT}"

if [[ "${SOURCE_DIR}" != "${TARGET_DIR}" ]]; then
  if [[ -e "${TARGET_DIR}" ]]; then
    backup="${BACKUP_ROOT}/CONTROL.$(date '+%Y%m%d-%H%M%S')"
    cp -a "${TARGET_DIR}" "${backup}"
    echo "Backed up existing CONTROL to ${backup}"
    rm -rf "${TARGET_DIR}"
  fi
  mkdir -p "${TARGET_DIR}"
  (cd "${SOURCE_DIR}" && tar -cf - .) | (cd "${TARGET_DIR}" && tar -xf -)
  for guardrail in .gitignore README.md; do
    if [[ -f "${SOURCE_REPO}/${guardrail}" ]]; then
      cp -p "${SOURCE_REPO}/${guardrail}" "${TARGET_REPO}/${guardrail}"
    fi
  done
fi

mkdir -p \
  "${DATA_ROOT}/CREATIVE" \
  "${DATA_ROOT}/BUILD/Repos" \
  "${DATA_ROOT}/CAPTURE" \
  "${DATA_ROOT}/ADMIN/audits" \
  "${DATA_ROOT}/LOGS"

chmod 700 "${DATA_ROOT}/ADMIN" "${DATA_ROOT}/LOGS" 2>/dev/null || true
chmod +x "${TARGET_DIR}/start.command" "${TARGET_DIR}/server.py" "${TARGET_DIR}"/scripts/*.sh

echo "Installed JUICE Control at ${TARGET_DIR}"
echo "Private data root: ${DATA_ROOT}"
echo "Run: bash \"${TARGET_DIR}/scripts/finish_setup.sh\" --backup-volume \"/Volumes/YOUR_DRIVE\" --yes"
