"""Verify official alternatives for exact models with missing Kwrt defaults."""
import argparse
import os
from pathlib import Path
from scripts import catalog,device_upstream as d
from scripts.build import normalize,require
from scripts.platform_qa import output_options

MODELS=('radxa_rock-3c','radxa_rock-4d','radxa_rock-5-itx','radxa_rock-5c','radxa_zero-3w','linkease_easepi-r1')
VERSION='25.12.6'
TARGET='rockchip/armv8'
CONFIG=Path('configs/public-official-device-qa.json')

def matrix():
    requested=list(MODELS)
    if os.environ.get('GITHUB_EVENT_NAME')=='push':
        request=d.read('configs/public-official-devices-trigger.txt',4096)
        require(isinstance(request,dict) and set(request)=={'profiles'} and isinstance(request['profiles'],list),'Invalid official retry request')
        requested=request['profiles']
        require(1<=len(requested)<=len(MODELS) and all(isinstance(p,str) and p in MODELS for p in requested) and len(set(requested))==len(requested),'Unknown or duplicate official model')
    import json
    with open(os.environ['GITHUB_OUTPUT'],'a') as output:output.write('profiles='+json.dumps(requested)+'\n')

def prepare(profile):
    require(profile in MODELS and not os.environ.get('GH_TOKEN') and not os.environ.get('GITHUB_TOKEN'),'Unrequested public model or account credential present')
    data=catalog.target_data(VERSION,TARGET)
    require(not data['package_metadata_errors'] and profile in data['profiles']['profiles'],'Incomplete official source metadata')
    fs,types=output_options(data['profiles']['profiles'][profile]['images'])
    require(types,'Official alternative must provide a complete device image')
    config=d.read('configs/x86-default.json')
    config.update(builder='official',version=VERSION,target=TARGET,profile=profile,build_mode='device',packages=['curl'],proxies=[])
    config['system'].update(hostname='OfficialDeviceQA',password_secret=True,password_source='root',https=True)
    config['output'].update(filesystem=fs,image_types=types,rootfs=False,efi=False,legacy=False,vmdk=False,rootfs_size_mb=256)
    d.write(CONFIG,normalize(config));d.write('work/public-official-device-metadata.json',data)

def verify(profile):
    config=d.read(CONFIG);image=d.read('outputs/image-report.json')
    require(profile in MODELS and config['profile']==profile and image.get('status')=='passed' and image.get('profile')==profile and image.get('target')==TARGET and image.get('version')==VERSION and image.get('hardware_tested') is False and image.get('boot_tested') is False and image.get('files'),'Official image proof mismatch')
    before=d.read('work/public-official-device-metadata.json')
    require(d.digest(before)==d.digest(catalog.target_data(VERSION,TARGET)),'Official metadata changed during testing')
    value={'schema_version':1,'status':'passed','scope':'actual-synthetic-official-device-build','run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'profile':profile,'target':TARGET,'version':VERSION,'metadata_sha256':d.digest(before),'config_sha256':d.digest(config),'image_validation':image,'kwrt_failure_reclassified':False,'private_repository_inputs_used':False,'private_release_published':False,'boot_tested':False,'hardware_tested':False}
    d.write('work/public-official-device-report.json',value)
    print('PUBLIC_OFFICIAL_DEVICE_RESULT='+d.canonical(value),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['matrix','prepare','verify']);parser.add_argument('--profile');args=parser.parse_args()
    if args.action=='matrix':matrix()
    else:{'prepare':prepare,'verify':verify}[args.action](args.profile)
