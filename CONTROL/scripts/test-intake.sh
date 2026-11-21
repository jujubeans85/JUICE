#!/usr/bin/env bash
set -Eeuo pipefail
CONTROL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m unittest discover -s "${CONTROL_DIR}/tests" -v
node --check "${CONTROL_DIR}/intake.js"
node "${CONTROL_DIR}/tests/intake-ui.cjs"
