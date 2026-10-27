"""Bounded opt-in cloud builds of real devices with different software bundles."""
import argparse
import copy
import json
import os
import re
from pathlib import Path
from scripts import device_upstream as u
from scripts.build import require

CASES=Path('configs/device-combinations.json')

def cases():
    value=u.read(CASES,64*1024);require(isinstance(value,list) and 1<=len(value)<=24,'Invalid bounded QA matrix')
    ids=set()
    for c in value:
        require(isinstance(c,dict) and {'id','target','profile','packages'}<=set(c)<= {'id','target','profile','packages','proxies','filesystem'},'Invalid QA case fields')
        require(re.fullmatch(r'[a-z0-9-]{1,60}',c['id']) and c['id'] not in ids,'Invalid QA case ID');ids.add(c['id'])
        require(re.fullmatch(r'[a-z0-9_-]+/[a-z0-9_-]+',c['target']) and c['target']!='x86/64' and u.PROFILE.fullmatch(c['profile']),'Invalid QA device')
        for field in ('packages','proxies'):
            names=c.get(field,[]);require(isinstance(names,list) and len(names)<=24 and all(isinstance(p,str) and u.PACKAGE.fullmatch(p) for p in names),'Invalid QA software list')
        require(c.get('filesystem','squashfs') in ('squashfs','ext4'),'Invalid QA filesystem')
    return value

def candidate():
    approved=u.read(u.APPROVED);extension=u.read(u.REGISTRY);version=approved['version']
    require(approved['policy_sha256']==u.policy_digest(),'Approval belongs to older validation code; run device update first')
    targets={}
    for target,item in approved['targets'].items():
        expected=f"updates/device-metadata/{item['metadata_sha256']}/{target}.json"
        require(item['metadata_path']==expected,'Invalid approved metadata path')
        data=u.read(expected,4*1024*1024)
        require(u.digest(data)==item['metadata_sha256'],'Approved metadata digest mismatch')
        targets[target]={'spec':copy.deepcopy(extension['versions'][version]['targets'][target]),'metadata':data}
    return u.validate_candidate({'schema_version':1,'version':version,'source_commit':os.environ.get('GITHUB_SHA','0'*40),'fingerprint':approved['fingerprint'],'policy_sha256':approved['policy_sha256'],'targets':targets})

def validate_models(value,c):
    for case in value:
        entry=c['targets'].get(case['target']);require(entry is not None and not entry['spec'].get('blocked_reason'),'QA platform unavailable: '+case['id'])
        data=entry['metadata'];profile=data['profiles']['profiles'].get(case['profile']);require(profile is not None,'QA profile unavailable: '+case['id'])
        filesystems={i.get('filesystem') for i in profile['images']}
        require(not case.get('filesystem') or case['filesystem'] in filesystems,'QA filesystem not advertised by this device: '+case['id'])
        missing=set(case['packages']+case.get('proxies',[]))-set(data['packages'])
        require(not missing,'QA packages unavailable: '+case['id']+' '+','.join(sorted(missing)))
    return value

def requested_cases(value,request):
    require(isinstance(request,dict) and set(request)=={'cases'} and isinstance(request['cases'],list) and request['cases'] and len(request['cases'])<=24,'Invalid QA retry request')
    ids=request['cases'];require(all(isinstance(i,str) for i in ids) and len(ids)==len(set(ids)) and set(ids)<={c['id'] for c in value},'Unknown or duplicate QA retry case')
    return [c for c in value if c['id'] in ids]

def prepare(case_id):
    selected=next((c for c in cases() if c['id']==case_id),None);require(selected is not None,'Unknown QA case')
    c=candidate();u.write(u.WORK/'candidate.json',c)
    config=u.prepare(c,selected['target'],selected['profile'],Path('configs/device-combination-qa.json'),selected['packages'],selected.get('proxies'),selected.get('filesystem'))
    u.write(u.WORK/'combination.json',selected);return config

def attest():
    c=u.read(u.WORK/'candidate.json');selected=u.read(u.WORK/'combination.json')
    u.attest(c,selected['target'],selected['profile'],Path('outputs/combination-proof.json'))
    summary=u.read('outputs/build-summary.json');summary['qa_case']=selected;u.write('outputs/combination-summary.json',summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:
            f.write('## Software combination passed\n\n'+selected['id']+' · '+selected['target']+' · '+selected['profile']+'\n\nActual compilation, dependency and manifest checks, and image integrity passed. No physical boot, radio, proxy connection or storage service test was performed.\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['matrix','prepare','attest']);parser.add_argument('--case');args=parser.parse_args()
    if args.action=='matrix':
        value=validate_models(cases(),candidate())
        if os.environ.get('GITHUB_EVENT_NAME')=='push':value=requested_cases(value,u.read('configs/device-combinations-trigger.txt',64*1024))
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('matrix='+json.dumps([c['id'] for c in value])+'\n')
    elif args.action=='prepare':prepare(args.case)
    else:attest()
