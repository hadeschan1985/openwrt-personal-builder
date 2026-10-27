"""Detect public box updates, require real repack evidence, publish data only."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request
import urllib.error
from scripts import box_resources as resources,box_registry as registry
from scripts.build import normalize,require
from scripts.upstream import api

ROOT=Path(__file__).resolve().parents[1]
WORK=Path('work/box-upstream')
POLICY=['scripts/build.py','scripts/builders.py','scripts/box_repack.py','scripts/box_resources.py','scripts/box_registry.py','scripts/box_upstream.py','scripts/image_verify.py','scripts/rebuild.py','scripts/onecloud_pack.py','scripts/n1_compat.py']
BRANCHES={'stable':('6.6','6.12','6.18'),'rk35xx':('6.1','6.12'),'rk3588':('6.1','6.12')}


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(registry.canonical(value)+'\n',encoding='utf-8')
def policy():return registry.digest({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in POLICY})


def public(repo,path):
    require(repo in resources.REPOSITORIES|{'ophub/kernel'},'Untrusted box public API repository')
    request=urllib.request.Request('https://api.github.com/repos/'+repo+path,headers={'User-Agent':'OpenWrt-Personal-Builder','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=60) as response:raw=response.read(12*1024**2+1)
    require(len(raw)<=12*1024**2,'Oversized box public metadata');return json.loads(raw)


def latest_assets(release,tag):
    result=[]
    for branch in BRANCHES[tag]:
        choices=[a for a in release['assets'] if re.fullmatch(re.escape(branch)+r'\.\d+\.tar\.gz',a['name']) and re.fullmatch(r'sha256:[a-f0-9]{64}',a.get('digest') or '')]
        if not choices:continue
        asset=max(choices,key=lambda a:tuple(map(int,a['name'].removesuffix('.tar.gz').split('.'))));version=asset['name'].removesuffix('.tar.gz')
        result.append({'id':tag+'-'+version,'tag':tag,'version':version,'asset_id':asset['id'],'bytes':asset['size'],'sha256':asset['digest'][7:]})
    require(result,'No checksum-pinned box kernels for '+tag);return result


def discover_sources():
    repositories=[]
    for repo in sorted(resources.REPOSITORIES):repositories.append({'repository':repo,'commit':public(repo,'/git/ref/heads/main')['object']['sha']})
    pin=next(x for x in repositories if x['repository']=='ophub/amlogic-s9xxx-openwrt')
    blobs={k:public(pin['repository'],'/contents/'+path+'?ref='+pin['commit'])['sha'] for k,path in [('model_database_blob',resources.DB_PATH),('remake_blob','remake')]}
    kernels=[]
    for tag in BRANCHES:kernels+=latest_assets(public('ophub/kernel','/releases/tags/kernel_'+tag),tag)
    return resources.source_config(value={'schema_version':1,'repositories':repositories,**blobs,'kernels':kernels})


def cases(catalog):
    rows=[]
    preferred={'amlogic':'s905d','rockchip':'orangepi-5-plus','allwinner':'orangepi-zero3'}
    for kernel in catalog['kernels']:
        for platform in ('amlogic','rockchip','allwinner'):
            choices=[m for m in catalog['models'] if kernel['id'] in m['kernels'] and m['platform']==platform]
            if not choices:continue
            model=next((m for m in choices if m['id']==preferred[platform]),next((m for m in choices if m['upstream_default']),choices[0]))
            rows.append({'model':model['id'],'kernel':kernel['id']})
    require(1<=len(rows)<=36,'Unexpected box regression matrix');return rows


def detect():
    sources=discover_sources();previous=read('updates/box-approved.json') if Path('updates/box-approved.json').exists() else None
    unchanged=previous and registry.pins(previous)==sources and previous['policy_sha256']==policy()
    if unchanged:
        registry.validate(previous);candidate=previous;matrix=[]
    else:
        candidate=resources.generate(sources,WORK/'resources.json',emit=False);candidate['policy_sha256']=policy();candidate['fingerprint']=registry.fingerprint(candidate);candidate['release']='box-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d')+'-'+candidate['fingerprint'][:8];registry.validate(candidate);matrix=cases(candidate)
    write(WORK/'candidate.json',candidate)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('changed='+str(not unchanged).lower()+'\nmatrix='+json.dumps({'include':matrix},separators=(',',':'))+'\n')
    print('BOX_UPDATE='+json.dumps({'release':candidate['release'],'changed':not bool(unchanged),'models':len(candidate['models']),'excluded':len(candidate['excluded_models']),'kernels':[k['id'] for k in candidate['kernels']],'cases':matrix},separators=(',',':')),flush=True)


def prepare(model,kernel):
    candidate=registry.validate(read(WORK/'candidate.json'));require(candidate['policy_sha256']==policy(),'Box validation policy changed')
    require({'model':model,'kernel':kernel} in cases(candidate),'Unrequested box validation combination')
    write('updates/box-catalogs/'+candidate['release']+'.json',candidate)
    devices=read('updates/devices-approved.json');config=read('configs/x86-default.json')
    config.update(builder='kwrt',version=devices['version'],target='armsr/armv8',profile='box',build_mode='device',packages=['curl'],box={'model':model,'kernel':kernel,'release':candidate['release']})
    config['system'].update(hostname='BoxUpdateQA',password_secret=True,password_source='root');config['output'].update(filesystem='squashfs',image_types=[],rootfs=True,efi=False,legacy=False,vmdk=False,rootfs_size_mb=256)
    write('configs/box-upstream-qa.json',normalize(config))


def validate_report(report,candidate,case):
    kernel=next(k for k in candidate['kernels'] if k['id']==case['kernel']);model=next(m for m in candidate['models'] if m['id']==case['model'])
    require(report.get('status')=='passed' and all(report.get(k)==v for k,v in case.items()) and report.get('kernel_release')==kernel['release'] and report.get('dtb')==model['dtb'] and report.get('dtb_sha256')==kernel['dtbs'][model['dtb']]['sha256'],'Box report does not match fixed candidate')
    require(report.get('repositories')==candidate['repositories'] and report.get('kernel_asset_sha256')==kernel['sha256'] and report.get('filesystem')=='btrfs' and report.get('module_vermagic_checked',0)>=20,'Box source/kernel verification missing')
    require(report.get('boot_tested') is False and report.get('hardware_tested') is False and registry.SHA.fullmatch(report.get('personal_defaults_sha256','')),'False box hardware evidence')
    file=report.get('file',{});require(re.fullmatch(r'[A-Za-z0-9_.+-]+\.img\.gz',file.get('name','')) and type(file.get('bytes')) is int and 0<file['bytes']<=1536*1024**2 and registry.SHA.fullmatch(file.get('sha256','')),'Invalid box output file')


def attest(model,kernel):
    candidate=registry.validate(read(WORK/'candidate.json'));require(policy()==candidate['policy_sha256'],'Box policy changed during validation')
    report=read('outputs/box-pack-report.json');case={'model':model,'kernel':kernel};validate_report(report,candidate,case)
    image=read('outputs/image-report.json');require(image['status']=='passed' and image['box_packaging']==report,'Final box image verification missing')
    proof={'case':case,'report':report,'release':candidate['release'],'run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'policy_sha256':policy()}
    write(WORK/'reports'/f'{model}-{kernel}.json',proof)


def publish():
    candidate=registry.validate(read(WORK/'candidate.json'));require(policy()==candidate['policy_sha256'],'Box source changed after detection')
    expected=cases(candidate);proofs=[]
    for case in expected:
        proof=read(WORK/'reports'/f"{case['model']}-{case['kernel']}.json")
        require(proof['case']==case and proof['release']==candidate['release'] and proof['run_id']==os.environ['GITHUB_RUN_ID'] and proof['source_commit']==os.environ['GITHUB_SHA'] and proof['policy_sha256']==policy(),'Box evidence belongs to another validation run')
        validate_report(proof['report'],candidate,case);proofs.append(proof)
    token=os.environ['GH_TOKEN'];require(api('',token)['private'],'Box approval requires the private repository')
    approved={**candidate,'status':'representative-repack-verified','approved_at':dt.datetime.now(dt.timezone.utc).isoformat(),'run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'verification_level':'repack-and-integrity-only','hardware_tested':False,'proofs':proofs}
    for attempt in range(3):
        parent=api('/git/ref/heads/main',token)['object']['sha']
        if parent!=os.environ['GITHUB_SHA']:
            diff=api('/compare/'+os.environ['GITHUB_SHA']+'...'+parent,token);require(diff.get('status') in ('ahead','identical') and all(f['filename'].startswith(('records/','snapshots/','updates/','docs/')) or f['filename']=='README.md' for f in diff.get('files',[])),'Code changed during box validation; next check will retry')
        base=api('/git/commits/'+parent,token)['tree']['sha'];entries=[{'path':p,'mode':'100644','type':'blob','content':registry.canonical(approved)} for p in ['updates/box-approved.json','updates/box-catalogs/'+candidate['release']+'.json']]
        tree=api('/git/trees',token,'POST',{'base_tree':base,'tree':entries})['sha'];commit=api('/git/commits',token,'POST',{'tree':tree,'parents':[parent],'message':'Approve tested box resources '+candidate['release']})['sha']
        try:api('/git/refs/heads/main',token,'PATCH',{'sha':commit,'force':False});break
        except urllib.error.HTTPError as error:
            if error.code not in (409,422) or attempt==2:raise
    print('Approved fixed box release:',candidate['release'],'models=',len(candidate['models']),'actual combinations=',len(proofs),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['detect','prepare','attest','publish']);parser.add_argument('--model');parser.add_argument('--kernel');args=parser.parse_args()
    if args.action=='detect':detect()
    elif args.action=='prepare':prepare(args.model,args.kernel)
    elif args.action=='attest':attest(args.model,args.kernel)
    else:publish()
