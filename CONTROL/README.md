# JUICE Control

Local-only control interface for the JUICE folders, pinned to Zed as the editor.

## What this fixes

`start.command` and the browser buttons no longer depend on an interactive terminal PATH. The Zed opener tries, in order:

1. `ZED_CLI` if you set it.
2. `zed` or `zed-preview` from common Homebrew/macOS paths.
3. Zed app bundle executables in `/Applications` or `~/Applications`.
4. macOS `open -a Zed` / `open -a "Zed Preview"` fallback.

That makes the control interface keep working when launched from Finder, Zed, Terminal, or a restored backup.

## Install / repair

```sh
cd ~/JUICE/CONTROL
chmod +x start.command server.py scripts/*.sh
./scripts/install.sh
./start.command
```

The installer recreates:

- `~/JUICE_DATA/CREATIVE`
- `~/JUICE_DATA/BUILD/Repos`
- `~/JUICE_DATA/CAPTURE`

## Doctor

```sh
cd ~/JUICE/CONTROL
./scripts/doctor.sh
```

## Zed manual fix

If doctor says Zed is missing, open Zed and run:

```text
Command Palette -> zed: install cli
```

The app fallback should still work even before the CLI is installed, as long as Zed is in `/Applications` or `~/Applications`.

## Monthly portfolio maintenance

The home page links to `/maintenance`: the latest local public audit report at
`~/JUICE_DATA/MAINTENANCE/latest/report.html`, with the committed baseline as a
fallback. It also links to the GitHub Actions audit history. Viewing a report
does not run commands or change repositories. The timestamp identifies stale
local evidence; reports are snapshots, not a live dashboard.

Run the one collector from the JUICE root with an existing read credential:

```sh
python3 MAINTENANCE/portfolio_audit.py --previous-from-actions \
  --output ~/JUICE_DATA/MAINTENANCE/latest
```

Read [the operating procedure](../MAINTENANCE/README.md) for scope, permissions,
state retention, rollback and private coverage. This integrates the known 8765
server source only; the actual Mac and reported 8780 interface are unverified.

## Project build intake

- [AFTERWORLDS](projects/afterworlds/README.md) — screenshot points, research leads and image/file intake. The repository handoff is ready; live Universal Capture wiring must be verified against the current Mac checkout.
