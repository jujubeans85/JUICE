#!/usr/bin/env python3
"""JUICE Control: local-only control interface with durable Zed opening."""

from __future__ import annotations

import html
import json
import os
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

APP_NAME = "JUICE Control"
APP_VERSION = "2026.07-zed-fix"
HOST = os.environ.get("JUICE_CONTROL_HOST", "127.0.0.1")
PORT = int(os.environ.get("JUICE_CONTROL_PORT", "8765"))
HOME = Path.home()
CONTROL_ROOT = Path(os.environ.get("JUICE_CONTROL_ROOT", HOME / "JUICE" / "CONTROL")).expanduser()
DATA_ROOT = Path(os.environ.get("JUICE_DATA_ROOT", HOME / "JUICE_DATA")).expanduser()
OPEN_IN_ZED = CONTROL_ROOT / "scripts" / "open_in_zed.sh"

TARGETS: dict[str, Path] = {
    "control": CONTROL_ROOT,
    "creative": DATA_ROOT / "CREATIVE",
    "build_repos": DATA_ROOT / "BUILD" / "Repos",
    "capture": DATA_ROOT / "CAPTURE",
}


def ensure_layout() -> None:
    CONTROL_ROOT.mkdir(parents=True, exist_ok=True)
    for path in TARGETS.values():
        path.mkdir(parents=True, exist_ok=True)
    if OPEN_IN_ZED.exists():
        OPEN_IN_ZED.chmod(OPEN_IN_ZED.stat().st_mode | 0o111)


def run_checked(args: list[str], timeout: float = 12.0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = ":".join([
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
        str(HOME / ".local" / "bin"),
        env.get("PATH", ""),
    ])
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, env=env, check=False)


def zed_status() -> dict[str, Any]:
    if not OPEN_IN_ZED.exists():
        return {"available": False, "command": None, "error": f"Missing {OPEN_IN_ZED}"}
    result = run_checked([str(OPEN_IN_ZED), "--print-command"])
    if result.returncode == 0:
        return {"available": True, "command": result.stdout.strip(), "error": None}
    return {"available": False, "command": None, "error": (result.stderr or result.stdout or "Zed command not found").strip()}


def safe_target(name: str) -> Path:
    try:
        path = TARGETS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown target: {name}") from exc
    resolved = path.expanduser().resolve()
    allowed_roots = [p.expanduser().resolve() for p in TARGETS.values()]
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise ValueError(f"Refusing to open path outside JUICE roots: {resolved}")
    return resolved


def open_in_zed(path: Path) -> tuple[bool, str]:
    if not OPEN_IN_ZED.exists():
        return False, f"Missing Zed opener script: {OPEN_IN_ZED}"
    result = run_checked([str(OPEN_IN_ZED), str(path)])
    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return True, f"Opened in Zed: {path}"
    return False, output or f"Zed open failed for {path}"


def diagnostics() -> dict[str, Any]:
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "host": HOST,
        "port": PORT,
        "control_root": str(CONTROL_ROOT),
        "data_root": str(DATA_ROOT),
        "targets": {key: str(path) for key, path in TARGETS.items()},
        "zed": zed_status(),
        "python": sys.version.split()[0],
    }


def render_page(message: str | None = None, ok: bool = True) -> bytes:
    zed = zed_status()
    status_text = "ready" if zed["available"] else "needs Zed CLI/app"
    labels = {
        "control": "CONTROL folder",
        "creative": "Creative",
        "build_repos": "Build repos",
        "capture": "Capture",
    }
    cards = []
    for key, path in TARGETS.items():
        cards.append(f"""
        <form method="post" action="/open" class="card">
          <input type="hidden" name="target" value="{html.escape(key)}">
          <button type="submit">Open {html.escape(labels[key])} in Zed</button>
          <code>{html.escape(str(path))}</code>
        </form>
        """)
    banner = ""
    if message:
        banner = f'<div class="banner {"ok" if ok else "bad"}">{html.escape(message)}</div>'
    payload = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{APP_NAME}</title>
<style>
  :root {{ color-scheme: light dark; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; }}
  body {{ margin: 0; padding: 32px; background: Canvas; color: CanvasText; }}
  main {{ max-width: 860px; margin: 0 auto; }}
  h1 {{ margin-bottom: 0.2rem; }}
  .muted {{ opacity: 0.72; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin: 24px 0; }}
  .card {{ border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 18px; padding: 18px; }}
  button {{ width: 100%; border: 0; border-radius: 14px; padding: 14px 16px; font-weight: 700; cursor: pointer; }}
  code {{ display: block; white-space: pre-wrap; word-break: break-word; margin-top: 12px; font-size: 0.84rem; opacity: 0.78; }}
  .banner {{ padding: 12px 14px; border-radius: 14px; margin: 18px 0; }}
  .ok {{ background: color-mix(in srgb, green 18%, transparent); }}
  .bad {{ background: color-mix(in srgb, red 18%, transparent); }}
  pre {{ overflow: auto; padding: 16px; border-radius: 14px; background: color-mix(in srgb, CanvasText 8%, transparent); }}
</style>
</head>
<body>
<main>
  <h1>{APP_NAME}</h1>
  <p class="muted">Local-only control interface. Zed status: <strong>{html.escape(status_text)}</strong>.</p>
  {banner}
  <section class="grid">{''.join(cards)}</section>
  <h2>Diagnostics</h2>
  <pre>{html.escape(json.dumps(diagnostics(), indent=2))}</pre>
</main>
</body>
</html>"""
    return payload.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def send_bytes(self, body: bytes, status: HTTPStatus = HTTPStatus.OK, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(json.dumps(payload, indent=2).encode("utf-8"), status, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self.send_bytes(render_page())
        elif parsed.path == "/health":
            self.send_json({"ok": True, "version": APP_VERSION})
        elif parsed.path == "/api/diagnostics":
            self.send_json(diagnostics())
        else:
            self.send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        fields = {key: values[-1] for key, values in parse_qs(body).items()}
        try:
            if parsed.path != "/open":
                raise ValueError("Unknown action")
            path = safe_target(fields.get("target", ""))
            path.mkdir(parents=True, exist_ok=True)
            ok, message = open_in_zed(path)
            self.send_bytes(render_page(message, ok), HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            traceback.print_exc()
            self.send_bytes(render_page(str(exc), False), HTTPStatus.BAD_REQUEST)


def already_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((HOST, PORT)) == 0


def main() -> int:
    ensure_layout()
    url = f"http://{HOST}:{PORT}/"
    if already_running():
        webbrowser.open(url)
        print(f"{APP_NAME} already running: {url}")
        return 0
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print(f"{APP_NAME} {APP_VERSION} serving {url}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping JUICE Control.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
