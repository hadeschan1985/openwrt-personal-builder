"""Immutable non-x86 release cohorts, tested before private publication.

Detection and compilation have read-only repository access. The fresh publisher
only validates JSON evidence, rechecks public metadata and writes data blobs.
It never extracts an ImageBuilder, runs firmware or executes package scripts.
"""
from __future__ import annotations
import argparse
import base64
import concurrent.futures
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error

from scripts import builders,catalog,device_catalog
from scripts.build import normalize,require,selected_images,package_plan
from scripts.delivery import policy
from scripts.platform_qa import output_options,PREFERRED
from scripts.upstream import api,canonical,digest,builder_checksum

ROOT=Path(__file__).resolve().parents[1]
REGISTRY='updates/device-builders.json'
APPROVED='updates/devices-approved.json'
WORK=Path('work/device-upstream')
SHA=re.compile(r'[a-f0-9]{64}')
COMMIT=re.compile(r'[a-f0-9]{40}')
PROFILE=re.compile(r'[A-Za-z0-9_,.+-]{1,180}')
PACKAGE=re.compile(r'[A-Za-z0-9][A-Za-z0-9+_.-]{0,120}')
POLICY_FILES=['scripts/build.py','scripts/builders.py','scripts/catalog.py','scripts/delivery.py','scripts/image_verify.py','scripts/platform_qa.py','scripts/device_catalog.py','scripts/device_upstream.py','scripts/n1_compat.py','scripts/source_cache.py','scripts/onecloud_provenance.py','scripts/onecloud_pack.py','scripts/box_repack.py','scripts/box_resources.py','scripts/box_registry.py','scripts/rebuild.py','scripts/archive.py','scripts/profile_campaign.py','configs/x86-default.json']

def read(path,limit=20*1024*1024):
    path=Path(path);require(path.is_file() and path.stat().st_size<=limit,'Device update data missing or oversized')
    return json.loads(path.read_text(encoding='utf-8'))

def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(canonical(value),encoding='utf-8')

def policy_digest():
    return digest({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in POLICY_FILES})

def validate_metadata(target,spec,data):
    builders.validate_spec(spec)
    require(target!='x86/64' and spec['target']==target,'Invalid device target')
    require(spec['exclude_defaults']==device_catalog.COMPAT.get(target,[]) and spec['replacement_packages']==[],'Unexpected device compatibility policy')
    meta=data.get('profiles',{})
    require(meta.get('target')==target and meta.get('version_number')==builders.series(spec)+'-SNAPSHOT' and meta.get('arch_packages')==spec['feeds'].rsplit('/',1)[1],'Device metadata identity mismatch')
    require(data.get('image_base')==spec['base'] and data.get('builder_sha256')==spec['sha256'],'Device builder metadata mismatch')
    require(not data.get('package_metadata_errors') and isinstance(data.get('packages'),list) and 100<len(data['packages'])<=40000 and all(isinstance(p,str) and PACKAGE.fullmatch(p) for p in data['packages']),'Incomplete device packages')
    profiles=meta.get('profiles')
    require(isinstance(profiles,dict) and 1<=len(profiles)<=3000,'Invalid device profile count')
    for name,profile in profiles.items():
        require(PROFILE.fullmatch(name) and isinstance(profile.get('images'),list) and 1<=len(profile['images'])<=64,'Invalid device profile')
        for image in profile['images']:
            require(isinstance(image,dict) and re.fullmatch(r'[A-Za-z0-9_.+-]{1,180}',image.get('name','')) and SHA.fullmatch(image.get('sha256','')),'Invalid device image metadata')
    require(data.get('build_blocked')==spec.get('blocked_reason'),'Device block status mismatch')
    require(device_catalog.fingerprint(data)==spec.get('metadata_fingerprint'),'Device metadata fingerprint mismatch')
    require(len(canonical(data).encode())<=4*1024*1024,'Device metadata exceeds per-platform limit')
    return data

def target_fingerprint(entry):return digest(entry)

def validate_candidate(value):
    require(value.get('schema_version')==1 and SHA.fullmatch(value.get('policy_sha256','')) and builders.VERSION.fullmatch(value.get('version','')),'Invalid device candidate header')
    require(COMMIT.fullmatch(value.get('source_commit','')),'Invalid candidate source commit')
    targets=value.get('targets');require(isinstance(targets,dict) and 1<=len(targets)<=128,'Invalid candidate platforms')
    for target,entry in targets.items():
        require(isinstance(entry,dict) and set(entry)=={'spec','metadata'},'Invalid candidate target entry')
        validate_metadata(target,entry['spec'],entry['metadata'])
    expected=digest({'policy_sha256':value['policy_sha256'],'targets':{t:target_fingerprint(e) for t,e in targets.items()}})
    require(value.get('fingerprint')==expected,'Device candidate digest mismatch')
    require(value['version'].endswith('-'+expected[:8]),'Device version must identify the candidate bytes')
    require(len(canonical(value).encode())<=20*1024*1024,'Device candidate exceeds limit')
    return value

