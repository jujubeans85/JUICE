# Mac mini HOME setup boundary

The automated setup handles JUICE code, data layout, startup, health checks, external snapshots, manifests, and restore drills.

These physical or privileged items must be deliberately confirmed on the actual Mac:

- FileVault is enabled and its recovery method is known.
- The external backup volume is encrypted.
- The Mac has reliable power; add a UPS if interruption matters.
- “Start up automatically after a power failure” is enabled where supported.
- Ethernet is preferred for a stationary control Mac.
- A keyboard/display recovery path exists even if the normal interface is remote.
- No router port is forwarded to JUICE Control.
- A second independent backup exists for genuinely irreplaceable material.

Useful observation commands:

```sh
fdesetup status
pmset -g
tmutil destinationinfo
diskutil info "/Volumes/YOUR_DRIVE"
```

Do not automate disk formatting, FileVault changes, account changes, or remote-access exposure inside a general setup script. Those are high-blast-radius operations and deserve explicit physical confirmation.
