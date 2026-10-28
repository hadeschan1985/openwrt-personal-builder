import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from qa import profile_variant as v

class ProfileVariantTest(unittest.TestCase):
    def proof(self):return json.loads(Path('site/data/r3d-correction.json').read_text())
    def test_exact_identity_and_actual_component_image_evidence_are_required(self):
        proof=self.proof();self.assertEqual(v.validate(proof,proof['run_id'],proof['source_commit'],proof['policy_sha256']),proof)
        for mutate in [lambda p:p.update(run_id='1'),lambda p:p.update(policy_sha256='a'*64),lambda p:p['retained_components'].pop(),lambda p:p['image_validation'].update(hardware_tested=True),lambda p:p['image_validation']['files'][0].update(sha256='invalid')]:
            changed=copy.deepcopy(proof);mutate(changed)
            with self.assertRaises(ValueError):v.validate(changed,proof['run_id'],proof['source_commit'],proof['policy_sha256'])
    def test_only_same_repository_main_candidate_with_successful_discovery_is_resolved(self):
        run={'id':123,'path':'.github/workflows/profile-campaign.yml','status':'queued','conclusion':None,'head_branch':'main','head_repository':{'full_name':'qa/firmware'},'event':'push','head_sha':'b'*40}
        for field,value in [(None,None),('head_branch','untrusted'),('event','pull_request'),('head_repository',{'full_name':'other/fork'}),('detect','failure')]:
            candidate=copy.deepcopy(run)
            if field and field!='detect':candidate[field]=value
            def api(path,token):return {'jobs':[{'name':'detect','conclusion':value if field=='detect' else 'success'}]} if path.endswith('/jobs?per_page=100') else candidate
            with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'GH_TOKEN':'synthetic','GITHUB_REPOSITORY':'qa/firmware','CANDIDATE_RUN':'123','GITHUB_OUTPUT':str(Path(folder)/'out')}),patch.object(v,'api',api):
                if field:
                    with self.assertRaises(ValueError):v.resolve()
                else:v.resolve();self.assertIn('run=123',Path(os.environ['GITHUB_OUTPUT']).read_text())
