"""Compile synthetic OneCloud firmware from independently verified public bytes.

No private repository inputs or credentials are copied to this public test.
Only a report is uploaded, never the source cache or test firmware.
"""
import argparse
import datetime as dt
import os
from pathlib import Path
from scripts import catalog,device_catalog,device_upstream as d
from scripts import onecloud_provenance as provenance,source_cache
from scripts.build import require,sha256
from qa.device_discovery import metadata

def prepare():
    require(not os.environ.get('GH_TOKEN') and not os.environ.get('GITHUB_TOKEN'),'No account credential may enter this synthetic test')
    provenance.main()
    proof=source_cache.validate_proof(d.read('outputs/onecloud-provenance.json'))
    original=catalog.kwrt_data
    try:
        catalog.kwrt_data=lambda spec:metadata(spec,original)
        target,spec,data=device_catalog.inspect('amlogic/meson8b',dynamic_issues=True)
    finally:catalog.kwrt_data=original
    require(spec.get('metadata_source') is None and spec.get('source_cache')==source_cache.CACHE_ID,'Expected original direct-feed candidate')
    entry={'spec':spec,'metadata':data};policy=d.policy_digest();fingerprint=d.digest({'policy_sha256':policy,'targets':{target:d.target_fingerprint(entry)}})
    version='kwrt-25.12-'+dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime('%Y%m%d')+'-'+fingerprint[:8]
    candidate=d.validate_candidate({'schema_version':1,'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),'source_commit':os.environ['GITHUB_SHA'],'version':version,'fingerprint':fingerprint,'policy_sha256':policy,'targets':{target:entry}})
    path=Path('work/downloads')/provenance.BUILDER_NAME;path.parent.mkdir(parents=True,exist_ok=True)
    require(not path.exists(),'Do not replace an existing QA input')
    (Path('outputs')/provenance.BUILDER_NAME).rename(path)
    require(path.stat().st_size==source_cache.BUILDER_BYTES and sha256(path)==source_cache.BUILDER_SHA256,'Public author builder mismatch')
    config=d.prepare(candidate,target,'thunder-onecloud',Path('configs/public-onecloud-qa.json'),packages=['curl'],filesystem='ext4')
    config['output'].update(image_types=['emmc_burn'],rootfs=False);d.write('configs/public-onecloud-qa.json',config)
    source_cache.prepare(config)  # Exact already verified bytes; no private API call.
    d.write('work/public-onecloud-candidate.json',candidate);d.write('work/public-onecloud-author-proof.json',proof)

def verify():
    candidate=d.read('work/public-onecloud-candidate.json');entry=candidate['targets']['amlogic/meson8b']
    report=d.read('outputs/image-report.json')
    require(report['status']=='passed' and report['target']=='amlogic/meson8b' and report['profile']=='thunder-onecloud' and report['hardware_tested'] is False,'Actual OneCloud image proof missing')
    require(d.digest(catalog.kwrt_data(entry['spec']))==d.digest(entry['metadata']),'Original feeds changed during compilation; no new approval')
    value={'schema_version':1,'status':'passed','scope':'actual-synthetic-public-OneCloud-build','run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'policy_sha256':candidate['policy_sha256'],'target_fingerprint':d.target_fingerprint(entry),'metadata_source':'seven-original-IPK-indexes','public_author_provenance':d.read('work/public-onecloud-author-proof.json'),'image_validation':report,'private_repository_inputs_used':False,'private_release_published':False,'approved':False,'hardware_tested':False}
    d.write('work/public-onecloud-report.json',value);print('PUBLIC_ONECLOUD_RESULT='+d.canonical(value),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','verify']);args=parser.parse_args();{'prepare':prepare,'verify':verify}[args.action]()
