# CRATE JUICE — Crate Map

`catalogue.json` is the single canonical catalogue. Existing IDs, source links, artwork status and favourites are preserved. Exact ordered recordings live in an entry's `tracks` array. An `index-only` entry is a playlist link, not an exported tracklist.

Run `python3 music_lists.py --check` to validate and `python3 music_lists.py` to rebuild derived exports. Use `--upsert /absolute/path/entry.json` to update a stable entry and regenerate outputs. Do not edit generated `index.html`, `offline.html`, `music-index.txt`, `revision.json` or `sw.js` directly.

Open the hosted map at https://crate-juice-map.xntfsstt5z.chatgpt.site . Exact YouTube recording IDs generate fresh queues when clicked, in chunks of at most 50. Temporary TL queue IDs are not canonical links. Unresolved exact platform mappings remain explicit. A queue is not a named public playlist saved in an account.

Open `offline.html` directly without a server. It embeds all catalogue data, archived tracklists, covers, CSS and JavaScript. Audio streams still need internet. Downloaded snapshots do not update themselves; replace them from the live map when online. The hosted page checks the canonical catalogue when opened/foregrounded online and uses its service worker and local catalogue cache offline after first preparation. Browser storage can be evicted; the downloaded HTML is the independent offline fallback.

The Site deployment is a generated projection of this directory. Preserve its identity `appgprj_6ae092c4a3748191a1d56b61841da627` and current audience. Synchronize the source before deploying through Sites. Do not modify the existing JUICE CONTROL server, music data roots or source playlists as part of catalogue maintenance.

See `SKILL_INDEX.md` for the automatically applied Music List Vault skill. Source playlists keep their existing privacy. No streaming audio is mirrored or downloaded.

## Music history atlas

The research pilot is at `/atlas/`, linked from the listening library. `atlas/history.json` is the canonical history graph; exact personal recording records stay in `catalogue.json`. The initial routes reference canonical YouTube recording keys rather than a competing catalogue. The build brief at `atlas/research.html` distinguishes implemented features, source findings and production work. No listening history has been inferred from saved playlists.

Run `node --test CRATE_MAP/atlas/core.test.mjs` from the repository root, then rebuild the index with `python3 CRATE_MAP/music_lists.py`. The globe and all vendor assets are locally served. Imported CRATE JUICE JSON stays in browser storage and does not write to this repository. Atlas browsing is online-first; the standalone listening-library export remains independent. Audio needs internet.

## On-demand exploration

The atlas now loads source-linked branches when a listener chooses politics, divergence, people, places, instruments, technology/media or another recording. `atlas/rabbit-core.mjs` owns relevance and graph contracts; `atlas/rabbit-sources.mjs` owns fixed public API adapters and browser persistence; `atlas/rabbit-ui.mjs` owns exploration state. No model credentials, new backend or generated fact publication are used. English Wikipedia passages and Commons audio are live discovery sources, not reviewed ancestry.

Live graphs remain in IndexedDB on the listener’s browser and in user-triggered exports. They are never committed to Git or merged into `catalogue.json` automatically. Atlas v2 exports restore explored branches; v3 also restores structured crate snapshots and the automatic research queue. Provider failures preserve labelled cached responses. Normal source coverage and heuristics can miss connections; absence is not proof that no historical link exists.

Run `node --test CRATE_MAP/atlas/*.test.mjs` for the data and relevance contracts. See `atlas/research.html#on-demand` for scope and remaining limits.

## Era-aware appearance

The atlas entrance uses the actual AFTERWORLDS slate/lime tokens. `atlas/era-theme.mjs` owns visual palettes; the shared CSS and both globe renderers consume them. Selecting a dated point applies its period automatically: manuscript, engraving, deco, mid-century, pop art, analog, electric, rave or digital. These are visual interpretations, not regional genre classifications. A date interval uses its opening year, disclosed beside the appearance control. Undated branches can retain a dated parent’s atmosphere with an explicit unresolved-date label; arbitrary dates in prose and artist birth dates are never used to infer a period.

The Appearance control can pin AFTERWORLDS or preview any era. That browser-local preference changes presentation only. New public source topics retain their supplied event/inception/publication dates, including when geographic coordinates are also available. Failed date lookups retain known coordinates. All catalogue, recording and history identities are preserved.


## Full-library ingestion and automatic research

Capture: 29 October 2026 (Sydney). The public archive has 196 complete snapshots (194 SoundCloud sources and two YouTube lists), 9,987 ordered slots and 8,300 distinct recordings. The 62 other stable index entries receive their current contents only through the owner-private overlay. Public metadata gaps are zero; performing-artist identity is a separate, often unresolved field.

`/atlas/import.html` imports ordered SoundCloud source snapshots through the documented player API or accepts a CRATE JUICE library JSON file. It checkpoints per-source progress in IndexedDB, caches exact numeric recording IDs and queues metadata retries. Duplicate appearances retain their positions and crate memberships. Player durations can describe previews; upload dates are not release dates, and source display credits are not automatically performing-artist credits. Unavailable metadata never deletes an ordered source slot.

A new or corrected recording automatically joins the resumable research queue on the import page and globe. The engine adds an exact recording root, resolves a single exact musical subject when supported, then adds source-linked artist geography and a genre context when available. New imports update the relevant recording’s globe and the full-library view. Wikipedia revisions and Wikidata sources remain attached. These first passes are context rather than reviewed causal histories; ambiguous names go to the topic review panel. Listeners can choose a music topic and continue the existing on-demand branches. The engine runs while an atlas/import page is open, supports pause/resume, uses a cross-tab lease, retries transient source failures and resumes checkpoints when reopened. It does not crawl while the browser is closed or silently change the public repository.

`catalogue.json` contains public source memberships. Owner-private memberships are overlaid from `private-library.json` only on the existing owner-private Site, with the same stable crate IDs. That file and the optional owner research checkpoint `research-bootstrap.json` are excluded from public Git; never copy a merged owner catalogue or owner offline export into the public repository. Source playlist visibility and membership are different facts: a pre-existing index link is not permission to publish private contents. On a first visit, the owner Site can seed the queue with captured source-linked first passes; changed recording fingerprints still requeue. The owner Site’s offline HTML and text export include its private overlay; the public repository’s exports contain public memberships only.

To reconcile an exported public library into Git, run:

```
node CRATE_MAP/ingest_catalogue.mjs --input /absolute/public-library.json
node CRATE_MAP/ingest_catalogue.mjs --input /absolute/public-library.json --apply
```

The dry run reports source counts; apply validates stable source URLs, retains complete snapshots when a partial import arrives, preserves earlier changed orders in `tracklist_history`, updates the canonical catalogue and rebuilds exports. Private input requires a separate explicit owner output path and cannot enter the public catalogue. `compile_imports.mjs` additionally joins native metadata to public numeric IDs only after independent source count, contiguous order and every previously resolved permalink agree. Public and owner bundles stay separate.

Run `node --test CRATE_MAP/atlas/*.test.mjs` and `python3 CRATE_MAP/music_lists.py --check`. Contract tests cover exact IDs, source order, privacy separation, empty snapshots, incremental queueing, name collisions, manual topic choices, graph provenance and single-tab ownership. The globe draws a bounded active set; every recording remains searchable and exportable. Saved lists do not establish play history, personal preference causation, measured BPM/key or historical ancestry.
