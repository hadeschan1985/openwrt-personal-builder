"""Inspect the verified author SDK without executing it or changing any drivers."""
import hashlib
import io
import os
from pathlib import Path,PurePosixPath
import re
import subprocess
import tarfile
from scripts import catalog,device_catalog,device_upstream as d
from scripts.build import download,require,sha256

require(not os.environ.get('GH_TOKEN') and not os.environ.get('GITHUB_TOKEN'),'No account credential may enter source diagnostics')
target,spec,data=device_catalog.inspect('rockchip/armv8',dynamic_issues=True)
path=Path('work/rockchip-source-diagnostic')/spec['archive'];path.parent.mkdir(parents=True,exist_ok=True)
download(spec['base']+'/'+spec['archive'],path);require(sha256(path)==spec['sha256'],'SDK checksum mismatch')
symbols=re.compile(r'(?:AIC8800|RFKILL|KEYBOARD_ADC|YT921|PCAT|43752|43430B0)',re.I)
def ipk_package(raw):
    control=None
    if raw.startswith(b'!<arch>\n'):
        offset=8
        while offset+60<=len(raw):
            header=raw[offset:offset+60];require(header[58:60]==b'`\n','Invalid SDK IPK header')
            size=int(header[48:58].strip());name=header[:16].decode().strip().rstrip('/');offset+=60
            require(0<=size<=len(raw)-offset,'Truncated SDK IPK')
            if name=='control.tar.gz':control=raw[offset:offset+size]
            offset+=size+size%2
    else:
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as outer:
            member=next((m for m in outer if m.name.removeprefix('./')=='control.tar.gz'),None)
            require(member is not None and member.isfile() and member.size<=1024**2,'Invalid SDK package control')
            control=outer.extractfile(member).read()
    require(control is not None and len(control)<=1024**2,'Missing SDK package control')
    with tarfile.open(fileobj=io.BytesIO(control),mode='r:gz') as inner:
        member=next((m for m in inner if m.name.removeprefix('./')=='control'),None)
        require(member is not None and member.isfile() and member.size<=64000,'Invalid SDK package fields')
        text=inner.extractfile(member).read().decode()
        match=re.search(r'^Package: ([A-Za-z0-9+_.-]+)$',text,re.M)
        require(match is not None,'Missing SDK package name')
        provided=re.search(r'^Provides: (.+)$',text,re.M)
        aliases=[]
        for item in provided[1].split(',') if provided else []:
            alias=re.match(r'[A-Za-z0-9+_.-]+',item.strip())
            if alias:aliases.append(alias[0])
        return match[1],aliases

related_paths=[];configuration=[];bundled_packages=set();bundled_providers=set();expanded=0;count=0
process=subprocess.Popen(['zstd','-dc',str(path)],stdout=subprocess.PIPE)
try:
    with tarfile.open(fileobj=process.stdout,mode='r|') as archive:
        for member in archive:
            count+=1;expanded+=max(0,member.size)
            require(count<=200000 and expanded<=16*1024**3,'SDK inventory exceeds diagnostic bounds')
            name=PurePosixPath(member.name)
            if symbols.search(str(name)):
                require(len(related_paths)<2000,'Too many related SDK entries')
                related_paths.append(str(name))
            if member.isfile() and name.suffix=='.ipk':
                require(member.size<=128*1024**2,'Oversized bundled SDK package')
                package,aliases=ipk_package(archive.extractfile(member).read())
                bundled_packages.add(package);bundled_providers.update(aliases)
            if member.isfile() and name.name in ('.config','kernel.config','config.buildinfo','Packages','modules.builtin'):
                require(member.size<=4*1024**2,'Oversized SDK text metadata')
                raw=archive.extractfile(member).read();text=raw.decode('utf-8',errors='replace')
                if name.name=='Packages':bundled_packages.update(re.findall(r'^Package: ([A-Za-z0-9+_.-]+)$',text,re.M))
                else:
                    lines=[line for line in text.splitlines() if symbols.search(line)]
                    if lines:configuration.append({'path':str(name),'sha256':hashlib.sha256(raw).hexdigest(),'matching_lines':lines[:300]})
    process.stdout.close();require(process.wait(timeout=30)==0,'SDK decoder failed')
finally:
    if process.poll() is None:process.kill();process.wait()
available=set(data['packages'])|bundled_packages|bundled_providers;missing=[];base=data['profiles'].get('default_packages',[])
for profile,item in data['profiles']['profiles'].items():
    tokens=base+item.get('device_packages',[])
    selected=set(p for p in tokens if not p.startswith('-'))-set(p[1:] for p in tokens if p.startswith('-'))-set(spec['exclude_defaults'])
    absent=selected-available
    if absent:missing.append({'profile':profile,'missing_default_packages':sorted(absent)})
require(d.digest(catalog.kwrt_data(spec))==d.digest(data),'Metadata changed while inspecting SDK')
report={'schema_version':1,'status':'inspected','scope':'read-only-verified-SDK-inventory-no-execution','run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'target':target,'target_fingerprint':d.target_fingerprint({'spec':spec,'metadata':data}),'builder_sha256':spec['sha256'],'sdk_entries':count,'bundled_package_names':sorted(bundled_packages),'bundled_provided_names':sorted(bundled_providers),'bundled_package_index_entries':len(bundled_packages),'profiles':len(data['profiles']['profiles']),'profiles_with_defaults_absent_from_selector_and_bundled_index':missing,'absence_is_not_a_build_failure_claim':True,'configuration':configuration,'related_sdk_paths':related_paths,'firmware_compiled':False,'kernel_builtin_claim':False,'hardware_tested':False}
d.write('work/rockchip-source-report.json',report)
print('ROCKCHIP_SOURCE_DIAGNOSTIC='+d.canonical(report),flush=True)
