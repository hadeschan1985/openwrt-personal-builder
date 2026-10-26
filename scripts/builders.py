"""Pinned Kwrt builders, including additional device platforms. Data only."""
import json
from pathlib import Path
import re

REGISTRY=Path(__file__).resolve().parents[1]/'configs/builders.json'
ROOT='https://dl.openwrt.ai/releases/targets'
ONECLOUD='https://dl.openwrt.ai/releases/25.12/targets/amlogic/meson8b'

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
    if 'blocked_reason' in spec and (not isinstance(spec['blocked_reason'],str) or not 1<=len(spec['blocked_reason'])<=300):raise ValueError('Invalid platform block reason')
    return spec

def resolve(version,target,registry=None):
    registry=json.loads(REGISTRY.read_text(encoding='utf-8')) if registry is None else registry
    family=registry.get(version,{})
    spec=family if family.get('target')==target else family.get('targets',{}).get(target)
    if not spec:raise ValueError('This Kwrt platform has no pinned builder')
    return validate_spec(spec)

def platforms(family):
    yield family['target'],validate_spec(family)
    for target,spec in family.get('targets',{}).items():
        if target==family['target'] or target!=spec.get('target'):raise ValueError('Duplicate or mismatched builder platform')
        yield target,validate_spec(spec)
