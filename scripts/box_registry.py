"""Immutable box resource versions, separate from native firmware releases."""
import hashlib
import json
from pathlib import Path
import re
from scripts.build import require
from scripts.box_resources import source_config

ROOT=Path(__file__).resolve().parents[1]
VERSION=re.compile(r'box-\d{8}-[a-f0-9]{8}')
SHA=re.compile(r'[a-f0-9]{64}')


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def pins(catalog):
    return source_config(value={k:catalog[k] for k in ('schema_version','repositories','model_database_blob','remake_blob')}|{'kernels':[{k:x[k] for k in ('id','tag','version','asset_id','bytes','sha256')} for x in catalog['kernels']]})


def fingerprint(catalog):
    return digest({k:catalog[k] for k in ('schema_version','repositories','model_database_blob','remake_blob','kernels','models','excluded_models','policy_sha256')})


def validate(catalog):
    pins(catalog)
    require(VERSION.fullmatch(catalog.get('release','')) and SHA.fullmatch(catalog.get('policy_sha256','')) and catalog.get('fingerprint')==fingerprint(catalog) and catalog['release'].endswith('-'+catalog['fingerprint'][:8]),'Box catalog identity mismatch')
    require(isinstance(catalog.get('models'),list) and 1<=len(catalog['models'])<=2000,'Invalid box model count')
    kernels={k['id']:k for k in catalog['kernels']};ids=set()
    for model in catalog['models']:
        require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,80}',model['id']) and model['id'] not in ids,'Invalid box model ID');ids.add(model['id'])
        require(model['platform'] in ('amlogic','rockchip','allwinner') and re.fullmatch(r'[A-Za-z0-9_.+-]+\.dtb',model['dtb']),'Invalid box DTB identity')
        require(isinstance(model['kernels'],list) and 1<=len(model['kernels'])<=12,'Invalid box kernel choices')
        for key in model['kernels']:
            require(key in kernels and model['dtb'] in kernels[key]['dtbs'],'Box model has no matching actual DTB')
            dtb=kernels[key]['dtbs'][model['dtb']];require(SHA.fullmatch(dtb['sha256']) and type(dtb['bytes']) is int and 40<=dtb['bytes']<=1024**2 and isinstance(dtb['compatible'],list) and dtb['compatible'],'Invalid actual box DTB evidence')
    require(len(canonical(catalog).encode())<=4*1024**2,'Box catalog exceeds web limit')
    return catalog


def load(release=None):
    if release is None:return json.loads((ROOT/'configs/box-builders.json').read_text(encoding='utf-8'))
    require(isinstance(release,str) and VERSION.fullmatch(release),'Invalid box resource release')
    path=ROOT/'updates/box-catalogs'/(release+'.json');require(path.is_file() and path.stat().st_size<=4*1024**2,'Historical box resource release is unavailable')
    value=validate(json.loads(path.read_text(encoding='utf-8')));require(value['release']==release,'Wrong box resource release');return value
