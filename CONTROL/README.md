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
