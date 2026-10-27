import copy
import io
import json
import os
from pathlib import Path
import tarfile
import subprocess
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
from scripts import rebuild as r
from scripts.build import ConfigError


def manifest():
    kinds=[('builder','work/downloads/builder.tar.zst'),('packages','work/rebuild-packages.tar.gz'),('engine','work/rebuild-engine.tar.gz')]
    return {'schema_version':1,'status':'captured','run_id':'123','engine_source_commit':'a'*40,'config_sha256':'b'*64,'assets':[{'kind':k,'destination':d,'name':str(i)*64+('.tar.zst' if k=='builder' else '.tar.gz'),'sha256':str(i)*64,'bytes':123} for i,(k,d) in enumerate(kinds,1)]}


class RebuildTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('git'),'Git is needed for detached source metadata regression')
    def test_empty_git_refs_directory_survives_source_capture(self):
        old=Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp);source=Path('work/onecloud-pack/AmlImg-source');source.mkdir(parents=True)
                subprocess.run(['git','init','-b','fixture',str(source)],check=True,capture_output=True)
                (source/'code.txt').write_text('synthetic source');subprocess.run(['git','-C',str(source),'add','code.txt'],check=True,capture_output=True)
                subprocess.run(['git','-C',str(source),'-c','user.name=QA','-c','user.email=qa@example.invalid','commit','-m','synthetic'],check=True,capture_output=True)
                head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip();subprocess.run(['git','-C',str(source),'checkout','--detach',head],check=True,capture_output=True)
                subprocess.run(['git','-C',str(source),'branch','-D','fixture'],check=True,capture_output=True)
                self.assertFalse(any(p.is_file() for p in (source/'.git/refs').rglob('*')))
                # Synthetic Git objects are read-only on Windows. Only change
                # files inside this verified temporary fixture before cleanup.
                self.assertTrue(source.resolve().is_relative_to(Path(temp).resolve()))
                for path in source.rglob('*'):
                    if path.is_file() and not path.is_symlink():path.chmod(stat.S_IRUSR|stat.S_IWUSR)
                archive=Path('source.tar.gz');r.archive_tree([source],archive)
                with tarfile.open(archive) as tar:self.assertIn('work/onecloud-pack/AmlImg-source/.git/refs',tar.getnames())
                shutil.rmtree(source);r.inspect_tar(archive,extract=True)
                self.assertEqual(subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),head)
            finally:os.chdir(old)
    def test_bundle_roles_paths_and_integrity_are_bound(self):
        r.validate(manifest())
        for change in ['digest','escape','role','duplicate']:
            c=manifest()
            if change=='digest':c['assets'][0]['sha256']='f'*64
            elif change=='escape':c['assets'][0]['destination']='../../secret'
            elif change=='role':c['assets'][0]['destination']='work/rebuild-engine.tar.gz'
            else:c['assets'][1]=copy.deepcopy(c['assets'][0])
            with self.assertRaises(ConfigError):r.validate(c)

    def test_only_explicit_sources_are_eligible_never_generated_secrets(self):
        for name in ['scripts/build.py','work/box-repack/sources/firmware/.git/objects/file','overlays/private.zip']:
            self.assertTrue(r.allowed(name))
        for name in ['work/builder/personal-files/etc/shadow','work/builder/build_dir/rootfs/etc/config/network','.git/config','scripts/../../outside','C:\\secret','outputs/router.img']:
            self.assertFalse(r.allowed(name))

    def test_tar_member_traversal_symlinks_and_extra_payloads_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'test.tar.gz'
            for name,link in [('../secret',None),('scripts/link','../../outside'),('work/builder/etc/shadow',None),('scripts/link','/etc/shadow')]:
                with tarfile.open(path,'w:gz') as out:
                    m=tarfile.TarInfo(name)
                    if link:m.type=tarfile.SYMTYPE;m.linkname=link;out.addfile(m)
                    else:m.size=1;out.addfile(m,io.BytesIO(b'x'))
                with self.assertRaises(ConfigError):r.inspect_tar(path)

    def test_offline_repo_uses_archived_packages_only_and_regenerates_index(self):
        old=Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            try:
                os.chdir(temp);work=Path('work/builder');(work/'packages').mkdir(parents=True);cache=Path('work/rebuild-packages');cache.mkdir()
                (cache/'curl_1_all.ipk').write_bytes(b'original');(work/'packages/curl_1_all.ipk').write_bytes(b'new')
                (work/'packages/Packages.gz').write_bytes(b'old index');(work/'repositories.conf').write_text('src/gz upstream https://upstream.invalid/\n');(work/'repositories').write_text('https://upstream.invalid')
                (work/'.config').write_text('CONFIG_SIGNATURE_CHECK=y\nCONFIG_USE_APK=y\n');r.offline_packages(work)
                self.assertEqual((work/'packages/curl_1_all.ipk').read_bytes(),b'original');self.assertFalse((work/'packages/Packages.gz').exists())
                self.assertNotIn('https:',(work/'repositories.conf').read_text());self.assertEqual((work/'repositories').read_text(),'');self.assertNotIn('CONFIG_SIGNATURE_CHECK=y',(work/'.config').read_text())
            finally:os.chdir(old)

    def test_rebuild_rejects_changed_configuration_and_package_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            state=Path(temp)/'state.json';c={'packages':['curl']};m=manifest();m['config_sha256']=r.digest(c);r.write(state,{'manifest':m})
            with patch.object(r,'STATE',state):
                self.assertIsNotNone(r.context(c))
                with self.assertRaises(ConfigError):r.context({'packages':['wget']})
