"""Exercise the real HTTP boundary, including proxy identity and iOS byte ranges.

A loopback HTTP server hosts the real MusicHTTP routes and durable service. Only
the GPU engine is faked; no Tailscale connection or real music inference occurs.
"""
from __future__ import annotations

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid

TEST_ROOT = Path(__file__).resolve().parent
CONTROL_ROOT = TEST_ROOT.parent
for directory in (CONTROL_ROOT, TEST_ROOT):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from music.http import MusicHTTP
from music.service import MusicService
from test_music_service import FakeComfy, WAV


PRIVATE_ORIGIN = "https://jc-fixture.example.ts.net"
PRIVATE_HOST = "jc-fixture.example.ts.net"
OWNER = "owner@example.com"


class MusicSecurityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = FakeComfy()
        self.service = MusicService(Path(self.temp.name), self.engine, start_worker=False)
        self.addCleanup(self.service.close)
        self.music = MusicHTTP(self.temp.name, service=self.service,
                               private_origin=PRIVATE_ORIGIN, allowed_login=OWNER)
        music = self.music

        class Handler(BaseHTTPRequestHandler):
            def dispatch(self):
                if not music.handle(self):
                    body = b"legacy-admin-reached"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)

            do_GET = dispatch
            do_HEAD = dispatch
            do_POST = dispatch
            do_OPTIONS = dispatch
            do_DELETE = dispatch

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.02}, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.port = self.server.server_address[1]
        self.local_host = f"127.0.0.1:{self.port}"
        self.local_origin = "http://" + self.local_host

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def proxy_headers(self, **changes):
        headers = {"Host": PRIVATE_HOST, "Tailscale-User-Login": OWNER,
                   "X-Forwarded-Proto": "https", "X-Forwarded-Host": PRIVATE_HOST,
                   "X-Forwarded-For": "100.100.100.100"}
        headers.update(changes)
        return headers

    def request(self, method, path, *, headers=None, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def duplicate_header_request(self, headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.putrequest("GET", "/api/music/status", skip_host=True)
            for name, value in headers:
                connection.putheader(name, value)
            connection.endheaders()
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def mutation_headers(self, private=False, **changes):
        headers = self.proxy_headers() if private else {"Host": self.local_host}
        headers.update({"Origin": PRIVATE_ORIGIN if private else self.local_origin,
                        "Content-Type": "application/json",
                        "X-Juice-Token": self.service.csrf_token})
        headers.update(changes)
        return headers

    def create_body(self):
        return json.dumps({"request_id": str(uuid.uuid4()), "style": "Funk test", "seed": 1}).encode()

    def audio_url(self):
        job = self.service.create(json.loads(self.create_body()))
        path = self.service._path(job["id"]) / "master-1.wav"
        path.write_bytes(WAV)
        self.service._update(job["id"], status="succeeded", outputs=[{
            "name": path.name, "bytes": len(WAV), "kind": "master",
        }])
        return f"/api/music/jobs/{job['id']}/files/{path.name}"

    def test_direct_local_music_and_legacy_remain_available(self):
        status, headers, body = self.request("GET", "/api/music/status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["csrf_token"], self.service.csrf_token)
        self.assertEqual(headers["Cache-Control"], "no-store")
        status, _, body = self.request("GET", "/legacy-admin")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"legacy-admin-reached")

    def test_authorised_private_music_and_root_redirect(self):
        status, _, body = self.request("GET", "/api/music/status", headers=self.proxy_headers())
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["private_access"])
        status, headers, body = self.request("GET", "/", headers=self.proxy_headers())
        self.assertEqual(status, 302)
        self.assertEqual(headers["Location"], "/music/")
        self.assertEqual(body, b"")
        status, _, body = self.request("GET", "/music/", headers=self.proxy_headers())
        self.assertEqual(status, 200)
        self.assertIn(b"<!doctype html", body.lower())

    def test_private_identity_never_exposes_legacy_routes_for_any_method(self):
        for method in ("GET", "HEAD", "POST", "OPTIONS", "DELETE"):
            with self.subTest(method=method):
                status, _, body = self.request(method, "/legacy-admin", headers=self.proxy_headers())
                self.assertEqual(status, 403)
                self.assertNotIn(b"legacy-admin-reached", body)

    def test_proxy_cannot_forge_local_host_to_gain_legacy_authority(self):
        cases = [
            self.proxy_headers(Host=self.local_host),
            self.proxy_headers(Host=self.local_host, **{"X-Forwarded-Host": self.local_host}),
            {"Host": self.local_host, "X-Forwarded-For": "100.100.100.100"},
            {"Host": self.local_host, "X-Forwarded-For": ""},
            {"Host": self.local_host, "Forwarded": ""},
            {"Host": self.local_host, "Tailscale-User-Login": ""},
        ]
        for headers in cases:
            with self.subTest(headers=headers):
                status, _, body = self.request("GET", "/legacy-admin", headers=headers)
                self.assertEqual(status, 403)
                self.assertNotIn(b"legacy-admin-reached", body)

    def test_wrong_or_missing_login_and_wrong_proxy_host_are_denied(self):
        cases = [
            self.proxy_headers(**{"Tailscale-User-Login": "other@example.com"}),
            self.proxy_headers(**{"Tailscale-User-Login": ""}),
            self.proxy_headers(Host="attacker.example"),
            self.proxy_headers(**{"X-Forwarded-Host": "attacker.example"}),
            self.proxy_headers(**{"X-Forwarded-Proto": "http"}),
        ]
        missing = self.proxy_headers()
        del missing["Tailscale-User-Login"]
        cases.append(missing)
        for headers in cases:
            with self.subTest(headers=headers):
                status, _, _ = self.request("GET", "/api/music/status", headers=headers)
                self.assertEqual(status, 403)

    def test_private_access_requires_explicit_opt_in_and_login(self):
        self.music.allowed_login = ""
        status, _, _ = self.request("GET", "/api/music/status", headers=self.proxy_headers())
        self.assertEqual(status, 403)
        self.music.allowed_login = OWNER
        self.music.private_origin = ""
        status, _, _ = self.request("GET", "/api/music/status", headers=self.proxy_headers())
        self.assertEqual(status, 403)

    def test_duplicate_authority_headers_fail_closed(self):
        base = list(self.proxy_headers().items())
        for name, value in (("Host", "localhost"), ("Tailscale-User-Login", OWNER),
                            ("X-Forwarded-Proto", "https"), ("X-Forwarded-Host", PRIVATE_HOST)):
            with self.subTest(name=name):
                status, _ = self.duplicate_header_request(base + [(name, value)])
                self.assertEqual(status, 403)
        status, _ = self.duplicate_header_request(base + [("Origin", PRIVATE_ORIGIN)] * 2)
        self.assertEqual(status, 403)

    def test_cross_site_navigation_cannot_read_status_token(self):
        for headers in ({"Sec-Fetch-Site": "cross-site"},
                        self.proxy_headers(**{"Sec-Fetch-Site": "cross-site"})):
            with self.subTest(headers=headers):
                status, _, body = self.request("GET", "/api/music/status", headers=headers)
                self.assertEqual(status, 403)
                self.assertNotIn(self.service.csrf_token.encode(), body)

    def test_mutations_require_origin_and_current_token(self):
        for private in (False, True):
            base = self.mutation_headers(private=private)
            cases = [{**base, "Origin": "https://attacker.example"},
                     {**base, "X-Juice-Token": "incorrect"}]
            cases.append({key: value for key, value in base.items() if key != "Origin"})
            cases.append({key: value for key, value in base.items() if key != "X-Juice-Token"})
            for headers in cases:
                with self.subTest(private=private, headers=headers):
                    status, _, _ = self.request("POST", "/api/music/jobs", headers=headers, body=self.create_body())
                    self.assertEqual(status, 403)
        self.assertEqual(self.service.list_jobs(), [])

    def test_authorised_mutation_retries_return_same_durable_job(self):
        body = self.create_body()
        first = self.request("POST", "/api/music/jobs", headers=self.mutation_headers(private=True), body=body)
        second = self.request("POST", "/api/music/jobs", headers=self.mutation_headers(private=True), body=body)
        self.assertEqual(first[0], 201)
        self.assertEqual(second[0], 201)
        self.assertEqual(json.loads(first[2])["job"]["id"], json.loads(second[2])["job"]["id"])
        self.assertEqual(len(self.service.list_jobs()), 1)

    def test_recover_route_uses_original_receipt_and_rejects_duplicate_recovery(self):
        job = self.service.create(json.loads(self.create_body()))
        self.service._update(job["id"], status="needs_attention", prompt_id=self.engine.prompt_id)
        self.assertTrue(self.service.get(job["id"])["recoverable"])
        url = f"/api/music/jobs/{job['id']}/recover"
        status, _, body = self.request("POST", url, headers=self.mutation_headers(private=True), body=b"{}")
        self.assertEqual(status, 200)
        result = json.loads(body)["job"]
        self.assertEqual(result["status"], "running")
        self.assertFalse(result["recoverable"])
        self.assertNotIn("prompt_id", result)
        status, _, _ = self.request("POST", url, headers=self.mutation_headers(private=True), body=b"{}")
        self.assertEqual(status, 409)
        self.assertEqual(self.engine.submissions, [])

    def test_existing_jc_handler_checks_music_guard_before_legacy_dispatch(self):
        spec = importlib.util.spec_from_file_location("jc_server_under_music_test", CONTROL_ROOT / "server.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.MUSIC = self.music

        class QuietJCHandler(module.Handler):
            def log_message(self, *args):
                pass

        self.server.RequestHandlerClass = QuietJCHandler
        status, _, body = self.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])
        status, _, body = self.request("GET", "/api/music/status", headers=self.proxy_headers())
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ready"])
        for method, path in (("GET", "/api/diagnostics"), ("POST", "/open"), ("HEAD", "/health")):
            with self.subTest(method=method, path=path):
                status, _, _ = self.request(method, path, headers=self.proxy_headers())
                self.assertEqual(status, 403)
                status, _, _ = self.request(method, path, headers=self.proxy_headers(Host=self.local_host))
                self.assertEqual(status, 403)

    def test_json_only_mutations_and_nonfinite_values_rejected(self):
        status, _, _ = self.request("POST", "/api/music/jobs",
                                    headers=self.mutation_headers(**{"Content-Type": "text/plain"}),
                                    body=self.create_body())
        self.assertEqual(status, 415)
        status, _, _ = self.request("POST", "/api/music/jobs", headers=self.mutation_headers(),
                                    body=b'{"style":"funk", "duration": NaN}')
        self.assertEqual(status, 400)
        self.assertEqual(self.service.list_jobs(), [])

    def test_traversal_and_absolute_request_targets_are_rejected(self):
        for path in ("/music/../legacy-admin", "/music/%2e%2e/legacy-admin",
                     "/api/music/jobs/../../private", "/music/a%5cb",
                     "/music/%00", "https://attacker.example/music/"):
            with self.subTest(path=path):
                status, _, body = self.request("GET", path, headers=self.proxy_headers())
                self.assertEqual(status, 400)
                self.assertNotIn(b"legacy-admin-reached", body)

    def test_only_allowlisted_static_files_are_served(self):
        for path in ("/music/service.py", "/music/.env", "/music/unknown", "/music/web/index.html"):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path, headers=self.proxy_headers())
                self.assertEqual(status, 404)

    def test_ios_audio_full_head_and_single_byte_ranges(self):
        url = self.audio_url()
        status, headers, body = self.request("GET", url, headers=self.proxy_headers())
        self.assertEqual(status, 200)
        self.assertEqual(body, WAV)
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        status, headers, body = self.request("HEAD", url, headers=self.proxy_headers())
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Length"], str(len(WAV)))
        self.assertEqual(body, b"")
        for request_range, start, end in (("bytes=0-1", 0, 1), ("bytes=10-19", 10, 19),
                                           ("bytes=20-", 20, len(WAV) - 1),
                                           ("bytes=-12", len(WAV) - 12, len(WAV) - 1),
                                           ("bytes=0-99999", 0, len(WAV) - 1)):
            with self.subTest(request_range=request_range):
                status, headers, body = self.request("GET", url, headers=self.proxy_headers(Range=request_range))
                self.assertEqual(status, 206)
                self.assertEqual(body, WAV[start:end + 1])
                self.assertEqual(headers["Content-Range"], f"bytes {start}-{end}/{len(WAV)}")
                self.assertEqual(int(headers["Content-Length"]), len(body))

    def test_invalid_and_multi_ranges_return_416(self):
        url = self.audio_url()
        for request_range in ("bytes=999999-", "bytes=8-3", "bytes=-0", "bytes=-", "bytes=0-1,4-5", "nonsense"):
            with self.subTest(request_range=request_range):
                status, headers, body = self.request("GET", url, headers=self.proxy_headers(Range=request_range))
                self.assertEqual(status, 416)
                self.assertEqual(headers["Content-Range"], f"bytes */{len(WAV)}")
                self.assertEqual(body, b"")

    def test_download_disposition_and_unlisted_files(self):
        url = self.audio_url()
        status, headers, body = self.request("GET", url + "?download=1", headers=self.proxy_headers())
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Disposition"], 'attachment; filename="master-1.wav"')
        self.assertEqual(body, WAV)
        status, _, _ = self.request("GET", url.replace("master-1.wav", "job.json"), headers=self.proxy_headers())
        self.assertEqual(status, 404)

    def test_upload_api_keeps_original_bytes_and_deduplicates(self):
        headers = self.mutation_headers(private=True, **{"Content-Type": "audio/wav"})
        first = self.request("POST", "/api/music/sources?filename=reference.wav", headers=headers, body=WAV)
        second = self.request("POST", "/api/music/sources?filename=another.wav", headers=headers, body=WAV)
        self.assertEqual(first[0], 201)
        self.assertEqual(second[0], 201)
        source = json.loads(first[2])["source"]
        self.assertEqual(source["id"], json.loads(second[2])["source"]["id"])
        self.assertEqual(self.service.source(source["id"])[1].read_bytes(), WAV)


if __name__ == "__main__":
    unittest.main()
