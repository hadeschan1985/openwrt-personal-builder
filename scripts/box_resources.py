"""Pin public TV-box source, kernel assets and actual device-tree bytes."""
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import re
import struct
import tarfile
import urllib.request

from scripts.build import require

ROOT=Path(__file__).resolve().parents[1]
SOURCES=ROOT/'configs/box-sources.json'
DB_PATH='make-openwrt/openwrt-files/common-files/etc/model_database.conf'
REPOSITORIES={'ophub/amlogic-s9xxx-openwrt','ophub/amlogic-s9xxx-armbian','ophub/u-boot','ophub/firmware','ophub/luci-app-amlogic'}
SHA=re.compile(r'[a-f0-9]{64}')
NAME=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.+-]{0,160}')

def source_config(path=SOURCES,value=None):
    value=json.loads(Path(path).read_text(encoding='utf-8')) if value is None else value
    require(value.get('schema_version')==1 and isinstance(value.get('repositories'),list) and len(value['repositories'])==5 and {r['repository'] for r in value['repositories']}==REPOSITORIES,'Unrecognized box source repositories')
    require(all(re.fullmatch(r'[a-f0-9]{40}',r['commit']) for r in value['repositories']),'Unpinned box source')
    require(all(re.fullmatch(r'[a-f0-9]{40}',value.get(k,'')) for k in ('model_database_blob','remake_blob')),'Unpinned box recipes')
    require(isinstance(value.get('kernels'),list) and 1<=len(value['kernels'])<=12,'Invalid box kernel set')
    ids=set()
    for k in value['kernels']:
        require(k.get('tag') in ('stable','rk35xx','rk3588') and re.fullmatch(r'\d+\.\d+\.\d+',k.get('version','')) and k.get('id')==k['tag']+'-'+k['version'] and k['id'] not in ids,'Invalid fixed box kernel');ids.add(k['id'])
        require(type(k.get('asset_id')) is int and type(k.get('bytes')) is int and 0<k['bytes']<=500*1024**2 and SHA.fullmatch(k.get('sha256','')),'Missing published box kernel integrity')
    return value

def fetch(url,path,size=None,sha=None,limit=500*1024**2):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and size and path.stat().st_size==size and sha:
        with path.open('rb') as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()==sha:return path
    request=urllib.request.Request(url,headers={'User-Agent':'OpenWrt-Personal-Builder/0.2'})
    total=0;digest=hashlib.sha256()
    with urllib.request.urlopen(request,timeout=90) as response,path.open('wb') as out:
        while block:=response.read(1024**2):
            total+=len(block);require(total<=(size or limit),'Box resource exceeds declared size');digest.update(block);out.write(block)
    require(not size or total==size,'Box resource size mismatch');require(not sha or digest.hexdigest()==sha,'Box resource SHA256 mismatch')
    return path

def git_blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def parse_models(text):
    models=[];ids=set()
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        fields=[x.strip() for x in line.split(':')];require(len(fields)==15,'Upstream model database schema changed')
        _,name,soc,dtb,overload,mainline,bootloader,description,tags,platform,family,bootconf,contributors,board,default_build=fields
        require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,80}',board) and board not in ids and NAME.fullmatch(dtb) and dtb.endswith('.dtb') and platform in ('amlogic','rockchip','allwinner') and bootconf in ('uEnv.txt','extlinux.conf','armbianEnv.txt'),'Unsafe box model identity')
        require(len(name)<=200 and len(description)<=500 and all(n=='NA' or NAME.fullmatch(n) for n in (overload,mainline,bootloader)),'Invalid box model metadata')
        ids.add(board);models.append({'id':board,'name':name,'soc':soc,'dtb':dtb,'uboot_overload':overload,'mainline_uboot':mainline,'bootloader':bootloader,'description':description,'kernel_tags':tags,'platform':platform,'family':family,'boot_config':bootconf,'upstream_default':default_build=='yes'})
    require(1<=len(models)<=2000,'Unexpected box model count');return models

