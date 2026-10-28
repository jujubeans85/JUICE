#!/usr/bin/env bash
# Read-only: identify the two recorded JC endpoints before changing a live Mac.
set -Eeuo pipefail
printf 'Current checkout: %s\n' "$(cd "$(dirname "$0")/.." && pwd)"
for port in 8765 8780; do
  printf '\nJC listener on port %s\n' "$port"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN || true
    while IFS= read -r pid; do
      [[ "$pid" =~ ^[0-9]+$ ]] || continue
      ps -p "$pid" -o pid=,command= || true
      lsof -a -p "$pid" -d cwd -Fn 2>/dev/null || true
    done < <(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u)
  fi
  python3 - "$port" <<'PY'
import json
import sys
from urllib.request import urlopen
port = int(sys.argv[1])
for route in ('/health', '/api/intake'):
    try:
        with urlopen(f'http://127.0.0.1:{port}{route}', timeout=2) as response:
            raw = response.read(16385)
            if len(raw) > 16384:
                raise ValueError('response exceeds diagnostic bound')
            data = json.loads(raw)
        if route == '/health':
            print('Health:', {k: data.get(k) for k in ('app', 'version', 'capabilities')})
        else:
            print('Intake:', {k: data.get(k) for k in ('staging_root', 'processing', 'logic_project')})
    except (OSError, ValueError, AttributeError) as exc:
        print(route, 'unverified:', str(exc))
PY
done
printf '\nNo processes, services, files or ports were changed.\n'
