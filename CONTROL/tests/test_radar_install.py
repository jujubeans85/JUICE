import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

CONTROL=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installer',CONTROL/'scripts/install-radar.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)

class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.target=Path(self.tmp.name)
        # This fixture is the pinned public baseline, not a local Mac installation.
        baseline=subprocess.check_output(['git','show','cf0a5338419b6d0591789283a6fef7272fe8d3a8:CONTROL/server.py'],cwd=CONTROL)
        (self.target/'server.py').write_bytes(baseline);self.baseline=baseline
        (self.target/'local-module.txt').write_text('synthetic local module')
    def tearDown(self): self.tmp.cleanup()
    def test_dry_run_does_not_write(self):
        mod.install(self.target);self.assertEqual((self.target/'server.py').read_bytes(),self.baseline)
        self.assertFalse((self.target/'skill_radar.py').exists())
    def test_preserves_modules_and_backup(self):
        mod.install(self.target,True)
        self.assertEqual((self.target/'local-module.txt').read_text(),'synthetic local module')
        self.assertEqual(next((self.target/'.radar-backups').glob('*/server.py')).read_bytes(),self.baseline)
        self.assertEqual((self.target/'server.py').read_bytes(),(CONTROL/'server.py').read_bytes())
    def test_custom_server_is_not_overwritten(self):
        (self.target/'server.py').write_text('custom server')
        with self.assertRaises(ValueError):mod.install(self.target,True)
        self.assertEqual((self.target/'server.py').read_text(),'custom server')
    def test_different_bridge_is_not_overwritten(self):
        (self.target/'skill_radar.py').write_text('different bridge')
        with self.assertRaises(ValueError):mod.install(self.target,True)
        self.assertEqual((self.target/'server.py').read_bytes(),self.baseline)

if __name__=='__main__':unittest.main()
