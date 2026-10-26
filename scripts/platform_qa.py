"""Prepare bounded representative builds from the complete pinned device set."""
import argparse
import json
from pathlib import Path

from scripts import catalog
from scripts.builders import resolve
from scripts.build import normalize,require
from scripts.delivery import policy

VERSION='kwrt-25.12-20261012'
PREFERRED={'armsr/armv8':'generic','mediatek/filogic':'xiaomi_redmi-router-ax6000','ramips/mt7621':'xiaomi_mi-router-3g','rockchip/armv8':'friendlyarm_nanopi-r4s','ipq806x/generic':'netgear_r7800'}
PRIORITY=['sysupgrade','sdcard','sdcard-sysupgrade','combined-efi','combined','emmc_burn','factory','bin','trx','firmware','nand-sysupgrade']

def output_options(images):
    usable=[i for i in images if i.get('filesystem') in ('squashfs','ext4') and not i.get('name','').endswith('.vmdk.zip')]
    if not usable and any(i.get('filesystem')=='targz' for i in images):return 'squashfs',[]
    require(usable,'No supported filesystem image')
    usable.sort(key=lambda i:(PRIORITY.index(i['type']) if i['type'] in PRIORITY else 100, i['filesystem']!='squashfs',i['name']))
    return usable[0]['filesystem'],[usable[0]['type']]

def prepare(target,path=Path('configs/platform-qa.json')):
    require(target!='x86/64','Use the full x86 delivery workflow for x86 testing')
    spec=resolve(VERSION,target)
    profiles=catalog.get_json(spec['base']+'/'+spec.get('profiles_file','profiles.json'))
    ids=sorted(profiles['profiles'])
    profile=PREFERRED.get(target)
    if profile not in ids:profile=ids[0]
    filesystem,types=output_options(profiles['profiles'][profile]['images'])
    raw=json.loads(Path('configs/x86-default.json').read_text(encoding='utf-8'))
    raw.update(builder='kwrt',version=VERSION,target=target,profile=profile,build_mode='device',packages=[])
    raw['system'].update(password_secret=True,password_source='root',hostname='PersonalQA')
    raw['output'].update(filesystem=filesystem,image_types=types,efi=False,legacy=False,vmdk=False,rootfs=not types,rootfs_size_mb=256)
    config=normalize(raw);policy(config,{'REPOSITORY_PRIVATE':'true'})
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Representative device:',target,profile,filesystem,','.join(types))
    return config

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('target');args=parser.parse_args();prepare(args.target)
