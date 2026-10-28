#!/usr/bin/env bash
set -Eeuo pipefail
SOURCE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_DIR="${JUICE_CONTROL_INSTALL_DIR:-${HOME}/JUICE/CONTROL}"
BACKUP_ROOT="${HOME}/JUICE/CONTROL.backups"

# A live JC checkout may contain the 8780 dashboard that is absent from GitHub.
# Do not replace a divergent server with this repository's smaller server.
if [[ "${SOURCE_DIR}" != "${TARGET_DIR}" && -f "${TARGET_DIR}/server.py" ]]; then
  python3 - "${TARGET_DIR}/server.py" "${SOURCE_DIR}/server.py" <<'PY_GUARD'
import hashlib
import sys
from pathlib import Path
current = hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest()
source = hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest()
if current not in {"b0c07b5cf1ca9bcb2a83fee2606f9e57698a64eac4ed0283f33123e8f75066ce", source}:
    raise SystemExit('Install stopped: target server differs from the verified repository baseline. Preserve and merge the live JC routes first; see AUDIO_INTAKE.md. No target files were changed.')
PY_GUARD
fi

mkdir -p "$(dirname "${TARGET_DIR}")" "${BACKUP_ROOT}"
if [[ "${SOURCE_DIR}" != "${TARGET_DIR}" ]]; then
  if [[ -e "${TARGET_DIR}" ]]; then
    backup="${BACKUP_ROOT}/CONTROL.$(date +%Y%m%d-%H%M%S).$$"
    cp -a "${TARGET_DIR}" "${backup}"
    printf 'Backed up existing CONTROL to %s\n' "${backup}"
  fi
  mkdir -p "${TARGET_DIR}"
  # Overlay tracked distribution files; never remove local capture/config/modules.
  (cd "${SOURCE_DIR}" && tar --exclude='__pycache__' --exclude='*.pyc' -cf - .) | (cd "${TARGET_DIR}" && tar -xf -)
fi

DATA_DIR="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
mkdir -p \
  "${DATA_DIR}/CREATIVE" \
  "${DATA_DIR}/BUILD/Repos" \
  "${DATA_DIR}/CAPTURE"

chmod +x "${TARGET_DIR}/start.command" "${TARGET_DIR}/server.py" "${TARGET_DIR}"/scripts/*.sh

printf 'Installed JUICE Control at %s\n' "${TARGET_DIR}"
printf 'Run: cd "%s" && ./start.command\n' "${TARGET_DIR}"
