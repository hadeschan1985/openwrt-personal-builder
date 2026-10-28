"""Actual synthetic box repacks from public sources; no private approval writes."""
import argparse
import datetime as dt
import os
from pathlib import Path
from scripts import box_registry,box_upstream as b,device_catalog,device_upstream as d
from scripts.build import normalize,require

def prepare(model,kernel):
    require(not os.environ.get('GH_TOKEN') and not os.environ.get('GITHUB_TOKEN'),'No account credential may enter this public test')
    candidate=box_registry.validate(b.read(b.WORK/'candidate.json'))
    require(candidate['policy_sha256']==b.policy() and {'model':model,'kernel':kernel} in b.cases(candidate),'Unrequested box test')
    target,spec,data=device_catalog.inspect('armsr/armv8',dynamic_issues=True)
    entry={'spec':spec,'metadata':data};policy=d.policy_digest()
    fingerprint=d.digest({'policy_sha256':policy,'targets':{target:d.target_fingerprint(entry)}})
    version='kwrt-25.12-'+dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y%m%d')+'-'+fingerprint[:8]
    device=d.validate_candidate({'schema_version':1,'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source_commit':os.environ['GITHUB_SHA'],'version':version,'fingerprint':fingerprint,'policy_sha256':policy,'targets':{target:entry}})
    b.write('updates/box-catalogs/'+candidate['release']+'.json',candidate)
    config=d.prepare(device,target,'box',Path('configs/public-box-qa.json'),packages=['curl'])
    config['box']={'model':model,'kernel':kernel,'release':candidate['release']}
    config['output'].update(filesystem='squashfs',image_types=[],rootfs=True,efi=False,legacy=False,vmdk=False,rootfs_size_mb=256)
    b.write('configs/public-box-qa.json',normalize(config))
    d.write('work/public-box-device-candidate.json',device)

def summarize():
    candidate=box_registry.validate(b.read(b.WORK/'candidate.json'))
    require(candidate['policy_sha256']==b.policy(),'Box compiler changed')
    expected=b.cases(candidate);proofs=[]
    require(len(list((b.WORK/'reports').glob('*.json')))==len(expected),'Incomplete or extra box report set')
    for case in expected:
        proof=b.read(b.WORK/'reports'/f"{case['model']}-{case['kernel']}.json")
        require(proof['case']==case and proof['release']==candidate['release'] and proof['run_id']==os.environ['GITHUB_RUN_ID'] and proof['source_commit']==os.environ['GITHUB_SHA'] and proof['policy_sha256']==b.policy(),'Box proof belongs to a different test')
        b.validate_report(proof['report'],candidate,case);proofs.append(proof)
    require(b.discover_sources()==box_registry.pins(candidate),'Upstream changed during box tests; no new validation')
    report={'schema_version':1,'status':'passed','scope':'actual-synthetic-public-box-repacks','run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'policy_sha256':b.policy(),'candidate_release':candidate['release'],'source_pins':box_registry.pins(candidate),'models':len(candidate['models']),'excluded_models':candidate['excluded_models'],'kernels':len(candidate['kernels']),'cases':proofs,'private_repository_inputs_used':False,'private_release_published':False,'approved':False,'boot_tested':False,'hardware_tested':False}
    b.write('work/public-box-report.json',report)
    print('PUBLIC_BOX_RESULT='+box_registry.canonical(report),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','summarize']);parser.add_argument('--model');parser.add_argument('--kernel');args=parser.parse_args()
    if args.action=='prepare':prepare(args.model,args.kernel)
    else:summarize()
