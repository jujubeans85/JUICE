#!/usr/bin/env bash
set -Eeuo pipefail

CONTROL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
ADMIN_ROOT="${DATA_ROOT}/ADMIN"
LOG_ROOT="${DATA_ROOT}/LOGS"
CONFIG_FILE="${JUICE_BACKUP_CONFIG:-${ADMIN_ROOT}/backup.env}"
STATE_FILE="${ADMIN_ROOT}/last-backup.json"
VERIFY_TOOL="${CONTROL_DIR}/scripts/verify_backup.py"
SENTINEL_NAME=".juice-backup-volume"
MAGIC="JUICE_BACKUP_VOLUME_V1"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin:${PATH:-}"

usage() {
  cat <<'USAGE'
Usage:
  backup_external.sh [--volume /Volumes/NAME] [--allow-unencrypted] [--dry-run]

The destination must first be initialised with init_backup_drive.sh.
Backups are immutable timestamped snapshots. Nothing is deleted or pruned.
USAGE
}

volume=""
allow_unencrypted="${JUICE_ALLOW_UNENCRYPTED_BACKUP:-0}"
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --volume)
      [[ $# -ge 2 ]] || { echo "ERROR: --volume needs a path" >&2; exit 64; }
      volume="$2"
      shift 2
      ;;
    --allow-unencrypted)
      allow_unencrypted=1
      shift
      ;;
    --dry-run)
      dry_run=1
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

mkdir -p "${ADMIN_ROOT}" "${LOG_ROOT}"
chmod 700 "${ADMIN_ROOT}" "${LOG_ROOT}" 2>/dev/null || true

command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is required" >&2; exit 69; }

if [[ -f "${CONFIG_FILE}" ]]; then
  # The file is created by init_backup_drive.sh and is private to this user.
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
fi

if [[ -z "${volume}" ]]; then
  volume="${JUICE_BACKUP_VOLUME:-}"
fi

timestamp="$(date '+%Y%m%d-%H%M%S')"
log_file="${LOG_ROOT}/backup-${timestamp}.log"
touch "${log_file}"
chmod 600 "${log_file}" 2>/dev/null || true
exec > >(tee -a "${log_file}") 2>&1

