"""Real synthetic official build and local archived-input replay; no publication.

The private GitHub record/release transfer and webpage dispatch are separate
acceptance tests. This test never claims to exercise those private API steps.
"""
import argparse
import os
from pathlib import Path
from scripts import rebuild as r
from scripts import profile_campaign as campaign
from scripts.build import normalize,require,sha256

CONFIG=Path('configs/public-offline-qa.json')
def prepare():
    require(not os.environ.get('GH_TOKEN') and not os.environ.get('GITHUB_TOKEN'),'No credential may enter synthetic compiler')
    config=r.read('configs/x86-default.json')
    config.update(builder='official',version='25.12.6',target='mediatek/filogic',profile='wavlink_wl-wn573hx3',build_mode='device',packages=['curl'])
    config['system'].update(hostname='OfflineQA',password_secret=True,password_source='root',https=True)
    config['output'].update(filesystem='squashfs',image_types=['WN573HX3-sysupgrade'],rootfs=False,efi=False,legacy=False,vmdk=False,rootfs_size_mb=256)
    r.write(CONFIG,normalize(config))
def capture():
    config=r.read(CONFIG);r.stage(config)
    manifest=r.validate(r.read('work/rebuild-upload/manifest.json'))
    for asset in manifest['assets']:
        require(sha256(Path('work/rebuild-upload')/asset['name'])==asset['sha256'],'Captured local snapshot checksum mismatch')
    r.write('work/public-offline-normal.json',r.read('outputs/image-report.json'))
    # These are the same tar validators/extractors used after a private transfer.
    r.inspect_tar('work/rebuild-engine.tar.gz');r.inspect_tar('work/rebuild-packages.tar.gz',True)
    campaign.clean()
    r.write(r.STATE,{'manifest':manifest})
    r.inspect_tar('work/rebuild-packages.tar.gz',True,True)
    r.inspect_tar('work/rebuild-engine.tar.gz',False,True)
def verify():
    original=r.read('work/public-offline-normal.json');image=r.read('outputs/image-report.json')
    network=r.read('work/offline-network-report.json');compat=r.read('work/offline-apk-compat-report.json')
    require(network['external_network']=='unreachable' and network['loopback_tcp']=='passed' and network['github_token_passed'] is False,'Offline network proof incomplete')
    require(image['status']=='passed' and image['profile']==original['profile'],'Offline image validation mismatch')
    r.verify_installed('outputs')
    report={'schema_version':1,'status':'passed','test_scope':'actual-build-and-local-archived-input-replay','private_api_transfer_tested':False,'run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'normal_image':original,'offline_image':image,'network':network,'apk_compatibility':compat,'package_versions':'exact-installed-manifest-equality','configuration':'original-unchanged','hardware_tested':False}
    r.write('work/public-offline-report.json',report);print('PUBLIC_OFFLINE_RESULT='+r.canonical(report),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','capture','verify']);args=parser.parse_args()
    {'prepare':prepare,'capture':capture,'verify':verify}[args.action]()
