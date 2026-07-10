#!/usr/bin/env python3
"""JUICE Control: local-only HOME control interface."""

from __future__ import annotations

import html
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

APP_NAME = "JUICE Control"
APP_VERSION = "2026.07-home-setup-v1"
SERVICE_ID = "juice-control"
HOST = os.environ.get("JUICE_CONTROL_HOST", "127.0.0.1")
PORT = int(os.environ.get("JUICE_CONTROL_PORT", "8765"))
ALLOW_REMOTE = os.environ.get("JUICE_ALLOW_REMOTE", "0") == "1"
OPEN_BROWSER = os.environ.get("JUICE_CONTROL_OPEN_BROWSER", "1") not in {"0", "false", "False"}
HOME = Path.home()
CONTROL_ROOT = Path(
    os.environ.get("JUICE_CONTROL_ROOT", HOME / "JUICE" / "CONTROL")
).expanduser()
DATA_ROOT = Path(os.environ.get("JUICE_DATA_ROOT", HOME / "JUICE_DATA")).expanduser()
ADMIN_ROOT = DATA_ROOT / "ADMIN"
LOG_ROOT = DATA_ROOT / "LOGS"
OPEN_IN_ZED = CONTROL_ROOT / "scripts" / "open_in_zed.sh"
BACKUP_SCRIPT = CONTROL_ROOT / "scripts" / "backup_external.sh"
DOCTOR_SCRIPT = CONTROL_ROOT / "scripts" / "doctor.sh"
BACKUP_STATE = ADMIN_ROOT / "last-backup.json"
BACKUP_CONFIG = ADMIN_ROOT / "backup.env"
ACTION_TOKEN = secrets.token_urlsafe(32)

TARGETS: dict[str, Path] = {
    "control": CONTROL_ROOT,
    "creative": DATA_ROOT / "CREATIVE",
    "build_repos": DATA_ROOT / "BUILD" / "Repos",
    "capture": DATA_ROOT / "CAPTURE",
}


def ensure_layout() -> None:
    CONTROL_ROOT.mkdir(parents=True, exist_ok=True)
    ADMIN_ROOT.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    for path in TARGETS.values():
        path.mkdir(parents=True, exist_ok=True)
    for script in CONTROL_ROOT.glob("scripts/*.sh"):
        try:
            script.chmod(script.stat().st_mode | 0o111)
        except OSError:
            pass


def command_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = ":".join(
        [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
            "/usr/sbin",
            "/sbin",
            str(HOME / ".local" / "bin"),
            env.get("PATH", ""),
        ]
    )
    env.setdefault("JUICE_CONTROL_ROOT", str(CONTROL_ROOT))
    env.setdefault("JUICE_DATA_ROOT", str(DATA_ROOT))
    return env


def run_checked(
    args: list[str],
    timeout: float = 20.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        capture_output=True,
        timeout=timeout,
        env=command_env(),
        check=False,
    )


def zed_status() -> dict[str, Any]:
    if not OPEN_IN_ZED.exists():
        return {
            "available": False,
            "command": None,
            "error": f"Missing {OPEN_IN_ZED}",
        }
    result = run_checked(["/bin/bash", str(OPEN_IN_ZED), "--print-command"])
    if result.returncode == 0:
        return {
            "available": True,
            "command": result.stdout.strip(),
            "error": None,
        }
    return {
        "available": False,
        "command": None,
        "error": (
            result.stderr or result.stdout or "Zed command not found"
        ).strip(),
    }


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def backup_status() -> dict[str, Any]:
    state = load_json(BACKUP_STATE) or {
        "status": "never",
        "message": "No verified JUICE external backup recorded.",
        "updated_at": None,
        "snapshot": None,
    }
    state["configured"] = BACKUP_CONFIG.is_file()
    return state


