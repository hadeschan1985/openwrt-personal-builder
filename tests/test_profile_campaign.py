import copy
import unittest
from scripts import profile_campaign as p
from tests.test_device_upstream import candidate


class CampaignTests(unittest.TestCase):
    def test_only_matching_successful_software_and_policy_proofs_are_reused(self):
        c=candidate();target='airoha/an7581';profile='fixture';identity=p.key(target,profile)
        self.assertEqual(p.required(c)[0]['profiles'],[profile])
        old={'profiles':{identity:{'status':'passed','fingerprint':p.fingerprint(c,target,profile)}}}
        self.assertEqual(p.required(c,old),[])
        old['profiles'][identity]['status']='failed';self.assertEqual(len(p.required(c,old)),1)
        old['profiles'][identity]['status']='passed';c['policy_sha256']='d'*64;self.assertEqual(len(p.required(c,old)),1)

    def test_private_source_cache_never_enters_public_compilation(self):
        c=candidate();c['targets']['airoha/an7581']['spec']['source_cache']='onecloud-author-20261012';self.assertEqual(p.required(c),[])

    def test_chunks_cover_each_profile_exactly_once(self):
        c=candidate();entry=c['targets']['airoha/an7581'];sample=entry['metadata']['profiles']['profiles']['fixture'];entry['metadata']['profiles']['profiles']={str(i):copy.deepcopy(sample) for i in range(25)}
        rows=p.required(c);self.assertTrue(all(len(r['profiles'])<=8 for r in rows));self.assertEqual(sorted(x for r in rows for x in r['profiles']),sorted(str(i) for i in range(25)))
