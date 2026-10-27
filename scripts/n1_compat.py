"""Restore the exact generic NVRAM link used by the N1 source platform.

The real calibration text remains owned by the upstream firmware package. No
radio data is invented, modified or borrowed from an undocumented source.
"""
import io
from pathlib import Path
import tarfile

RECIPE='n1-nvram-v1'
PACKAGE='brcmfmac-nvram-43455-sdio-generic'
DEPENDENCY='brcmfmac-nvram-43455-sdio'
LINK='lib/firmware/brcm/brcmfmac43455-sdio.txt'
DESTINATION='brcmfmac43455-sdio.raspberrypi,4-model-b.txt'
SOURCE='https://github.com/istoreos/istoreos/blob/283d02639c740f8ae6e9425b48be8c61f152c6b8/package/firmware/linux-firmware/broadcom.mk'

def metadata(data,spec):
    if spec.get('compatibility_recipe')!=RECIPE:return data
    if spec['target']!='amlogic/meson' or set(data['profiles']['profiles'])!={'phicomm_n1'} or DEPENDENCY not in data['packages']:
        raise ValueError('N1 source recipe no longer matches this platform')
    data['packages']=sorted(set(data['packages'])|{PACKAGE})
    data['compatibility_adjustments']['n1_nvram']={'recipe':RECIPE,'source':SOURCE,'link':LINK,'destination':DESTINATION}
    return data

def create_package(workspace):
    def archive(files):
        stream=io.BytesIO()
        with tarfile.open(fileobj=stream,mode='w:gz') as tar:
            for name,body in files.items():
                member=tarfile.TarInfo(name);member.mode=0o644;member.mtime=0
                if isinstance(body,tuple):member.type=tarfile.SYMTYPE;member.linkname=body[0];tar.addfile(member)
                else:member.size=len(body);tar.addfile(member,io.BytesIO(body))
        return stream.getvalue()
    control=(f'Package: {PACKAGE}\nVersion: 1.0+pb1\nArchitecture: all\nDepends: {DEPENDENCY}\nSection: firmware\n'
             f'Description: Restore original iStoreOS N1 generic NVRAM symlink. Source: {SOURCE}\n').encode()
    payload=archive({'./debian-binary':b'2.0\n','./control.tar.gz':archive({'./control':control}),'./data.tar.gz':archive({'./'+LINK:(DESTINATION,)})})
    path=Path(workspace)/'packages'/f'{PACKAGE}_1.0+pb1_all.ipk';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(payload)
    return path

def verify_rootfs(root):
    members={m.name.removeprefix('./'):m for m in root}
    link=members.get(LINK);target=members.get('lib/firmware/brcm/'+DESTINATION)
    if not link or not link.issym() or link.linkname!=DESTINATION or not target or not target.isfile() or target.size<100:
        raise ValueError('N1 generic calibration link or its real firmware-package data is missing')
