import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from scripts import n1_compat as n
from scripts.build import ipk_control
from scripts.builders import resolve,validate_spec

class N1CompatibilityTests(unittest.TestCase):
    def test_recipe_requires_exact_n1_profile_and_real_dependency(self):
        for target,profiles,packages in [('x86/64',{'phicomm_n1':{}},[n.DEPENDENCY]),('amlogic/meson',{'other':{}},[n.DEPENDENCY]),('amlogic/meson',{'phicomm_n1':{}},[])]:
            with self.assertRaises(ValueError):n.metadata({'profiles':{'profiles':profiles},'packages':packages,'compatibility_adjustments':{}},{'target':target,'compatibility_recipe':n.RECIPE})
        data={'profiles':{'profiles':{'phicomm_n1':{}}},'packages':[n.DEPENDENCY],'compatibility_adjustments':{}}
        n.metadata(data,{'target':'amlogic/meson','compatibility_recipe':n.RECIPE});self.assertIn(n.PACKAGE,data['packages']);self.assertIn('283d02639c740f8ae6e9425b48be8c61f152c6b8',data['compatibility_adjustments']['n1_nvram']['source'])

    def test_package_contains_only_the_original_link_and_no_host_scripts(self):
        with tempfile.TemporaryDirectory() as folder:
            path=n.create_package(Path(folder));fields=ipk_control(path,'aarch64_cortex-a53');self.assertEqual(fields['Depends'],n.DEPENDENCY)
            with tarfile.open(path,'r:gz') as outer:
                with tarfile.open(fileobj=io.BytesIO(outer.extractfile('./control.tar.gz').read()),mode='r:gz') as control:self.assertEqual(control.getnames(),['./control'])
                with tarfile.open(fileobj=io.BytesIO(outer.extractfile('./data.tar.gz').read()),mode='r:gz') as data:
                    self.assertEqual(data.getnames(),['./'+n.LINK]);link=data.getmembers()[0];self.assertTrue(link.issym());self.assertEqual(link.linkname,n.DESTINATION)

    def test_rootfs_requires_correct_link_and_nonempty_real_calibration(self):
        for destination,include_target,passed in [(n.DESTINATION,True,True),('guessed.txt',True,False),(n.DESTINATION,False,False)]:
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode='w') as tar:
                link=tarfile.TarInfo('./'+n.LINK);link.type=tarfile.SYMTYPE;link.linkname=destination;tar.addfile(link)
                if include_target:
                    target=tarfile.TarInfo('./lib/firmware/brcm/'+n.DESTINATION);target.size=200;tar.addfile(target,io.BytesIO(b'a'*200))
            stream.seek(0)
            with tarfile.open(fileobj=stream,mode='r:') as tar:
                # The normal builder has already enumerated the rootfs archive.
                list(tar)
                if passed:n.verify_rootfs(tar)
                else:
                    with self.assertRaises(ValueError):n.verify_rootfs(tar)

    def test_other_platforms_cannot_request_this_recipe(self):
        spec=resolve('kwrt-25.12-20261012','rockchip/armv8');spec['compatibility_recipe']=n.RECIPE
        with self.assertRaises(ValueError):validate_spec(spec)
