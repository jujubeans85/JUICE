#!/usr/bin/env bash
set -Eeuo pipefail

# Opens a file/folder in Zed without depending on an interactive shell PATH.
# Usage:
#   scripts/open_in_zed.sh ~/JUICE_DATA/BUILD/Repos
#   scripts/open_in_zed.sh --status
#   scripts/open_in_zed.sh --print-command

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${HOME}/.local/bin:${PATH:-}"

resolve_zed_cli() {
  if [[ -n "${ZED_CLI:-}" && -x "${ZED_CLI}" ]]; then
    printf '%s\n' "${ZED_CLI}"
    return 0
  fi

  local found
  for name in zed zed-preview; do
    if found="$(command -v "${name}" 2>/dev/null)"; then
      printf '%s\n' "${found}"
      return 0
    fi
  done

  local app candidate
  for app in \
    "/Applications/Zed.app" \
    "${HOME}/Applications/Zed.app" \
    "/Applications/Zed Preview.app" \
    "${HOME}/Applications/Zed Preview.app"; do
    for candidate in \
      "${app}/Contents/MacOS/cli" \
      "${app}/Contents/MacOS/zed" \
      "${app}/Contents/MacOS/Zed"; do
      if [[ -x "${candidate}" ]]; then
        printf '%s\n' "${candidate}"
        return 0
      fi
    done
  done

  return 1
}

zed_app_available() {
  [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]] || return 1
  command -v open >/dev/null 2>&1 || return 1

  # This checks the Launch Services registry without launching the app.
  if command -v osascript >/dev/null 2>&1; then
    osascript -e 'id of application "Zed"' >/dev/null 2>&1 && return 0
    osascript -e 'id of application "Zed Preview"' >/dev/null 2>&1 && return 0
  fi

  [[ -d "/Applications/Zed.app" || -d "${HOME}/Applications/Zed.app" || -d "/Applications/Zed Preview.app" || -d "${HOME}/Applications/Zed Preview.app" ]]
}

print_command() {
  local cli
  if cli="$(resolve_zed_cli)"; then
    printf '%s\n' "${cli}"
    return 0
  fi
  if zed_app_available; then
    printf '%s\n' 'open -a Zed'
    return 0
  fi
  return 1
}

if [[ "${1:-}" == "--print-command" ]]; then
  print_command
  exit $?
fi

if [[ "${1:-}" == "--status" ]]; then
  if cmd="$(print_command)"; then
    printf 'Zed available: %s\n' "${cmd}"
    exit 0
  fi
  cat >&2 <<'STATUS'
Zed is not available to JUICE Control.
Install Zed, then in Zed run: Command Palette -> zed: install cli
This script also supports /Applications/Zed.app and open -a Zed as fallbacks.
STATUS
  exit 1
fi

target="${1:-.}"
if [[ ! -e "${target}" ]]; then
  printf 'Path does not exist: %s\n' "${target}" >&2
  exit 2
fi

if cli="$(resolve_zed_cli)"; then
  exec "${cli}" "${target}"
fi

if zed_app_available; then
  # Prefer the stable app name; if that fails, try Preview.
  open -a "Zed" "${target}" >/dev/null 2>&1 && exit 0
  open -a "Zed Preview" "${target}" >/dev/null 2>&1 && exit 0
fi

cat >&2 <<'ERROR'
Could not open Zed.
Install Zed or install its CLI from inside Zed: Command Palette -> zed: install cli
ERROR
exit 1