def safe_target(name: str) -> Path:
    try:
        path = TARGETS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown target: {name}") from exc

    resolved = path.expanduser().resolve()
    allowed_roots = [candidate.expanduser().resolve() for candidate in TARGETS.values()]
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise ValueError(f"Refusing to open path outside JUICE roots: {resolved}")
    return resolved


def open_in_zed(path: Path) -> tuple[bool, str]:
    if not OPEN_IN_ZED.exists():
        return False, f"Missing Zed opener script: {OPEN_IN_ZED}"
    result = run_checked(["/bin/bash", str(OPEN_IN_ZED), str(path)])
    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return True, f"Opened in Zed: {path}"
    return False, output or f"Zed open failed for {path}"


def start_backup() -> tuple[bool, str]:
    if not BACKUP_SCRIPT.is_file():
        return False, f"Missing backup script: {BACKUP_SCRIPT}"
    if not BACKUP_CONFIG.is_file() and not os.environ.get("JUICE_BACKUP_VOLUME"):
        return (
            False,
            "Backup drive is not configured. Run init_backup_drive.sh once.",
        )

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    action_log = LOG_ROOT / "backup-action.log"
    with action_log.open("a", encoding="utf-8") as handle:
        handle.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] UI backup request\n")
        handle.flush()
        subprocess.Popen(
            ["/bin/bash", str(BACKUP_SCRIPT)],
            cwd=str(CONTROL_ROOT),
            env=command_env(),
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    return True, "Backup started. Refresh this page to see its verified state."


def run_doctor() -> tuple[bool, str, str]:
    if not DOCTOR_SCRIPT.is_file():
        return False, f"Missing doctor script: {DOCTOR_SCRIPT}", ""
    result = run_checked(
        ["/bin/bash", str(DOCTOR_SCRIPT)],
        timeout=90.0,
    )
    details = (result.stdout + result.stderr).strip()
    return (
        result.returncode == 0,
        "Checks passed." if result.returncode == 0 else "Checks found problems.",
        details,
    )


def diagnostics() -> dict[str, Any]:
    return {
        "app": APP_NAME,
        "service": SERVICE_ID,
        "version": APP_VERSION,
        "host": HOST,
        "port": PORT,
        "local_only": not ALLOW_REMOTE,
        "control_root": str(CONTROL_ROOT),
        "data_root": str(DATA_ROOT),
        "targets": {key: str(path) for key, path in TARGETS.items()},
        "zed": zed_status(),
        "backup": backup_status(),
        "launch_agent_plist": str(
            HOME / "Library" / "LaunchAgents" / "com.juice.control.plist"
        ),
        "python": sys.version.split()[0],
    }


def status_label(state: dict[str, Any]) -> str:
    status = str(state.get("status", "unknown"))
    if status == "success":
        return "verified"
    if status in {"copying", "preflight"}:
        return "running"
    if status == "never":
        return "not yet run"
    return status


def render_page(
    message: str | None = None,
    ok: bool = True,
    details: str | None = None,
) -> bytes:
    zed = zed_status()
    backup = backup_status()
    zed_text = "ready" if zed["available"] else "needs attention"
    backup_text = status_label(backup)
    labels = {
        "control": "CONTROL",
        "creative": "Creative",
        "build_repos": "Build repos",
        "capture": "Capture",
    }

    cards: list[str] = []
    for key, path in TARGETS.items():
        cards.append(
            f"""
            <form method="post" action="/open" class="card">
              <input type="hidden" name="token" value="{html.escape(ACTION_TOKEN)}">
              <input type="hidden" name="target" value="{html.escape(key)}">
              <button type="submit">Open {html.escape(labels[key])} in Zed</button>
              <code>{html.escape(str(path))}</code>
            </form>
            """
        )

    banner = ""
    if message:
        banner = (
            f'<div class="banner {"ok" if ok else "bad"}">'
            f"{html.escape(message)}</div>"
        )
    detail_block = ""
    if details:
        detail_block = f"<h2>Result</h2><pre>{html.escape(details)}</pre>"

    backup_message = html.escape(str(backup.get("message") or "No status message."))
    backup_updated = html.escape(str(backup.get("updated_at") or "never"))
    backup_snapshot = html.escape(str(backup.get("snapshot") or "none"))

    payload = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{APP_NAME}</title>
<style>
  :root {{ color-scheme: light dark; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; }}
  body {{ margin: 0; padding: 28px; background: Canvas; color: CanvasText; }}
  main {{ max-width: 920px; margin: 0 auto; }}
  h1 {{ margin-bottom: 0.2rem; }}
  h2 {{ margin-top: 2rem; }}
  .muted {{ opacity: 0.72; }}
  .status {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }}
  .pill {{ border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 999px; padding: 8px 12px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; margin: 18px 0; }}
  .card {{ border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 18px; padding: 16px; }}
  button {{ width: 100%; border: 0; border-radius: 14px; padding: 14px 16px; font-weight: 750; cursor: pointer; }}
  code {{ display: block; white-space: pre-wrap; word-break: break-word; margin-top: 11px; font-size: 0.82rem; opacity: 0.75; }}
  .banner {{ padding: 12px 14px; border-radius: 14px; margin: 18px 0; }}
  .ok {{ background: color-mix(in srgb, green 18%, transparent); }}
  .bad {{ background: color-mix(in srgb, red 18%, transparent); }}
  pre {{ overflow: auto; padding: 16px; border-radius: 14px; background: color-mix(in srgb, CanvasText 8%, transparent); }}
  .actions {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }}
