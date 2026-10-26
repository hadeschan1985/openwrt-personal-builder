import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import urllib.error
from scripts import archive as a

class ArchiveTests(unittest.TestCase):
    def test_public_repository_cannot_archive(self):
        with patch.dict(a.os.environ, {'GH_TOKEN':'test'}), patch.object(a,'api',return_value={'private':False}) as api:
            with self.assertRaises(ValueError): a.archive('123')
            self.assertEqual(api.call_count,1)

    def test_safe_extraction_preserves_exact_bytes_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); destination=root/'out';destination.mkdir(); file=root/'artifact.zip'
            payload=b'exact image bytes';expected={'disk.img.gz':{'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}}
            with zipfile.ZipFile(file,'w') as z:z.writestr('disk.img.gz',payload)
            paths=a.extract(file,destination,expected);self.assertEqual(paths[0].read_bytes(),payload)
            with self.assertRaises(ValueError):a.extract(file,destination,expected)
            paths[0].unlink();expected['disk.img.gz']['sha256']='0'*64
            with self.assertRaises(ValueError):a.extract(file,destination,expected)

    def test_traversal_symlink_and_unknown_files_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);destination=root/'out';destination.mkdir();file=root/'artifact.zip'
            for name in ['../escape','folder/file','C:escape','unexpected']:
                with zipfile.ZipFile(file,'w') as z:z.writestr(name,b'x')
                with self.assertRaises(ValueError):a.extract(file,destination,{})
            info=zipfile.ZipInfo('link');info.external_attr=0o120777<<16
            with zipfile.ZipFile(file,'w') as z:z.writestr(info,b'target')
            with self.assertRaises(ValueError):a.extract(file,destination,{'link':{}})

    def test_archive_cap_stops_before_downloading(self):
        responses=[{'private':True},{'path':'.github/workflows/build.yml','conclusion':'success','run_number':8},[{'tag_name':f'personal-build-{n}-{n}','draft':False} for n in range(5)]]
        with patch.dict(a.os.environ,{'GH_TOKEN':'test'}),patch.object(a,'api',side_effect=responses),patch.object(a,'download') as download:
            with self.assertRaises(ValueError):a.archive('123')
            download.assert_not_called()

    def test_completed_archive_is_idempotent_and_never_overwritten(self):
        responses=[{'private':True},{'path':'.github/workflows/build.yml','conclusion':'success','run_number':6},[{'tag_name':'personal-build-6-123','draft':False}]]
        with patch.dict(a.os.environ,{'GH_TOKEN':'test'}),patch.object(a,'api',side_effect=responses) as api,patch.object(a,'download') as download:
            a.archive('123');self.assertEqual(api.call_count,3);download.assert_not_called()

    def test_expired_or_digestless_artifact_never_downloaded(self):
        item={'id':1,'expired':True,'size_in_bytes':10}
        with patch.dict(a.os.environ,{'GITHUB_REPOSITORY':'owner/repo'}),patch.object(a.urllib.request,'build_opener') as opener:
            with self.assertRaises(ValueError):a.download(item,Path('unused'),'test')
            item['expired']=False
            with self.assertRaises(ValueError):a.download(item,Path('unused'),'test')
            opener.assert_not_called()

    def test_signed_storage_download_never_forwards_api_credential(self):
        payload=b'private artifact';item={'id':1,'expired':False,'size_in_bytes':len(payload),'digest':'sha256:'+hashlib.sha256(payload).hexdigest()}
        redirect=urllib.error.HTTPError('https://api.github.com',302,'redirect',{'Location':'https://test.blob.core.windows.net/signed'},None)
        with tempfile.TemporaryDirectory() as folder,patch.dict(a.os.environ,{'GITHUB_REPOSITORY':'owner/repo'}),patch.object(a.urllib.request,'build_opener') as opener,patch.object(a.urllib.request,'urlopen',return_value=io.BytesIO(payload)) as fetch:
            opener.return_value.open.side_effect=redirect;path=Path(folder)/'artifact.zip';a.download(item,path,'private-api-token')
            self.assertEqual(path.read_bytes(),payload);self.assertIsNone(fetch.call_args.args[0].get_header('Authorization'))
