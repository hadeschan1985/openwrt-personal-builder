"""Resumable actual profile compilation, synthetic settings, reports only.

Runs on public standard Actions runners without user secrets. The one private
author-cache profile is verified separately by the real private webpage E2E.
No firmware images, user files or private build records are uploaded here.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import urllib.error
from scripts import device_upstream as d
from scripts.build import require
from scripts.upstream import api

WORK=Path('work/profile-campaign')
CHUNK=8


def key(target,profile):return hashlib.sha256((target+'/'+profile).encode()).hexdigest()[:24]
def fingerprint(candidate,target,profile):return d.digest({'policy':candidate['policy_sha256'],'target':d.target_fingerprint(candidate['targets'][target]),'profile':profile,'software':['curl'],'output_policy':'first-supported-device-image-v1'})


def required(candidate,previous=None):
    previous=(previous or {}).get('profiles',{});rows=[]
    for target,entry in candidate['targets'].items():
        if entry['spec'].get('source_cache'):continue
        todo=[]
        for profile in sorted(entry['metadata']['profiles']['profiles']):
            old=previous.get(key(target,profile),{})
            if old.get('status')=='passed' and old.get('fingerprint')==fingerprint(candidate,target,profile):continue
            todo.append(profile)
        for start in range(0,len(todo),CHUNK):rows.append({'target':target,'batch':len(rows),'profiles':todo[start:start+CHUNK]})
    require(len(rows)<=256,'Profile campaign exceeds Actions matrix limit');return rows


def detect():
    candidate=d.discover();d.write(WORK/'candidate.json',candidate)
    previous=d.read('updates/profile-coverage.json') if Path('updates/profile-coverage.json').exists() else None
    rows=required(candidate,previous);d.write(WORK/'batches.json',rows)
    with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('matrix='+json.dumps({'include':[{'target':r['target'],'batch':r['batch']} for r in rows]},separators=(',',':'))+'\nchanged='+str(bool(rows)).lower()+'\n')
    print('Actual profile campaign:',sum(len(r['profiles']) for r in rows),'profiles in',len(rows),'bounded batches; private author source is covered by private E2E')


def clean():
    require(sys.platform.startswith('linux') and os.environ.get('GITHUB_ACTIONS')=='true','Profile cleanup is only for its isolated Actions workspace')
    root=Path.cwd().resolve()
    for name in ('work/builder','work/extracted','work/box-repack','work/onecloud-pack','outputs'):
        path=Path(name);require(path.resolve().is_relative_to(root) and not path.is_symlink(),'Profile workspace escaped checkout')
        if path.exists():shutil.rmtree(path)


def execute(command,log):
    env={k:v for k,v in os.environ.items() if k not in {'GH_TOKEN','GITHUB_TOKEN','ROUTER_PASSWORD','PPPOE_USERNAME','PPPOE_PASSWORD','WIFI_PASSWORD','CONFIG_JSON'} and not k.startswith('ACTIONS_')}
    with log.open('w',encoding='utf-8') as output:
        process=subprocess.Popen(command,stdout=output,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        try:return process.wait(timeout=900)
        except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait();return 124


def run(batch):
    candidate=d.validate_candidate(d.read(WORK/'candidate.json'));require(candidate['policy_sha256']==d.policy_digest(),'Campaign source policy changed')
    row=next((r for r in d.read(WORK/'batches.json') if r['batch']==batch),None);require(row,'Unknown profile batch')
    folder=WORK/'reports';folder.mkdir(parents=True,exist_ok=True);logs=WORK/'logs';logs.mkdir(exist_ok=True)
    for profile in row['profiles']:
        target=row['target'];identity=key(target,profile);report={'target':target,'profile':profile,'fingerprint':fingerprint(candidate,target,profile),'policy_sha256':candidate['policy_sha256'],'target_fingerprint':d.target_fingerprint(candidate['targets'][target]),'run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'hardware_tested':False,'boot_tested':False}
        log=logs/(identity+'.log')
        try:
            clean();d.prepare(candidate,target,profile,Path('configs/profile-campaign-qa.json'),packages=['curl'])
            code=execute([sys.executable,'-m','scripts.build','--config','configs/profile-campaign-qa.json'],log);require(code==0,'Compilation failed' if code!=124 else 'Compilation exceeded 15 minute per profile bound')
            code=execute([sys.executable,'-m','scripts.image_verify'],logs/(identity+'-integrity.log'));require(code==0,'Image container verification failed')
            image=d.read('outputs/image-report.json');require(image['status']=='passed' and image['target']==target and image['profile']==profile and image['hardware_tested'] is False,'Image proof mismatch')
            report.update(status='passed',image_validation=image)
        except (ValueError,OSError,subprocess.SubprocessError) as error:
            report.update(status='failed',reason=str(error)[:500],diagnostic=log.read_text(encoding='utf-8',errors='replace')[-1200:] if log.exists() else '')
        d.write(folder/(identity+'.json'),report);print('PROFILE_RESULT='+json.dumps({k:report[k] for k in ('target','profile','status','run_id')},separators=(',',':')),flush=True)
    clean()


def summarize(publish=False):
    candidate=d.validate_candidate(d.read(WORK/'candidate.json'));batches=d.read(WORK/'batches.json');expected={(r['target'],p) for r in batches for p in r['profiles']};reports={}
    for path in (WORK/'reports').glob('*.json'):
        item=d.read(path);target,profile=item['target'],item['profile'];require((target,profile) in expected and item.get('run_id')==os.environ['GITHUB_RUN_ID'] and item.get('source_commit')==os.environ['GITHUB_SHA'] and item.get('fingerprint')==fingerprint(candidate,target,profile) and item.get('status') in ('passed','failed') and item.get('hardware_tested') is False,'Campaign evidence identity mismatch')
        if item['status']=='passed':require(item.get('image_validation',{}).get('status')=='passed' and item['image_validation']['profile']==profile and item['image_validation']['target']==target,'Missing actual image verification')
        require(key(target,profile) not in reports,'Duplicate campaign proof');reports[key(target,profile)]=item
    require(len(reports)==len(expected),'Some profile batches did not finish; partial reports retained without promotion')
    old=d.read('updates/profile-coverage.json') if Path('updates/profile-coverage.json').exists() else {'profiles':{}}
    ledger={'schema_version':1,'policy_sha256':candidate['policy_sha256'],'updated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'candidate_version':candidate['version'],'hardware_tested':False,'profiles':{**old['profiles'],**reports}}
    current=[p for t,e in candidate['targets'].items() for p in e['metadata']['profiles']['profiles'] if not e['spec'].get('source_cache')]
    ledger['summary']={'requested':len(expected),'passed':sum(x['status']=='passed' for x in reports.values()),'failed':sum(x['status']=='failed' for x in reports.values()),'current_public_profiles':len(current),'private_author_cache_profiles':sum(len(e['metadata']['profiles']['profiles']) for e in candidate['targets'].values() if e['spec'].get('source_cache'))}
    d.write(WORK/'coverage.json',ledger);print('PROFILE_CAMPAIGN_SUMMARY='+json.dumps(ledger['summary'],separators=(',',':')),flush=True)
    if not publish:return
    token=os.environ['GH_TOKEN'];require(not api('',token)['private'],'Full synthetic profile campaign uses public standard runners')
    for attempt in range(3):
        parent=api('/git/ref/heads/main',token)['object']['sha'];base=api('/git/commits/'+parent,token)['tree']['sha']
        diff=api('/compare/'+os.environ['GITHUB_SHA']+'...'+parent,token)
        require(parent==os.environ['GITHUB_SHA'] or diff.get('status') in ('ahead','identical') and all(f['filename'].startswith(('updates/','docs/','site/','qa/','tests/','.github/')) or f['filename']=='README.md' for f in diff.get('files',[])),'Source changed during campaign; retain reports for review, no current-coverage promotion')
        tree=api('/git/trees',token,'POST',{'base_tree':base,'tree':[{'path':'updates/profile-coverage.json','mode':'100644','type':'blob','content':d.canonical(ledger)}]})['sha']
        commit=api('/git/commits',token,'POST',{'tree':tree,'parents':[parent],'message':'Record actual profile compilation coverage'})['sha']
        try:api('/git/refs/heads/main',token,'PATCH',{'sha':commit,'force':False});return
        except urllib.error.HTTPError as error:
            if error.code not in (409,422) or attempt==2:raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['detect','run','summarize','publish']);parser.add_argument('--batch',type=int);args=parser.parse_args()
    if args.action=='detect':detect()
    elif args.action=='run':run(args.batch)
    else:summarize(args.action=='publish')
