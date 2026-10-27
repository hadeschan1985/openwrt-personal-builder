import io
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
import urllib.error
from scripts import source_cache as c
from scripts.builders import resolve,validate_spec

class SourceCacheTests(unittest.TestCase):
    def test_other_platforms_and_other_digests_cannot_request_this_cache(self):
        spec=resolve('kwrt-25.12-20261012','amlogic/meson8b');spec['source_cache']=c.CACHE_ID;validate_spec(spec)
        for bad in [{**spec,'target':'amlogic/meson'},{**spec,'sha256':'0'*64},{**spec,'source_cache':'unverified'}]:
            with self.assertRaises(ValueError):validate_spec(bad)

    def test_only_the_fixed_author_builder_can_be_preserved(self):
        proof={'source_repository':'kiddin9/Kwrt','source_commit':c.SOURCE_COMMIT,'run_id':c.RUN_ID,'artifact_id':c.ARTIFACT_ID,'artifact_sha256':c.ARTIFACT_SHA256,'builder_name':c.BUILDER_NAME,'builder_sha256':c.BUILDER_SHA256,'builder_bytes':c.BUILDER_BYTES,'executed':False,'verification':'author-artifact-sha256-and-member-crc'}
        c.validate_proof(proof)
        for key,value in [('source_repository','other/repo'),('artifact_sha256','0'*64),('builder_sha256','0'*64),('executed',True)]:
            with self.assertRaises(ValueError):c.validate_proof({**proof,key:value})

    def test_signed_storage_download_does_not_receive_api_credential(self):
        data=b'verified';digest=hashlib.sha256(data).hexdigest()
        asset={'id':123,'name':c.BUILDER_NAME,'size':len(data),'digest':'sha256:'+digest}
        redirect=urllib.error.HTTPError('https://api.github.com/file',302,'redirect',{'Location':'https://release-assets.githubusercontent.com/file?temporary=example'},None)
        with tempfile.TemporaryDirectory() as folder,patch.object(c,'BUILDER_BYTES',len(data)),patch.object(c,'BUILDER_SHA256',digest),patch.object(c.urllib.request,'build_opener',return_value=Mock(open=Mock(side_effect=redirect))),patch.object(c.urllib.request,'urlopen',return_value=io.BytesIO(data)) as fetch:
            destination=Path(folder)/'builder';c.download_asset(asset,destination,'private-test-token','owner/private-builds')
            self.assertIsNone(fetch.call_args.args[0].get_header('Authorization'));self.assertEqual(destination.read_bytes(),data)

    def test_foreign_redirect_is_rejected_before_following_it(self):
        asset={'id':123,'name':c.BUILDER_NAME,'size':c.BUILDER_BYTES,'digest':'sha256:'+c.BUILDER_SHA256}
        redirect=urllib.error.HTTPError('https://api.github.com/file',302,'redirect',{'Location':'https://evil.test/file'},None)
        with patch.object(c.urllib.request,'build_opener',return_value=Mock(open=Mock(side_effect=redirect))),patch.object(c.urllib.request,'urlopen') as fetch:
            with self.assertRaisesRegex(ValueError,'Untrusted'):c.download_asset(asset,Path('unused'),'private-test-token','owner/private-builds')
            fetch.assert_not_called()
