# Reader regression gate

Run from the repository root:

```sh
python3 READER/tests/regression.py
```

Requires Node.js and Python standard libraries only. GitHub Actions pins Node 22
and Python 3.12 and runs on Reader/workflow pushes, pull requests and manual
dispatch. The job has read-only repository access, a five-minute timeout and
no deployment, credentials, live Site calls, or Mac dependencies.

Coverage: JavaScript syntax; local HTML assets; public neutral sample; module
contract; existing direct Site tools tests; intake validation/FIFO; mocked speech
sequencing, boundary resume, cancellation and errors; same-origin client setup,
acknowledgements, retry, queue capacity and disposal. Speech mocks establish
state transitions only, never audible quality or physical-browser behavior.

The committed kit is checked BEFORE any rebuild: exact member allowlist,
source parity, SOURCE.json hashes, SHA256SUMS and CRC. Rebuild happens in a
temporary copy and must produce identical uncompressed contents. ZIP compression
bytes are intentionally not compared across Python/zlib versions. To change
an authored asset, regenerate the kit with `python3 READER/scripts/package-jc-kit.py`
and commit source and kit together. Never repair a stale kit automatically in CI.

The neutral sample is an intentional public allowlist. Changing it requires
privacy review and an explicit test update. This is a focused regression guard,
not a general secret scanner. Existing private Site source, access controls,
hosting metadata and publication remain outside this workflow.

Independent gates still pending:

- Physical iPhone/iPad/Mac: audible voice quality, actual pause/resume and browser lifecycle.
- Supported desktop: actual ChatGPT Site tools contact and receipt.
- Mac: JC install, authenticated stream, working routes and runtime acceptance.

Passing CI does not mark any of these complete. This workflow supplies a failing
status check; branch-protection enforcement is a separate repository admin setting.

Baseline: pre-gate JUICE commit `bd447f29e82cf1733661c6a0589845ffac6a25a8`.
The original import `cb16ad00fe030f0eb2734717ada1caa85cd6ba6c` and
`rollback/reader-import-2026-09-20` remain historical provenance. Revert the
CI-only change to roll back this gate; do not reset unrelated later work.
