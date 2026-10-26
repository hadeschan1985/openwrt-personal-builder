"""Validate every listed device configuration against its own pinned metadata."""
import argparse
import json
from pathlib import Path
import re

from scripts import build,builders
from scripts.delivery import policy
from scripts.platform_qa import output_options

def audit(data,destination):
    index=json.loads((data/'catalog.json').read_text(encoding='utf-8'))
    devices=[d for d in index['devices'] if d.get('builder')=='kwrt']
    cache={};seen=set();blocked=[];rootfs=[]
    template=json.loads(Path('configs/x86-default.json').read_text(encoding='utf-8'))
    for device in devices:
        identity=(device['version'],device['target'],device['id'])
        build.require(identity not in seen,'Duplicate device identity');seen.add(identity)
        key=(device['version'],device['target'])
        if key not in cache:cache[key]=json.loads((data/device['metadata']).read_text(encoding='utf-8'))
        metadata=cache[key];spec=builders.resolve(*key)
        build.require(metadata['profiles']['target']==device['target'] and metadata['builder_sha256']==spec['sha256'],'Wrong platform metadata')
        profile=metadata['profiles']['profiles'][device['id']]
        raw=json.loads(json.dumps(template));raw.update(builder='kwrt',version=device['version'],target=device['target'],profile=device['id'],build_mode='device',packages=[])
        raw['system'].update(password_secret=True,password_source='root')
        if device['target']!='x86/64':
            filesystem,types=output_options(profile['images'])
            raw['output'].update(filesystem=filesystem,image_types=types,efi=False,legacy=False,vmdk=False,rootfs=not types)
        config=build.normalize(raw);policy(config,{'REPOSITORY_PRIVATE':'true'});build.package_plan(config)
        images=build.selected_images(profile['images'],config)
        build.require(images and all(re.fullmatch(r'[A-Za-z0-9_.+-]{1,180}',i['name']) for i in images),'No safe selectable device output')
        if spec.get('blocked_reason'):blocked.append({'target':device['target'],'profile':device['id'],'reason':spec['blocked_reason']})
        if all(i.get('filesystem')=='targz' for i in images):rootfs.append({'target':device['target'],'profile':device['id']})
    result={'schema_version':1,'device_profiles':len(seen),'platforms':len(cache),'configuration_audit':'passed','blocked':blocked,'rootfs_only':rootfs,'hardware_tested':False}
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('All device configurations audited:',len(seen),'profiles,',len(cache),'platforms;',len(blocked),'blocked by upstream;',len(rootfs),'ROOTFS only.')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('site/data'));parser.add_argument('--destination',type=Path,default=Path('site/data/device-coverage.json'));args=parser.parse_args();audit(args.data,args.destination)
