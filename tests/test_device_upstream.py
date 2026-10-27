import copy
import json
import os
import base64
import urllib.error
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import builders,device_catalog,device_upstream as u
from scripts import build
from scripts.upstream import digest

def candidate(target='airoha/an7581'):
    spec=copy.deepcopy(builders.resolve('kwrt-25.12-20261012',target))
    data={'profiles':{'target':target,'version_number':'25.12-SNAPSHOT','arch_packages':spec['feeds'].rsplit('/',1)[1],'default_packages':[],'profiles':{'fixture':{'titles':[{'vendor':'QA','model':'Device'}],'images':[{'name':'fixture-sysupgrade.bin','type':'sysupgrade','filesystem':'squashfs','size':10,'sha256':'a'*64}]}}},'packages':['package-'+str(i) for i in range(110)],'package_metadata_errors':[],'image_base':spec['base'],'builder_sha256':spec['sha256']}
    if spec.get('blocked_reason'):data['build_blocked']=spec['blocked_reason']
    spec['metadata_fingerprint']=device_catalog.fingerprint(data)
    targets={target:{'spec':spec,'metadata':data}};policy='c'*64
    fingerprint=digest({'policy_sha256':policy,'targets':{target:digest(targets[target])}})
    return {'schema_version':1,'version':'kwrt-25.12-20261027-'+fingerprint[:8],'source_commit':'b'*40,'policy_sha256':policy,'fingerprint':fingerprint,'targets':targets}

def proof(c,target='airoha/an7581'):
    return {'status':'passed','target':target,'profile':'fixture','tested_version':c['version'],'target_fingerprint':u.target_fingerprint(c['targets'][target]),'policy_sha256':c['policy_sha256'],'run_id':'123','source_commit':'b'*40,'report':{'status':'passed','target':target,'profile':'fixture','version':c['version'],'boot_tested':False,'hardware_tested':False,'files':[{'name':'firmware.bin','bytes':10,'sha256':'a'*64}]}}

