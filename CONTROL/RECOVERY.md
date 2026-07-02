# Recovery

1. Restore the `CONTROL` folder from Git or a backup ZIP.
2. Place it at `~/JUICE/CONTROL`.
3. Run `chmod +x start.command server.py scripts/*.sh`.
4. Recreate `~/JUICE_DATA/CREATIVE`, `~/JUICE_DATA/BUILD/Repos`, and `~/JUICE_DATA/CAPTURE`.
5. Run `./start.command`.

No database migration is required.

For Zed-specific failures, run `./scripts/doctor.sh`. The permanent opener is `./scripts/open_in_zed.sh`; it does not rely on Finder inheriting your shell PATH.
