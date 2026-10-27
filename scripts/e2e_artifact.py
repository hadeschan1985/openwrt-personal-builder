"""Check the real private per-file artifact selected by the browser test."""
import argparse
import base64
import json
import os
from pathlib import Path,PurePosixPath
import zipfile
from scripts.archive import download
from scripts.build import require,sha256
from scripts.delivery import validate_record,MAX_BYTES
from scripts.upstream import api


def obtain(run_id,destination):
    require(str(run_id).isdigit(),'Invalid test run ID');token=os.environ['GH_TOKEN']
    require(api('',token)['private'],'Browser build QA requires the existing private repository')
    run=api('/actions/runs/'+str(run_id),token);require(run['conclusion']=='success','Build did not succeed')
    raw=api('/contents/records/'+str(run_id)+'.json',token);require(raw['encoding']=='base64' and raw['size']<=256*1024,'Invalid private record')
    record=validate_record(json.loads(base64.b64decode(raw['content'])))
    images=[f for f in record['files'] if f['group']=='device'];require(len(images)==1,'QA expects one individually downloadable device image')
    expected=images[0];artifacts=api('/actions/runs/'+str(run_id)+'/artifacts?per_page=100',token)['artifacts']
    matches=[a for a in artifacts if a['name']==f"firmware-{run['run_number']}-device-01"]
    require(len(matches)==1,'No unique per-file artifact');artifact=matches[0]
    destination=Path(destination).resolve();require(destination.is_relative_to(Path('work/web-e2e').resolve()),'QA downloads must stay in the QA workspace');destination.mkdir(parents=True,exist_ok=True)
    archive=destination/'firmware.zip';download(artifact,archive,token)
    with zipfile.ZipFile(archive) as package:
        members=package.infolist();require(len(members)==1,'Per-file firmware artifact unexpectedly contains multiple files')
        member=members[0];require(PurePosixPath(member.filename).name==member.filename==expected['name'] and member.file_size==expected['bytes']<=MAX_BYTES,'Artifact file does not match delivery record')
        target=destination/member.filename
        with package.open(member) as src,target.open('wb') as dst:
            remaining=expected['bytes']
            while block:=src.read(1024**2):remaining-=len(block);require(remaining>=0,'Oversized artifact member');dst.write(block)
        require(remaining==0 and sha256(target)==expected['sha256'],'Downloaded image SHA256 mismatch')
    value={'run_id':run_id,'run_number':run['run_number'],'artifact_id':artifact['id'],'artifact_digest':artifact['digest'],'zip':str(archive),'raw':str(target),'file':expected,'config':record['config']}
    (destination/'download.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('E2E_DOWNLOAD='+json.dumps(value,ensure_ascii=False,separators=(',',':')))
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True);parser.add_argument('--destination',required=True);args=parser.parse_args();obtain(args.run,args.destination)
