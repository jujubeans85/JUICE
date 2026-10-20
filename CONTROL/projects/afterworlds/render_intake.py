#!/usr/bin/env python3
"""Render the human-readable intake from its canonical JSON manifest."""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
manifest = json.loads((OUT/"intake-2026-10-21.json").read_text())
items = manifest["items"]
sources = manifest["sources"]

lines = ['# AFTERWORLDS → JC: screenshot intake, 21 October 2026', '', '**Captured:** 10 originals · 8 world selections · 11 paper leads · 1 layout bug · 1 explicit ingestion requirement = **21 tracked items**.', '', 'The [JSON manifest](intake-2026-10-21.json) is the editable source of truth; this is its reading view. After editing the manifest, run `python3 render_intake.py` in this directory. Items are queued requirements/leads, not completed research or shipped fixes.', '', '## Scope and evidence', ''] + ['- '+s for s in manifest['scope_notes']]
lines += ['', '## World selections', '', '| Item | World | Research concept | Title | Existing evidence status |', '|---|---|---|---|---|']
for item in items[:8]:
    lines.append(f"| {item['id']} | {item['world_number']} | {item['concept_id']} | {item['title']} | {item['research_register_at_capture']['status']} |")
for item in items:
    lines += ['', f"## {item['id']} — {item['title']}", '', f"Source: {', '.join(item['source_ids'])}. Status: `{item['status']}`.", '']
    for key,label in [('question_in_screenshot','Screenshot question'), ('research_direction_in_screenshot','Screenshot direction'), ('annotation_reading','Visible annotation'), ('annotation_interpretation','Interpretation'), ('visible_metadata','Visible bibliographic text'), ('proposed_triage_question','Proposed triage question, not a paper finding'), ('observed','Observed'), ('explicit_request','User request')]:
        if key in item: lines += [f"**{label}:** {item[key]}", '']
    if item.get('title_truncated'): lines += ['**Title is cropped in the image. Full title remains unresolved.**', '']
    if item['kind']=='paper_lead': lines += ['Exact paper URL, version, dataset identity and relevance remain unverified.', '']
    if 'research_register_at_capture' in item:
        state=item['research_register_at_capture']
        lines += [f"**Existing register:** {state['status']}. {state['next_evidence']}", '']
    lines += ['- [ ] '+s for s in item['next_actions']]
    if 'acceptance' in item: lines += ['', '**Acceptance:**', ''] + ['- [ ] '+s for s in item['acceptance']]
lines += ['', '## Source register', '', 'Originals remain in the supplied private attachments. These hashes permit a later Mac import to verify the exact files. No screenshot bytes or unrelated browser tabs are published here.', '', '| Source | Filename | Bytes | SHA-256 |', '|---|---|---:|---|']
for source in sources: lines.append(f"| {source['id']} | {source['filename']} | {source['bytes']} | `{source['sha256']}` |")
lines += ['', '## Build order', '', '1. Reconcile this batch into the existing JC capture/project queue on the real Mac checkout.', '2. Reproduce and repair the iPad home-page alignment issue on the correct Site/build.', '3. Prioritize the explicitly marked GO DEEP / EXPLORE / WORTH EXPLORING worlds, preserving evidence holds.', '4. Triage the remaining world selections and all eleven paper leads. Record rejection or no-useful-signal outcomes.', '5. Validate image/file intake end to end through the existing JC owner, including deduplication, failed uploads and receipts.', '', 'Implementation order is a proposed operational sequence; it does not turn a research lead into accepted evidence.', '']
(OUT/'INTAKE_2026-10-21.md').write_text('\n'.join(lines))
