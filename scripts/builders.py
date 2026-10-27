"""Pinned Kwrt builders, including additional device platforms. Data only."""
import json
from pathlib import Path
import re

REGISTRY=Path(__file__).resolve().parents[1]/'configs/builders.json'
ROOT='https://dl.openwrt.ai/releases/targets'
ONECLOUD='https://dl.openwrt.ai/releases/25.12/targets/amlogic/meson8b'
VERSION=re.compile(r'kwrt-25\.12-\d{8}(?:-[a-f0-9]{8})?')

def validate_device_family(family):
    if not isinstance(family,dict) or set(family)!={'device_only','label','targets'} or family.get('device_only') is not True:raise ValueError('Invalid device-only registry family')
    if not isinstance(family['label'],str) or not 1<=len(family['label'])<=120:raise ValueError('Invalid device release label')
    if not isinstance(family['targets'],dict) or not 1<=len(family['targets'])<=128:raise ValueError('Invalid device platform set')
    for target,spec in family['targets'].items():
        validate_spec(spec)
        if target=='x86/64' or target!=spec['target'] or not re.fullmatch(r'[a-f0-9]{64}',spec.get('metadata_fingerprint','')):raise ValueError('Invalid device-only platform pin')
    return family

def load_registry(path=REGISTRY):
    path=Path(path);registry=json.loads(path.read_text(encoding='utf-8'))
    extension=path.parent.parent/'updates/device-builders.json'
    if extension.exists():
        if extension.stat().st_size>16*1024*1024:raise ValueError('Device registry exceeds limit')
        data=json.loads(extension.read_text(encoding='utf-8'))
        if set(data)!={'schema_version','versions'} or data['schema_version']!=1 or not isinstance(data['versions'],dict) or len(data['versions'])>512:raise ValueError('Invalid device registry')
        for version,family in data['versions'].items():
            if not VERSION.fullmatch(version) or version in registry:raise ValueError('Conflicting or unpinned device version')
            registry[version]=validate_device_family(family)
    return registry

def validate_spec(spec):
    target=spec.get('target','')
    if not re.fullmatch(r'[a-z0-9_-]+/[a-z0-9_-]+',target):raise ValueError('Invalid pinned target')
    if spec.get('base')!=ROOT+'/'+target and not (target=='amlogic/meson8b' and spec.get('base')==ONECLOUD):raise ValueError('Untrusted builder location')
    if not re.fullmatch(r'kwrt-imagebuilder-[A-Za-z0-9_.+-]+\.Linux-x86_64\.tar\.(?:zst|xz)',spec.get('archive','')):raise ValueError('Invalid pinned ImageBuilder')
    if not re.fullmatch(r'[a-f0-9]{64}',spec.get('sha256','')):raise ValueError('Invalid builder digest')
    if not re.fullmatch(r'https://dl\.openwrt\.ai/releases/25\.12/packages/[a-z0-9_-]+',spec.get('feeds','')):raise ValueError('Untrusted package feed')
    if not re.fullmatch(r'https://dl\.openwrt\.ai/releases/25\.12/targets/'+re.escape(target)+r'/\d+\.\d+\.\d+',spec.get('kernel_feed','')):raise ValueError('Untrusted kernel feed')
    for key in ['exclude_defaults','replacement_packages']:
        if not isinstance(spec.get(key),list) or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.-]{0,120}',v) for v in spec[key]):raise ValueError('Invalid compatibility packages')
    if spec.get('profiles_file','profiles.json') not in ('profiles.json','profiles.json.b'):raise ValueError('Invalid profile metadata path')
    if spec.get('metadata_source') not in (None,'selector'):raise ValueError('Invalid metadata source')
    if 'compatibility_recipe' in spec and (spec['target']!='amlogic/meson' or spec['compatibility_recipe']!='n1-nvram-v1'):raise ValueError('Unreviewed board compatibility recipe')
    if 'source_cache' in spec and (spec['source_cache']!='onecloud-author-20261012' or target!='amlogic/meson8b' or spec['archive']!='kwrt-imagebuilder-amlogic-meson8b.Linux-x86_64.tar.zst' or spec['sha256']!='e29abe52fea3bdaf77a0af313ccb5c6f06c6564a4f7cdb27d41fd9215d6926b5'):raise ValueError('Untrusted source cache selection')
    if 'blocked_reason' in spec and (not isinstance(spec['blocked_reason'],str) or not 1<=len(spec['blocked_reason'])<=300):raise ValueError('Invalid platform block reason')
    return spec

def resolve(version,target,registry=None):
    registry=load_registry() if registry is None else registry
    family=registry.get(version,{})
    spec=family if family.get('target')==target else family.get('targets',{}).get(target)
    if not spec:raise ValueError('This Kwrt platform has no pinned builder')
    return validate_spec(spec)

def platforms(family):
    if not family.get('device_only'):yield family['target'],validate_spec(family)
    for target,spec in family.get('targets',{}).items():
        if target==family.get('target') or target!=spec.get('target'):raise ValueError('Duplicate or mismatched builder platform')
        yield target,validate_spec(spec)
