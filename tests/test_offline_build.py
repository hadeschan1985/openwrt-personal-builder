from pathlib import Path
import tempfile
import unittest
from qa.offline_build import canonical_name,canonicalize

class OfflineBuildTest(unittest.TestCase):
    def test_identity_comes_from_package_metadata_and_bytes_remain_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);packages=root/'packages';packages.mkdir();cached=packages/'misleading-cache.a1234567.apk';cached.write_bytes(b'exact package bytes')
            rows=canonicalize(root,lambda p:{'info':{'name':'real-package','version':'1.2.3-r4'}})
            self.assertEqual(rows[0]['local'],'real-package-1.2.3-r4.apk');self.assertFalse(cached.exists());self.assertEqual((packages/rows[0]['local']).read_bytes(),b'exact package bytes');self.assertEqual((packages/rows[0]['local']).stat().st_mtime_ns,1000000000)
    def test_invalid_paths_and_conflicting_versions_stop_before_renaming(self):
        for data in [{'info':{'name':'../escape','version':'1'}},{'info':{'name':'valid','version':'../../escape'}},{'info':{'name':'valid','version':'1'}}]:
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder);packages=root/'packages';packages.mkdir();cached=packages/'cached.apk';cached.write_bytes(b'one')
                if data['info']['name']=='valid' and data['info']['version']=='1':(packages/'valid-1.apk').write_bytes(b'other')
                with self.assertRaises(ValueError):canonicalize(root,lambda p:data)
                self.assertTrue(cached.exists())
        with self.assertRaises(ValueError):canonical_name({'info':{'name':'valid','version':None}})
