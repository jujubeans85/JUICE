# Skill Radar integration

This adds a **disabled-by-default** route adapter and same-tab JC link. The canonical detector, instructions, audit, ballot, UI and private runtime decisions belong to JUICE-SKILLS. There is no copied catalogue or detector here, and no automatic producer is connected.

Read the private [complete installation and data-flow handoff](https://github.com/jujubeans85/JUICE-SKILLS/blob/codex/skill-radar-jc/docs/JC_INTEGRATION.md) before enabling anything. Obtain explicit approval of manual collection first. This public repository contains only generic code, documentation and synthetic tests.

`JUICE_RADAR_MODE` defaults to `disabled`. Only `manual-v1` is implemented; it requires an explicit `JUICE_SKILLS_ROOT` pointing outside this public checkout at the reviewed private JUICE-SKILLS clone. No third-party libraries, background process, event database, polling or new port are added.

The existing main server has no completion-summary feed. Folder opens, audio upload receipts and Reader deliveries are not workflow completion. The actual Mac server on port 8780 remains unverified. Do not overwrite a custom server or create a second dashboard. `scripts/install-radar.py` dry-runs by default, backs up just two changed files when applied, preserves other modules and refuses an unknown server. It does not activate collection or modify the current launcher.

Test with a reviewed sibling companion checkout (or set `JUICE_RADAR_TEST_SKILLS_ROOT`):

```sh
python3 -m unittest discover -s CONTROL/tests -v
```

The API is private to the local panel: status, manual events, on-demand review/ballot, decisions and pause. No activate endpoint, automatic subscription, GitHub publication or skill installation exists. All new write routes require loopback binding/client, exact Host/Origin and a per-process token; request contents are not logged. A missing/corrupt companion fails closed while normal JC routes continue working.