def choose_profile(data):
    target=data['profiles']['target'];ids=sorted(data['profiles']['profiles'])
    return PREFERRED[target] if PREFERRED.get(target) in ids else ids[0]

def discover(previous=None):
    rolling=catalog.get_json(builders.ROOT+'/x86/64/profiles.json');match=re.fullmatch(r'(\d{2}\.\d{2})-SNAPSHOT',rolling.get('version_number',''));require(match,'Unrecognized Kwrt release number');series=match.group(1)
    overview=catalog.get_json('https://openwrt.ai/json/v1/releases/'+series+'/overview.json')
    require(overview.get('release')==series and isinstance(overview.get('profiles'),list),'Unexpected selector release')
    targets=sorted({p['target'] for p in overview['profiles']} - {'x86/64'})
    require(1<=len(targets)<=128,'Unexpected selector target count')
    entries={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for target,spec,data in pool.map(lambda t:device_catalog.inspect(t,dynamic_issues=True,series=series),targets):
            validate_metadata(target,spec,data);entries[target]={'spec':spec,'metadata':data}
    expected={(p['target'],p['id']) for p in overview['profiles'] if p['target']!='x86/64'}
    actual={(t,p) for t,e in entries.items() for p in e['metadata']['profiles']['profiles']}
    require(expected==actual,'Selector profile set and device metadata disagree')
    policy_sha=policy_digest();fingerprint=digest({'policy_sha256':policy_sha,'targets':{t:target_fingerprint(e) for t,e in entries.items()}})
    date=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y%m%d')
    version=previous['version'] if previous and previous.get('fingerprint')==fingerprint else f'kwrt-{series}-{date}-{fingerprint[:8]}'
    return validate_candidate({'schema_version':1,'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source_commit':os.environ.get('GITHUB_SHA','0'*40),'version':version,'fingerprint':fingerprint,'policy_sha256':policy_sha,'targets':entries})

def detect():
    previous=read(APPROVED) if Path(APPROVED).exists() else None
    candidate=discover(previous);write(WORK/'candidate.json',candidate)
    cases=[]
    for target,entry in candidate['targets'].items():
        old=(previous or {}).get('targets',{}).get(target,{})
        if entry['spec'].get('blocked_reason'):continue
        reusable=old.get('target_fingerprint')==target_fingerprint(entry) and (previous or {}).get('policy_sha256')==candidate['policy_sha256']
        if reusable:
            try:validate_proof(old.get('proof'),candidate,target)
            except ValueError:reusable=False
        if reusable:continue
        cases.append({'target':target,'profile':choose_profile(entry['metadata'])})
    require(len(cases)<=128,'Too many platform validation jobs')
    changed=not previous or candidate['fingerprint']!=previous['fingerprint'] or bool(cases)
    write(WORK/'required.json',cases)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
            f.write('changed='+str(changed).lower()+'\n')
            f.write('matrix='+json.dumps({'include':cases},separators=(',',':'))+'\n')
            f.write('has_cases='+str(bool(cases)).lower()+'\n')
    print('Device update:',candidate['version'],'changed=',changed,'required platform builds=',len(cases),'blocked=',sum(bool(e['spec'].get('blocked_reason')) for e in candidate['targets'].values()))

def family(candidate):
    return builders.validate_device_family({'device_only':True,'label':'Kwrt 多设备自动更新 · '+candidate['version'].split('-')[2], 'targets':{t:e['spec'] for t,e in candidate['targets'].items()}})

def prepare(candidate,target,profile,path=Path('configs/device-upstream-qa.json'),packages=None,proxies=None,filesystem=None):
    candidate=validate_candidate(candidate);require(policy_digest()==candidate['policy_sha256'],'Validation code changed after detection')
    entry=candidate['targets'][target];require(not entry['spec'].get('blocked_reason'),'Device remains blocked by upstream')
    require(profile in entry['metadata']['profiles']['profiles'],'Unknown representative profile')
    extension=read(REGISTRY) if Path(REGISTRY).exists() else {'schema_version':1,'versions':{}}
    extension['versions'][candidate['version']]=family(candidate);write(REGISTRY,extension)
    images=entry['metadata']['profiles']['profiles'][profile]['images']
    fs,types=output_options(images)
    if filesystem:
        require(filesystem in ('squashfs','ext4'),'Invalid requested test filesystem')
        fs,types=output_options([i for i in images if i.get('filesystem')==filesystem])
    raw=read('configs/x86-default.json')
    raw.update(builder='kwrt',version=candidate['version'],target=target,profile=profile,build_mode='device',packages=packages or [],proxies=proxies or [])
    raw['system'].update(password_secret=True,password_source='root',hostname='DeviceQA')
    raw['output'].update(filesystem=fs,image_types=types,efi=False,legacy=False,vmdk=False,rootfs=not types,rootfs_size_mb=256)
    config=normalize(raw);policy(config,{'REPOSITORY_PRIVATE':'true'});package_plan(config)
    require(selected_images(images,config),'Test requests unavailable device output')
    write(path,config)
    print('Prepared candidate device:',target,profile,fs)
    return config

def attest(candidate,target,profile,destination):
    candidate=validate_candidate(candidate);entry=candidate['targets'][target]
    report=read('outputs/image-report.json');summary=read('outputs/build-summary.json')
    require(report.get('status')=='passed' and report.get('boot_tested') is False and report.get('hardware_tested') is False,'Image validation missing')
    require(report.get('target')==target and report.get('profile')==profile and report.get('version')==candidate['version'],'Wrong device test result')
    require(summary.get('builder_sha256')==entry['spec']['sha256'] and summary.get('dependency_preflight',{}).get('status')=='passed','Wrong builder or missing dependency check')
    require(summary.get('provenance',{}).get('source_commit')==os.environ['GITHUB_SHA'] and str(summary['provenance'].get('run_id'))==os.environ['GITHUB_RUN_ID'],'Device test provenance mismatch')
    _,spec,data=device_catalog.inspect(target,dynamic_issues=True)
    require(target_fingerprint({'spec':spec,'metadata':data})==target_fingerprint(entry),'Device upstream changed during QA')
    require(policy_digest()==candidate['policy_sha256'],'Validation source changed during QA')
    proof={'status':'passed','target':target,'profile':profile,'tested_version':candidate['version'],'target_fingerprint':target_fingerprint(entry),'policy_sha256':candidate['policy_sha256'],'run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'report':report}
    validate_proof(proof,candidate,target);write(destination,proof)

def validate_proof(proof,candidate,target):
    require(isinstance(proof,dict) and proof.get('status')=='passed' and proof.get('target')==target and proof.get('profile') in candidate['targets'][target]['metadata']['profiles']['profiles'],'Invalid platform proof identity')
    require(proof.get('target_fingerprint')==target_fingerprint(candidate['targets'][target]) and proof.get('policy_sha256')==candidate['policy_sha256'],'Stale platform proof')
    require(re.fullmatch(r'[0-9]+',str(proof.get('run_id',''))) and COMMIT.fullmatch(proof.get('source_commit','')) and builders.VERSION.fullmatch(proof.get('tested_version','')),'Invalid proof provenance')
    report=proof.get('report',{})
    require(report.get('status')=='passed' and report.get('boot_tested') is False and report.get('hardware_tested') is False and report.get('target')==target and report.get('profile')==proof['profile'] and report.get('version')==proof['tested_version'],'Invalid platform image report')
    require(isinstance(report.get('files'),list) and 1<=len(report['files'])<=32,'Missing tested device image files')
    for f in report['files']:require(re.fullmatch(r'[A-Za-z0-9_.+-]{1,180}',f.get('name','')) and type(f.get('bytes')) is int and 0<f['bytes']<=1536*1024*1024 and SHA.fullmatch(f.get('sha256','')),'Invalid tested image integrity')
    return proof

def approved_manifest(candidate,proofs,previous,run_id,commit):
    candidate=validate_candidate(candidate);require(re.fullmatch(r'\d+',str(run_id)) and COMMIT.fullmatch(commit),'Invalid publication identity')
    result={'schema_version':1,'version':candidate['version'],'label':family(candidate)['label'],'fingerprint':candidate['fingerprint'],'policy_sha256':candidate['policy_sha256'],'approved_at':dt.datetime.now(dt.timezone.utc).isoformat(),'run_id':str(run_id),'source_commit':commit,'verification_level':'build-and-integrity-only','hardware_tested':False,'targets':{},'devices':[]}
    for target,entry in candidate['targets'].items():
        data=entry['metadata'];metadata_sha=digest(data)
        item={'metadata_path':f'updates/device-metadata/{metadata_sha}/{target}.json','metadata_sha256':metadata_sha,'builder_sha256':entry['spec']['sha256'],'target_fingerprint':target_fingerprint(entry),'profile_count':len(data['profiles']['profiles'])}
        if entry['spec'].get('blocked_reason'):item.update(status='blocked',reason=entry['spec']['blocked_reason'])
        else:
            proof=proofs.get(target)
            if proof:require(proof.get('run_id')==str(run_id) and proof.get('source_commit')==commit,'Proof belongs to another workflow')
            else:proof=(previous or {}).get('targets',{}).get(target,{}).get('proof')
            validate_proof(proof,candidate,target);item.update(status='passed',proof=proof)
        result['targets'][target]=item
        for profile_id,profile in data['profiles']['profiles'].items():
            names=[catalog.title(t) for t in profile.get('titles',[])]
            result['devices'].append({'id':profile_id,'target':target,'version':candidate['version'],'builder':'kwrt','name':names[0] if names else profile_id,'aliases':names,'metadata':item['metadata_path'],'private_metadata':True})
    require(any(t['status']=='passed' for t in result['targets'].values()),'No passed platform in device release')
    require(len(canonical(result).encode())<=4*1024*1024,'Approved device catalog exceeds web limit')
    return result

def api_json(path,token,parent,default):
    try:
        file=api('/contents/'+path+'?ref='+parent,token)
        require(file.get('encoding')=='base64' and file.get('size',0)<=16*1024*1024,'Invalid registry API payload')
        return json.loads(base64.b64decode(file['content']))
    except urllib.error.HTTPError as error:
        require(error.code==404,'Cannot read existing device registry');return copy.deepcopy(default)

def publish(candidate_path=WORK/'candidate.json',reports=WORK/'reports'):
    candidate=validate_candidate(read(candidate_path));previous=read(APPROVED) if Path(APPROVED).exists() else None
    require(candidate['source_commit']==os.environ['GITHUB_SHA'],'Candidate belongs to another source commit')
    require(discover(previous)['fingerprint']==candidate['fingerprint'],'Upstream changed after platform validation; retain previous approved version')
    proofs={}
    for p in Path(reports).glob('*.json'):
        proof=read(p,256*1024);require(proof.get('target') not in proofs,'Duplicate platform evidence');proofs[proof.get('target')]=proof
    require(set(proofs)<=set(candidate['targets']),'Unexpected platform proof')
    approved=approved_manifest(candidate,proofs,previous,os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_SHA'])
    token=os.environ['GH_TOKEN'];require(api('',token)['private'],'Device approvals must stay in the private repository')
    blobs=[]
    for target,entry in candidate['targets'].items():
        path=approved['targets'][target]['metadata_path'];body=canonical(entry['metadata'])
        sha=api('/git/blobs',token,'POST',{'encoding':'utf-8','content':body})['sha']
        blobs.append({'path':path,'mode':'100644','type':'blob','sha':sha})
    for attempt in range(3):
        parent=api('/git/ref/heads/main',token)['object']['sha']
        if parent!=os.environ['GITHUB_SHA']:
            comparison=api('/compare/'+os.environ['GITHUB_SHA']+'...'+parent,token)
            require(comparison.get('status') in ('ahead','identical') and all(f['filename'].startswith(('records/','snapshots/','updates/','docs/')) or f['filename']=='README.md' for f in comparison.get('files',[])),'Source changed during validation; next check will retry')
        extension=api_json(REGISTRY,token,parent,{'schema_version':1,'versions':{}})
        require(set(extension)=={'schema_version','versions'} and extension['schema_version']==1 and isinstance(extension['versions'],dict) and len(extension['versions'])<512,'Invalid or full device history registry')
        existing=extension['versions'].get(candidate['version'])
        require(not existing or existing==family(candidate),'Device version collision')
        extension['versions'][candidate['version']]=family(candidate)
        entries=blobs+[{'path':p,'mode':'100644','type':'blob','content':canonical(v)} for p,v in [(REGISTRY,extension),(APPROVED,approved),(f"updates/device-catalogs/{candidate['version']}.json",approved)]]
        base=api('/git/commits/'+parent,token)['tree']['sha'];tree=api('/git/trees',token,'POST',{'base_tree':base,'tree':entries})['sha']
        commit=api('/git/commits',token,'POST',{'message':'Approve tested device release '+candidate['version'],'tree':tree,'parents':[parent]})['sha']
        try:api('/git/refs/heads/main',token,'PATCH',{'sha':commit,'force':False});break
        except urllib.error.HTTPError as error:
            if attempt==2 or error.code not in (409,422):raise
    print('Approved device release:',candidate['version'],'platforms=',len(approved['targets']),'profiles=',len(approved['devices']))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write('## Device release approved\n\n'+candidate['version']+'\n\n'+str(sum(t['status']=='passed' for t in approved['targets'].values()))+' platforms passed representative build/integrity checks. Physical hardware was NOT tested.\n')
    return approved

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['detect','prepare','attest','publish']);parser.add_argument('--target');parser.add_argument('--profile');args=parser.parse_args()
    if args.action=='detect':detect()
    elif args.action=='prepare':prepare(read(WORK/'candidate.json'),args.target,args.profile)
    elif args.action=='attest':attest(read(WORK/'candidate.json'),args.target,args.profile,WORK/'reports'/f"{args.target.replace('/','-')}.json")
    else:publish()
