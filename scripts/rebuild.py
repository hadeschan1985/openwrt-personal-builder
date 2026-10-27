"""Private, checksum-bound input snapshots and genuinely offline rebuilds.

Only explicit source paths and package archives are captured. Generated rootfs,
personal-files, process environments and secret values are never snapshotted.
Publication runs in a fresh job which executes no captured source code.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import posixpath
import shutil
import tarfile
import urllib.error
import urllib.parse
import urllib.request
from scripts.build import require,sha256
from scripts.archive import NoRedirect,upload
from scripts.upstream import api

TAG='rebuild-inputs-v1'
MAX_ASSET=1536*1024**2
MAX_STORE=10*1024**3
STATE=Path('work/rebuild-state.json')
SHA=re.compile(r'[a-f0-9]{64}')


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(canonical(value)+'\n',encoding='utf-8')
def run_id(value):require(isinstance(value,str) and re.fullmatch(r'[1-9][0-9]{0,19}',value),'Invalid rebuild run');return value


def context(config):
    if not STATE.exists():return None
    state=read(STATE);validate(state['manifest'])
    require(state['manifest']['config_sha256']==digest(config),'归档重建必须使用原始软件和配置；请从原构建记录启动。')
    return state


def offline_packages(workspace):
    source=Path('work/rebuild-packages');require(source.is_dir(),'Archived package cache is missing')
    for path in source.iterdir():
        require(path.is_file() and not path.is_symlink() and path.suffix in ('.ipk','.apk'),'Unexpected offline package')
        destination=workspace/'packages'/path.name
        shutil.copy2(path,destination)
    # These indexes are rebuilt from the archived, SHA-verified local packages.
    for name in ('Packages','Packages.gz','Packages.sig','packages.adb','APKINDEX.tar.gz'):
        (workspace/'packages'/name).unlink(missing_ok=True)
    if (workspace/'repositories.conf').exists():(workspace/'repositories.conf').write_text('src imagebuilder file:packages\n')
    if (workspace/'repositories').exists():(workspace/'repositories').write_text('')
    config=workspace/'.config';text=config.read_text();text=re.sub(r'(?m)^CONFIG_SIGNATURE_CHECK=.*$','# CONFIG_SIGNATURE_CHECK is not set',text);config.write_text(text)


def package_manifest(directory):
    paths=list(Path(directory).glob('*.manifest'));require(paths,'Missing installed package manifest')
    return sorted({' '.join(line.split()) for p in paths for line in p.read_text().splitlines() if line.strip()})


def verify_installed(outputs):
    if STATE.exists():require(package_manifest(outputs)==read('work/rebuild-source-inputs.json')['installed_manifest'],'Offline rebuild resolved different package versions; delivery stopped')


def allowed(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name:return False
    return name.startswith(('scripts/','firmware-assets/','work/box-repack/sources/','work/onecloud-pack/AmlImg-source/','updates/box-catalogs/')) or name in ('configs/builders.json','configs/box-builders.json','configs/box-sources.json','configs/rebuild-original.json','updates/device-builders.json','work/rebuild-source-inputs.json','work/onecloud-pack/uboot-template.img') or bool(re.fullmatch(r'overlays/[A-Za-z0-9_.-]+\.(zip|tar\.gz|tgz|7z)',name)) or bool(re.fullmatch(r'work/box-repack/(stable|rk35xx|rk3588)-\d+\.\d+\.\d+\.tar\.gz',name))


def archive_tree(paths,destination):
    with tarfile.open(destination,'w:gz',compresslevel=1) as out:
        seen=set()
        for path in paths:
            path=Path(path)
            if not path.exists():continue
            items=[path] if path.is_file() else sorted(path.rglob('*'))
            for item in items:
                if '__pycache__' in item.parts or item.suffix=='.pyc':continue
                name=item.as_posix();require(allowed(name),'Unexpected snapshot source path')
                require(not item.is_symlink() or item.resolve().is_relative_to(path.resolve()),'Source symlink escapes its repository')
                if name not in seen:out.add(item,arcname=name,recursive=False);seen.add(name)
    require(destination.stat().st_size<=MAX_ASSET,'Snapshot source bundle exceeds 1.5 GiB')


def validate(value):
    require(value.get('schema_version')==1 and value.get('status')=='captured' and SHA.fullmatch(value.get('config_sha256','')) and re.fullmatch(r'[a-f0-9]{40}',value.get('engine_source_commit','')),'Invalid input snapshot identity')
    run_id(value.get('run_id'));assets=value.get('assets');require(isinstance(assets,list) and 3<=len(assets)<=8,'Invalid input snapshot assets')
    names=set();kinds=set()
    for a in assets:
        require(a.get('kind') in ('builder','packages','engine','kernel') and a['kind'] not in kinds and re.fullmatch(r'[a-f0-9]{64}\.(tar\.gz|tar\.zst|tar\.xz)',a.get('name','')) and a['name'] not in names and SHA.fullmatch(a.get('sha256','')) and a['name'].startswith(a['sha256']+'.') and type(a.get('bytes')) is int and 0<a['bytes']<=MAX_ASSET,'Invalid snapshot asset integrity');names.add(a['name']);kinds.add(a['kind'])
        destinations={'builder':bool(re.fullmatch(r'work/downloads/[A-Za-z0-9_.+-]+\.tar\.(zst|xz|gz)',a['destination'])),'packages':a['destination']=='work/rebuild-packages.tar.gz','engine':a['destination']=='work/rebuild-engine.tar.gz','kernel':bool(re.fullmatch(r'work/box-repack/(stable|rk35xx|rk3588)-\d+\.\d+\.\d+\.tar\.gz',a['destination']))}
        require(destinations[a['kind']],'Invalid snapshot asset destination')
    require({'builder','packages','engine'}<=kinds and sum(a['bytes'] for a in assets)<=2*MAX_ASSET,'Input snapshot exceeds total limit')
    return value


def add_asset(path,kind,destination,folder):
    path=Path(path);checksum=sha256(path);suffix='.tar.gz' if path.name.endswith('.tar.gz') else '.tar.zst' if path.name.endswith('.tar.zst') else '.tar.xz'
    target=folder/(checksum+suffix)
    if not target.exists():os.link(path,target)
    return {'kind':kind,'name':target.name,'sha256':checksum,'bytes':path.stat().st_size,'destination':destination}


def stage(config):
    folder=Path('work/rebuild-upload');folder.mkdir(parents=True,exist_ok=True)
    inputs=read('work/build-inputs.json');workspace=Path('work/builder')
    inputs['installed_manifest']=package_manifest('outputs');write('work/rebuild-source-inputs.json',inputs)
    write('configs/rebuild-original.json',config)
    cache=Path('work/rebuild-collected-packages');cache.mkdir(parents=True,exist_ok=True)
    for base in (workspace/'dl',workspace/'packages'):
        if not base.exists():continue
        for path in base.rglob('*'):
            if path.suffix not in ('.ipk','.apk') or not path.is_file() or path.is_symlink():continue
            require(re.fullmatch(r'[A-Za-z0-9_.+~-]+\.(ipk|apk)',path.name),'Unsafe cached package name')
            destination=cache/path.name
            if destination.exists():require(sha256(destination)==sha256(path),'Conflicting package cache filenames')
            else:os.link(path,destination)
    require(any(cache.iterdir()),'No actual package archives were captured')
    cache_tar=Path('work/rebuild-packages.tar.gz')
    with tarfile.open(cache_tar,'w:gz',compresslevel=1) as out:
        for p in sorted(cache.iterdir()):out.add(p,arcname=p.name,recursive=False)
    assets=[add_asset(Path('work/downloads')/inputs['archive'],'builder','work/downloads/'+inputs['archive'],folder),add_asset(cache_tar,'packages','work/rebuild-packages.tar.gz',folder)]
    paths=['scripts','firmware-assets','configs/builders.json','configs/box-builders.json','configs/box-sources.json','configs/rebuild-original.json','updates/device-builders.json','work/rebuild-source-inputs.json']
    if config['overlay']:paths.append(config['overlay'])
    if config.get('box'):
        paths.append('work/box-repack/sources')
        if config['box'].get('release'):paths.append('updates/box-catalogs/'+config['box']['release']+'.json')
        kernel=Path('work/box-repack')/(config['box']['kernel']+'.tar.gz');assets.append(add_asset(kernel,'kernel',kernel.as_posix(),folder))
    if (Path('work/onecloud-pack/AmlImg-source').exists()):paths+=['work/onecloud-pack/AmlImg-source','work/onecloud-pack/uboot-template.img']
    engine=Path('work/rebuild-engine.tar.gz');archive_tree(paths,engine);assets.append(add_asset(engine,'engine',engine.as_posix(),folder))
    manifest={'schema_version':1,'status':'captured','run_id':run_id(os.environ['GITHUB_RUN_ID']),'engine_source_commit':read(STATE)['manifest']['engine_source_commit'] if STATE.exists() else os.environ['GITHUB_SHA'],'config_sha256':digest(config),'assets':assets,'package_count':len(list(cache.iterdir())),'hardware_tested':False}
    validate(manifest);write(folder/'manifest.json',manifest)
    write('outputs/rebuild-report.json',{'status':'captured-awaiting-private-publication','run_id':manifest['run_id'],'package_count':manifest['package_count'],'snapshot_bytes':sum(a['bytes'] for a in assets),'offline_rebuilt':STATE.exists(),'same_package_versions':True if STATE.exists() else None,'hardware_tested':False})
    print('Rebuild input capture:',manifest['package_count'],'package archives;',sum(a['bytes'] for a in assets),'bytes; no generated rootfs or environment captured')


def inspect_tar(path,packages=False,extract=False):
    with tarfile.open(path,'r:gz') as archive:
        members=archive.getmembers();require(1<=len(members)<=100000 and sum(m.size for m in members)<=6*1024**3,'Oversized input bundle')
        names=set()
        for m in members:
            require(m.name not in names and not m.isdev() and (m.isfile() or m.issym() or m.isdir()),'Unsafe or duplicate input member');names.add(m.name)
            require(bool(re.fullmatch(r'[A-Za-z0-9_.+~-]+\.(ipk|apk)',m.name)) if packages else allowed(m.name),'Unexpected input member path')
            if m.issym():
                target=PurePosixPath(m.linkname);resolved=posixpath.normpath(str(PurePosixPath(m.name).parent/target));require(not target.is_absolute() and '\\' not in m.linkname and allowed(resolved) and resolved.split('/')[:4]==m.name.split('/')[:4],'Unsafe source symbolic link')
        if extract:
            destination=Path('work/rebuild-packages') if packages else Path('.')
            destination.mkdir(parents=True,exist_ok=True);archive.extractall(destination,filter='data')


def publish():
    folder=Path('work/rebuild-upload');manifest=validate(read(folder/'manifest.json'));require(manifest['run_id']==os.environ['GITHUB_RUN_ID'],'Snapshot belongs to another run')
    token=os.environ['GH_TOKEN'];require(api('',token)['private'],'Rebuild inputs must stay private')
    for asset in manifest['assets']:
        path=folder/asset['name'];require(path.is_file() and not path.is_symlink() and path.stat().st_size==asset['bytes'] and sha256(path)==asset['sha256'],'Snapshot transfer checksum mismatch')
        if asset['kind'] in ('packages','engine'):inspect_tar(path,asset['kind']=='packages')
    try:release=api('/releases/tags/'+TAG,token)
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        release=api('/releases',token,'POST',{'tag_name':TAG,'target_commitish':'main','name':'Private immutable rebuild inputs','draft':True,'make_latest':'false','body':'Verified original builders, package archives and fixed sources. Not firmware downloads. No generated rootfs or environment/secret values are archived. Existing assets are never overwritten or automatically deleted.'})
    # Paginate asset accounting; never silently exceed the private safety cap.
    assets=[]
    for page in range(1,21):
        batch=api(f"/releases/{release['id']}/assets?per_page=100&page={page}",token);assets+=batch
        if len(batch)<100:break
    require(len(assets)<2000,'Source archive asset count limit reached')
    release['assets']=assets;existing={a['name'] for a in assets}
    require(sum(a['size'] for a in assets)+sum(a['bytes'] for a in manifest['assets'] if a['name'] not in existing)<=MAX_STORE,'Private source archive reached its 10 GiB safety cap; existing snapshots retained. Manage storage before adding more.')
    for asset in manifest['assets']:upload(release,folder/asset['name'],token)
    api(f"/releases/{release['id']}",token,'PATCH',{'draft':False,'make_latest':'false'})
    record_path=Path('work/build-record.json');record=read(record_path);record['rebuild']={'status':'available','run_id':manifest['run_id'],'manifest_sha256':digest(manifest),'engine_source_commit':manifest['engine_source_commit']};write(record_path,record)
    # Save the small manifest alongside the existing private record atomically.
    write('work/rebuild-manifest.json',manifest)
    print('Private input snapshot verified and stored. Original firmware and old snapshots retained.')


def transfer(asset,description,destination,token):
    require(asset['name']==description['name'] and asset['size']==description['bytes'] and asset.get('digest')=='sha256:'+description['sha256'],'Archived source asset metadata mismatch')
    request=urllib.request.Request(f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/releases/assets/{asset['id']}",headers={'Authorization':'Bearer '+token,'Accept':'application/octet-stream','User-Agent':'OpenWrt-Personal-Builder'})
    try:response=urllib.request.build_opener(NoRedirect()).open(request,timeout=60)
    except urllib.error.HTTPError as error:
        require(error.code in (301,302,303,307,308),'Cannot read archived inputs');location=error.headers['Location'];url=urllib.parse.urlsplit(location)
        require(url.scheme=='https' and url.hostname in ('release-assets.githubusercontent.com','objects.githubusercontent.com'),'Untrusted source redirect')
        response=urllib.request.urlopen(urllib.request.Request(location),timeout=120)
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True);size=0
    with response,destination.open('wb') as out:
        while block:=response.read(1024**2):size+=len(block);require(size<=description['bytes'],'Oversized input transfer');out.write(block)
    require(size==description['bytes'] and sha256(destination)==description['sha256'],'Archived input SHA256 mismatch')


def restore(identifier):
    identifier=run_id(identifier);token=os.environ['GH_TOKEN'];require(api('',token)['private'],'Private rebuild required')
    def content(path):
        item=api('/contents/'+path+'?ref=main',token);require(item['size']<=256*1024 and item['encoding']=='base64','Invalid private input metadata');return json.loads(base64.b64decode(item['content']))
    record=content('records/'+identifier+'.json');manifest=validate(content('snapshots/'+identifier+'.json'))
    require(record.get('rebuild',{}).get('manifest_sha256')==digest(manifest) and manifest['run_id']==identifier and manifest['config_sha256']==digest(record['config']),'Input snapshot and original build record disagree')
    raw=os.environ.get('CONFIG_JSON','').strip()
    if raw:require(digest(json.loads(raw))==manifest['config_sha256'],'Snapshot rebuild cannot change the original configuration')
    release=api('/releases/tags/'+TAG,token);require(not release['draft'],'Input snapshot publication is incomplete')
    for desc in manifest['assets']:
        matches=[a for a in release['assets'] if a['name']==desc['name']]
        if not matches:
            for page in range(1,21):
                batch=api(f"/releases/{release['id']}/assets?per_page=100&page={page}",token);matches=[a for a in batch if a['name']==desc['name']]
                if matches or len(batch)<100:break
        require(len(matches)==1,'Archived source asset unavailable');transfer(matches[0],desc,desc['destination'],token)
    # Validate every member before replacing any engine file. Captured code is
    # not imported or executed in this credential-bearing transfer process.
    inspect_tar('work/rebuild-engine.tar.gz');inspect_tar('work/rebuild-packages.tar.gz',True)
    write(STATE,{'manifest':manifest});inspect_tar('work/rebuild-packages.tar.gz',True,True)
    print('Archived source inputs verified; next build step has no network or GitHub credential.')
    inspect_tar('work/rebuild-engine.tar.gz',False,True)
    # Early snapshots omitted empty directories. A detached shallow Git source
    # needs refs/ even when it contains no branch/tag files, otherwise Git walks
    # up to the parent checkout. Recreate metadata directories, never source data.
    roots=[Path('work/onecloud-pack/AmlImg-source')]+list(Path('work/box-repack/sources').glob('*'))
    for root in roots:
        if (root/'.git/HEAD').is_file() and (root/'.git/objects').is_dir():(root/'.git/refs').mkdir(exist_ok=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['stage','publish','restore']);parser.add_argument('--run');args=parser.parse_args()
    if args.action=='restore':restore(args.run)
    elif args.action=='publish':publish()
    else:
        from scripts.delivery import config
        stage(config())
