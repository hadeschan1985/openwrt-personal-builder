import copy
import unittest
import json
from pathlib import Path
from unittest.mock import patch
from scripts import device_combinations as q

class DeviceCombinationTests(unittest.TestCase):
    def test_real_profiles_reject_unadvertised_filesystems_before_scheduling_runners(self):
        cases=q.cases();targets={}
        for c in cases:
            if c['target'] not in targets:targets[c['target']]={'spec':{},'metadata':json.loads((Path('site/data/targets/kwrt-25.12-20261012')/(c['target']+'.json')).read_text(encoding='utf-8'))}
        candidate={'targets':targets};q.validate_models(cases,candidate)
        wrong=copy.deepcopy(cases);next(c for c in wrong if c['profile']=='rpi-4')['filesystem']='ext4'
        with self.assertRaisesRegex(ValueError,'not advertised'):q.validate_models(wrong,candidate)
        selected=q.requested_cases(cases,{'cases':[cases[0]['id']]});self.assertEqual(selected,[cases[0]])
        with self.assertRaises(ValueError):q.requested_cases(cases,{'cases':['unknown']})

    def test_cases_are_bounded_unique_real_platforms_and_distinct_bundles(self):
        cases=q.cases();self.assertEqual(len(cases),12);self.assertEqual(len({c['id'] for c in cases}),12)
        self.assertGreaterEqual(len({c['target'] for c in cases}),8)
        self.assertTrue(any(c.get('filesystem')=='ext4' for c in cases))
        self.assertTrue(any('luci-app-dockerman' in c['packages'] for c in cases))

    def test_unsafe_duplicate_or_oversized_matrix_is_rejected_before_build(self):
        cases=q.cases()
        for bad in [cases*3,[cases[0],cases[0]],[{**cases[0],'id':'$(run)'}],[{**cases[0],'target':'x86/64'}],[{**cases[0],'packages':['foo;command']}]]:
            with patch.object(q.u,'read',return_value=copy.deepcopy(bad)):
                with self.assertRaises(ValueError):q.cases()
