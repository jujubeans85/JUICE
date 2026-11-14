# Mac-local ZIP and stem intake

## Scope and interface evidence

The reported failure concerned the existing JC audio drop zone, with prior
session records pointing to `http://127.0.0.1:8780/`, a single-audio-file processor,
and a browser storage/first-file-only failure. These are earlier session records,
not an inspection of the current Mac. A July live audit placed an older Control
at `~/JUICE/CONTROL` on 8765. The GitHub main checkout at
`d06af3b2f4e16e6e4b12dfdef1a94abb6c44a726` implements the folder/Zed server on 8765,
without an audio uploader, worker or Logic generator. Its available remote
branches also do not supply the recorded 8780 audio dashboard.

This change adds intake inside that existing `CONTROL/server.py` and its home
page. It adds no other server, daemon, watcher, database, offline audio store or
processing queue. The live 8780 dashboard has not been patched: its source and
current process must first be identified on the Mac. Do not report the original
8780 rejection as repaired until that interface passes the checklist below.
ChatGPT's own attachment controls are outside the scope of this server.

## Identify before installing

From the review checkout, run on the Mac:

```sh
bash CONTROL/scripts/identify-jc.sh
```

This reads listener PIDs, process commands, working directories and bounded JSON
health/intake responses on both 8765 and 8780. It changes nothing. Inspect the
identified source for its capture route, drop handler, queue owner and audio
processor; do not infer ownership from a port number or page title. Keep this
output private because it may contain local paths/process arguments.

If the target server differs from the known repository baseline, `install.sh`
refuses the replacement before modifying target files. That is a deliberate
protection for locally installed routes/modules. Preserve the live source and
merge the integration described below into that owner. Merely running this
repository on 8780 does not integrate or repair the separate dashboard.

## Review and install a matching checkout

Runtime: macOS, Python 3.9+ standard library. Node 18+ is needed only for the UI
tests; no Python packages, audio packages, credentials or paid services are added.

Use an isolated review checkout so local JC work is preserved:

```sh
git clone --branch feat/control-audio-intake https://github.com/jujubeans85/JUICE.git ~/JUICE-intake-review
cd ~/JUICE-intake-review
bash CONTROL/scripts/identify-jc.sh
bash CONTROL/scripts/test-intake.sh
bash CONTROL/scripts/install.sh
```

The installer backs up an existing matching `~/JUICE/CONTROL` to
`~/JUICE/CONTROL.backups/CONTROL.<timestamp>.<pid>`, then overlays the distribution;
it preserves untracked capture/config/modules. It does not stop or restart a
process. If it refuses a divergent server, use the integration path below.

After verifying which process owns JC, quit that specific old instance using its
existing launcher/service. If a LaunchAgent owns it, use that agent's normal
restart procedure; do not kill all Python processes or install a second agent.
Start the updated matching Control:

```sh
cd ~/JUICE/CONTROL
bash start.command
```

It opens `http://127.0.0.1:8765/` by default. `JUICE_CONTROL_PORT` selects a port
only after its ownership is verified. Only loopback hosts are accepted. A running
instance is reused only if `/health` matches this exact app/version. An old or
unrelated listener produces a clear restart diagnostic. Reload old browser tabs
because session tokens change on restart. A process lock prevents two instances
from recovering/writing the same intake store on different ports.

`JUICE_DATA_ROOT` relocates all data; it defaults to `~/JUICE_DATA`.
`JUICE_CONTROL_ROOT` points folder/Zed actions at the installed Control folder;
`start.command` sets it to its own directory. Existing `ZED_CLI` discovery and app
fallbacks remain available.

## Use and staging contract

Drop a ZIP or select multiple stems in the existing Control home page. Files are
sent sequentially as raw `File` bodies; no whole-file JavaScript reads, Base64,
IndexedDB or offline queue. Browser localStorage is optional and holds only the
last receipt ID. The picker/drop adapter enumerates every selected file.

Each drop gets one batch ID and one atomic, disk-backed manifest:

```text
~/JUICE_DATA/CAPTURE/audio-intake/<batch-id>/
  manifest.json
  originals/0000/source.zip
  originals/0001/lead.wav
  audio/0000/0000/drums.wav
  audio/0000/0001/bass.wav
  audio/0001/lead.wav
```

