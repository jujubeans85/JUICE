from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


CONTROL = Path(__file__).resolve().parents[1]
BACKUP = CONTROL / "scripts" / "backup_external.sh"
VERIFY = CONTROL / "scripts" / "verify_backup.py"


class BackupScriptIntegrationTests(unittest.TestCase):
    def test_round_trip_state_and_tamper_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="juice-backup-test-") as temp:
            root = Path(temp)
            home = root / "home"
            data = home / "JUICE_DATA"
            code = home / "JUICE"
            volume = root / "fake-external"
            code.mkdir(parents=True)
            data.mkdir(parents=True)
            volume.mkdir()
            (volume / ".juice-backup-volume").write_text(
                "JUICE_BACKUP_VOLUME_V1\n", encoding="utf-8"
            )

            (code / "CONTROL").mkdir()
            (code / "CONTROL" / "code.txt").write_text("version one\n", encoding="utf-8")
            (data / "CREATIVE").mkdir()
            (data / "CREATIVE" / "idea with spaces.txt").write_text(
                "make something useful\n", encoding="utf-8"
            )
            (data / "CAPTURE").mkdir()
            (data / "CAPTURE" / "binary.bin").write_bytes(bytes(range(64)))
            try:
                (data / "latest-idea").symlink_to("CREATIVE/idea with spaces.txt")
            except OSError:
                pass

            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "JUICE_DATA_ROOT": str(data),
                    "JUICE_ALLOW_NON_VOLUME_BACKUP": "1",
                    "JUICE_ALLOW_UNENCRYPTED_BACKUP": "1",
                    "JUICE_RESTORE_SAMPLE_COUNT": "50",
                }
            )
            result = subprocess.run(
                [
                    "/bin/bash",
                    str(BACKUP),
                    "--volume",
                    str(volume),
                    "--allow-unencrypted",
                ],
                env=env,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
            )
            self.assertIn("ROCK SOLID", result.stdout)

            state_path = data / "ADMIN" / "last-backup.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "success")
            snapshot = Path(state["snapshot"])
            self.assertTrue((snapshot / "COMPLETED.json").is_file())
            manifest = snapshot / "MANIFEST.json"
            self.assertTrue(manifest.is_file())

            verify_ok = subprocess.run(
                [
                    os.environ.get("PYTHON", "python3"),
                    str(VERIFY),
                    "verify",
                    "--manifest",
                    str(manifest),
                    "--backup-root",
                    str(snapshot),
                ],
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(verify_ok.returncode, 0, verify_ok.stderr)

            copied = snapshot / "JUICE_DATA" / "CREATIVE" / "idea with spaces.txt"
            copied.write_text("corrupted\n", encoding="utf-8")
            verify_bad = subprocess.run(
                [
                    os.environ.get("PYTHON", "python3"),
                    str(VERIFY),
                    "verify",
                    "--manifest",
                    str(manifest),
                    "--backup-root",
                    str(snapshot),
                ],
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(verify_bad.returncode, 1)
            self.assertIn("mismatch", verify_bad.stderr)


if __name__ == "__main__":
    unittest.main()
