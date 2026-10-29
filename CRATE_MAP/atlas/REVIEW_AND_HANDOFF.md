# Music Atlas: recovery, genre search and CSS review

Review branch: `codex/atlas-backup-genre-review`. Based on main `4f919fd`. Prepared 29 October 2026. No deployment or merge is included.

## CSS review first

The existing CSS has useful shared tokens and reduced-motion handling, but `applyAppearance()` changes body-wide colours, display fonts and concept attributes. Several labels are only 8–10 px. Long introductory, matching, research and exploration sections compete with the globe. Making every surface change with every era increases visual instability and makes the page harder to learn.

The supplied references are strongest in material, light and hierarchy: a dark, quiet shell; a large reflective globe; restrained coloured light; selected labels with clear anchors. The reference dashboard's extra metrics and navigation are not needed here. Their illustrated numbers are not data for this Atlas.

Open `design-review.html` for a working, isolated comparison. The proposal changes neither the live shell nor concept assignments. It uses the existing renderer and geographic outlines, with a Canvas fallback. The attached review screenshot shows that fallback, not the final reflective material.

| Direction | Use | Actual visual distinction |
| --- | --- | --- |
| **Mosaic Night — recommended** | Default, house, disco, club maps | Tiled graphite; magenta/cyan light; specular surface; rounded dark frame |
| **Deco Signal** | Jazz and relevant archive contexts | Champagne/jade; radial engraving; restrained serif heading; double rectangular frame |
| **Print Pop** | Pop and psychedelic contexts | Matte halftone; vermilion/cream; heavy compact title; offset print frame |

Do not assign these by decade alone. Keep the current evidence-based concept matching, uncertainty and manual choices. Map differences should use at least two channels (surface, lighting, frame or heading), not merely hue. Keep UI text contrast, controls and geography consistent. Hybrids remain possible through the current registry.

The next design change should remove visible complexity: one search with optional genre, one globe, one detail panel; advanced research/concept controls under one disclosure. Keep current capabilities reachable. Do not add a new navigation system, score widgets, taxonomy database or renderer. A physical mirror-ball result requires a subsequent measured Three.js material/geometry pass; CSS cannot supply it. Keep the existing low-power renderer, reduced-motion option, pause control and Canvas fallback. Check iPhone thermal/battery behaviour before adding bloom or post-processing.

## Implemented in this branch

- Existing `crate-juice-music-atlas-v3` root fields retained. Additive `backup` metadata includes SHA-256 hashes and counts; no competing library format. Legacy v2/v3 exports are accepted with an explicit missing-checksum label.
- Filenames include UTC timestamp, milliseconds and a content-hash suffix. A requested download is never reported as a confirmed file save.
- **Backups** replaces the existing Export entry point. The panel distinguishes browser storage, requested download, selected-file validation, isolated storage rehearsal and an actual restore readback.
- Complete validation happens before restore. Checks include versions, ordered crate slots, recording identities, concept choices, research jobs and graph/source relationships. SHA-256 detects accidental changes; it is not a signature, encryption or proof of authenticity.
- Restore merges into existing work. Complete crate snapshots win over partial snapshots; incoming complete snapshots may replace same-ID snapshots. Newer dated contexts/choices/jobs win. Running jobs become queued; research remains paused after recovery.
- The same restore adapter writes both the live stores and namespaced rehearsal stores. Rehearsals read data back and remove their temporary databases. A rehearsal does not verify the full UI, future storage retention or an independent device.
- Before the first live write, a local journal preserves existing store contents. A later failure rolls changes back. If rollback cannot complete, the journal survives and boot blocks normal work until **Recover previous browser data** succeeds. This journal lives in the same browser; it is not an independent backup.
- One shared `storage-schema.mjs` defines existing database names/versions/stores for both runtime and recovery. No production database migration, new canonical catalogue or background backup service.
- Genre search uses imported source labels and cached artist context. The existing concept registry limits the selector to 48 common music labels, excluding most uploader jokes/artist names. All original labels remain searchable. Results identify evidence scope; filters update the same research globe. No genre birthplace or track-level certainty is fabricated.
- Personal export/runtime filenames are ignored by Git. No private exports, history or source URLs were added to this branch. Synthetic tests include a clearly synthetic private-style URL solely to verify preservation.

## Backup choices for Safari

**Recommended:** a user-chosen `Music Atlas Backups` folder in their own iCloud Drive, plus a second dated copy on their Mac/external storage. This is a recommendation, not a selected or connected destination. The app does not upload to iCloud or choose a folder.

| Option | Tradeoff |
| --- | --- |
| Browser IndexedDB/localStorage | Working state only. Can be evicted, cleared or isolated by site/profile. Persistence permission is useful but not a backup. |
| On My iPhone/iPad | Simple, no cloud transfer; a second copy is needed to survive device loss. |
| Personal iCloud Drive folder | Convenient handoff among Apple devices; synchronisation is not an independent archive. Keep dated copies and a separate copy. |
| Mac folder plus encrypted external backup | Strongest local control and second-copy separation. Requires a chosen drive/folder and actual restore verification. |
| Future Mac helper | Could validate and rotate already-exported files. It cannot capture unexported Safari state or silently write to an arbitrary device folder from a closed web page. Defer until the simpler workflow is proven. |

Best value: existing Files/Finder storage and the user's existing SSD. Premium: a Mac-managed encrypted second-copy workflow with a scheduled restore drill; no paid SaaS or new NAS is needed for JSON backups. Avoid another browser store labelled “cloud backup,” public GitHub exports, sync-only copies, or claims of unattended Safari filesystem access. Personally choose the recommended folder + external copy, and keep one primary editing device to avoid split-brain libraries.

