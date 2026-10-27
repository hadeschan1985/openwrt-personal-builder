import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from scripts.build import ConfigError
from scripts import box_registry as registry,box_upstream as upstream

ROOT=Path(__file__).resolve().parents[1]


def candidate():
    c=json.loads((ROOT/'configs/box-builders.json').read_text())
    c['policy_sha256']='a'*64;c['fingerprint']=registry.fingerprint(c);c['release']='box-20261027-'+c['fingerprint'][:8]
    return c


class BoxUpdateTests(unittest.TestCase):
    def test_legacy_script_entry_can_load_snapshot_and_box_modules(self):
        c=json.loads((ROOT/'configs/x86-default.json').read_text());c.update(builder='kwrt',version='kwrt-25.12-20261012',target='armsr/armv8',profile='box',box={'model':'s905d','kernel':'stable-6.12.114'})
        c['output'].update(rootfs=True,efi=False,legacy=False,vmdk=False,image_types=[])
        result=subprocess.run([sys.executable,'scripts/build.py','--plan'],cwd=ROOT,env={**os.environ,'CONFIG_JSON':json.dumps(c)},capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(json.loads(result.stdout)['config']['box'],c['box'])

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

    def test_legacy_kernel_expansion_tests_newly_supported_dtb(self):
        c={'kernels':[{'id':'stable-5.15.223','tag':'stable','version':'5.15.223'}],'models':[{'id':m,'platform':'amlogic','upstream_default':False,'kernels':['stable-5.15.223']} for m in ('s905d','s905x-tx9')]}
        self.assertEqual(upstream.cases(c),[{'model':'s905x-tx9','kernel':'stable-5.15.223'}])

    def test_history_paths_cannot_escape_registry(self):
        for release in ['../../secrets','box-20261027-zzzzzzzz','https://example.com']:
            with self.assertRaises(ConfigError):registry.load(release)
