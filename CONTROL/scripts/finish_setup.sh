#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_CONTROL="$(cd "$(dirname "$0")/.." && pwd)"
DATA_ROOT="${JUICE_DATA_ROOT:-${HOME}/JUICE_DATA}"
REPORT_ROOT="${DATA_ROOT}/ADMIN/setup-reports"
backup_volume=""
yes=0
allow_unencrypted=0
skip_backup=0
skip_launch_agent=0

usage() {
  cat <<'USAGE'
Usage:
  finish_setup.sh --backup-volume "/Volumes/DRIVE" [--yes] [--allow-unencrypted]
  finish_setup.sh [--yes]                  # uses an already configured drive

Options:
  --skip-backup        Install and verify, but do not run the external backup.
  --skip-launch-agent  Do not install automatic login startup.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-volume)
      [[ $# -ge 2 ]] || { echo "ERROR: --backup-volume needs a path" >&2; exit 64; }
      backup_volume="$2"
      shift 2
      ;;
    --yes)
      yes=1
      shift
      ;;
    --allow-unencrypted)
      allow_unencrypted=1
      shift
      ;;
    --skip-backup)
      skip_backup=1
      shift
      ;;
    --skip-launch-agent)
      skip_launch_agent=1
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

if [[ "$(uname -s 2>/dev/null || true)" != "Darwin" ]]; then
  echo "ERROR: finish_setup.sh must run on the physical Mac." >&2
  exit 69
fi

mkdir -p "${REPORT_ROOT}"
report="${REPORT_ROOT}/finish-setup-$(date '+%Y%m%d-%H%M%S').log"
touch "${report}"
chmod 600 "${report}" 2>/dev/null || true
exec > >(tee -a "${report}") 2>&1

echo "JUICE Mac mini HOME setup"
echo "Evidence log: ${report}"
echo

echo "STEP 1 — observe current state"
bash "${SOURCE_CONTROL}/scripts/audit.sh"

echo
echo "STEP 2 — install canonical CONTROL and private data layout"
bash "${SOURCE_CONTROL}/scripts/install.sh"
ACTIVE_CONTROL="${HOME}/JUICE/CONTROL"

echo
echo "STEP 3 — run six-pass software verification"
bash "${ACTIVE_CONTROL}/scripts/verify.sh"

if [[ -n "${backup_volume}" ]]; then
  echo
  echo "STEP 4 — initialise the explicitly selected external drive"
  init_args=("${backup_volume}")
  [[ ${yes} -eq 1 ]] && init_args+=("--yes")
  [[ ${allow_unencrypted} -eq 1 ]] && init_args+=("--allow-unencrypted")
  bash "${ACTIVE_CONTROL}/scripts/init_backup_drive.sh" "${init_args[@]}"
else
  echo
  echo "STEP 4 — use existing external-drive configuration"
fi

if [[ ${skip_launch_agent} -eq 0 ]]; then
  echo
  echo "STEP 5 — install and start the user LaunchAgent"
  bash "${ACTIVE_CONTROL}/scripts/install_launch_agent.sh"
else
  echo "STEP 5 — LaunchAgent skipped; start one local session for acceptance"
  mkdir -p "${DATA_ROOT}/LOGS"
  JUICE_CONTROL_OPEN_BROWSER=0 nohup bash "${ACTIVE_CONTROL}/scripts/run_service.sh" \
    >> "${DATA_ROOT}/LOGS/juice-control.manual.log" 2>&1 &
  manual_service_pid=$!
  healthy=0
  for _ in $(seq 1 20); do
    if curl -fsS --max-time 1 "http://127.0.0.1:${JUICE_CONTROL_PORT:-8765}/health" \
      | grep -q '"service": "juice-control"'; then
      healthy=1
      break
    fi
    sleep 0.25
  done
  if [[ ${healthy} -ne 1 ]]; then
    echo "ERROR: manually started JUICE Control did not become healthy (pid ${manual_service_pid})." >&2
    exit 70
  fi
fi

if [[ ${skip_backup} -eq 0 ]]; then
  echo
  echo "STEP 6 — copy to external drive and run five backup verification passes"
  backup_args=()
  [[ -n "${backup_volume}" ]] && backup_args+=("--volume" "${backup_volume}")
  [[ ${allow_unencrypted} -eq 1 ]] && backup_args+=("--allow-unencrypted")
  bash "${ACTIVE_CONTROL}/scripts/backup_external.sh" "${backup_args[@]}"
else
  echo "STEP 6 — external backup skipped by explicit request"
fi

echo
echo "STEP 7 — final strict doctor and independent deep backup re-verification"
doctor_args=("--strict")
[[ ${skip_backup} -eq 0 ]] && doctor_args+=("--deep") || doctor_args+=("--allow-no-backup")
[[ ${skip_launch_agent} -eq 1 ]] && doctor_args+=("--allow-no-launch-agent")
bash "${ACTIVE_CONTROL}/scripts/doctor.sh" "${doctor_args[@]}"

echo
echo "STEP 8 — live service acceptance"
health="$(curl -fsS --max-time 5 "http://127.0.0.1:${JUICE_CONTROL_PORT:-8765}/health")"
printf '%s\n' "${health}"
printf '%s' "${health}" | grep -q '"service": "juice-control"'

echo
echo "ROCK SOLID: automated Mac-side setup, startup, backup and verification passed."
echo "Report: ${report}"
echo "Open:   http://127.0.0.1:${JUICE_CONTROL_PORT:-8765}/"
