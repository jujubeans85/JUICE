# JUICE Control

A local-only HOME control interface for the Mac mini.

It is deliberately small: Python standard library, shell scripts, Zed integration, an external-drive backup path, a user LaunchAgent, diagnostics, and tests. No database. No cloud dependency. No arbitrary command box.

## Privacy boundary

This repository is public code and documentation only.

**Never commit health information, family records, personal memories, credentials, API keys, private photos, or actual contents from `~/JUICE_DATA`.** Private material belongs under `~/JUICE_DATA` and on its encrypted external backup.

## One-command physical-Mac setup

First mount an **encrypted external APFS volume**. Then:

```sh
cd ~/JUICE
git pull --ff-only
bash CONTROL/scripts/finish_setup.sh \
  --backup-volume "/Volumes/YOUR_DRIVE" \
  --yes
```

The setup orchestrator:

1. Captures a private state audit.
2. Installs the canonical `~/JUICE/CONTROL` layout.
3. Runs six software verification passes.
4. Initialises the exact external volume with a safety sentinel.
5. Installs and starts the user LaunchAgent.
6. Creates an immutable external snapshot.
7. Runs full SHA-256 comparison, re-verification, and a restore drill.
8. Runs a strict final doctor and checks the live HTTP service.

It does not erase, format, prune, or delete external-drive snapshots.

## Manual commands

```sh
# Audit only
bash ~/JUICE/CONTROL/scripts/audit.sh

# Software verification
bash ~/JUICE/CONTROL/scripts/verify.sh

# Initialise a selected external drive once
bash ~/JUICE/CONTROL/scripts/init_backup_drive.sh "/Volumes/YOUR_DRIVE"

# Verified backup
bash ~/JUICE/CONTROL/scripts/backup_external.sh

# Install automatic login startup
bash ~/JUICE/CONTROL/scripts/install_launch_agent.sh

# Deep system doctor
bash ~/JUICE/CONTROL/scripts/doctor.sh --strict --deep

# Open the interface
open http://127.0.0.1:8765/
```

## Backup guarantees and limits

Each backup is written to:

```text
/Volumes/YOUR_DRIVE/JUICE_BACKUPS/<mac-name>/<timestamp>/
```

A snapshot is not marked complete until five passes succeed:

1. Destination and source preflight.
2. Copy.
3. Full source-to-backup SHA-256 comparison.
4. Independent verification against the generated manifest.
5. Restore-and-rehash drill on a deterministic file sample.

The script preserves old snapshots and never prunes them automatically. This avoids clever retention logic quietly eating the only good copy.

The external disk is still a physical object. Theft, fire, controller failure, or two disks dying together remain possible. A second independent backup—such as Time Machine to another device—is still sensible.

## Startup and recovery

The LaunchAgent is:

```text
~/Library/LaunchAgents/com.juice.control.plist
```

Logs are under:

```text
~/JUICE_DATA/LOGS/
```

Recovery instructions are in [`RECOVERY.md`](RECOVERY.md).

## Security

JUICE Control binds to `127.0.0.1` by default. It rejects non-loopback binding unless `JUICE_ALLOW_REMOTE=1` is explicitly set. That override is not authentication and should not be used as a shortcut for phone access or router port-forwarding.

State-changing browser actions use a per-process action token. Only fixed allowlisted actions exist.

## Zed

The opener tries, in order:

1. `ZED_CLI`.
2. `zed` or `zed-preview` in common paths.
3. Zed application-bundle executables.
4. macOS `open -a Zed` fallback.

If required, open Zed and run:

```text
Command Palette → zed: install cli
```
