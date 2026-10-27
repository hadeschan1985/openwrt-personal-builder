"""Repack a generated ARM64 rootfs using fixed public board/kernel resources.

Runs only in an isolated Linux Actions runner. All loop devices are created
from files in this run; user initialization scripts are copied, never sourced.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shlex
import shutil
import subprocess
import tarfile

from scripts.build import require,sha256
from scripts.box_resources import source_config,fetch,git_blob,inspect_kernel,dtb_compatible
from scripts.onecloud_pack import clean_env,run

ROOT=Path(__file__).resolve().parents[1]
CATALOG=ROOT/'configs/box-builders.json'
READONLY_OPTIONS={'ext4':'ro,noload','btrfs':'ro,rescue=nologreplay','vfat':'ro'}


def restore_rootfs_recipe(workspace):
    path=Path(workspace)/'target/linux/armsr/image/Makefile';source=path.read_text()
    pattern=r'(?m)^define Image/Build\n.*?^endef(?:\n|$)'
    matches=re.findall(pattern,source,re.S)
    require(len(matches)==1 and '/data/packit/amlogic-s9xxx-openwrt' in matches[0] and '~/packit/packit_amlogic.sh' in matches[0] and 'PROFILE_SANITIZED' in matches[0],'Unknown ARM64 box server packaging hook')
    path.write_text(re.sub(pattern,'',source,flags=re.S))


def selection(config):
    box=config.get('box');require(isinstance(box,dict) and set(box)=={'model','kernel'},'Box selection needs a fixed model and kernel')
    require(config['builder']=='kwrt' and config['target']=='armsr/armv8' and config['profile']=='box','Box repacking requires the generic ARM64 box profile')
    require(config['output']['rootfs'] and not config['output'].get('image_types'),'Box repacking requires only its intermediate ROOTFS')
    require(not any(config['features'][k] for k in ('usb_net','usb_wireless','wwan')),'Box drivers come from the selected kernel; native OpenWrt driver switches cannot be mixed')
    require(not any(p.startswith(('kmod-','kernel')) for p in config['packages']),'Native OpenWrt kernel packages cannot be mixed with a box kernel')
    data=json.loads(CATALOG.read_text(encoding='utf-8'));sources=source_config()
    require(data['repositories']==sources['repositories'] and data['model_database_blob']==sources['model_database_blob'] and data['remake_blob']==sources['remake_blob'],'Box catalog source pins changed; regenerate and test first')
    models=[m for m in data['models'] if m['id']==box['model']];kernels=[k for k in data['kernels'] if k['id']==box['kernel']]
    require(len(models)==len(kernels)==1 and box['kernel'] in models[0]['kernels'],'This box model/kernel combination has no verified DTB')
    model,kernel=models[0],kernels[0]
    require(any(all(kernel.get(k)==v for k,v in pin.items()) for pin in sources['kernels']),'Box kernel differs from its public SHA256 pin')
    return model,kernel,sources


def patched_recipe(source,sources):
    require(git_blob(source.encode())==sources['remake_blob'],'Repacker recipe differs from fixed source')
    # Replace all clone/download helpers. The runner must only consume the
    # commits and bytes already checked below, never rolling main/latest data.
    clone='''git_pull_dir() {
    local repo="${1#https://github.com/}"
    case "$repo" in
      ophub/amlogic-s9xxx-armbian|ophub/u-boot|ophub/firmware|ophub/luci-app-amlogic) ;;
      *) error_msg "Unexpected box resource repository" ;;
    esac
    rsync -a --exclude=.git "${BOX_SOURCE_ROOT}/${repo##*/}/" "${3}/" || error_msg "Pinned box source copy failed"
}
'''
    find='''find_openwrt() {
    openwrt_default_file="personal-rootfs.tar.gz"
    [[ -s "${openwrt_path}/${openwrt_default_file}" ]] || error_msg "Missing personal rootfs"
    source_repo="github.com/kiddin9/Kwrt"
    source_codename="kwrt"
    source_branch="25.12"
}
'''
    kernel='''download_kernel() {
    [[ -d "${kernel_path}/stable/${specific_kernel[0]}" ]] || error_msg "Missing verified fixed kernel"
    check_kernel "${kernel_path}/stable/${specific_kernel[0]}"
}
'''
    for name,replacement in [('git_pull_dir',clone),('find_openwrt',find),('download_kernel',kernel)]:
        pattern=r'(?m)^'+name+r'\(\) \{\n.*?^\}\n'
        require(len(re.findall(pattern,source,re.S))==1,'Repacker function layout changed: '+name)
        source=re.sub(pattern,lambda _:replacement,source,count=1,flags=re.S)
    require('source "${temp_dir}/${source_release_file}"' not in source,'Unsafe host sourcing of firmware release metadata')
    return source


def checkout(sources,work):
    checkouts=work/'sources';checkouts.mkdir(parents=True,exist_ok=True)
    paths={}
    for pin in sources['repositories']:
        repo=pin['repository'];path=checkouts/repo.split('/')[1]
        if not path.exists():
            path.mkdir();run(['git','init',path]);run(['git','-C',path,'fetch','--depth=1','https://github.com/'+repo+'.git',pin['commit']]);run(['git','-C',path,'checkout','--detach','FETCH_HEAD'])
        head=run(['git','-C',path,'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
        require(head==pin['commit'],'Box resource checkout mismatch');paths[repo]=path
    return checkouts,paths


def extract_fixed_kernel(path,destination):
    with tarfile.open(path,'r:gz') as archive:
        members=archive.getmembers();require(1<=len(members)<=100 and sum(m.size for m in members)<=600*1024**2,'Oversized box kernel container')
        for member in members:
            name=PurePosixPath(member.name)
            require(not name.is_absolute() and '..' not in name.parts and (member.isfile() or member.isdir()),'Unsafe box kernel archive member')
        archive.extractall(destination,filter='data')


def verify_disk(compressed,model,kernel,defaults_hash,work):
    raw=work/'verification.img'
    with gzip.open(compressed,'rb') as src,raw.open('wb') as dst:
        total=0
        while chunk:=src.read(1024**2):
            total+=len(chunk);require(total<=2*1024**3,'Box disk exceeds validation bound');dst.write(chunk)
    loop=run(['sudo','losetup','--find','--show','--partscan','--read-only',raw],capture_output=True,text=True).stdout.strip()
    require(re.fullmatch(r'/dev/loop\d+',loop),'Unexpected private loop device')
    run(['sudo','udevadm','settle','--timeout=30'])
    mounts=[]
    try:
        identity=run(['sudo','losetup','--noheadings','--output','BACK-FILE',loop],capture_output=True,text=True).stdout.strip()
        require(Path(identity).resolve()==raw.resolve(),'Loop device does not belong to this image')
        boot=work/'verify-boot';root=work/'verify-root';boot.mkdir();root.mkdir()
        for number,directory,kind in [(1,boot,'ext4' if model['platform']=='rockchip' else 'vfat'),(2,root,'btrfs')]:
            options=READONLY_OPTIONS[kind]
            try:run(['sudo','mount','-t',kind,'-o',options,loop+'p'+str(number),directory])
            except subprocess.CalledProcessError:
                diagnostic=run(['sudo','dmesg'],capture_output=True,text=True).stdout
                print('\n'.join(line for line in diagnostic.splitlines() if 'btrfs' in line.lower())[-12000:],flush=True)
                run(['sudo','blkid',loop+'p'+str(number)])
                raise
            mounts.append(directory)
        dtb=boot/'dtb'/model['platform']/model['dtb'];expected=kernel['dtbs'][model['dtb']]
        require(dtb.is_file() and sha256(dtb)==expected['sha256'] and dtb_compatible(dtb.read_bytes())==expected['compatible'],'Final box DTB does not match chosen model/kernel')
        configs=[p for p in [boot/'uEnv.txt',boot/'extlinux/extlinux.conf',boot/'armbianEnv.txt'] if p.is_file()]
        require(any(model['dtb'] in p.read_text() and 'btrfs' in p.read_text() for p in configs),'Final boot configuration does not reference chosen DTB and Btrfs')
        defaults=root/'etc/uci-defaults/99-personal-builder';require(defaults.is_file() and sha256(defaults)==defaults_hash,'Personal first-boot settings were altered by repacking')
        module_root=root/'lib/modules'/kernel['release'];require(module_root.is_dir(),'Final kernel modules directory missing')
        releases=[p.name for p in (root/'lib/modules').iterdir() if p.is_dir()]
        require(releases==[kernel['release']],'Native kernel modules remained beside replacement kernel')
        modules=[p for p in module_root.rglob('*.ko') if p.is_file() and not p.is_symlink()]
        require(20<=len(modules)<=20000,'Final kernel modules unexpectedly incomplete')
        checked=0
        for path in modules:
            require(path.stat().st_size<=32*1024**2,'Oversized kernel module')
            data=path.read_bytes();match=re.search(rb'vermagic=([^\x00]+)',data)
            require(match and match.group(1).decode().split()[0]==kernel['release'],'Final module ABI differs from selected kernel');checked+=1
        return {'status':'passed','model':model['id'],'kernel':kernel['id'],'kernel_release':kernel['release'],'filesystem':'btrfs','dtb':model['dtb'],'dtb_sha256':expected['sha256'],'compatible':expected['compatible'],'module_vermagic_checked':checked,'personal_defaults_sha256':defaults_hash,'boot_tested':False,'hardware_tested':False}
    finally:
        for directory in reversed(mounts):run(['sudo','umount',directory])
        run(['sudo','losetup','-d',loop])


def repack(rootfs,config,output,work):
    model,kernel,sources=selection(config);require(os.environ.get('GITHUB_ACTIONS')=='true' and os.name=='posix','Box repacking runs only on isolated GitHub Linux runners')
    rootfs=Path(rootfs).resolve();output=Path(output).resolve();work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True)
    with tarfile.open(rootfs,'r:gz') as archive:
        members=[m for m in archive if m.name.removeprefix('./')=='etc/uci-defaults/99-personal-builder']
        require(len(members)==1 and members[0].isfile() and members[0].size<=64000,'Missing bounded personal settings')
        defaults_hash=hashlib.sha256(archive.extractfile(members[0]).read()).hexdigest()
    checkouts,paths=checkout(sources,work);source=paths['ophub/amlogic-s9xxx-openwrt'];runner=work/'runner'
    require(not runner.exists(),'Box packaging workspace must be new');shutil.copytree(source,runner,ignore=shutil.ignore_patterns('.git'))
    recipe=runner/'remake';recipe.write_text(patched_recipe(recipe.read_text(),sources))
    inputs=runner/'openwrt-armsr';inputs.mkdir(exist_ok=True);shutil.copy2(rootfs,inputs/'personal-rootfs.tar.gz')
    bundle=fetch(f"https://github.com/ophub/kernel/releases/download/kernel_{kernel['tag']}/{kernel['version']}.tar.gz",work/(kernel['id']+'.tar.gz'),kernel['bytes'],kernel['sha256'])
    actual=inspect_kernel(bundle,kernel,[model]);require(actual['release']==kernel['release'] and actual['dtbs'][model['dtb']]==kernel['dtbs'][model['dtb']],'Downloaded kernel DTB differs from approved resource catalog')
    kernel_dir=runner/'make-openwrt/kernel'/kernel['tag'];kernel_dir.mkdir(parents=True,exist_ok=True);extract_fixed_kernel(bundle,kernel_dir)
    command=['sudo','env','BOX_SOURCE_ROOT='+str(checkouts),'bash',str(recipe),'-b',model['id'],'-k',kernel['version'],'-a','false','-s','384/1280','-n','PersonalBuilder']
    log=output/'box-pack.log'
    with log.open('w',encoding='utf-8') as stream:
        process=subprocess.Popen(command,cwd=runner,env=clean_env(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,errors='replace')
        for line in process.stdout:print(line,end='',flush=True);stream.write(line)
        require(process.wait()==0,'Box packaging failed; see box-pack.log')
    files=list((runner/'openwrt/out').glob('*.img.gz'));require(len(files)==1,'Box packer did not produce one unique image')
    report=verify_disk(files[0],model,kernel,defaults_hash,work)
    destination=output/('personal-box-'+model['id']+'-'+kernel['version']+'.img.gz');require(not destination.exists(),'Duplicate box output');shutil.copy2(files[0],destination)
    report.update(schema_version=1,repositories=sources['repositories'],kernel_asset_sha256=kernel['sha256'],file={'name':destination.name,'bytes':destination.stat().st_size,'sha256':sha256(destination)})
    (output/'box-pack-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('BOX_PACK_REPORT='+json.dumps(report,ensure_ascii=False,separators=(',',':')),flush=True)
    return report