class DeviceUpstreamTests(unittest.TestCase):
    def test_candidate_has_immutable_version_and_strict_origin(self):
        c=candidate();u.validate_candidate(c)
        for mutate in [lambda x:x.update(version='kwrt-25.12-20261027-deadbeef'),lambda x:x['targets']['airoha/an7581']['spec'].update(base='https://evil.test'),lambda x:x['targets']['airoha/an7581']['metadata']['profiles'].update(target='x86/64')]:
            bad=copy.deepcopy(c);mutate(bad)
            with self.assertRaises(ValueError):u.validate_candidate(bad)

    def test_new_device_family_cannot_advertise_or_override_x86(self):
        c=candidate();family=u.family(c);self.assertTrue(family['device_only'])
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'configs').mkdir();(root/'updates').mkdir()
            path=root/'configs/builders.json';path.write_text('{}')
            u.write(root/u.REGISTRY,{'schema_version':1,'versions':{c['version']:family}})
            registry=builders.load_registry(path);self.assertEqual(builders.resolve(c['version'],'airoha/an7581',registry)['sha256'],c['targets']['airoha/an7581']['spec']['sha256'])
            with self.assertRaises(ValueError):builders.resolve(c['version'],'x86/64',registry)
            family['targets']['x86/64']=copy.deepcopy(c['targets']['airoha/an7581']['spec'])
            with self.assertRaises(ValueError):builders.validate_device_family(family)

    def test_missing_stale_or_forged_proofs_never_promote(self):
        c=candidate();p=proof(c)
        for mutate in [lambda x:x.update(run_id='999'),lambda x:x.update(target_fingerprint='0'*64),lambda x:x['report'].update(boot_tested=True),lambda x:x['report']['files'][0].update(sha256='bad')]:
            bad=copy.deepcopy(p);mutate(bad)
            with self.assertRaises(ValueError):u.approved_manifest(c,{'airoha/an7581':bad},None,'123','b'*40)
        with self.assertRaises(ValueError):u.approved_manifest(c,{},None,'123','b'*40)

    def test_matching_prior_proof_is_reusable_but_never_claims_hardware_boot(self):
        c=candidate();first=u.approved_manifest(c,{'airoha/an7581':proof(c)},None,'123','b'*40)
        second=u.approved_manifest(c,{},first,'456','d'*40)
        self.assertEqual(second['targets']['airoha/an7581']['proof']['run_id'],'123');self.assertFalse(second['hardware_tested'])
        self.assertTrue(second['devices'][0]['private_metadata']);self.assertTrue(second['devices'][0]['metadata'].startswith('updates/device-metadata/'))
        first['targets']['airoha/an7581']['proof']['policy_sha256']='f'*64
        with self.assertRaises(ValueError):u.approved_manifest(c,{},first,'456','d'*40)

    def test_no_new_platforms_do_not_cause_repeated_expensive_builds(self):
        c=candidate();previous=u.approved_manifest(c,{'airoha/an7581':proof(c)},None,'123','b'*40)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);u.write(root/'approved.json',previous);out=root/'output'
            with patch.object(u,'APPROVED',str(root/'approved.json')),patch.object(u,'WORK',root/'work'),patch.object(u,'discover',return_value=c),patch.dict(os.environ,{'GITHUB_OUTPUT':str(out)}):u.detect()
            self.assertIn('changed=false',out.read_text());self.assertIn('has_cases=false',out.read_text())
            previous['targets']['airoha/an7581'].pop('proof');u.write(root/'approved.json',previous)
            with patch.object(u,'APPROVED',str(root/'approved.json')),patch.object(u,'WORK',root/'work'),patch.object(u,'discover',return_value=c),patch.dict(os.environ,{'GITHUB_OUTPUT':str(out)}):u.detect()
            self.assertIn('has_cases=true',out.read_text())

    def test_data_file_sha_is_the_exact_utf8_payload_digest(self):
        c=candidate();c['targets']['airoha/an7581']['metadata']['profiles']['profiles']['fixture']['titles'][0]['model']='测试设备'
        e=c['targets']['airoha/an7581'];e['spec']['metadata_fingerprint']=device_catalog.fingerprint(e['metadata'])
        c['fingerprint']=digest({'policy_sha256':c['policy_sha256'],'targets':{'airoha/an7581':digest(e)}});c['version']='kwrt-25.12-20261027-'+c['fingerprint'][:8]
        value=u.approved_manifest(c,{'airoha/an7581':proof(c)},None,'123','b'*40)
        self.assertEqual(value['targets']['airoha/an7581']['metadata_sha256'],digest(e['metadata']))

    def test_preparation_and_normal_build_resolve_the_private_approved_registry(self):
        c=candidate();original=Path.cwd()
        baseline=builders.REGISTRY.read_text(encoding='utf-8');template=Path('configs/x86-default.json').read_text()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'configs').mkdir();(root/'configs/builders.json').write_text(baseline,encoding='utf-8');(root/'configs/x86-default.json').write_text(template)
            try:
                os.chdir(root)
                with patch.object(u,'policy_digest',return_value=c['policy_sha256']),patch.object(build,'REGISTRY',root/'configs/builders.json'):
                    config=u.prepare(c,'airoha/an7581','fixture');self.assertEqual(build.normalize(config),config)
                    bad=copy.deepcopy(config);bad['target']='x86/64'
                    with self.assertRaises(ValueError):build.normalize(bad)
            finally:os.chdir(original)

    def test_publisher_preserves_history_and_record_only_concurrent_commits(self):
        c=candidate();p=proof(c);calls=[];trees=[];updates=[]
        old_version='kwrt-25.12-20260101-12345678';old_registry={'schema_version':1,'versions':{old_version:u.family(c)}}
        def api(path,token,method='GET',body=None):
            calls.append((path,method,body))
            if path=='':return {'private':True}
            if path=='/git/blobs':return {'sha':'a'*40}
            if path=='/git/ref/heads/main':return {'object':{'sha':'e'*40}}
            if path.startswith('/git/trees/'):
                return {'truncated':False,'tree':[{'path':name,'type':'blob','sha':u.hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()} for name in u.POLICY_FILES+u.PUBLISH_POLICY for raw in [(u.ROOT/name).read_bytes()]]}
            if path.startswith('/contents/'):
                raw=json.dumps(old_registry).encode();return {'size':len(raw),'encoding':'base64','content':base64.b64encode(raw).decode()}
            if path=='/git/commits/'+'e'*40:return {'tree':{'sha':'f'*40}}
            if path=='/git/trees':trees.append(body);return {'sha':'1'*40}
            if path=='/git/commits':return {'sha':'2'*40}
            if path=='/git/refs/heads/main':updates.append(body);return {}
            raise AssertionError(path)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);u.write(root/'candidate.json',c);u.write(root/'reports/target.json',p)
            with patch.object(u,'APPROVED',str(root/'absent.json')),patch.object(u,'discover',return_value=c),patch.object(u,'api',side_effect=api),patch.dict(os.environ,{'GITHUB_RUN_ID':'123','GITHUB_SHA':'b'*40,'GH_TOKEN':'test-memory-only'}):
                value=u.publish(root/'candidate.json',root/'reports')
            registry=json.loads(next(e['content'] for e in trees[0]['tree'] if e['path']==u.REGISTRY))
            self.assertIn(old_version,registry['versions']);self.assertIn(c['version'],registry['versions']);self.assertEqual(trees[0]['base_tree'],'f'*40)
            self.assertEqual(updates,[{'sha':'2'*40,'force':False}]);self.assertFalse(value['hardware_tested'])
            self.assertFalse(any(e.get('sha') is None and e.get('content') is None for e in trees[0]['tree']))

if __name__=='__main__':unittest.main()
