#!/usr/bin/env bash
set -Eeuo pipefail
SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${JUICE_CONTROL_INSTALL_DIR:-${HOME}/JUICE/CONTROL}"
BACKUP_ROOT="${HOME}/JUICE/CONTROL.backups"

mkdir -p "$(dirname "${TARGET_DIR}")" "${BACKUP_ROOT}"

if [[ "${SOURCE_DIR}" != "${TARGET_DIR}" ]]; then
  if [[ -e "${TARGET_DIR}" ]]; then
    backup="${BACKUP_ROOT}/CONTROL.$(date +%Y%m%d-%H%M%S)"
    cp -a "${TARGET_DIR}" "${backup}"
    printf 'Backed up existing CONTROL to %s\n' "${backup}"
    rm -rf "${TARGET_DIR}"
  fi
  mkdir -p "${TARGET_DIR}"
  (cd "${SOURCE_DIR}" && tar -cf - .) | (cd "${TARGET_DIR}" && tar -xf -)
fi

mkdir -p \
  "${HOME}/JUICE_DATA/CREATIVE" \
  "${HOME}/JUICE_DATA/BUILD/Repos" \
  "${HOME}/JUICE_DATA/CAPTURE"

chmod +x "${TARGET_DIR}/start.command" "${TARGET_DIR}/server.py" "${TARGET_DIR}"/scripts/*.sh

printf 'Installed JUICE Control at %s\n' "${TARGET_DIR}"
printf 'Run: cd "%s" && ./start.command\n' "${TARGET_DIR}"