</style>
</head>
<body>
<main>
  <h1>{APP_NAME}</h1>
  <p class="muted">Local HOME control. One source of truth, explicit actions, visible failures.</p>
  <div class="status">
    <span class="pill">Zed: <strong>{html.escape(zed_text)}</strong></span>
    <span class="pill">Backup: <strong>{html.escape(backup_text)}</strong></span>
    <span class="pill">Version: <strong>{html.escape(APP_VERSION)}</strong></span>
  </div>
  {banner}

  <h2>Open</h2>
  <section class="grid">{''.join(cards)}</section>

  <h2>System</h2>
  <section class="actions">
    <form method="post" action="/action" class="card">
      <input type="hidden" name="token" value="{html.escape(ACTION_TOKEN)}">
      <input type="hidden" name="action" value="backup">
      <button type="submit">Back up now</button>
      <code>Status: {html.escape(backup_text)}
Updated: {backup_updated}
Snapshot: {backup_snapshot}
{backup_message}</code>
    </form>
    <form method="post" action="/action" class="card">
      <input type="hidden" name="token" value="{html.escape(ACTION_TOKEN)}">
      <input type="hidden" name="action" value="doctor">
      <button type="submit">Run checks</button>
      <code>Runs the non-destructive JUICE doctor and shows its evidence.</code>
    </form>
  </section>

  {detail_block}
  <h2>Diagnostics</h2>
  <pre>{html.escape(json.dumps(diagnostics(), indent=2))}</pre>
