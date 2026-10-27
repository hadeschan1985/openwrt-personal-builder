"""Portable OneCloud USB-burn packaging from public, fixed author sources.

Only operates on regular workspace files. Never opens block devices or flashes
hardware. The native LEDE disk is an intermediate, not a USB-burn container.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

from scripts.build import require,sha256
from scripts.box_resources import fetch

TOOL_REPO='hzyitc/AmlImg'
TOOL_COMMIT='5ede4ed30b27c10187af5258f7e2f61f9ad71e1e'
TEMPLATE_URL='https://github.com/hzyitc/u-boot/releases/download/build-20221028-0940/eMMC.burn.img'
TEMPLATE_SHA='d33d979d23b8a607447c5af424b1e24003820e7e159e540c7f47c89d45cdc491'
TEMPLATE_BYTES=1367540


def clean_env():
    return {k:v for k,v in os.environ.items() if k not in {'GH_TOKEN','GITHUB_TOKEN','ROUTER_PASSWORD','PPPOE_USERNAME','PPPOE_PASSWORD','WIFI_PASSWORD','CONFIG_JSON'} and not k.startswith('ACTIONS_')}


def run(args,**kwargs):
    return subprocess.run([str(a) for a in args],check=True,env=clean_env(),**kwargs)


def prepare(work):
    work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
    template=fetch(TEMPLATE_URL,work/'uboot-template.img',TEMPLATE_BYTES,TEMPLATE_SHA)
    source=work/'AmlImg-source'
    if not source.exists():
        source.mkdir();run(['git','init',source])
        run(['git','-C',source,'fetch','--depth=1','https://github.com/'+TOOL_REPO+'.git',TOOL_COMMIT])
        run(['git','-C',source,'checkout','--detach','FETCH_HEAD'])
    head=run(['git','-C',source,'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
    require(head==TOOL_COMMIT,'OneCloud packer source is not the pinned commit')
    require(not (source/'go.sum').exists() and 'require' not in (source/'go.mod').read_text(),'Unexpected OneCloud packer dependencies')
    tool=work/'AmlImg'
    env={**clean_env(),'GOPROXY':'off','GOSUMDB':'off','GOTOOLCHAIN':'local'}
    subprocess.run(['go','build','-trimpath','-o',str(tool),'.'],cwd=source,check=True,env=env)
    return tool,template


def restore_native_recipe(workspace):
    """Fail closed when the known publisher-only host hook changes."""
    path=Path(workspace)/'target/linux/amlogic/image/meson8b.mk'
    source=path.read_text()
    pattern=r'define (?:Build/run-host-script|Image/Build)[^\S\n]*\n.*?\n[^\S\n]*endef(?:\n|$)'
    matches=re.findall(pattern,source,re.S)
    require(len(matches)==1 and '/data/packit/openwrt-onecloud' in matches[0] and '~/packit/packit_onecloud1.sh' in matches[0],'Unknown OneCloud host packaging recipe')
    require(source.count(' | run-host-script')==(1 if 'Build/run-host-script' in matches[0] else 0),'Ambiguous OneCloud host packaging hook')
    path.write_text(re.sub(pattern,'',source,flags=re.S).replace(' | run-host-script',''))


def partitions(path):
    path=Path(path);require(path.is_file() and not path.is_symlink(),'OneCloud input must be a regular file')
    with path.open('rb') as stream:header=stream.read(512)
    require(len(header)==512 and header[510:]==b'\x55\xaa','OneCloud native image has no MBR')
    result=[]
    for n in range(4):
        entry=header[446+n*16:462+n*16];kind=entry[4];start,size=struct.unpack_from('<II',entry,8)
        if not size:
            require(kind==0,'Malformed empty MBR partition');continue
        require(n<2 and kind in ((0x0c,0x0e) if n==0 else (0x83,)),'Unexpected OneCloud partition layout')
        offset=start*512;length=size*512
        require(offset>=1024*1024 and 0<length<=2*1024**3 and offset+length<=path.stat().st_size,'OneCloud partition outside image')
        require(not result or result[-1]['offset']+result[-1]['bytes']<=offset,'Overlapping OneCloud partitions')
        result.append({'name':('boot','rootfs')[n],'offset':offset,'bytes':length})
    require(len(result)==2,'OneCloud image needs exactly two partitions')
    return result


def native_disk(workspace,directory,filename,work):
    """Some publisher recipes compress output without updating profiles.json."""
    workspace=Path(workspace).resolve();directory=Path(directory).resolve();work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
    require(Path(filename).name==filename,'Unsafe native OneCloud filename')
    candidates=[directory/filename,directory/(filename+'.gz')]
    candidates += sorted((workspace/'build_dir').glob('*/linux-amlogic_meson8b/tmp/'+filename))
    for path in candidates:
        if not path.is_file() or path.is_symlink():continue
        require(path.resolve().is_relative_to(workspace),'Native OneCloud image left workspace')
        with path.open('rb') as stream:magic=stream.read(2)
        if magic==b'\x1f\x8b':
            raw=work/'native-disk.img';total=0
            with gzip.open(path,'rb') as src,raw.open('wb') as dst:
                while data:=src.read(1024**2):
                    total+=len(data);require(total<=2*1024**3,'Oversized native OneCloud disk');dst.write(data)
            partitions(raw);return raw
        partitions(path);return path
    raise ValueError('No native OneCloud disk produced; refusing to deliver a fake burn image')


def commands(directory):
    rows=[]
    for line in (directory/'commands.txt').read_text().splitlines():
        if not line or line.startswith('#'):continue
        row=line.split(':');require(len(row)==4 and row[2] in ('normal','sparse') and all(re.fullmatch(r'[A-Za-z0-9_.+-]+',v) and v not in ('.','..') for v in row),'Unsafe OneCloud burn command')
        require((directory/row[3]).is_file() and not (directory/row[3]).is_symlink(),'Missing OneCloud burn payload')
        require((row[0],row[1]) not in {(x[0],x[1]) for x in rows},'Duplicate OneCloud burn component');rows.append(row)
    require(1<=len(rows)<=32,'Unexpected OneCloud burn components');return rows


def pack(raw,destination,work):
    raw=Path(raw);destination=Path(destination);work=Path(work).resolve()
    require(destination.name.endswith('.img.gz') and not destination.exists(),'Invalid OneCloud destination')
    tool,template=prepare(work);burn=work/'burn';burn.mkdir()
    run([tool,'unpack',template,burn]);rows=commands(burn)
    require(not any(r[1] in ('boot','rootfs') for r in rows),'Bootloader template already contains OS partitions')
    report={'schema_version':1,'status':'passed','hardware_tested':False,'tool_repository':TOOL_REPO,'tool_commit':TOOL_COMMIT,'template_url':TEMPLATE_URL,'template_sha256':TEMPLATE_SHA,'partitions':[]}
    for partition in partitions(raw):
        name=partition['name'];extracted=work/(name+'.raw')
        with raw.open('rb') as src,extracted.open('wb') as dst:
            src.seek(partition['offset']);remaining=partition['bytes']
            while remaining:
                data=src.read(min(1024**2,remaining));require(data,'Truncated native partition');dst.write(data);remaining-=len(data)
        digest=sha256(extracted);sparse=burn/(name+'.simg');run(['img2simg',extracted,sparse])
        # Amlogic VERIFY expects SHA1 of sparse bytes, not a cryptographic trust
        # decision. All downloads and round-trip payloads use SHA256 separately.
        with sparse.open('rb') as stream:verify=hashlib.file_digest(stream,'sha1').hexdigest()
        (burn/(name+'.VERIFY')).write_text('sha1sum '+verify)
        rows.extend([['PARTITION',name,'sparse',sparse.name],['VERIFY',name,'normal',name+'.VERIFY']])
        report['partitions'].append({**partition,'sha256':digest})
    (burn/'commands.txt').write_text(''.join(':'.join(r)+'\n' for r in rows))
    packed=work/'onecloud.burn.img';run([tool,'pack',packed,burn])
    check=work/'roundtrip';check.mkdir();run([tool,'unpack',packed,check]);actual=commands(check)
    require({tuple(r[:3]) for r in actual}=={tuple(r[:3]) for r in rows},'Burn component list changed during packing')
    for row in rows:
        other=next(r for r in actual if r[:3]==row[:3])
        require(sha256(burn/row[3])==sha256(check/other[3]),'Burn component changed during round trip')
    for partition in report['partitions']:
        sparse=next(r for r in actual if r[:2]==['PARTITION',partition['name']])
        restored=work/(partition['name']+'.restored');run(['simg2img',check/sparse[3],restored])
        require(restored.stat().st_size==partition['bytes'] and sha256(restored)==partition['sha256'],'Burn partition failed byte-for-byte round trip')
        partition['roundtrip']='identical'
    report['container_crc']='verified-by-AmlImg';report['uncompressed_sha256']=sha256(packed)
    with packed.open('rb') as src,destination.open('wb') as stream,gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0) as dst:shutil.copyfileobj(src,dst)
    report['file']={'name':destination.name,'bytes':destination.stat().st_size,'sha256':sha256(destination)}
    (destination.parent/'onecloud-pack-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print('OneCloud burn CRC and both partitions passed byte-for-byte round trip.',flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');args=parser.parse_args()
    if args.prepare:prepare(Path('work/onecloud-pack'))