def dtb_compatible(data):
    require(40<=len(data)<=1024**2,'Invalid DTB size')
    header=struct.unpack('>10I',data[:40]);magic,total,structure,strings=header[:4]
    require(magic==0xd00dfeed and 40<=total<=len(data) and structure<total and strings<total,'Invalid DTB header')
    cursor=structure;depth=0
    while cursor+4<=total:
        token=struct.unpack_from('>I',data,cursor)[0];cursor+=4
        if token==1:
            end=data.find(b'\0',cursor,total);require(end>=cursor,'Invalid DTB node');cursor=(end+4)&~3;depth+=1
        elif token==2:depth-=1
        elif token==3:
            require(cursor+8<=total,'Invalid DTB property');length,nameoff=struct.unpack_from('>II',data,cursor);cursor+=8
            require(cursor+length<=total and strings+nameoff<total,'Invalid DTB property bounds')
            end=data.find(b'\0',strings+nameoff,total);require(end>=strings+nameoff,'Invalid DTB string table')
            name=data[strings+nameoff:end]
            if depth==1 and name==b'compatible':return [v.decode('ascii') for v in data[cursor:cursor+length].split(b'\0') if v]
            cursor=(cursor+length+3)&~3
        elif token==4:continue
        elif token==9:break
        else:raise ValueError('Invalid DTB structure token')
    raise ValueError('Device tree lacks root compatible property')

def inspect_kernel(path,kernel,models):
    result={**kernel,'dtbs':{}}
    with tarfile.open(path,'r:gz') as package:
        members=package.getmembers();require(1<=len(members)<=100,'Unexpected kernel bundle layout')
        boot=[m for m in members if m.isfile() and PurePosixPath(m.name).name.startswith('boot-'+kernel['version']) and m.name.endswith('.tar.gz')]
        require(len(boot)==1,'No unique kernel boot payload')
        result['release']=PurePosixPath(boot[0].name).name.removeprefix('boot-').removesuffix('.tar.gz')
        for platform in ('amlogic','rockchip','allwinner'):
            matches=[m for m in members if m.isfile() and PurePosixPath(m.name).name=='dtb-'+platform+'-'+result['release']+'.tar.gz']
            if not matches:continue
            require(len(matches)==1 and matches[0].size<=48*1024**2,'Oversized or ambiguous DTB bundle')
            with tarfile.open(fileobj=io.BytesIO(package.extractfile(matches[0]).read()),mode='r:gz') as dtbs:
                required={m['dtb'] for m in models if m['platform']==platform}
                for member in dtbs:
                    name=PurePosixPath(member.name).name
                    if name not in required or not member.isfile():continue
                    require(name not in result['dtbs'] and member.size<=1024**2,'Duplicate or oversized DTB')
                    data=dtbs.extractfile(member).read();result['dtbs'][name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'compatible':dtb_compatible(data)}
    return result

def generate(sources=None,destination=None,emit=True):
    sources=source_config(value=sources) if sources is not None else source_config();work=ROOT/'work/box-resources';work.mkdir(parents=True,exist_ok=True)
    repo=next(r for r in sources['repositories'] if r['repository']=='ophub/amlogic-s9xxx-openwrt')
    database=fetch(f"https://raw.githubusercontent.com/{repo['repository']}/{repo['commit']}/{DB_PATH}",work/'model_database.conf',limit=512*1024)
    raw=database.read_bytes();require(git_blob(raw)==sources['model_database_blob'],'Pinned device database mismatch')
    models=parse_models(raw.decode('utf-8'));kernels=[]
    for k in sources['kernels']:
        path=fetch(f"https://github.com/ophub/kernel/releases/download/kernel_{k['tag']}/{k['version']}.tar.gz",work/(k['id']+'.tar.gz'),k['bytes'],k['sha256'])
        kernels.append(inspect_kernel(path,k,models));print('Verified kernel and actual device trees:',k['id'],len(kernels[-1]['dtbs']),flush=True)
    available=[];excluded=[]
    for m in models:
        tag,versions=m['kernel_tags'].split('/',1)
        choices=[k['id'] for k in kernels if k['tag']==tag and (versions=='all' or '.'.join(k['version'].split('.')[:2])+'.y' in versions.split('_')) and m['dtb'] in k['dtbs']]
        if choices:available.append({**m,'kernels':choices})
        else:excluded.append({'id':m['id'],'reason':'No matching fixed kernel and device-tree bytes'})
    result={**sources,'status':'resources-verified','models':available,'excluded_models':excluded,'kernels':kernels}
    path=Path(destination) if destination else ROOT/'outputs/box-resources.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n',encoding='utf-8')
    if emit:print('BOX_RESOURCE_CATALOG='+json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':')),flush=True)
    return result

if __name__=='__main__':generate()
