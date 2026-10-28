import copy
import json
from pathlib import Path
import unittest
import urllib.error
from qa.device_discovery import metadata

URL='https://openwrt.ai/json/v1/releases/packages-25.12/arm_cortex-a5_vfpv4-index.json'
class DeviceDiscoveryTest(unittest.TestCase):
    def spec(self):return copy.deepcopy(json.loads(Path('configs/builders.json').read_text())['kwrt-25.12-20261012']['targets']['amlogic/meson8b'])
    def test_missing_selector_uses_same_feed_configuration_and_records_supported_parser(self):
        spec=self.spec();before=copy.deepcopy(spec);calls=[]
        def original(value):
            calls.append(copy.deepcopy(value))
            if value.get('metadata_source')=='selector':raise urllib.error.HTTPError(URL,404,'missing',{},None)
            return {'package_index_sha256':['a'*64]*7,'package_metadata_errors':[]}
        metadata(spec,original);expected=copy.deepcopy(before);expected.pop('metadata_source')
        self.assertEqual(spec,expected);self.assertEqual(calls,[before,expected])
    def test_other_targets_errors_and_incomplete_fallback_never_change_the_spec(self):
        for code,url,target,incomplete in [(503,URL,'amlogic/meson8b',False),(404,'https://other.invalid/index','amlogic/meson8b',False),(404,URL,'x86/64',False),(404,URL,'amlogic/meson8b',True)]:
            spec=self.spec();spec['target']=target;before=copy.deepcopy(spec)
            def original(value):
                if not value.get('metadata_source'):return {'package_index_sha256':['a'*64]*6,'package_metadata_errors':[]}
                raise urllib.error.HTTPError(url,code,'missing',{},None)
            with self.assertRaises((urllib.error.HTTPError,ValueError)):metadata(spec,original)
            self.assertEqual(spec,before)
