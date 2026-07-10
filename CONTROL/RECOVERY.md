# JUICE recovery

## What must exist

```text
~/JUICE/CONTROL          public code and control scripts
~/JUICE_DATA             private live data
external/JUICE_BACKUPS   timestamped verified snapshots
```

## Restore after a damaged CONTROL install

```sh
cd ~/JUICE
git status
git pull --ff-only
bash CONTROL/scripts/install.sh
bash ~/JUICE/CONTROL/scripts/install_launch_agent.sh
bash ~/JUICE/CONTROL/scripts/verify.sh
bash ~/JUICE/CONTROL/scripts/doctor.sh
```

Do not pull over unexplained local changes. Copy or commit them first.

## Restore private data from an external snapshot

1. Stop JUICE Control:

   ```sh
   launchctl bootout "gui/$(id -u)" \
     "$HOME/Library/LaunchAgents/com.juice.control.plist" 2>/dev/null || true
   ```

2. Select a snapshot containing both `COMPLETED.json` and `MANIFEST.json`.

3. Verify it before restoring:

   ```sh
   SNAPSHOT="/Volumes/YOUR_DRIVE/JUICE_BACKUPS/MAC_NAME/TIMESTAMP"

   python3 ~/JUICE/CONTROL/scripts/verify_backup.py verify \
     --manifest "$SNAPSHOT/MANIFEST.json" \
     --backup-root "$SNAPSHOT"
   ```

4. Move the damaged live data aside. Do not delete it:

   ```sh
   mv ~/JUICE_DATA ~/JUICE_DATA.damaged.$(date +%Y%m%d-%H%M%S)
   ```

5. Restore:

   ```sh
   ditto --rsrc --extattr --acl \
     "$SNAPSHOT/JUICE_DATA" \
     "$HOME/JUICE_DATA"
   ```

6. Reinstall startup and run the doctor:

   ```sh
   bash ~/JUICE/CONTROL/scripts/install_launch_agent.sh
   bash ~/JUICE/CONTROL/scripts/doctor.sh --strict --deep
   ```

## Clean-Mac recovery

Clone the public repository into `~/JUICE`, restore `JUICE_DATA` as above, then run:

```sh
bash ~/JUICE/CONTROL/scripts/finish_setup.sh --skip-backup --yes
```

After confirming the restored live data, run a fresh external backup.

## Important limit

A folder existing is not proof that its contents were recovered. Recovery is complete only after the manifest verifies, the application starts, and representative private files open correctly.
