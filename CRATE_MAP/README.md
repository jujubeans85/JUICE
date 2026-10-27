# CRATE JUICE — Crate Map

256 linked playlists, 225 owned playlists, 31 saved/external entries.

Live private deployment: https://crate-juice-map.xntfsstt5z.chatgpt.site

`catalogue.json` is the canonical catalogue. IDs stay attached to the same playlist.
The app searches title, symbol, edition and ID, filters by family and ownership,
and saves favourites locally on each device. Playlist tiles open exact observed
SoundCloud URLs. Private playlists require the owner’s SoundCloud sign-in.

## Local run

From this folder, run `python3 -m http.server 8080` and open http://localhost:8080.
Do not double-click index.html: browsers generally block local-file JSON requests.

## Artwork and maintenance

Run `python3 build_covers.py` after editing the catalogue to regenerate all 256
editable SVG covers. No dependencies or external assets are needed.
Browser Save Image downloads SVG; export to JPG/PNG for SoundCloud uploads.

The four verified SoundCloud replacements are CJ-002, CJ-007, CJ-009 and CJ-017.
221 owned-playlist uploads remain pending. A generated cover is not proof of an
upload. Update `artwork_status` only after confirming the saved image on SoundCloud.
External playlist covers are local map graphics; only their owners can change
the SoundCloud originals. No source playlists were renamed, deleted or made public.

Catalogue snapshot: 27 October 2026. Families are filing suggestions based on
playlist titles, not a track-level audio analysis. Favourites do not sync between
devices. The application works on a normal static web server and under a subpath.

## JUICE Control

The launcher in `CONTROL/server.py` points to the live private map. Pull the JUICE
repository and restart Control to receive it. The hosted map and this Git source
are separately deployed; the live version must be published after source changes.
