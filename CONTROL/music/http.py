"""Same-origin music routes, with a narrow authenticated private iOS entry."""
from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import re
import secrets
import threading
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .service import MusicError, MusicService

WEB_ROOT = Path(__file__).resolve().parent / "web"
STATIC = {"index.html", "app.js", "style.css", "manifest.webmanifest", "sw.js", "icon.svg", "icon-180.png", "icon-192.png", "icon-512.png"}
JOB = r"([0-9a-f]{32})"


class MusicHTTP:
    def __init__(self, data_root, *, service=None, private_origin=None, allowed_login=None):
        self.data_root = Path(data_root)
        self._service = service
        self._lock = threading.Lock()
        self.private_origin = (private_origin if private_origin is not None else os.environ.get("JUICE_MUSIC_PRIVATE_ORIGIN", "")).rstrip("/")
        self.allowed_login = allowed_login if allowed_login is not None else os.environ.get("JUICE_MUSIC_TAILSCALE_LOGIN", "")
        if self.private_origin:
            origin = urlsplit(self.private_origin)
            if origin.scheme != "https" or not origin.hostname or origin.path or origin.query or origin.fragment or origin.username or origin.password:
                raise ValueError("JUICE_MUSIC_PRIVATE_ORIGIN must be a private HTTPS origin without a path.")
        self.private_host = urlsplit(self.private_origin).netloc.lower()

    @property
    def service(self):
        with self._lock:
            if self._service is None:
                self._service = MusicService(self.data_root)
            return self._service

    def close(self):
        if self._service is not None:
            self._service.close()

    def request_context(self, handler):
        """Proxy traffic is never allowed to fall back to legacy local authority."""
        headers = handler.headers
        try:
            if not ipaddress.ip_address(handler.client_address[0]).is_loopback:
                return None
        except ValueError:
            return None
        for header in ["Host", "Origin", "Tailscale-User-Login", "X-Forwarded-Proto", "X-Forwarded-Host"]:
            if len(headers.get_all(header, [])) > 1:
                return None
        host = headers.get("Host", "").lower()
        if headers.get("Sec-Fetch-Site") == "cross-site":
            return None
        proxied = any(k.lower().startswith(("tailscale-", "x-forwarded-")) or k.lower() in {"forwarded", "x-real-ip"} for k in headers)
        port = handler.server.server_address[1]
        local_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if not proxied:
            expected = "http://" + host
            if host in local_hosts and headers.get("Origin", expected) == expected:
                return "local"
            return None
        if not self.private_origin or not self.allowed_login:
            return None
        login = headers.get("Tailscale-User-Login", "")
        expected_forwarded = headers.get("X-Forwarded-Host", host).lower()
        if (host == self.private_host and expected_forwarded == self.private_host
                and headers.get("X-Forwarded-Proto", "").lower() == "https"
                and secrets.compare_digest(login.encode(), self.allowed_login.encode())
                and headers.get("Origin", self.private_origin) == self.private_origin):
            return "private"
        return None

    @staticmethod
    def _headers(handler, status, content_type, length, extra=None):
        handler.send_response(status)
        for key, value in {"Content-Type": content_type, "Content-Length": str(length),
                           "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                           "Referrer-Policy": "no-referrer",
                           "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'",
                           **(extra or {})}.items():
            handler.send_header(key, value)
        handler.end_headers()

    def send(self, handler, payload, status=200, content_type="application/json; charset=utf-8", extra=None):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode() if isinstance(payload, (dict, list)) else payload
        self._headers(handler, status, content_type, len(body), extra)
        if handler.command != "HEAD":
            handler.wfile.write(body)

    def _length(self, handler, maximum):
        values = handler.headers.get_all("Content-Length", [])
        if handler.headers.get("Transfer-Encoding") is not None or len(values) != 1 or not values[0].isdigit():
            raise MusicError("One explicit Content-Length is required.", 411)
        length = int(values[0])
        if length > maximum:
            raise MusicError("This request exceeds its size limit.", 413)
        return length

    def _json(self, handler):
        length = self._length(handler, 128 * 1024)
        if handler.headers.get_content_type() != "application/json":
            raise MusicError("Expected JSON.", 415)
        raw = handler.rfile.read(length)
        if len(raw) != length:
            raise MusicError("The request was interrupted.")
        try:
            def reject_nonfinite(value):
                raise ValueError(value)
            result = json.loads(raw, parse_constant=reject_nonfinite)
        except (ValueError, UnicodeError) as exc:
            raise MusicError("Invalid JSON request.") from exc
        if not isinstance(result, dict):
            raise MusicError("Expected a JSON object.")
        return result

    def _file(self, handler, path, download=False):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        extra = {"Accept-Ranges": "bytes"}
        if download:
            extra["Content-Disposition"] = f'attachment; filename="{path.name}"'
        ranges = handler.headers.get_all("Range", [])
        if ranges:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", ranges[0]) if len(ranges) == 1 else None
            valid = bool(match and size > 0 and (match[1] or match[2]))
            if valid:
                if match[1]:
                    start = int(match[1])
                    end = min(int(match[2]), size - 1) if match[2] else size - 1
                else:
                    count = int(match[2])
                    start, end = max(0, size - count), size - 1
                    valid = count > 0
                valid = valid and 0 <= start <= end < size
            if not valid:
                self.send(handler, b"", 416, "application/octet-stream", {"Content-Range": f"bytes */{size}", "Accept-Ranges": "bytes"})
                return
            status = 206
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._headers(handler, status, mime, max(0, end - start + 1), extra)
        if handler.command == "HEAD":
            return
        with path.open("rb") as source:
            source.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = source.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                remaining -= len(chunk)

    def handle(self, handler):
        """Return False only for an authenticated direct-local legacy route."""
        handler.connection.settimeout(30)
        parsed = urlsplit(handler.path)
        path = unquote(parsed.path)
        context = self.request_context(handler)
        if context is None:
            self.send(handler, {"error": "Use this JC instance locally or its authorised private music connection."}, 403)
            handler.close_connection = True
            return True
        if any(x in {"..", "."} for x in path.split("/")) or "\\" in path or "\x00" in path or parsed.scheme or parsed.netloc:
            self.send(handler, {"error": "Invalid path."}, 400)
            return True
        if context == "private" and path == "/" and handler.command in {"GET", "HEAD"}:
            self.send(handler, b"", 302, "text/plain", {"Location": "/music/"})
            return True
        is_music = path == "/music" or path.startswith("/music/") or path == "/api/music" or path.startswith("/api/music/")
        if not is_music:
            if context == "private":
                self.send(handler, {"error": "This private connection only exposes Music."}, 403)
                return True
            return False
        try:
            if handler.command in {"GET", "HEAD"}:
                if path == "/music":
                    self.send(handler, b"", 302, "text/plain", {"Location": "/music/"})
                elif path.startswith("/music/"):
                    name = path[len("/music/"):] or "index.html"
                    if name not in STATIC or not (WEB_ROOT / name).is_file():
                        raise MusicError("File not found.", 404)
                    content_type = {".js": "text/javascript", ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml"}.get(Path(name).suffix, mimetypes.guess_type(name)[0] or "application/octet-stream")
                    self.send(handler, (WEB_ROOT / name).read_bytes(), content_type=content_type,
                              extra={"Service-Worker-Allowed": "/music/"} if name == "sw.js" else None)
                elif path == "/api/music/status":
                    result = self.service.status()
                    result["private_access"] = bool(self.private_origin and self.allowed_login)
                    self.send(handler, result)
                elif path == "/api/music/jobs":
                    self.send(handler, {"jobs": self.service.list_jobs()})
                elif match := re.fullmatch("/api/music/jobs/" + JOB, path):
                    self.send(handler, {"job": self.service.get(match[1])})
                elif match := re.fullmatch("/api/music/jobs/" + JOB + "/files/([A-Za-z0-9._-]+)", path):
                    self._file(handler, self.service.artifact(match[1], match[2]), parse_qs(parsed.query).get("download") == ["1"])
                elif match := re.fullmatch("/api/music/jobs/" + JOB + "/(receipt|workflow|score)", path):
                    job_id, kind = match.groups()
                    self.service.get(job_id)
                    if kind == "receipt":
                        self.send(handler, self.service.get(job_id), extra={"Content-Disposition": f'attachment; filename="take-{job_id}.json"'})
                    else:
                        target = self.service._path(job_id) / ("workflow.json" if kind == "workflow" else "score.abc")
                        if not target.is_file():
                            raise MusicError("This take does not have that artifact yet.", 404)
                        self.send(handler, target.read_bytes(), content_type="application/json" if kind == "workflow" else "text/plain; charset=utf-8", extra={"Content-Disposition": f'attachment; filename="{target.name}"'})
                else:
                    raise MusicError("Music route not found.", 404)
            elif handler.command == "POST":
                handler.close_connection = True
                origin = handler.headers.get("Origin")
                expected = self.private_origin if context == "private" else "http://" + handler.headers.get("Host", "")
                if origin != expected:
                    raise MusicError("A same-origin music request is required.", 403)
                token = handler.headers.get("X-Juice-Token", "")
                if not token.isascii() or not secrets.compare_digest(token, self.service.csrf_token):
                    raise MusicError("Refresh Music before making changes; the session has changed.", 403)
                if path == "/api/music/sources":
                    length = self._length(handler, 100 * 1024 * 1024)
                    filename = parse_qs(parsed.query).get("filename", [""])[0]
                    self.send(handler, {"source": self.service.upload(filename, handler.rfile, length)}, 201)
                else:
                    body = self._json(handler)
                    if path == "/api/music/refresh":
                        self.send(handler, self.service.status(force=True))
                    elif path == "/api/music/jobs":
                        self.send(handler, {"job": self.service.create(body)}, 201)
                    elif match := re.fullmatch("/api/music/jobs/" + JOB + "/(keep|cancel|recover)", path):
                        if match[2] == "keep":
                            result = self.service.keep(match[1], body.get("kept"))
                        elif match[2] == "recover":
                            result = self.service.recover(match[1])
                        else:
                            result = self.service.cancel(match[1])
                        self.send(handler, {"job": result})
                    else:
                        raise MusicError("Music action not found.", 404)
            else:
                self.send(handler, {"error": "Method not supported."}, 405, extra={"Allow": "GET, HEAD, POST"})
        except MusicError as exc:
            self.send(handler, {"ok": False, "error": str(exc)}, exc.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except (OSError, ValueError):
            self.send(handler, {"ok": False, "error": "JC could not complete this request. Your existing takes are preserved."}, 500)
        return True
