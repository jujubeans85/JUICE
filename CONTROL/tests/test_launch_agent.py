from __future__ import annotations

import os
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path


CONTROL = Path(__file__).resolve().parents[1]
INSTALLER = CONTROL / "scripts" / "install_launch_agent.sh"


class LaunchAgentTests(unittest.TestCase):
    def test_rendered_agent_is_persistent_and_uses_explicit_home(self) -> None:
        with tempfile.TemporaryDirectory(prefix="juice-launch-agent-test-") as temp:
            root = Path(temp)
            home = root / "home"
            home.mkdir()
            output = root / "com.juice.control.plist"
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(home),
                    "JUICE_DATA_ROOT": str(home / "JUICE_DATA"),
                }
            )
            result = subprocess.run(
                [
                    "/bin/bash",
                    str(INSTALLER),
                    "--render-only",
                    str(output),
                ],
                env=env,
                text=True,
                capture_output=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with output.open("rb") as handle:
                payload = plistlib.load(handle)

            self.assertEqual(payload["Label"], "com.juice.control")
            self.assertIs(payload["KeepAlive"], True)
            self.assertIs(payload["RunAtLoad"], True)
            self.assertEqual(payload["EnvironmentVariables"]["HOME"], str(home))
            self.assertEqual(
                Path(payload["ProgramArguments"][1]).name,
                "run_service.sh",
            )


if __name__ == "__main__":
    unittest.main()