</main>
</body>
</html>"""
    return payload.encode("utf-8")


def host_is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def client_is_loopback(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_loopback
    except ValueError:
        return False


class JuiceHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = f"{APP_NAME}/{APP_VERSION}"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def send_bytes(
        self,
        body: bytes,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str = "text/html; charset=utf-8",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'unsafe-inline'; "
            "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
    ) -> None:
        self.send_bytes(
            json.dumps(payload, indent=2).encode("utf-8"),
            status,
            "application/json; charset=utf-8",
        )

    def allowed_client(self) -> bool:
        return ALLOW_REMOTE or client_is_loopback(self.client_address[0])

    def read_form(self) -> dict[str, str]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length < 0 or length > 16_384:
            raise ValueError("Request body is too large")
        body = self.rfile.read(length).decode("utf-8")
        return {
            key: values[-1]
            for key, values in parse_qs(body, keep_blank_values=True).items()
        }

    def require_action_token(self, fields: dict[str, str]) -> None:
        supplied = fields.get("token", "")
        if not secrets.compare_digest(supplied, ACTION_TOKEN):
            raise PermissionError("Invalid or expired action token. Refresh the page.")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            if not self.allowed_client():
                self.send_json(
                    {"ok": False, "error": "local access only"},
                    HTTPStatus.FORBIDDEN,
                )
                return
            self.send_bytes(render_page())
        elif parsed.path == "/health":
            self.send_json(
                {
                    "ok": True,
                    "service": SERVICE_ID,
                    "app": APP_NAME,
                    "version": APP_VERSION,
                }
            )
        elif parsed.path == "/api/diagnostics":
            if not self.allowed_client():
                self.send_json(
                    {"ok": False, "error": "local access only"},
                    HTTPStatus.FORBIDDEN,
                )
                return
            self.send_json(diagnostics())
        else:
            self.send_json(
                {"ok": False, "error": "not found"},
                HTTPStatus.NOT_FOUND,
            )

    def do_POST(self) -> None:
        if not self.allowed_client():
            self.send_json(
                {"ok": False, "error": "local access only"},
                HTTPStatus.FORBIDDEN,
            )
            return

        parsed = urlparse(self.path)
        try:
            fields = self.read_form()
            self.require_action_token(fields)

            if parsed.path == "/open":
                path = safe_target(fields.get("target", ""))
                path.mkdir(parents=True, exist_ok=True)
                ok, message = open_in_zed(path)
                self.send_bytes(
                    render_page(message, ok),
                    HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
                )
                return

            if parsed.path == "/action":
                action = fields.get("action", "")
                if action == "backup":
                    ok, message = start_backup()
                    self.send_bytes(
                        render_page(message, ok),
                        HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
                    )
                    return
                if action == "doctor":
                    ok, message, details = run_doctor()
                    self.send_bytes(
                        render_page(message, ok, details),
                        HTTPStatus.OK if ok else HTTPStatus.BAD_REQUEST,
                    )
                    return
                raise ValueError(f"Unknown action: {action}")

            raise ValueError("Unknown action endpoint")
        except PermissionError as exc:
            self.send_bytes(
                render_page(str(exc), False),
                HTTPStatus.FORBIDDEN,
            )
        except Exception as exc:  # Keep the local UI useful while logging evidence.
            traceback.print_exc()
            self.send_bytes(
                render_page(str(exc), False),
                HTTPStatus.BAD_REQUEST,
            )


def probe_existing_service() -> str:
    url = f"http://{HOST}:{PORT}/health"
    try:
        with urllib.request.urlopen(url, timeout=0.6) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if (
            isinstance(payload, dict)
            and payload.get("ok") is True
            and payload.get("service") == SERVICE_ID
        ):
            return "juice"
        return "foreign"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return "foreign" if sock.connect_ex((HOST, PORT)) == 0 else "free"


def main() -> int:
    ensure_layout()

    if not ALLOW_REMOTE and not host_is_loopback(HOST):
        print(
            f"Refusing non-loopback host {HOST!r}. "
            "Set JUICE_ALLOW_REMOTE=1 only after adding real authentication.",
            file=sys.stderr,
        )
        return 64

    url = f"http://{HOST}:{PORT}/"
    existing = probe_existing_service()
    if existing == "juice":
        if OPEN_BROWSER:
            webbrowser.open(url)
        print(f"{APP_NAME} already running: {url}")
        return 0
    if existing == "foreign":
        print(
            f"Port {PORT} is occupied by something other than {APP_NAME}.",
            file=sys.stderr,
        )
        return 98

    try:
        httpd = JuiceHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        print(f"Could not bind {HOST}:{PORT}: {exc}", file=sys.stderr)
        return 98

    if OPEN_BROWSER:
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
