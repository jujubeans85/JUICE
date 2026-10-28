# Verification record — 28 October 2026

Base: `d06af3b2f4e16e6e4b12dfdef1a94abb6c44a726`.
Branch: `feat/control-audio-intake`.

## Executed in the development container

Environment: Linux, Python 3.12.14, Node v24.22.1.

| Check | Observed result |
| --- | --- |
| `bash CONTROL/scripts/test-intake.sh` | 42 Python tests passed; JavaScript syntax passed; four UI scenarios passed |
| ZIP mutation regression (included above) | 100 seeded small mutations terminated as accepted/rejected receipts |
| `python3 READER/tests/regression.py` | Existing Reader regression passed, including five Node behavior tests and package parity |
| `bash -n CONTROL/start.command CONTROL/scripts/*.sh` | Passed |
| `git diff --check` | Passed |

The backend suite uses temporary storage, real HTTP requests, and a TCP
half-close during upload. The interrupted file remains unpublished, its durable
receipt says interrupted, and a full retry succeeds. Restart recovery is tested
against on-disk receiving/partial state. Bounds use smaller configured limits
for deterministic tests; a real 2 GiB/8 GiB transfer was not performed.

The UI checks run the actual intake adapter with DOM/network doubles. They verify
all dropped/selected stems are submitted, blocked browser storage is tolerated,
remaining stems continue after one HTTP failure, and cancellation leaves the
unfinished files visible. They do not establish Safari/Firefox behavior.

Installer tests verify a fresh install, backups/overlay preservation of a local
module, and refusal to change an unrecognized live server. Zed HTTP tests mock the
actual app launch while checking all four existing folder targets. They do not
establish that Zed opens on the user's Mac.

## Not verified by these results

- The user's Mac, its current 8780 drop-zone source, listener ownership, capture
  registry, LaunchAgent or installed audio processors.
- An actual Safari/Firefox drop, the original MAC DREAMS bundle, or cloud-file
  download availability on that Mac.
- Full audio decoding, listening, matching stem duration/sample rate/alignment,
  FFmpeg/Demucs processing or native Logic project generation.
- ChatGPT attachment behavior.

CI is configured for hosted Ubuntu/Python 3.12 and macOS/Python 3.9. The workflow's
actual run status must be checked independently; configuration is not a passing
result. Even a hosted macOS pass does not complete the user's Mac checklist in
[AUDIO_INTAKE.md](../AUDIO_INTAKE.md).
