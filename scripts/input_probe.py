"""Inventory public build inputs only; never reads generated user configuration."""
import json
from pathlib import Path
from scripts.build import sha256,require


def inspect(root=Path('.')):
    root=Path(root);workspace=root/'work/builder';require(workspace.is_dir(),'Missing builder workspace')
    packages=[];indexes=[]
    for directory in ('dl','packages'):
        base=workspace/directory
        if not base.exists():continue
        for path in sorted(base.rglob('*')):
            if not path.is_file() or path.is_symlink():continue
            name=path.name
            if name.endswith(('.ipk','.apk')) or name in ('Packages','Packages.gz','Packages.sig','APKINDEX.tar.gz','packages.adb'):
                item={'path':path.relative_to(workspace).as_posix(),'bytes':path.stat().st_size,'sha256':sha256(path)}
                (packages if name.endswith(('.ipk','.apk')) else indexes).append(item)
    require(len(packages)<=5000 and len(indexes)<=1000,'Unexpected input cache size')
    result={'schema_version':1,'packages':packages,'indexes':indexes,'package_bytes':sum(x['bytes'] for x in packages),'workspace_directories':[p.name for p in workspace.iterdir() if p.is_dir() and not p.is_symlink()]}
    path=root/'outputs/input-probe.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(result,indent=2)+'\n')
    print('INPUT_PROBE='+json.dumps(result,separators=(',',':')))
    return result


if __name__=='__main__':inspect()
