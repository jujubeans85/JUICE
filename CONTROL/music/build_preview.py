#!/usr/bin/env python3
"""Build an offline review copy from the production JUICE Music UI.

The generated HTML embeds the same CSS and JavaScript, enables its explicit
preview mode, and blocks all network connections with a content security policy.
It does not contain a server, engine, queue, sample recordings or user data.

Run: python3 CONTROL/music/build_preview.py
"""
from __future__ import annotations

import argparse
import base64
from pathlib import Path


ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Expected exactly one UI marker: {old!r}")
    return source.replace(old, new, 1)


def data_url(path: Path, mime: str) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def build_preview(output: Path | None = None) -> Path:
    output = (output or ROOT / "preview.html").resolve()
    if output == (WEB / "index.html").resolve():
        raise ValueError("The review preview must not replace the production page.")

    page = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "style.css").read_text(encoding="utf-8")
    script = (WEB / "app.js").read_text(encoding="utf-8")
    if "</style" in css.lower() or "</script" in script.lower():
        raise ValueError("Source contains a closing HTML tag; inspect before embedding.")

    page = replace_once(page, '<html lang="en">', '<html lang="en" data-preview="true">')
    page = replace_once(page, '<meta charset="utf-8">', '''<meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'none'; media-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'">''')
    page = replace_once(page, '<title>Music · JUICE Control</title>', '<title>Music interface preview · JUICE Control</title>')
    page = replace_once(page, '  <link rel="manifest" href="/music/manifest.webmanifest">\n', '')
    page = replace_once(page, 'href="/music/icon.svg"', f'href="{data_url(WEB / "icon.svg", "image/svg+xml")}"')
    page = replace_once(page, 'href="/music/icon-180.png"', f'href="{data_url(WEB / "icon-180.png", "image/png")}"')
    page = replace_once(page, '  <link rel="stylesheet" href="/music/style.css">', f'  <style>\n{css}\n  </style>')
    page = replace_once(page, '  <script src="/music/app.js" defer></script>\n', '')
    page = replace_once(page, '<a class="home-link" href="/" aria-label="Back to JUICE Control home">', '<a class="home-link" href="#create" aria-label="Back to interface preview home">')
    page = replace_once(page, '<a class="wordmark" href="/music/"', '<a class="wordmark" href="#create"')
    page = replace_once(page, 'id="connection-label">Checking</span>', 'id="connection-label">Preview</span>')
    page = replace_once(page, '<p class="eyebrow">THE MUSIC DOOR</p>', '<p class="eyebrow">INTERFACE PREVIEW</p>')
    page = replace_once(page, 'Checking your music engine. You can start writing.', 'Draft and explore here. Generation connects through your installed JC Music Door.')
    page = replace_once(page, '<span id="setup-badge" class="engine-badge">Checking</span>', '<span id="setup-badge" class="engine-badge">Interface preview</span>')
    page = replace_once(page, '</body>', f'  <script>\n{script}\n  </script>\n</body>')

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Output HTML path; defaults to CONTROL/music/preview.html")
    arguments = parser.parse_args()
    path = build_preview(arguments.output)
    print(f"Built {path} ({path.stat().st_size:,} bytes)")