write_state() {
  local status="$1"
  local message="$2"
  local snapshot="${3:-}"
  local manifest="${4:-}"
  python3 - "${STATE_FILE}" "${status}" "${message}" "${volume:-}" "${snapshot}" "${manifest}" <<'PY'
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
status, message, volume, snapshot, manifest_path = sys.argv[2:7]
payload = {
    "format": "juice-backup-state-v1",
    "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "status": status,
    "message": message,
    "volume": volume or None,
    "snapshot": snapshot or None,
    "manifest": manifest_path or None,
}
if manifest_path and Path(manifest_path).is_file():
    raw = Path(manifest_path).read_bytes()
    payload["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        manifest = json.loads(raw)
        payload["summary"] = manifest.get("summary")
    except (OSError, json.JSONDecodeError):
        pass
state_path.parent.mkdir(parents=True, exist_ok=True)
tmp = state_path.with_name(f".{state_path.name}.tmp-{os.getpid()}")
with tmp.open("w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
os.replace(tmp, state_path)
try:
    os.chmod(state_path, 0o600)
except OSError:
    pass
PY
}

completed=0
lock_dir="${ADMIN_ROOT}/backup.lock"
cleanup() {
  local exit_code=$?
  set +e
  rm -rf "${lock_dir}"
  if [[ ${exit_code} -ne 0 && ${completed} -eq 0 ]]; then
    write_state "failed" "Backup failed; inspect ${log_file}" "${final_snapshot:-}" "${manifest_path:-}"
  fi
  exit "${exit_code}"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

if ! mkdir "${lock_dir}" 2>/dev/null; then
  echo "ERROR: another JUICE backup appears to be running: ${lock_dir}" >&2
  exit 75
fi
printf '%s\n' "$$" > "${lock_dir}/pid"

write_state "preflight" "Checking sources and external destination"

[[ -n "${volume}" ]] || {
  echo "ERROR: no backup volume configured." >&2
  echo "Run: bash \"${CONTROL_DIR}/scripts/init_backup_drive.sh\" \"/Volumes/YOUR_DRIVE\"" >&2
  exit 66
}
[[ -d "${volume}" ]] || { echo "ERROR: backup volume is not mounted: ${volume}" >&2; exit 66; }

volume="$(cd "${volume}" && pwd -P)"
if [[ "${JUICE_ALLOW_NON_VOLUME_BACKUP:-0}" != "1" ]]; then
  case "${volume}" in
    /Volumes/*) ;;
    *)
      echo "ERROR: refusing destination outside /Volumes: ${volume}" >&2
      exit 65
      ;;
  esac
fi

sentinel="${volume}/${SENTINEL_NAME}"
[[ -f "${sentinel}" && ! -L "${sentinel}" ]] || {
  echo "ERROR: backup-volume sentinel is missing: ${sentinel}" >&2
  echo "Initialise the drive explicitly before backup." >&2
  exit 65
}
[[ "$(head -n 1 "${sentinel}" 2>/dev/null || true)" == "${MAGIC}" ]] || {
  echo "ERROR: invalid backup-volume sentinel: ${sentinel}" >&2
  exit 65
}

write_probe="${volume}/.juice-write-test.$$"
( umask 077; printf 'JUICE\n' > "${write_probe}" ) || {
  echo "ERROR: backup volume is not writable: ${volume}" >&2
  exit 73
}
rm -f "${write_probe}"

if [[ "${JUICE_ALLOW_NON_VOLUME_BACKUP:-0}" != "1" ]]; then
  home_device="$(df -P "${HOME}" | awk 'END {print $1}')"
  volume_device="$(df -P "${volume}" | awk 'END {print $1}')"
  if [[ -n "${home_device}" && "${home_device}" == "${volume_device}" ]]; then
    echo "ERROR: destination is on the same filesystem as HOME; this is not an external backup." >&2
    exit 65
  fi
  if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]] && command -v diskutil >/dev/null 2>&1; then
    disk_info="$(diskutil info "${volume}" 2>/dev/null || true)"
    if printf '%s\n' "${disk_info}" | grep -Eq '^[[:space:]]*Virtual:[[:space:]]*Yes'; then
      echo "ERROR: destination is a virtual disk, not a physical external drive." >&2
      exit 65
    fi
    if ! printf '%s\n' "${disk_info}" | grep -Eq '^[[:space:]]*(Device Location:[[:space:]]*External|Internal:[[:space:]]*No)'; then
      echo "ERROR: diskutil does not identify the destination as external." >&2
      exit 65
    fi
  fi
fi

encryption="unknown"
if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]] && command -v diskutil >/dev/null 2>&1; then
  if diskutil info "${volume}" 2>/dev/null | grep -Eq '^[[:space:]]*(Encrypted|FileVault):[[:space:]]*Yes'; then
    encryption="yes"
  else
    encryption="no"
  fi
fi
if [[ "${encryption}" == "no" && "${allow_unencrypted}" != "1" ]]; then
  echo "ERROR: external volume does not appear encrypted." >&2
  echo "Use an encrypted APFS volume, or explicitly pass --allow-unencrypted." >&2
  exit 77
fi
if [[ "${encryption}" != "yes" ]]; then
  echo "WARNING: external-volume encryption status: ${encryption}"
fi

source_code="${HOME}/JUICE"
source_data="${DATA_ROOT}"
[[ -d "${source_code}" ]] || { echo "ERROR: source missing: ${source_code}" >&2; exit 66; }
[[ -d "${source_data}" ]] || { echo "ERROR: source missing: ${source_data}" >&2; exit 66; }
[[ -f "${VERIFY_TOOL}" ]] || { echo "ERROR: verifier missing: ${VERIFY_TOOL}" >&2; exit 66; }

source_kb_code="$(du -sk "${source_code}" | awk '{print $1}')"
source_kb_data="$(du -sk "${source_data}" | awk '{print $1}')"
source_kb=$((source_kb_code + source_kb_data))
required_kb=$((source_kb + source_kb / 5 + 102400))
free_kb="$(df -Pk "${volume}" | awk 'END {print $4}')"
if [[ -n "${free_kb}" && "${free_kb}" -lt "${required_kb}" ]]; then
  echo "ERROR: external drive lacks space. Need roughly ${required_kb} KB; free ${free_kb} KB." >&2
  exit 72
fi

host_name="$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo mac)"
host_name="$(printf '%s' "${host_name}" | tr -cd 'A-Za-z0-9._-')"
[[ -n "${host_name}" ]] || host_name="mac"

backup_parent="${volume}/JUICE_BACKUPS/${host_name}"
snapshot_name="${timestamp}"
if [[ -e "${backup_parent}/${snapshot_name}" || -e "${backup_parent}/.incomplete-${snapshot_name}" ]]; then
  snapshot_name="${timestamp}-$$"
fi
stage="${backup_parent}/.incomplete-${snapshot_name}"
final_snapshot="${backup_parent}/${snapshot_name}"
manifest_path="${stage}/MANIFEST.json"

echo "JUICE external backup"
echo "  code:        ${source_code}"
echo "  data:        ${source_data}"
echo "  destination: ${final_snapshot}"
echo "  encryption:  ${encryption}"
echo "  estimated:   ${source_kb} KB"

if [[ ${dry_run} -eq 1 ]]; then
  echo "PASS preflight: dry run only; no files copied."
  write_state "dry-run" "Backup preflight passed; no files copied"
  completed=1
  exit 0
fi

mkdir -p "${stage}"
printf 'INCOMPLETE\n' > "${stage}/.INCOMPLETE"

copy_tree() {
  local source="$1"
  local destination="$2"
  if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]] && command -v ditto >/dev/null 2>&1; then
    ditto --rsrc --extattr --acl "${source}" "${destination}"
  else
    cp -a "${source}" "${destination}"
  fi
}

write_state "copying" "Copying JUICE code and data"
echo
echo "PASS 1/5 preflight"
echo "PASS 2/5 copy: starting"
copy_tree "${source_code}" "${stage}/JUICE"
copy_tree "${source_data}" "${stage}/JUICE_DATA"
echo "PASS 2/5 copy: complete"

echo "PASS 3/5 source-to-backup cryptographic comparison"
python3 "${VERIFY_TOOL}" compare \
  --source "JUICE=${source_code}" \
  --source "JUICE_DATA=${source_data}" \
  --backup-root "${stage}" \
  --manifest-out "${manifest_path}"

echo "PASS 4/5 independent manifest verification"
python3 "${VERIFY_TOOL}" verify \
  --manifest "${manifest_path}" \
  --backup-root "${stage}"

echo "PASS 5/5 restore drill"
python3 "${VERIFY_TOOL}" restore-drill \
  --manifest "${manifest_path}" \
  --backup-root "${stage}" \
  --sample-count "${JUICE_RESTORE_SAMPLE_COUNT:-25}"

python3 - "${stage}/COMPLETED.json" "${manifest_path}" <<'PY'
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path

out = Path(sys.argv[1])
manifest = Path(sys.argv[2])
payload = {
    "format": "juice-backup-completion-v1",
    "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    "passes": [
        "preflight",
        "copy",
        "source-to-backup-compare",
        "manifest-reverify",
        "restore-drill",
    ],
}
tmp = out.with_name(f".{out.name}.tmp-{os.getpid()}")
tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(tmp, out)
PY

rm -f "${stage}/.INCOMPLETE"
mv "${stage}" "${final_snapshot}"
manifest_path="${final_snapshot}/MANIFEST.json"
printf '%s\n' "${final_snapshot}" > "${backup_parent}/LATEST.txt"
write_state "success" "Backup completed and passed all verification passes" "${final_snapshot}" "${manifest_path}"
completed=1

echo
echo "ROCK SOLID: backup completed and verified."
echo "Snapshot: ${final_snapshot}"
echo "Manifest: ${manifest_path}"
echo "Log:      ${log_file}"
