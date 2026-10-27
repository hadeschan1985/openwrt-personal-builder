"""Private durable copy of the exact author-published OneCloud builder.

Tokens are used only in this data transfer process, never in ImageBuilder.
The selected builder still has to match the original published SHA256.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from scripts.archive import NoRedirect,upload
from scripts.build import normalize,require,sha256
from scripts.builders import resolve
from scripts.onecloud_provenance import BUILDER_NAME,ARTIFACT_SHA256,ARTIFACT_ID,RUN_ID,SOURCE_COMMIT
from scripts.upstream import api

TAG='source-onecloud-20261012'
CACHE_ID='onecloud-author-20261012'
BUILDER_SHA256='e29abe52fea3bdaf77a0af313ccb5c6f06c6564a4f7cdb27d41fd9215d6926b5'
BUILDER_BYTES=313895435

def validate_proof(value):
    require(value.get('source_repository')=='kiddin9/Kwrt' and value.get('source_commit')==SOURCE_COMMIT and value.get('run_id')==RUN_ID and value.get('artifact_id')==ARTIFACT_ID and value.get('artifact_sha256')==ARTIFACT_SHA256,'Untrusted author provenance')
    require(value.get('builder_name')==BUILDER_NAME and value.get('builder_sha256')==BUILDER_SHA256 and value.get('builder_bytes')==BUILDER_BYTES and value.get('executed') is False and value.get('verification')=='author-artifact-sha256-and-member-crc','Incorrect author builder proof')
    return value

def publish():
    token=os.environ['GH_TOKEN'];require(api('',token)['private'],'Source cache must remain private')
    proof=validate_proof(json.loads(Path('outputs/onecloud-provenance.json').read_text(encoding='utf-8')))
    builder=Path('outputs')/BUILDER_NAME;require(builder.stat().st_size==BUILDER_BYTES and sha256(builder)==BUILDER_SHA256,'Cached builder bytes do not match the author')
    try:release=api('/releases/tags/'+TAG,token)
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        release=api('/releases',token,'POST',{'tag_name':TAG,'target_commitish':'main','name':'Verified OneCloud source builder (not firmware)','draft':True,'make_latest':'false','body':'Private durable source cache. The exact ImageBuilder matches the original published SHA256. Independently checked against kiddin9/Kwrt run 38270404059, artifact 11760922364 and its published ZIP digest. No downloaded builder was executed by this publisher. This is not a firmware download or a hardware boot approval.'})
    require(release['tag_name']==TAG,'Wrong source cache release')
    upload(release,builder,token);upload(release,Path('outputs/onecloud-provenance.json'),token)
    api('/releases/'+str(release['id']),token,'PATCH',{'draft':False,'make_latest':'false'})
    print('Private author source cache published; original SHA256 retained:',BUILDER_SHA256)

def download_asset(asset,destination,token,repo):
    require(type(asset.get('id')) is int and asset.get('name')==BUILDER_NAME and asset.get('size')==BUILDER_BYTES and asset.get('digest')=='sha256:'+BUILDER_SHA256,'Private source cache metadata mismatch')
    request=urllib.request.Request(f"https://api.github.com/repos/{repo}/releases/assets/{asset['id']}",headers={'Authorization':'Bearer '+token,'Accept':'application/octet-stream','User-Agent':'OpenWrt-Personal-Builder'})
    try:response=urllib.request.build_opener(NoRedirect()).open(request,timeout=60)
    except urllib.error.HTTPError as error:
        require(error.code in (301,302,303,307,308),'Cannot access private source cache')
        parsed=urllib.parse.urlsplit(error.headers['Location'])
        require(parsed.scheme=='https' and parsed.hostname in ('release-assets.githubusercontent.com','objects.githubusercontent.com'),'Untrusted source cache redirect')
        # Credentials are deliberately not sent to the signed storage URL.
        response=urllib.request.urlopen(urllib.request.Request(error.headers['Location']),timeout=120)
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    size=0;digest=hashlib.sha256()
    with response,destination.open('wb') as out:
        while chunk:=response.read(1024**2):
            size+=len(chunk);require(size<=BUILDER_BYTES,'Source cache exceeds expected size');digest.update(chunk);out.write(chunk)
    require(size==BUILDER_BYTES and digest.hexdigest()==BUILDER_SHA256,'Original author builder SHA256 mismatch')

def prepare(config):
    if config['builder']!='kwrt':return
    spec=resolve(config['version'],config['target'])
    if not spec.get('source_cache'):return
    require(spec['source_cache']==CACHE_ID and spec['target']=='amlogic/meson8b' and spec['sha256']==BUILDER_SHA256,'Unrecognized private source cache request')
    destination=Path('work/downloads')/BUILDER_NAME
    if destination.exists() and destination.stat().st_size==BUILDER_BYTES and sha256(destination)==BUILDER_SHA256:return
    token=os.environ['GH_TOKEN'];require(api('',token)['private'],'Private source cache required')
    release=api('/releases/tags/'+TAG,token);require(not release['draft'] and release['tag_name']==TAG,'Verified source cache is not ready')
    selected=[a for a in release['assets'] if a.get('name')==BUILDER_NAME];require(len(selected)==1,'No unique verified source builder')
    download_asset(selected[0],destination,token,os.environ['GITHUB_REPOSITORY'])
    print('Exact author builder restored from private cache; SHA256:',BUILDER_SHA256)

def read_config(path):
    raw=os.environ.get('CONFIG_JSON','').strip()
    if not raw:
        path=Path(path).resolve();require(path.is_relative_to(Path('configs').resolve()),'Config must be under configs/')
        raw=path.read_text(encoding='utf-8')
    require(len(raw.encode())<=60000,'Config exceeds limit');return normalize(json.loads(raw))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['publish','prepare']);parser.add_argument('--config',default='configs/x86-default.json');args=parser.parse_args()
    publish() if args.action=='publish' else prepare(read_config(args.config))