Numeric source/member namespaces preserve duplicate names, case variants and
Unicode-equivalent names on common Mac filesystems. ZIP member names remain in
the receipt; extracted basenames use NFC normalization. There are no overwrite
or flattening collisions.

Complete original uploads remain byte-identical, SHA-256 recorded and read-only
(mode 0400). A complete corrupt/rejected archive is retained with its rejection
receipt. Failed or cancelled byte transfers publish no partial original; their
`.part` files are removed. Extracted audio is a separate working copy. No source
is normalized, converted, time-stretched or mixed by intake.

`manifest.json` uses schema `juice.audio-intake/v1`. `files[]` records every input
with `pending`, `receiving`, `interrupted`, `accepted` or `rejected`, plus a reason,
original path and checksum when available. ZIP `entries[]` names every readable
central-directory entry, including unsupported files and skipped metadata. An
unreadable directory cannot supply a trustworthy entry inventory; the archive
itself is rejected with the parser error. Each accepted audio entry has its byte
count, SHA-256, relative working path and source-original reference.

An accepted archive can contain rejected unsupported entries; inspect the entry
report. Unsafe metadata, expansion-limit violations, member CRC failures or bad
audio headers reject the whole archive and remove its extracted working files.
No earlier accepted member is left marked accepted after rollback. Directories,
`__MACOSX`, `.DS_Store` and AppleDouble files are visibly skipped; nested archives
and nonaudio files are visibly rejected and never expanded.

`complete` means every upload finished as accepted/rejected. `ready` additionally
requires at least one accepted source; neither flag means music was processed.
A downstream tool must read the manifest and consume only accepted entry paths,
never scan for `.wav` files or watch partially extracted folders.

## Limits and interruption behavior

| Bound | Default |
| --- | --- |
| Files per drop | 128 |
| Uploaded source or extracted audio member | 2 GiB |
| Total declared uploads per drop | 8 GiB |
| Expanded audio per ZIP | 8 GiB |
| Upload reservation plus accepted working audio per drop | 16 GiB |
| ZIP entries | 2,048 |
| ZIP central directory | 8 MiB |
| Per-member uncompressed/compressed ratio | 1,000 |
| Stream copy chunk | 1 MiB |
| JSON selection request | 64 KiB |
| Socket inactivity timeout | 30 seconds |
| Required free-space reserve | 64 MiB |
| Concurrent upload/extraction operations | 1 (others receive 409) |

The code bounds metadata before `ZipFile` allocates its directory and verifies
the actual directory entry count. Store/deflate and ordinary ZIP64 are supported;
multi-disk, encrypted and unusual ZIP layouts/compression are rejected. Paths
with traversal, absolute roots, drive/alternate-stream syntax, backslashes, NUL,
control characters or excessive length/depth are rejected. Links and special
entries are rejected; ZIP-supplied permissions are never applied. Extraction
uses generated numeric namespaces, not `extractall`.

Limits are `IntakeStore` constructor settings; the current server uses these
fixed defaults and exposes them at `/api/intake`. Raising limits needs review
and corresponding tests. Limits apply per drop, not lifetime retention: completed
batches remain on disk until deliberately archived/deleted by the user. Disk-free
checks run before upload and expansion, and write failures are reported.

Cancel stops the current transfer and leaves later sources pending. Receipt
links survive page refresh; blocked browser storage does not prevent import.
After disconnection, inspect the receipt: a fully received/validated file may
already have completed even if its response was lost. Completed sources cannot
be uploaded over. A stopped process recovers `receiving` entries to `interrupted`
at next startup, removes partial working files and retains complete originals.
Retry interrupted files through the same batch/index API, or re-drop them in a
new batch in the UI. Re-dropping intentionally creates a new batch, not implicit
content deduplication. API retry compares bytes if an original survived a crash
and never overwrites differing bytes. This is retry-from-start, not resumable
byte-range transfer.

Header checks recognize WAV/AIFF/MP3 containers; they do not establish full decode
integrity, matching sample rates/durations, tempo, key, phase, alignment or sound
quality. ZIP CRC validates accepted member bytes. Unsupported filenames, empty
files and extension/header mismatches are reported explicitly.

## Reuse in the actual 8780 capture interface

Once its source is available, merge rather than replace its server/dashboard:

1. Instantiate one `IntakeStore` under the existing `JUICE_DATA_ROOT/CAPTURE` with
   one process owner. Reuse the existing authentication/job/event owner if one is
   present; do not create a duplicate queue or public action endpoint.
