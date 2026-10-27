import copy
import json
from pathlib import Path
import unittest
from scripts.build import ConfigError
from scripts import box_registry as registry,box_upstream as upstream

ROOT=Path(__file__).resolve().parents[1]


def candidate():
    c=json.loads((ROOT/'configs/box-builders.json').read_text())
    c['policy_sha256']='a'*64;c['fingerprint']=registry.fingerprint(c);c['release']='box-20261027-'+c['fingerprint'][:8]
    return c


class BoxUpdateTests(unittest.TestCase):
    def test_all_resource_pairs_must_have_real_dtb_bytes(self):
        c=candidate();registry.validate(c)
        broken=copy.deepcopy(c);broken['models'][0]['dtb']='missing.dtb';broken['fingerprint']=registry.fingerprint(broken);broken['release']='box-20261027-'+broken['fingerprint'][:8]
        with self.assertRaisesRegex(ConfigError,'actual DTB'):registry.validate(broken)
        c['repositories'][0]['commit']='b'*40
        with self.assertRaisesRegex(ConfigError,'identity'):registry.validate(c)

    def test_every_kernel_platform_has_a_real_repack_case(self):
        c=candidate();rows=upstream.cases(c)
        expected={(k['id'],m['platform']) for k in c['kernels'] for m in c['models'] if k['id'] in m['kernels']}
        platforms={m['id']:m['platform'] for m in c['models']}
        self.assertEqual({(r['kernel'],platforms[r['model']]) for r in rows},expected)

    def test_latest_patch_requires_primary_asset_digest(self):
        def asset(v,d='sha256:'+'a'*64):return {'name':v+'.tar.gz','digest':d,'id':1,'size':42}
        rows=upstream.latest_assets({'assets':[asset('6.12.9'),asset('6.12.10'),asset('6.12.11',None)]},'stable')
        self.assertEqual(rows[0]['version'],'6.12.10')
        with self.assertRaises(ConfigError):upstream.latest_assets({'assets':[]},'rk3588')

    def test_history_paths_cannot_escape_registry(self):
        for release in ['../../secrets','box-20261027-zzzzzzzz','https://example.com']:
            with self.assertRaises(ConfigError):registry.load(release)
