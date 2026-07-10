from __future__ import annotations

import http.server
import json
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


CONTROL = Path(__file__).resolve().parents[1]
SERVER = CONTROL / "server.py"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ServerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="juice-server-test-")
        self.home = Path(self.temp.name)
        self.port = free_port()
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(self.home),
                "JUICE_CONTROL_ROOT": str(CONTROL),
                "JUICE_DATA_ROOT": str(self.home / "JUICE_DATA"),
                "JUICE_CONTROL_HOST": "127.0.0.1",
                "JUICE_CONTROL_PORT": str(self.port),
                "JUICE_CONTROL_OPEN_BROWSER": "0",
                "ZED_CLI": "/bin/true",
            }
        )
        self.process = subprocess.Popen(
            [os.environ.get("PYTHON", "python3"), str(SERVER)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self.base = f"http://127.0.0.1:{self.port}"
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{self.base}/health", timeout=0.4):
                    break
            except OSError:
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate(timeout=2)
                    self.fail(f"server exited early\nstdout={stdout}\nstderr={stderr}")
                time.sleep(0.05)
        else:
            self.fail("server did not become ready")

    def tearDown(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.communicate(timeout=3)
        self.temp.cleanup()

    def test_health_diagnostics_csrf_and_zed_open(self) -> None:
        with urllib.request.urlopen(f"{self.base}/health", timeout=2) as response:
            health = json.loads(response.read())
        self.assertEqual(health["service"], "juice-control")
        self.assertTrue(health["ok"])

        with urllib.request.urlopen(f"{self.base}/api/diagnostics", timeout=2) as response:
            diagnostics = json.loads(response.read())
        self.assertEqual(diagnostics["service"], "juice-control")
        self.assertTrue(diagnostics["local_only"])

        with urllib.request.urlopen(f"{self.base}/", timeout=2) as response:
            page = response.read().decode("utf-8")
        match = re.search(r'name="token" value="([^"]+)"', page)
        self.assertIsNotNone(match)
        token = match.group(1)

        no_token = urllib.request.Request(
            f"{self.base}/open",
            data=urllib.parse.urlencode({"target": "creative"}).encode(),
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(no_token, timeout=2)
        self.assertEqual(caught.exception.code, 403)

        valid = urllib.request.Request(
            f"{self.base}/open",
            data=urllib.parse.urlencode(
                {"target": "creative", "token": token}
            ).encode(),
            method="POST",
        )
        with urllib.request.urlopen(valid, timeout=3) as response:
            body = response.read().decode("utf-8")
        self.assertIn("Opened in Zed", body)

        invalid = urllib.request.Request(
            f"{self.base}/open",
            data=urllib.parse.urlencode(
                {"target": "not-a-target", "token": token}
            ).encode(),
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(invalid, timeout=3)
        self.assertEqual(caught.exception.code, 400)

    def test_refuses_non_loopback_without_explicit_override(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(self.home),
                "JUICE_CONTROL_ROOT": str(CONTROL),
                "JUICE_DATA_ROOT": str(self.home / "other-data"),
                "JUICE_CONTROL_HOST": "0.0.0.0",
                "JUICE_CONTROL_PORT": str(free_port()),
                "JUICE_CONTROL_OPEN_BROWSER": "0",
            }
        )
        result = subprocess.run(
            [os.environ.get("PYTHON", "python3"), str(SERVER)],
            env=env,
            text=True,
            capture_output=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 64)
        self.assertIn("Refusing non-loopback", result.stderr)


class ForeignHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b'{"ok": true, "service": "something-else"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: object) -> None:
        pass


class ForeignPortTests(unittest.TestCase):
    def test_refuses_foreign_listener(self) -> None:
        port = free_port()
        server = http.server.HTTPServer(("127.0.0.1", port), ForeignHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory(prefix="juice-foreign-test-") as home:
            env = os.environ.copy()
            env.update(
                {
                    "HOME": home,
                    "JUICE_CONTROL_ROOT": str(CONTROL),
                    "JUICE_DATA_ROOT": str(Path(home) / "JUICE_DATA"),
                    "JUICE_CONTROL_HOST": "127.0.0.1",
                    "JUICE_CONTROL_PORT": str(port),
                    "JUICE_CONTROL_OPEN_BROWSER": "0",
                }
            )
            result = subprocess.run(
                [os.environ.get("PYTHON", "python3"), str(SERVER)],
                env=env,
                text=True,
                capture_output=True,
                timeout=5,
            )
        server.shutdown()
        server.server_close()
        self.assertEqual(result.returncode, 98)
        self.assertIn("occupied", result.stderr)


if __name__ == "__main__":
    unittest.main()
