"""Resolve a trusted public candidate and publish data-only R3D variant proof."""
import json
import os
from pathlib import Path
import re
import urllib.error
from scripts import device_upstream as d
from scripts.build import require
from scripts.upstream import api,assert_policy_current

COMPONENTS={'kmod-hwmon-drivetemp','kmod-hwmon-emc2305','kmod-hwmon-lm75','luci-app-fan'}
def validate(value,run,source,policy):
    sha=lambda v:isinstance(v,str) and re.fullmatch('[a-f0-9]{64}',v)
    image=value.get('image_validation',{})
    require(value.get('schema_version')==1 and value.get('status')=='passed' and value.get('run_id')==run and value.get('source_commit')==source and value.get('policy_sha256')==policy and sha(value.get('config_sha256')) and sha(value.get('target_fingerprint')),'Variant proof identity mismatch')
    require(value.get('target')=='ipq806x/generic' and value.get('profile')=='xiaomi_r3d' and value.get('removed_alias')=='hwmon-drivetemp' and value.get('retained_driver')=='kmod-hwmon-drivetemp' and set(value.get('retained_components',[]))==COMPONENTS and value.get('hardware_tested') is False,'Variant hardware components mismatch')
    require(image.get('status')=='passed' and image.get('target')==value['target'] and image.get('profile')==value['profile'] and image.get('boot_tested') is False and image.get('hardware_tested') is False and isinstance(image.get('files'),list) and 1<=len(image['files'])<=32,'Variant image proof missing')
    for file in image['files']:require(isinstance(file.get('name'),str) and re.fullmatch('[A-Za-z0-9_.+-]{1,180}',file['name']) and type(file.get('bytes')) is int and 0<file['bytes']<=1536*1024**2 and sha(file.get('sha256')),'Invalid variant image file')
    return value

def resolve():
    token=os.environ['GH_TOKEN'];identifier=os.environ.get('CANDIDATE_RUN','')
    if not identifier:
        runs=api('/actions/workflows/profile-campaign.yml/runs?per_page=5',token)['workflow_runs']
        runs=[r for r in runs if r.get('head_branch')=='main' and (r.get('status')=='in_progress' or r.get('conclusion')=='success')]
        require(runs,'No public campaign candidate');identifier=str(runs[0]['id'])
    require(re.fullmatch('[1-9][0-9]{0,19}',identifier),'Invalid campaign run')
    run=api('/actions/runs/'+identifier,token)
    require(run['path']=='.github/workflows/profile-campaign.yml' and (run['status']=='in_progress' or run['conclusion']=='success') and run['head_branch']=='main' and run['head_repository']['full_name']==os.environ['GITHUB_REPOSITORY'] and run['event']!='pull_request','Untrusted candidate campaign')
    jobs=api('/actions/runs/'+identifier+'/jobs?per_page=100',token)['jobs']
    require(any(job['name']=='detect' and job['conclusion']=='success' for job in jobs),'Candidate discovery has not completed successfully')
    with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('run='+identifier+'\nsource='+run['head_sha']+'\n')

def publish():
    value=validate(d.read('work/profile-variant/profile-probe-result.json'),os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_SHA'],d.policy_digest());token=os.environ['GH_TOKEN']
    require(api('',token)['private'] is False,'Variant reports are public synthetic evidence only')
    guarded=d.POLICY_FILES+d.PUBLISH_POLICY+['qa/profile_variant.py','.github/workflows/profile-probe.yml','site/lib/compatibility.js']
    for attempt in range(3):
        parent=api('/git/ref/heads/main',token)['object']['sha'];base=api('/git/commits/'+parent,token)['tree']['sha'];assert_policy_current(base,token,guarded,root=d.ROOT,request=api)
        old=api('/contents/site/data/r3d-corrections.json?ref=main',token)
        import base64
        previous=json.loads(base64.b64decode(old['content']));require(previous.get('schema_version')==1 and isinstance(previous.get('proofs'),list),'Existing variant registry invalid')
        key=lambda p:p.get('policy_sha256','')+'/'+p.get('target_fingerprint','')
        matches=[p for p in previous['proofs'] if key(p)==key(value)]
        if any(int(p.get('run_id',0))>=int(value['run_id']) for p in matches):print('Newer matching variant proof retained');return
        proofs=[p for p in previous['proofs'] if key(p)!=key(value)]+[value];require(len(proofs)<=512,'Variant proof registry full; all historical proof retained')
        tree=api('/git/trees',token,'POST',{'base_tree':base,'tree':[{'path':'site/data/r3d-corrections.json','mode':'100644','type':'blob','content':d.canonical({'schema_version':1,'proofs':proofs})}]})['sha']
        commit=api('/git/commits',token,'POST',{'tree':tree,'parents':[parent],'message':'Record tested R3D package-name variant for exact upstream fingerprint'})['sha']
        try:api('/git/refs/heads/main',token,'PATCH',{'sha':commit,'force':False});print('Tested variant metadata published; firmware not published');return
        except urllib.error.HTTPError as error:
            if error.code not in (409,422) or attempt==2:raise

if __name__=='__main__':
    import sys
    require(len(sys.argv)==2 and sys.argv[1] in ('resolve','publish'),'Unknown variant action')
    {'resolve':resolve,'publish':publish}[sys.argv[1]]()
