"""Replay the archived compiler with a recorded APK cache compatibility adapter.

Only local package timestamps and filenames change. Original archive bytes,
compiler files, configuration and installed versions are preserved and checked.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from scripts import build as compiler,rebuild
from qa.offline_apk_mtime import prepare

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical_name(data):
    info=data.get('info') if isinstance(data,dict) else None
    if not isinstance(info,dict) or not isinstance(info.get('name'),str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.-]{0,120}',info['name']) or not isinstance(info.get('version'),str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.~-]{0,180}',info['version']):raise ValueError('Invalid APK package identity')
    return info['name']+'-'+info['version']+'.apk'

def canonicalize(workspace,describe=None):
    workspace=Path(workspace).resolve();folder=workspace/'packages'
    if not folder.is_dir() or folder.is_symlink():raise ValueError('Local package repository missing or linked')
    paths=sorted(folder.glob('*.apk'))
    if not paths:return []
    apk=workspace/'staging_dir/host/bin/apk'
    if describe is None:
        def describe(path):
            result=subprocess.run([str(apk),'adbdump','--format','json',str(path)],check=True,capture_output=True,text=True,timeout=30)
            if len(result.stdout)>16*1024**2:raise ValueError('Oversized APK metadata')
            return json.loads(result.stdout)
    rows=[];destinations={}
    # Inspect and validate the complete plan before changing local names.
    for path in paths:
        if path.is_symlink() or not path.is_file():raise ValueError('Linked or missing APK file')
        name=canonical_name(describe(path));checksum=digest(path)
        if name in destinations and destinations[name]!=checksum:raise ValueError('Conflicting APK package identity')
        target=folder/name
        if target.exists() and (target.is_symlink() or not target.is_file() or digest(target)!=checksum):raise ValueError('Canonical APK name collision')
        destinations[name]=checksum;rows.append({'source':path.name,'local':name,'sha256':checksum})
    for row in rows:
        path=folder/row['source'];target=folder/row['local']
        if path!=target:
            if target.exists():path.unlink()
            else:path.rename(target)
        kwargs={'follow_symlinks':False} if os.utime in os.supports_follow_symlinks else {}
        os.utime(target,ns=(1000000000,1000000000),**kwargs)
        if digest(target)!=row['sha256']:raise ValueError('APK bytes changed while preparing local repository')
    return rows

def main():
    report=prepare('work/rebuild-packages')
    report.update(adapter_sha256=digest(__file__),archived_compiler='unchanged')
    original=rebuild.offline_packages
    def compatible(workspace):
        original(workspace);rows=canonicalize(workspace)
        report['canonical_apk_files']=len(rows);report['packages']=rows
        rebuild.write('work/offline-apk-compat-report.json',report)
        print('OFFLINE_APK_COMPAT='+rebuild.canonical({k:v for k,v in report.items() if k!='packages'}),flush=True)
    rebuild.offline_packages=compatible
    return compiler.main()

if __name__=='__main__':raise SystemExit(main())
