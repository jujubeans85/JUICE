#!/usr/bin/env python3
"""JUICE Control: local-only control interface with durable Zed opening."""

from __future__ import annotations

import html
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import fcntl
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from audio_intake import IntakeError, IntakeStore

APP_NAME = "JUICE Control"
APP_VERSION = "2026.10-audio-intake-v1"
SOURCE_ROOT = Path(__file__).resolve().parent
CSRF_TOKEN = secrets.token_urlsafe(32)
INTAKE = None
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


def valid_token(value: str) -> bool:
    return value.isascii() and secrets.compare_digest(value, CSRF_TOKEN)


def intake_store() -> IntakeStore:
    global INTAKE
    if INTAKE is None:
        INTAKE = IntakeStore(DATA_ROOT / "CAPTURE" / "audio-intake")
    return INTAKE


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
        "audio_intake": intake_store().config(),
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
          <input type="hidden" name="csrf" value="{CSRF_TOKEN}">
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
<meta name="juice-csrf" content="{CSRF_TOKEN}">
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
  <section class="card" aria-label="Crate Juice music library">\n    <h2>CRATE JUICE — Crate Map</h2>\n    <p>Search the linked playlist library by title, symbol or cover family.</p>\n    <a href="https://crate-juice-map.xntfsstt5z.chatgpt.site" target="_blank" rel="noopener">Open the Crate Map ↗</a>\n  </section>\n  <section class="grid">{''.join(cards)}</section>
  {(SOURCE_ROOT / "intake.html").read_text()}
  <h2>Diagnostics</h2>
  <pre>{html.escape(json.dumps(diagnostics(), indent=2))}</pre>
</main>
</body>
</html>"""
    return payload.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(30)

    def local_request(self) -> bool:
        # Reject DNS rebinding, cross-site POSTs and cross-site read attempts.
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return (host in allowed and (not origin or origin == f"http://{host}")
                and self.headers.get("Sec-Fetch-Site") not in {"cross-site"})

    def content_length(self, maximum: int) -> int:
        values = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(values) != 1 or not values[0].isdigit():
            raise IntakeError("One explicit Content-Length required; chunked transfer is unsupported", 411)
        length = int(values[0])
        if length > maximum:
            raise IntakeError("Request exceeds size limit", 413)
        return length

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def send_bytes(self, body: bytes, status: HTTPStatus = HTTPStatus.OK, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_bytes(json.dumps(payload, indent=2).encode("utf-8"), status, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        if not self.local_request():
            self.send_json({"error": "Local same-origin request required"}, HTTPStatus.FORBIDDEN)
            return
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self.send_bytes(render_page())
        elif parsed.path == "/intake.js":
            self.send_bytes((SOURCE_ROOT / "intake.js").read_bytes(), content_type="text/javascript; charset=utf-8")
        elif parsed.path == "/api/intake":
            self.send_json(intake_store().config())
        elif re.fullmatch(r"/api/intake/batches/[0-9a-f]{32}", parsed.path):
            try:
                self.send_json(intake_store().receipt(parsed.path.rsplit("/", 1)[1]))
            except IntakeError as exc:
                self.send_json({"error": str(exc)}, HTTPStatus(exc.status))
        elif parsed.path == "/health":
            self.send_json({"ok": True, "app": APP_NAME, "version": APP_VERSION, "capabilities": ["audio-intake-v1", "open-in-zed"]})
        elif parsed.path == "/api/diagnostics":
            self.send_json(diagnostics())
        else:
            self.send_json({"ok": False, "error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        self.close_connection = True
        try:
            if not self.local_request():
                raise IntakeError("Local same-origin request required", 403)
            parsed = urlparse(self.path)
            if parsed.path.startswith("/api/intake/"):
                if not valid_token(self.headers.get("X-Juice-Token", "")):
                    raise IntakeError("Reload JUICE Control before uploading (session token changed)", 403)
                if parsed.path == "/api/intake/batches":
                    length = self.content_length(64 * 1024)
                    if self.headers.get_content_type() != "application/json":
                        raise IntakeError("Expected JSON file selection")
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise IntakeError("Interrupted file selection")
                    data = json.loads(raw)
                    if not isinstance(data, dict):
                        raise IntakeError("Expected a file selection object")
                    self.send_json(intake_store().create(data.get("files")), HTTPStatus.CREATED)
                    return
                match = re.fullmatch(r"/api/intake/batches/([0-9a-f]{32})/files/([0-9]{1,3})", parsed.path)
                if not match:
                    raise IntakeError("Unknown intake action", 404)
                length = self.content_length(intake_store().max_file)
                self.send_json(intake_store().upload(match[1], int(match[2]), self.rfile, length))
                return
            if parsed.path != "/open":
                raise IntakeError("Unknown action", 404)
            length = self.content_length(4096)
            body = self.rfile.read(length).decode("utf-8")
            fields = {key: values[-1] for key, values in parse_qs(body).items()}
            if not valid_token(fields.get("csrf", "")):
                raise IntakeError("Reload JUICE Control before opening a folder", 403)
            path = safe_target(fields.get("target", ""))
            path.mkdir(parents=True, exist_ok=True)
            ok, message = open_in_zed(path)
            self.send_bytes(render_page(message, ok), HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST)
        except (BrokenPipeError, ConnectionResetError):
            pass  # IntakeStore persisted interrupted/completed state before reply.
        except (IntakeError, ValueError, UnicodeError, OSError) as exc:
            try:
                self.send_json({"ok": False, "error": str(exc)}, HTTPStatus(getattr(exc, "status", 400)))
            except (BrokenPipeError, ConnectionResetError):
                pass


def already_running() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((HOST, PORT)) == 0


def main() -> int:
    if HOST not in {"127.0.0.1", "localhost"}:
        print("JUICE Control intake requires a loopback host (127.0.0.1 or localhost).", file=sys.stderr)
        return 2
    url = f"http://{HOST}:{PORT}/"
    if already_running():
        try:
            with urlopen(url + "health", timeout=2) as response:
                health = json.loads(response.read(4096))
            if health.get("app") != APP_NAME or health.get("version") != APP_VERSION:
                raise ValueError("Different server/version is running")
        except (OSError, ValueError, AttributeError):
            print(f"Port {PORT} is occupied by another server/version. Inspect it with scripts/identify-jc.sh; restart the identified JC process before retrying.", file=sys.stderr)
            return 2
        webbrowser.open(url)
        print(f"{APP_NAME} already running: {url}")
        return 0
    ensure_layout()
    root = DATA_ROOT / "CAPTURE" / "audio-intake"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    owner = (root / ".owner.lock").open("a")
    try:
        fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        owner.close()
        print("Another JUICE Control process owns audio intake; reuse its port.", file=sys.stderr)
        return 2
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    intake_store()
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    print(f"{APP_NAME} {APP_VERSION} serving {url}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping JUICE Control.")
    finally:
        httpd.server_close()
        owner.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
