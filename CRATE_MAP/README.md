# CRATE JUICE — Crate Map

`catalogue.json` is the single canonical catalogue. Existing IDs, source links, artwork status and favourites are preserved. Exact ordered recordings live in an entry's `tracks` array. An `index-only` entry is a playlist link, not an exported tracklist.

Run `python3 music_lists.py --check` to validate and `python3 music_lists.py` to rebuild derived exports. Use `--upsert /absolute/path/entry.json` to update a stable entry and regenerate outputs. Do not edit generated `index.html`, `offline.html`, `music-index.txt`, `revision.json` or `sw.js` directly.

Open the hosted map at https://crate-juice-map.xntfsstt5z.chatgpt.site . Exact YouTube recording IDs generate fresh queues when clicked, in chunks of at most 50. Temporary TL queue IDs are not canonical links. Unresolved exact platform mappings remain explicit. A queue is not a named public playlist saved in an account.

Open `offline.html` directly without a server. It embeds all catalogue data, archived tracklists, covers, CSS and JavaScript. Audio streams still need internet. Downloaded snapshots do not update themselves; replace them from the live map when online. The hosted page checks the canonical catalogue when opened/foregrounded online and uses its service worker and local catalogue cache offline after first preparation. Browser storage can be evicted; the downloaded HTML is the independent offline fallback.

The Site deployment is a generated projection of this directory. Preserve its identity `appgprj_6ae092c4a3748191a1d56b61841da627` and current audience. Synchronize the source before deploying through Sites. Do not modify the existing JUICE CONTROL server, music data roots or source playlists as part of catalogue maintenance.

See `SKILL_INDEX.md` for the automatically applied Music List Vault skill. Source playlists keep their existing privacy. No streaming audio is mirrored or downloaded.
