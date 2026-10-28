import hashlib
from pathlib import Path
import tempfile
import unittest
from qa.offline_apk_mtime import prepare

class OfflineApkMtimeTest(unittest.TestCase):
    def test_epoch_zero_packages_keep_exact_bytes_and_ipk_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);apk=root/'package-1.apk';ipk=root/'other-1.ipk'
            apk.write_bytes(b'ADBd archived package bytes');ipk.write_bytes(b'ipk bytes')
            import os
            os.utime(apk,ns=(0,0));os.utime(ipk,ns=(0,0));before=hashlib.sha256(apk.read_bytes()).digest()
            report=prepare(root);self.assertEqual(report['apk_files'],1);self.assertEqual(apk.stat().st_mtime_ns,1000000000);self.assertEqual(ipk.stat().st_mtime_ns,0);self.assertEqual(hashlib.sha256(apk.read_bytes()).digest(),before);self.assertEqual(prepare(root),report)
    def test_unexpected_files_and_directories_stop_before_build(self):
        for is_dir in (False,True):
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'unexpected';path.mkdir() if is_dir else path.write_bytes(b'not a package')
                with self.assertRaises(ValueError):prepare(folder)