Steps in the existing Backups panel:

1. Save after an import/research session and before clearing website data or changing the site address.
2. Locate the dated JSON in Files/Finder. iPhone/iPad: Settings → Apps → Safari → Downloads. Mac: Safari → Settings → General → File download location.
3. Select that saved file in Backups. Check its counts and checksum status.
4. Run **Test in temporary storage**. This uses the actual storage adapter in isolated databases.
5. For an independent recovery test, keep the original browser intact. On a second device or fresh Safari profile, open the same app version over HTTPS, restore the file, reload and verify counts plus a known crate, research relationship and concept choice. Resume research only after checking. Record this separately; the app cannot attest that another device was independently checked.
6. Keep a second dated copy in a chosen, non-public location. Exports are readable JSON and can contain private source links/membership. They contain metadata/research, not music audio or the offline app package.

The reviewed history shipped with the installed app remains authoritative on restore. Its exported snapshot stays in the file; this is not a route for promoting browser research into the reviewed catalogue. Disposable fetched-article caches, site appearance, playback position and unrelated Crate Map favourites are outside the existing v3 recovery scope. Stay on the same site origin for normal use. Downloads, a home-screen app and a new browser profile do not imply shared state.

Source verification, 29 October 2026:

- [WebKit: storage policy, eviction and persistence](https://www.webkit.org/blog/14403/updates-to-storage-policy/)
- [WebKit: origin-private filesystem](https://webkit.org/blog/12257/the-file-system-access-api-with-origin-private-file-system/) — still site storage, not a user-selected backup folder.
- [Apple: Safari download locations on iPhone](https://support.apple.com/en-mt/guide/iphone/iphb3100d149/ios)
- [Apple: Safari download locations on iPad](https://support.apple.com/en-by/guide/ipad/ipad54f3cde6/ipados)
- [Apple: Safari downloads on Mac](https://support.apple.com/en-mt/guide/safari/sfri40598/mac)
- [Apple: making independent copies of iCloud information](https://support.apple.com/en-ie/108306)

## Validation and remaining gates

Commands:

```sh
node --test CRATE_MAP/atlas/*.test.mjs
npm ci --prefix CRATE_MAP/atlas/tests --ignore-scripts --no-audit --no-fund
npm test --prefix CRATE_MAP/atlas/tests
```

85 Node tests passed, including the 73 pre-existing tests. The Node suite also round-trips synthetic data matching the reported owner-library scale (12,374 slots / 10,358 identities), without importing owner data. Seven additional restore-adapter tests passed using pinned `fake-indexeddb` (development tests only): full readback, committed restore, late-write rollback, quota failure before writing, failed rollback and journal recovery, rehearsal cleanup/isolation, and refusing production-prefix deletion. CI runs both suites; hosted CI status must be checked on the PR, not inferred from local success.

Observed in the cloud browser: 101 House-tagged records filtered from 8,300 public recording identities; the globe updated to their available researched anchors. Backups panel rendered with distinct status labels. All three visual directions changed and motion paused. No full-library reimport was performed.

The local preview uses `http://terminal.local:4173`, which is not a secure context, and its browser has WebGL disabled. Consequently browser SHA-256/download/check/rehearsal/live-restore flow and reflective WebGL appearance are **not verified here**. The browser harness explicitly reports this block. Source-level SHA-256 tests pass in Node. `tests/backup-browser.html` is ready for HTTPS or trusted localhost and uses synthetic temporary databases only.

Before deployment: run the end-to-end workflow on Safari iPhone, iPad and Mac over HTTPS; include cancelled file choice, corrupt/legacy backup, reload after restore, low-storage failure, interrupted restore and a 12k-entry synthetic load. Check actual file placement and a second-device restore. The owner-private totals from the earlier report are not independently re-counted in this checkout: only the public 258 crates / 9,987 slots / 8,300 recording identities are accessible here. Canonical `catalogue.json`, reviewed history, concept rules and research engine algorithms are unchanged.

Storage writes span several existing databases and localStorage, so there is no cross-database atomic transaction. The recoverable journal mitigates interruption; it cannot survive the browser deleting all site storage. Close other Atlas tabs for restore: the existing research lease coordinates research writers, while concept/exploration edits in another tab are not globally locked. The current 60 MiB import limit and in-memory validation require Safari load testing before calling the workflow production-ready.

## Bounded handoff / next work

One implementation owner. One independent recovery/privacy reviewer should challenge the journal, merge policy, stale jobs, graph references, origin boundaries and failure messaging. A separate Safari visual/performance reviewer is useful after selecting a direction. Do not start parallel feature builders or another catalogue importer.

Mac Codex handoff:

> Fetch `codex/atlas-backup-genre-review` from `jujubeans85/JUICE` into an isolated checkout. Read this document and repository instructions. Do not merge or deploy. Run both test commands. Serve the existing CRATE_MAP on trusted localhost; verify the browser harness. On physical Safari, use synthetic fixtures first, then a user-selected owner export kept outside the repository. Exercise save → locate file → check → isolated rehearsal → restore on a spare profile → reload → inspect known data. Test interruption and quota paths. Keep private files out of screenshots, logs, commits and PR attachments. Report exact counts, file path chosen by the user, independent restore evidence, device/OS/browser versions and unresolved failures. Only after that, implement the selected CSS simplification using one stable shell and the current concept registry; no new features or data model.

Queue, in order: independent recovery review; physical Safari acceptance; select visual direction; simplify the visible interface; then measure whether a small renderer material upgrade earns its battery cost. Unattended device backup helpers and cross-device sync are deferred.
