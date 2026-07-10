from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_backup.py"
SPEC = importlib.util.spec_from_file_location("verify_backup", MODULE_PATH)
assert SPEC and SPEC.loader
verify_backup = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verify_backup
SPEC.loader.exec_module(verify_backup)


class VerifyBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="juice-manifest-test-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.backup = self.root / "backup"
        self.source.mkdir()
        (self.source / "folder with spaces").mkdir()
        (self.source / "folder with spaces" / "hello.txt").write_text(
            "hello\n", encoding="utf-8"
        )
        (self.source / "unicodé.txt").write_bytes(b"\x00\x01juice\xff")
        (self.source / "empty").mkdir()
        (self.source / "LOGS").mkdir()
        (self.source / "LOGS" / "changing.log").write_text("ignore", encoding="utf-8")
        (self.source / "ADMIN").mkdir()
        (self.source / "ADMIN" / "last-backup.json").write_text(
            '{"status":"running"}', encoding="utf-8"
        )
        try:
            (self.source / "hello-link").symlink_to("folder with spaces/hello.txt")
        except OSError:
            pass
        shutil.copytree(self.source, self.backup / "DATA", symlinks=True)
        self.manifest = self.backup / "MANIFEST.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_compare_verify_restore_and_tamper_detection(self) -> None:
        result = verify_backup.main(
            [
                "compare",
                "--source",
                f"DATA={self.source}",
                "--backup-root",
                str(self.backup),
                "--manifest-out",
                str(self.manifest),
            ]
        )
        self.assertEqual(result, 0)
        payload = json.loads(self.manifest.read_text(encoding="utf-8"))
        paths = {entry["path"] for entry in payload["entries"]}
        self.assertNotIn("DATA/LOGS", paths)
        self.assertNotIn("DATA/ADMIN/last-backup.json", paths)

        self.assertEqual(
            verify_backup.main(
                [
                    "verify",
                    "--manifest",
                    str(self.manifest),
                    "--backup-root",
                    str(self.backup),
                ]
            ),
            0,
        )
        self.assertEqual(
            verify_backup.main(
                [
                    "restore-drill",
                    "--manifest",
                    str(self.manifest),
                    "--backup-root",
                    str(self.backup),
                    "--sample-count",
                    "10",
                ]
            ),
            0,
        )

        (self.backup / "DATA" / "folder with spaces" / "hello.txt").write_text(
            "tampered\n", encoding="utf-8"
        )
        captured = io.StringIO()
        with contextlib.redirect_stderr(captured):
            result = verify_backup.main(
                [
                    "verify",
                    "--manifest",
                    str(self.manifest),
                    "--backup-root",
                    str(self.backup),
                ]
            )
        self.assertEqual(result, 1)
        self.assertIn("mismatch", captured.getvalue())

    def test_rejects_manifest_path_traversal(self) -> None:
        payload = {
            "format": verify_backup.FORMAT,
            "labels": ["DATA"],
            "entries": [
                {
                    "path": "DATA/../../outside.txt",
                    "type": "file",
                    "size": 1,
                    "sha256": "0" * 64,
                    "mode": 0o600,
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "unsafe path"):
            verify_backup.entries_from_manifest(payload)

    def test_rejects_invalid_source_label(self) -> None:
        with self.assertRaises(Exception):
            verify_backup.parse_source("../bad=/tmp")


if __name__ == "__main__":
    unittest.main()
