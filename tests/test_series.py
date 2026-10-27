import copy
import json
from pathlib import Path
import unittest
from scripts.builders import validate_spec,series

class SeriesTests(unittest.TestCase):
    def test_new_series_must_bind_both_feed_and_kernel_origin(self):
        spec=json.loads((Path(__file__).resolve().parents[1]/'configs/builders.json').read_text())['kwrt-25.12-20261012'];spec=copy.deepcopy(spec);spec.pop('targets',None)
        spec['feeds']=spec['feeds'].replace('25.12','26.12')
        with self.assertRaises(ValueError):validate_spec(spec)
        spec['kernel_feed']=spec['kernel_feed'].replace('25.12','26.12');validate_spec(spec);self.assertEqual(series(spec),'26.12')
        spec['feeds']='https://attacker.invalid/releases/26.12/packages/x86_64'
        with self.assertRaises(ValueError):validate_spec(spec)
