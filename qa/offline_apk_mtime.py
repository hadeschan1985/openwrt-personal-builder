"""Avoid apk-tools 3.0.5 mkndx reading a nonexistent prior index for mtime=0.

The deterministic source archive retains its original bytes. Only extracted
APK filesystem timestamps are set to one second after epoch, before the
archived compiler copies them. No package content or configuration is changed.
"""
import hashlib
import json
import os
from pathlib import Path

def prepare(directory):
    directory=Path(directory)
    if not directory.is_dir() or directory.is_symlink():raise ValueError('Archived package directory missing or linked')
    count=0
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix not in ('.apk','.ipk'):raise ValueError('Unexpected archived package entry')
        if path.suffix!='.apk':continue
        before=hashlib.sha256(path.read_bytes()).hexdigest()
        os.utime(path,ns=(1000000000,1000000000),follow_symlinks=False)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=before:raise ValueError('Package content changed during timestamp adjustment')
        count+=1
    return {'schema_version':1,'status':'passed','apk_files':count,'package_bytes':'unchanged-sha256-verified','extracted_mtime_seconds':1,'reason':'apk-tools-3.0.5-zero-mtime-index-compatibility'}

if __name__=='__main__':
    report=prepare('work/rebuild-packages')
    Path('work/offline-apk-compat-report.json').write_text(json.dumps(report,sort_keys=True)+'\n',encoding='utf8')
    print('OFFLINE_APK_COMPAT='+json.dumps(report,sort_keys=True),flush=True)
