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

## Project build intake

- [AFTERWORLDS](projects/afterworlds/README.md) — screenshot points, research leads and image/file intake. The repository handoff is ready; live Universal Capture wiring must be verified against the current Mac checkout.

## ZIP and audio-stem intake

The existing Control home page now accepts dropped ZIP bundles and multiple WAV,
AIFF/AIF and MP3 files. Sources and receipts live outside Git at
`~/JUICE_DATA/CAPTURE/audio-intake/<batch-id>/` (or under `JUICE_DATA_ROOT`).
There is no browser audio queue, multipart buffering, or new service.

**Read [AUDIO_INTAKE.md](AUDIO_INTAKE.md) before updating a live Mac.** The reported
JC audio interface used port 8780; this repository defaults to 8765 and does not
contain that dashboard's source. The read-only identification command is:

```sh
bash ~/JUICE/CONTROL/scripts/identify-jc.sh
```

The installer now refuses an unrecognized target server and overlays files after
backup rather than deleting local modules. Do not replace a divergent live JC
server to obtain this feature; merge the intake into its existing capture owner.

Run the executable regression suite (Python 3.9+ and Node 18+):

```sh
bash CONTROL/scripts/test-intake.sh
```

Python alone runs the backend/HTTP tests:

```sh
python3 -m unittest discover -s CONTROL/tests -v
```

Intake stages sources for `$flood-my-ears`; processing and native Logic project
authoring are not connected or verified. Local intake changes do not alter
ChatGPT attachment restrictions.
