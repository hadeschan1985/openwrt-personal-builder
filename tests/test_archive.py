import hashlib
import io
import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import urllib.error
from scripts import archive as a

class ArchiveTests(unittest.TestCase):
    def test_one_time_split_request_is_only_data_and_only_used_on_explicit_push(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'request.json';path.write_text('{"run_id":"40198910508"}')
            with patch.dict(a.os.environ,{'GITHUB_EVENT_NAME':'workflow_dispatch'}):
                with self.assertRaises(ValueError):a.requested_run(path)
            with patch.dict(a.os.environ,{'GITHUB_EVENT_NAME':'push'}):
                self.assertEqual(a.requested_run(path),'40198910508')
                for value in [{'run_id':'../bad'},{'run_id':123},{'run_id':'123','command':'never execute'}]:
                    path.write_text(json.dumps(value))
                    with self.assertRaises(ValueError):a.requested_run(path)

    def historical_bundle(self, path, extra=None):
        payloads={name:b'SYNTHETIC TEST ONLY: '+name.encode() for name in ['a-combined-efi.img.gz','a-combined.img.gz','a-combined-efi.vmdk.zip','a-combined.vmdk.zip','build.log','a.manifest']}
        files=[{'name':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()} for name,content in payloads.items()]
        with zipfile.ZipFile(path,'w') as package:
            for name,content in payloads.items():package.writestr(name,content)
            package.writestr('build-summary.json',json.dumps({'files':files}))
            package.writestr('SHA256SUMS','\n'.join(f"{f['sha256']}  {f['name']}" for f in files)+'\n')
            if extra:package.writestr(extra,b'unverified')
        return payloads

    def test_historical_four_image_bundle_splits_exact_bytes_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'old.zip';destination=root/'out';destination.mkdir()
            payloads=self.historical_bundle(archive);expected=a.legacy_manifest(archive);files=a.extract(archive,destination,expected)
            self.assertEqual(len(files),8)
            for name,content in payloads.items():self.assertEqual((destination/name).read_bytes(),content)
            self.assertEqual(len([p for p in files if p.name.endswith(('.img.gz','.vmdk.zip'))]),4)

    def test_historical_private_archive_preserves_source_without_requiring_workflow_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);bundle=root/'old.zip';payloads=self.historical_bundle(bundle);requests=[];uploaded=[]
            def api(path,token,method='GET',value=None):
                requests.append((path,method,value))
                if path=='':return {'private':True}
                if path=='/actions/runs/123':return {'path':'.github/workflows/build.yml','conclusion':'success','run_number':5,'head_sha':'a'*40}
                if path=='/releases?per_page=100' and method=='GET':return []
                if path.endswith('/artifacts?per_page=100'):return {'artifacts':[{'id':1,'name':'firmware-5','expired':False,'size_in_bytes':bundle.stat().st_size}]}
                if path.startswith('/contents/'):raise urllib.error.HTTPError('',404,'not found',{},None)
                if path=='/releases' and method=='POST':return {'id':9,'assets':[]}
                if path=='/releases/9' and method=='PATCH':return {}
                raise AssertionError(path)
            previous=Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(a.os.environ,{'GH_TOKEN':'test-only','GITHUB_REPOSITORY':'owner/private'}),patch.object(a,'api',side_effect=api),patch.object(a,'download',side_effect=lambda item,path,token:shutil.copyfile(bundle,path)),patch.object(a,'upload',side_effect=lambda release,file,token:uploaded.append((file.name,file.read_bytes()))):
                    a.archive('123')
            finally:os.chdir(previous)
            creation=next(value for path,method,value in requests if path=='/releases' and method=='POST')
            self.assertEqual(creation['target_commitish'],'main');self.assertIn('a'*40,creation['body']);self.assertTrue(creation['draft'])
            self.assertEqual(len(uploaded),8)
            for name,content in uploaded:
                if name in payloads:self.assertEqual(content,payloads[name])

    def test_historical_bundle_rejects_unverified_files_links_and_conflicting_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'old.zip'
            for name in ['unverified.bin','../escape']:
                self.historical_bundle(archive,name)
                with self.assertRaises(ValueError):a.legacy_manifest(archive)
            self.historical_bundle(archive)
            with zipfile.ZipFile(archive) as package:entries={n:package.read(n) for n in package.namelist()}
            entries['SHA256SUMS']=b'0'*64+b'  a-combined.img.gz\n'
            with zipfile.ZipFile(archive,'w') as package:
                for name,content in entries.items():package.writestr(name,content)
            with self.assertRaises(ValueError):a.legacy_manifest(archive)

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
