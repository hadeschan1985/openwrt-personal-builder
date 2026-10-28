"""Inspect the verified author SDK without executing it or changing any drivers."""
import hashlib
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
related_paths=[];configuration=[];bundled_packages=set();expanded=0;count=0
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
available=set(data['packages'])|bundled_packages;missing=[];base=data['profiles'].get('default_packages',[])
for profile,item in data['profiles']['profiles'].items():
    tokens=base+item.get('device_packages',[])
    selected=set(p for p in tokens if not p.startswith('-'))-set(p[1:] for p in tokens if p.startswith('-'))-set(spec['exclude_defaults'])
    absent=selected-available
    if absent:missing.append({'profile':profile,'missing_default_packages':sorted(absent)})
require(d.digest(catalog.kwrt_data(spec))==d.digest(data),'Metadata changed while inspecting SDK')
report={'schema_version':1,'status':'inspected','scope':'read-only-verified-SDK-inventory-no-execution','run_id':os.environ['GITHUB_RUN_ID'],'source_commit':os.environ['GITHUB_SHA'],'target':target,'target_fingerprint':d.target_fingerprint({'spec':spec,'metadata':data}),'builder_sha256':spec['sha256'],'sdk_entries':count,'bundled_package_index_entries':len(bundled_packages),'profiles':len(data['profiles']['profiles']),'profiles_with_defaults_absent_from_selector_and_bundled_index':missing,'configuration':configuration,'related_sdk_paths':related_paths,'firmware_compiled':False,'kernel_builtin_claim':False,'hardware_tested':False}
d.write('work/rockchip-source-report.json',report)
print('ROCKCHIP_SOURCE_DIAGNOSTIC='+d.canonical(report),flush=True)
