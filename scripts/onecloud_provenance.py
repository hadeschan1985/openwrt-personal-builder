"""Verify the author's independently published artifact, without running it."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import stat
import shutil
import urllib.request
import zipfile

ARTIFACT_ID=11760922364
RUN_ID=38270404059
SOURCE_COMMIT='72d10a7d43d85dae0ab057493d5a4aa81e97ac82'
ARTIFACT_SHA256='45c39e568391b77cb628086e5f8f3eb96374e323ecef959ffc9d731e5237c57d'
ARTIFACT_BYTES=613745374
BUILDER_NAME='kwrt-imagebuilder-amlogic-meson8b.Linux-x86_64.tar.zst'
PUBLIC_REDIRECT='https://nightly.link/kiddin9/Kwrt/actions/runs/38270404059/10.12_amlogic_meson8b.zip'

def require(value,message):
    if not value:raise ValueError(message)

def inspect(path,expected_sha=ARTIFACT_SHA256,expected_bytes=ARTIFACT_BYTES):
    path=Path(path)
    require(path.stat().st_size==expected_bytes,'Author artifact size mismatch')
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    require(digest==expected_sha,'Author artifact SHA256 mismatch; content was not processed')
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        # Firmware disk images can advertise several GiB of expanded data. We
        # never extract or read them; bound the central directory and the one
        # selected member that is actually streamed instead.
        require(1<=len(entries)<=20000,'Unexpected artifact entry count')
        print('Verified author ZIP directory:',len(entries),'entries;',sum(i.file_size for i in entries),'expanded bytes (not extracted)',flush=True)
        selected=[i for i in entries if PurePosixPath(i.filename).name==BUILDER_NAME]
        require(len(selected)==1,'No unique OneCloud ImageBuilder in author artifact')
        entry=selected[0]
        require(not entry.is_dir() and not stat.S_ISLNK(entry.external_attr>>16) and not PurePosixPath(entry.filename).is_absolute() and '..' not in PurePosixPath(entry.filename).parts and 1<=entry.file_size<=700*1024**2,'Unsafe ImageBuilder archive member')
        digest=hashlib.sha256()
        with archive.open(entry) as stream:
            while block:=stream.read(1024**2):digest.update(block)
        # Reading to EOF also checks the ZIP member CRC. Nothing is extracted.
        result={'schema_version':1,'source_repository':'kiddin9/Kwrt','source_commit':SOURCE_COMMIT,'run_id':RUN_ID,'artifact_id':ARTIFACT_ID,'artifact_sha256':expected_sha,'artifact_bytes':expected_bytes,'archive_member':entry.filename,'builder_name':BUILDER_NAME,'builder_sha256':digest.hexdigest(),'builder_bytes':entry.file_size,'verification':'author-artifact-sha256-and-member-crc','executed':False}
    return result

def main():
    destination=Path('work/onecloud-provenance/author.zip');destination.parent.mkdir(parents=True,exist_ok=True)
    if not destination.exists():
        request=urllib.request.Request(PUBLIC_REDIRECT,headers={'User-Agent':'OpenWrt-Personal-Builder/0.2'})
        with urllib.request.urlopen(request,timeout=90) as response,destination.open('wb') as out:
            size=0
            while block:=response.read(1024**2):
                size+=len(block);require(size<=ARTIFACT_BYTES,'Unexpected author artifact size');out.write(block)
    result=inspect(destination)
    Path('outputs').mkdir(exist_ok=True)
    with zipfile.ZipFile(destination) as archive,archive.open(result['archive_member']) as src,(Path('outputs')/BUILDER_NAME).open('wb') as out:
        shutil.copyfileobj(src,out,1024**2)
    with (Path('outputs')/BUILDER_NAME).open('rb') as stream:
        require(hashlib.file_digest(stream,'sha256').hexdigest()==result['builder_sha256'],'Copied author builder digest mismatch')
    Path('outputs/onecloud-provenance.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()
