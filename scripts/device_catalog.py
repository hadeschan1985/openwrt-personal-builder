"""Pin every device exposed by the public selector; never submit upstream builds."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import re
import urllib.request

from scripts import catalog
from scripts.builders import ROOT,ONECLOUD,validate_spec

VERSION='kwrt-25.12-20261012'
COMPAT={'ath79/nand':['autocore'],'ramips/mt7621':['autocore'],'siflower/sf21':['autocore','luci-app-fan']}
ONECLOUD_BAD_DIGEST='e29abe52fea3bdaf77a0af313ccb5c6f06c6564a4f7cdb27d41fd9215d6926b5'
BLOCKED={'amlogic/meson8b':'上游 ImageBuilder 实际 SHA256 与公布值不一致，已暂停构建；不能跳过校验。','amlogic/meson':'上游 N1 默认无线校准包 brcmfmac-nvram-43455-sdio-generic 已缺失，暂停构建，避免交付缺少无线校准数据的固件。'}

def fingerprint(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def inspect(target,dynamic_issues=False,series='25.12'):
    if not re.fullmatch(r'\d{2}\.\d{2}',series):raise ValueError('Invalid source series')
    base='https://dl.openwrt.ai/releases/'+series+'/targets/'+target if target=='amlogic/meson8b' else ROOT+'/'+target
    profile_file='profiles.json.b' if target=='amlogic/meson8b' else 'profiles.json'
    profiles=catalog.get_json(base+'/'+profile_file)
    if profiles.get('version_number')!=series+'-SNAPSHOT' or profiles.get('target')!=target:raise ValueError('Unexpected target release family')
    with urllib.request.urlopen(urllib.request.Request(base+'/sha256sums',headers={'User-Agent':'OpenWrt-Personal-Builder/0.1'}),timeout=60) as response:sums=response.read(1024*1024).decode()
    found=[]
    for line in sums.splitlines():
        parts=line.split()
        if len(parts)==2 and re.fullmatch(r'[a-f0-9]{64}',parts[0]) and re.fullmatch(r'kwrt-imagebuilder-[A-Za-z0-9_.+-]+\.Linux-x86_64\.tar\.(?:zst|xz)',parts[1].lstrip('*')):found.append((parts[1].lstrip('*'),parts[0]))
    if len(found)!=1:raise ValueError('Missing unique ImageBuilder checksum')
    spec={'target':target,'base':base,'archive':found[0][0],'sha256':found[0][1],'feeds':'https://dl.openwrt.ai/releases/'+series+'/packages/'+profiles['arch_packages'],'kernel_feed':'https://dl.openwrt.ai/releases/'+series+'/targets/'+target+'/'+profiles['linux_kernel']['version'],'exclude_defaults':[],'replacement_packages':[],'metadata_source':'selector'}
    if profile_file!='profiles.json':spec['profiles_file']=profile_file
    spec['exclude_defaults']=COMPAT.get(target,[])
    if target in BLOCKED:spec['blocked_reason']=BLOCKED[target]
    validate_spec(spec)
    data=catalog.kwrt_data(spec)
    if dynamic_issues:
        repaired=(target=='amlogic/meson8b' and spec['sha256']!=ONECLOUD_BAD_DIGEST) or (target=='amlogic/meson' and 'brcmfmac-nvram-43455-sdio-generic' in data['packages'])
        if target=='amlogic/meson8b' and spec['sha256']==ONECLOUD_BAD_DIGEST:
            # The independently verified author artifact contains these exact
            # originally published bytes. Never replace the expected checksum.
            spec['source_cache']='onecloud-author-20261012';repaired=True
        if target=='amlogic/meson' and not repaired and 'brcmfmac-nvram-43455-sdio' in data['packages']:
            from scripts.n1_compat import RECIPE,metadata
            spec['compatibility_recipe']=RECIPE;data=metadata(data,spec);repaired=True
        if repaired:spec.pop('blocked_reason',None);data.pop('build_blocked',None)
    spec['metadata_fingerprint']=fingerprint(data)
    return target,spec,data

def sync(registry_path=Path('configs/builders.json'),destination=Path('work/device-catalog')):
    original=catalog.get_json('https://openwrt.ai/json/v1/releases/25.12/overview.json')
    if original.get('release')!='25.12' or not isinstance(original.get('profiles'),list):raise ValueError('Unexpected selector overview')
    targets=sorted({p['target'] for p in original['profiles']})
    if not 1<=len(targets)<=128:raise ValueError('Unexpected platform count')
    registry=json.loads(registry_path.read_text(encoding='utf-8'))
    family=registry[VERSION]
    family['targets']={}
    records=[];all_profiles=set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for target,spec,data in pool.map(inspect,[t for t in targets if t!='x86/64']):
            family['targets'][target]=spec
            all_profiles.update((target,p) for p in data['profiles']['profiles'])
            records.append({'target':target,'profiles':len(data['profiles']['profiles']),'builder_sha256':spec['sha256'],'status':'builder-pinned-not-hardware-tested'})
            path=destination/'targets'/VERSION/f'{target}.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
            print('Pinned',target,len(data['profiles']['profiles']),'devices',flush=True)
    all_profiles.add(('x86/64','generic'))
    requested={(p['target'],p['id']) for p in original['profiles']}
    if requested!=all_profiles:raise ValueError('Public selector and pinned device set disagree: '+str(sorted(requested-all_profiles)))
    family['label']='Kwrt 25.12 · 全设备固定构建器'
    registry_path.write_text(json.dumps(registry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    overview={'schema_version':1,'source':'https://openwrt.ai/json/v1/releases/25.12/overview.json','release':'25.12','device_profiles':len(requested),'platforms':len(targets),'complete_selector_match':True,'targets':records+[{'target':'x86/64','profiles':1,'status':'existing-vm-verified'}]}
    (destination/'coverage.json').write_text(json.dumps(overview,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in overview.items() if k!='targets'},ensure_ascii=False),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--registry',type=Path,default=Path('configs/builders.json'));parser.add_argument('--destination',type=Path,default=Path('work/device-catalog'));args=parser.parse_args();sync(args.registry,args.destination)
