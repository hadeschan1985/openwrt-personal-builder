"""Synthetic packaging QA only. No firmware generation, secrets or network."""
import argparse
import hashlib
import json
from pathlib import Path
from scripts.delivery import file_group,prepare_downloads


def prepare(variant):
    output=Path('outputs');output.mkdir(exist_ok=True)
    extension='.vmdk.zip' if variant=='native' else '.vmdk'
    names=['qa-combined-efi.img.gz','qa-combined.img.gz','qa-combined-efi'+extension,'qa-combined'+extension]
    files=[]
    for name in names:
        payload=('SYNTHETIC PACKAGING TEST. NOT FIRMWARE. '+name).encode()
        (output/name).write_bytes(payload)
        files.append({'name':name,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'group':file_group(name)})
    groups=prepare_downloads(files,output,Path('work/downloads-separated'))
    assert set(groups)=={'efi','legacy','efi-vmdk','legacy-vmdk'}
    report={'synthetic_not_firmware':True,'variant':variant,'groups':{}}
    for group in groups:
        entries=list((Path('work/downloads-separated')/group).iterdir())
        assert len(entries)==1
        file=entries[0];checksum=hashlib.sha256(file.read_bytes()).hexdigest()
        assert checksum==next(f['sha256'] for f in files if f['name']==file.name)
        report['groups'][group]={'name':file.name,'sha256':checksum,'bytes':file.stat().st_size,'files':1}
    Path('work/download-qa-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('Synthetic packaging verified: four independent downloads, exactly one original file per download.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('variant',choices=['native','converted']);prepare(parser.parse_args().variant)
