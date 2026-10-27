import hashlib
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from scripts import onecloud_provenance as p

class OneCloudProvenanceTests(unittest.TestCase):
    def test_selected_member_is_bounded_even_in_an_author_verified_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'author.zip'
            with zipfile.ZipFile(path,'w') as archive:archive.writestr(p.BUILDER_NAME,b'test')
            data=path.read_bytes();entry=zipfile.ZipInfo(p.BUILDER_NAME);entry.file_size=701*1024**2
            with patch.object(zipfile.ZipFile,'infolist',return_value=[entry]):
                with self.assertRaisesRegex(ValueError,'Unsafe'):p.inspect(path,hashlib.sha256(data).hexdigest(),len(data))

    def test_whole_author_digest_is_required_before_zip_member_is_processed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'author.zip'
            with zipfile.ZipFile(path,'w') as archive:archive.writestr(p.BUILDER_NAME,b'independent author bytes')
            data=path.read_bytes();digest=hashlib.sha256(data).hexdigest()
            result=p.inspect(path,digest,len(data));self.assertEqual(result['builder_sha256'],hashlib.sha256(b'independent author bytes').hexdigest());self.assertFalse(result['executed'])
            with self.assertRaisesRegex(ValueError,'SHA256'):p.inspect(path,'0'*64,len(data))
            with self.assertRaisesRegex(ValueError,'size mismatch'):p.inspect(path,digest,len(data)+1)

    def test_ambiguous_or_traversing_members_are_not_used(self):
        for names in [[p.BUILDER_NAME,'other/'+p.BUILDER_NAME],['../'+p.BUILDER_NAME],['unrelated.bin']]:
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'author.zip'
                with zipfile.ZipFile(path,'w') as archive:
                    for name in names:archive.writestr(name,b'test')
                data=path.read_bytes()
                with self.assertRaises(ValueError):p.inspect(path,hashlib.sha256(data).hexdigest(),len(data))
