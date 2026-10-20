# AFTERWORLDS build intake in JC

[Add images, files, links or build notes](https://github.com/jujubeans85/JUICE/issues/new?template=afterworlds-build-intake.yml)

[Track implementation: issue #6](https://github.com/jujubeans85/JUICE/issues/6)

[Read the 21 October screenshot batch](INTAKE_2026-10-21.md) · [Canonical structured manifest](intake-2026-10-21.json)

This repository intake is available while the Mac is unavailable. It is a handoff into the existing JC Universal Capture/project queue, not a replacement runtime or a claim that the live dashboard has been updated. The current GitHub `CONTROL/server.py` is an older folder launcher and does not expose the later Universal Capture API. Inspect the real Mac checkout before wiring anything into it.

Use the form for non-sensitive project material. GitHub issues in this repository are public. For private images, attach them through the existing private JC capture flow or keep them in approved private storage and enter only a safe reference. Do not publish unrelated browser/account content. The original ten images remain private; filenames and byte hashes link this intake to them.

## One destination, one receipt

The live integration must reuse the existing project registry, capture service, event owner and storage. Give the action an obvious name such as **Add to AFTERWORLDS**. Support multi-image upload, files, pasted text and URLs with an optional world/concept, a short note and privacy selection. Keep capture low effort; project defaults should do the filing.

Preserve immutable originals → extract text/annotations separately → review uncertain/cropped material → create source-linked points → queue accepted work → return a durable receipt. Track exact-file hashes and source/point IDs so retries do not duplicate work. Show partial failure and retry, rather than reporting success for a whole failed batch.

The JSON manifest owns the batch's structured requirements; the Markdown file is its generated reading view (`python3 render_intake.py`). The tracking issue owns execution discussion/status. AFTERWORLDS links here and does not maintain a second editable copy. Once live JC adopts a batch, store its JC receipt ID on the tracking issue and use that same identity for subsequent changes.

## Integration acceptance

- Ten source images reconcile to the 20 extracted items; the user message adds the 21st intake requirement.
- Each point can open its original through an authorized private path and show extraction confidence.
- Unsupported/missing files, uncertain OCR and partial uploads are visible; retry is idempotent.
- KEEP/BIN is reversible; accepted findings remain distinct from hypotheses and unverified paper leads.
- A real dashboard/CLI intake, queue entry and durable receipt are verified before reporting that JC is connected.
- No second daemon, watcher, public action bus or duplicate project database.

The iPad layout bug and deeper research are tracked, not implemented by this intake change. Preserve frozen research, the system voice through JUICE Reader and all current development work.
