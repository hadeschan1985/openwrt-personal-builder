"""Read the real APK tool's index errors for the fixed synthetic QA snapshot."""
from pathlib import Path
import os
import subprocess
from scripts import rebuild as r
from scripts.build import require,sha256

inputs=r.read('work/rebuild-source-inputs.json');archive=Path('work/downloads')/inputs['archive']
require(sha256(archive)==inputs['builder_sha256'],'Wrong archived builder')
destination=Path('work/apk-diagnostic');destination.mkdir()
subprocess.run(['tar','-xf',str(archive),'-C',str(destination)],check=True)
roots=[p for p in destination.iterdir() if (p/'Makefile').is_file()];require(len(roots)==1,'Unexpected builder layout')
workspace=roots[0].resolve();r.offline_packages(workspace)
packages=sorted((workspace/'packages').glob('*.apk'));require(packages,'Archived APKs missing')
print('DIAGNOSTIC_APK_FILES=',len(packages),[p.name for p in packages[:6]],flush=True)
apk=workspace/'staging_dir/host/bin/apk'
subprocess.run([str(apk),'--version'],check=True)
print('DIAGNOSTIC_HEADER=',packages[0].read_bytes()[:16].hex(),flush=True)
print('DIAGNOSTIC_ORIGINAL_MTIME=',packages[0].stat().st_mtime_ns,flush=True)
original={p.name:sha256(p) for p in packages}
for p in packages:os.utime(p,ns=(1000000000,1000000000),follow_symlinks=False)
command=[str(apk),'mkndx','--allow-untrusted','--pkgname-spec','${name}-${version}.${hash:8}.apk','--output','packages.adb']+[p.name for p in packages]
result=subprocess.run(command,cwd=workspace/'packages',text=True)
print('DIAGNOSTIC_INDEX_EXIT=',result.returncode,flush=True)
require(result.returncode==0 and (workspace/'packages/packages.adb').is_file(),'Nonzero package timestamp did not fix index')
require(original=={p.name:sha256(p) for p in packages},'Package bytes changed')
print('DIAGNOSTIC_APK_MTIME_FIX=passed',flush=True)
print('DIAGNOSTIC_INSPECTION=completed',flush=True)
