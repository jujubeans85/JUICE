# Music delivery and acceptance record

Date: 16 November 2026 (Australia/Sydney).

## Implemented and verified here

The code is integrated into the existing repository `CONTROL/server.py`; the
Music Door and both client sizes use the same API and job store. The server
continues to bind to loopback. Generation is performed by a separately configured
ComfyUI engine, not in a browser or on the phone.

53 automated Python checks pass. They exercise workflow contracts, durable queue
behavior, concurrency/idempotency, source preservation, restart and result
recovery, the actual HTTP adapter, private identity/origin boundaries, upload
validation and audio byte ranges. A local fake Comfy HTTP server exercises
transport and output handling. These are integration tests using a test double;
they do not run the YuE2 model.

JavaScript syntax checks pass for the app and service worker. Static file routes
and assets are checked. The home-screen icons were visually inspected.

The real interface also passes a Chromium browser integration run at 390 × 844,
834 × 1112 and 1440 × 1000. Each size exercises presets, saved drafts, the real JC
HTTP/service queue, Keep/filter, source upload, melody-based rework and displaying
the newly submitted take. Six fixture jobs complete without duplicate submission.
Create, Takes, Rework and Setup have no horizontal overflow at those widths, and
the screenshots have been inspected. These tests use an explicit fake engine and
do not decode or listen to its fixture audio.

The generated standalone preview also opens as a local file, supports editable
presets and tab navigation, keeps generation disabled and performs no fetch,
service-worker registration or external network requests. This does not establish
installed-PWA offline operation.

Evidence: [successful browser and backend CI run](https://github.com/jujubeans85/JUICE/actions/runs/43733881346)
for commit `a6df51a33b9a3e9a5360b9fa3df134d5b19288f9`. The workflow runs
`CONTROL/tests/music_browser.py` and uploads viewport screenshots and its log;
those Actions artifacts have a seven-day retention period.

## Explicitly not yet verified

- A complete YuE2 GPU generation, its speed or its musical quality.
- Generation on the user's Mac mini M2.
- Physical iPhone/iPad Safari installation, playback or file sharing.
- A live Tailscale private connection.
- Installed-PWA offline operation on a physical device.
- The exact supplied `yue2_full.json`; its download was blocked. Graphs were
  independently authored from the official current node definitions.

The offline preview is generated from the same HTML, CSS and JavaScript, with
network access and generation disabled. It is a review artifact, not a second
runtime, library or music engine.

## Deployment acceptance

Identify the live Mac checkout/process before applying the change. Preserve the
current server and unmerged changes on PRs #3, #7 and #12. The reviewed patch must
be integrated into that real checkout rather than copied over an unknown runtime.

Then complete the first-generation proof in SETUP_ENGINE.md and the physical
device check in SETUP_IOS.md. Record the working Comfy commit, model file hashes,
device, memory, requested maximum and actual audio duration, wall time, and any
vocal/lyric/cover issues heard. Keep those local records with the first take.

No merge, live-Mac installation, model download or paid GPU provisioning is
claimed by this delivery record.