2. Mount the same routes below in that server and retain its other routes. Apply
   equivalent loopback, Host, Origin, session-token and request-size checks. The
   repository adapter is same-origin only; there is deliberately no cross-port
   CORS workaround.
3. Insert the intake markup into its existing capture area or call
   `window.JuiceAudioIntake.attach(element).importFiles(Array.from(files))` from
   that drop handler. Include the expected `data-*` controls from `intake.html`,
   the `juice-csrf` meta token, and the script once. Remove its audio bytes from
   any offline queue and ensure the drop does not also call a single-file
   processor. This is an integration contract, not a claim that source was edited.
4. Link the saved receipt/manifest into that capture's existing record. Do not
   enqueue processing from the presence of files alone. Verify the processor's
   actual interface and tests before passing accepted paths to it.

| Request | Contract |
| --- | --- |
| `GET /api/intake` | Bounds, staging path, honest processing status |
| `POST /api/intake/batches` | JSON `{"files":[{"name":"stems.zip","size":123}]}` → 201 receipt |
| `POST /api/intake/batches/<id>/files/<index>` | Exact declared `Content-Length`, raw file body → receipt |
| `GET /api/intake/batches/<id>` | Durable receipt, including partial/rejected outcomes |

POSTs require `X-Juice-Token` from the same page (folder forms use hidden `csrf`).
Chunked transfer, missing/duplicate/invalid lengths and cross-origin requests are
rejected. There is no arbitrary-path upload, extraction or shell-command API.

Prior CrateJuice records describe FFmpeg/ffprobe and optional Demucs, but those
components are absent from this repository and their current Mac installation
was not inspected. No worker hook is enabled based on that description. The
manifest is the verified handoff boundary here; processing and native `.logicx`
authoring remain unconnected. Future processing must keep derivatives linked to
sources, preserve the established Logic template if supplied, export stems from
a common origin and verify an actual native project before claiming one exists.

## Verification and Mac demo checklist

Automated checks are reproducible with:

```sh
bash CONTROL/scripts/test-intake.sh
```

They cover normal imports, multiple loose stems, duplicate/case/Unicode names,
mixed ZIP reports, corrupt/CRC/deflate archives, unsafe paths/NUL/links/special
entries, ZIP64, directory/member/ratio/upload/staging bounds, disk-space refusal,
real socket interruption and retry, restart recovery, bounded reads, no overwrite,
request validation, CSRF/origin/Host guards, startup version checks and existing
folder/Zed routes. UI network/DOM doubles exercise multiple-file picker/drop,
blocked storage, continuation after an upload error and cancellation. They are
not a real Safari/Firefox test or a listening test.

The CI workflow runs the suite on Ubuntu/Python 3.12 and a hosted macOS/Python 3.9
runner. A hosted Mac is still not Adam's Mac or its actual JC installation.
See [tests/VERIFICATION.md](tests/VERIFICATION.md) for recorded local results.

On the actual Mac, complete these before calling the reported JC failure fixed:

- [ ] Identify and preserve the live 8780 owner/source and verify capture wiring.
- [ ] Verify `/health` reports `2026.10-audio-intake-v1` on the intended interface.
- [ ] Drop the original `MAC_DREAMS_10_26.zip` and verify all nine expected WAVs,
      if that is still the source bundle. Compare the ZIP SHA-256 with the source.
- [ ] Drop several loose stems together in Firefox and Safari, including with
      browser storage blocked. Verify every source and receipt entry.
- [ ] Drop duplicate names and a mixed unsupported file. Confirm no overwrite and
      exact rejection reasons; inspect a bad/traversal ZIP's rollback.
- [ ] Cancel a transfer, reload, inspect the receipt, re-drop only unfinished files.
- [ ] Restart during a transfer and verify recovery without modifying originals.
- [ ] Open CONTROL, Creative, Build repos and Capture in real Zed from Finder launch.
- [ ] Verify staging is local/private and no unexpected process/queue was created.
- [ ] Only after a real processor is located: verify its input contract and handoff.
      Native Logic creation is a separate end-to-end verification item.

For rollback, stop only the identified updated process, restore the backed-up
Control code, and restart using its original launcher. Keep
`JUICE_DATA/CAPTURE/audio-intake` intact; restoring old code does not require
removing captured sources.
