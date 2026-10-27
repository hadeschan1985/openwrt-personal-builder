"""Bounded container/integrity validation. Does not boot or execute firmware."""
import gzip
import hashlib
import json
import re
import struct
from pathlib import Path
import tarfile
import zipfile
import zlib

from scripts.build import normalize,require,sha256
from scripts.delivery import config as load_config,MAX_BYTES,file_group

def gzip_image(path):
    """Check gzip CRC and recognized OpenWrt fwtool trailers; never ignore tails.

    Format reference: openwrt/fwtool fwimage.h and fwtool.c. fwtool stores
    the non-final-XOR CRC32 of every preceding byte before each trailer.
    """
    total=0;decoder=zlib.decompressobj(31)
    with path.open('rb') as stream:
        while not decoder.eof:
            data=stream.read(1024*1024);require(data,'Truncated gzip firmware')
            while data and not decoder.eof:
                total+=len(decoder.decompress(data,1024*1024));require(total<=8*1024**3,'Uncompressed image exceeds validation limit')
                data=decoder.unconsumed_tail
        compressed_end=stream.tell()-len(decoder.unused_data)
    end=path.stat().st_size;trailers=0
    with path.open('rb') as stream:
        while end>compressed_end:
            require(trailers<2 and end-compressed_end>=16,'Unrecognized gzip trailing data')
            stream.seek(end-16);magic,expected,kind,size=struct.unpack('>IIB3xI',stream.read(16))
            require(magic==0x46577830 and kind in (0,1) and 16<=size<=32*1024 and end-size>=compressed_end,'Invalid OpenWrt firmware trailer')
            stream.seek(0);remaining=end-16;crc=0
            while remaining:
                data=stream.read(min(1024*1024,remaining));require(data,'Truncated firmware trailer');crc=zlib.crc32(data,crc);remaining-=len(data)
            require((crc^0xffffffff)==expected,'OpenWrt firmware trailer CRC mismatch')
            if kind==1:
                stream.seek(end-size);payload=stream.read(size-16)
                require(len(payload)>=8 and payload[:4]==bytes(4),'Unsupported firmware metadata header')
                require(isinstance(json.loads(payload[8:]),dict),'Invalid firmware metadata JSON')
            end-=size;trailers+=1
    require(end==compressed_end,'Unexpected data after gzip firmware')
    return 'gzip-crc-and-fwtool-checked' if trailers else 'gzip-crc-checked'

def verify(config,output=Path('outputs')):
    summary=json.loads((output/'build-summary.json').read_text(encoding='utf-8'))
    require(all(summary[k]==config[k] for k in ('version','target','profile','builder')), 'Image summary belongs to another device')
    require(summary.get('dependency_preflight',{}).get('status')=='passed','Package dependency validation missing')
    files=[]
    require(isinstance(summary.get('files'),list) and 1<=len(summary['files'])<=100,'Invalid output file count')
    for item in summary['files']:
        require(re.fullmatch(r'[A-Za-z0-9_.+-]{1,180}',item.get('name','')) and item['name'] not in ('.','..'),'Unsafe image filename')
        path=output/item['name']
        require(path.is_file() and not path.is_symlink() and path.stat().st_size<=MAX_BYTES and path.stat().st_size==item['bytes'] and sha256(path)==item['sha256'],'Image file integrity mismatch')
        if file_group(path.name)=='reports':continue
        require(path.stat().st_size>0,'Empty firmware image')
        kind='binary-output'
        if path.name.endswith('.gz') and not path.name.endswith('.tar.gz'):
            kind=gzip_image(path)
        elif path.name.endswith('.zip'):
            with zipfile.ZipFile(path) as archive:
                require(len(archive.infolist())<=100 and sum(m.file_size for m in archive.infolist())<=8*1024**3,'Oversized image container')
                require(archive.testzip() is None,'Image ZIP CRC mismatch')
            kind='zip-crc-checked'
        elif tarfile.is_tarfile(path):
            with tarfile.open(path) as archive:
                members=archive.getmembers();require(len(members)<=100000 and sum(m.size for m in members)<=8*1024**3,'Oversized image TAR')
            kind='tar-header-checked'
        files.append({'name':path.name,'bytes':item['bytes'],'sha256':item['sha256'],'check':kind})
    require(files,'No device firmware output to validate')
    report={'schema_version':1,'status':'passed','verification_level':'build-and-integrity-only','boot_tested':False,'hardware_tested':False,'version':config['version'],'target':config['target'],'profile':config['profile'],'files':files}
    if config.get('box'):
        proof=json.loads((output/'box-pack-report.json').read_text(encoding='utf-8'))
        require(proof.get('status')=='passed' and proof.get('model')==config['box']['model'] and proof.get('kernel')==config['box']['kernel'] and proof.get('filesystem')=='btrfs' and proof.get('module_vermagic_checked',0)>=20 and proof.get('boot_tested') is False and proof.get('hardware_tested') is False,'Missing matching box kernel/DTB/ABI validation')
        require(len(files)==1 and all(proof['file'][key]==files[0][key] for key in ('name','bytes','sha256')),'Box proof belongs to a different image')
        report['box_packaging']=proof
    if config['target']=='amlogic/meson8b' and any('emmc_burn' in f['name'] for f in files):
        proof=json.loads((output/'onecloud-pack-report.json').read_text(encoding='utf-8'))
        require(proof.get('status')=='passed' and proof.get('container_crc')=='verified-by-AmlImg' and proof.get('hardware_tested') is False and [p.get('name') for p in proof.get('partitions',[])]==['boot','rootfs'] and all(p.get('roundtrip')=='identical' for p in proof['partitions']),'OneCloud burn partition verification missing')
        require(any(all(proof['file'][key]==f[key] for key in ('name','bytes','sha256')) for f in files),'OneCloud proof belongs to another image')
        report['onecloud_packaging']=proof
    (output/'image-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Device build and file integrity passed; device boot/hardware have NOT been tested.')
    return report

if __name__=='__main__':verify(load_config())
