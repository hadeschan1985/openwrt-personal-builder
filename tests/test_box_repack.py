import json
from pathlib import Path
import unittest
import tempfile

from scripts.build import ConfigError,normalize
from scripts.box_repack import selection,patched_recipe,restore_rootfs_recipe,READONLY_OPTIONS
from scripts.box_resources import source_config,git_blob

ROOT=Path(__file__).resolve().parents[1]


def example():
    c=json.loads((ROOT/'configs/x86-default.json').read_text());c.update(builder='kwrt',version='kwrt-25.12-20261012',target='armsr/armv8',profile='box',build_mode='device',box={'model':'s905d','kernel':'stable-6.12.114'})
    c['output'].update(efi=False,legacy=False,vmdk=False,rootfs=True,image_types=[])
    return c


class BoxRepackTests(unittest.TestCase):
    def test_readonly_validation_preserves_checksums_and_never_replays_logs(self):
        self.assertEqual(READONLY_OPTIONS['btrfs'],'ro,rescue=nologreplay')
        self.assertEqual(READONLY_OPTIONS['ext4'],'ro,noload')
    def test_fixed_selection_and_native_kernel_rejection(self):
        c=normalize(example());m,k,_=selection(c);self.assertEqual(m['dtb'],'meson-gxl-s905d-phicomm-n1.dtb');self.assertEqual(k['release'],'6.12.114-ophub')
        for change in [{'model':'s905d;echo unsafe','kernel':'stable-6.12.114'},{'model':'s905d','kernel':'https://example.com/kernel'},{'model':'s905d','kernel':'stable-6.12.114','dtb':'other.dtb'}]:
            c=example();c['box']=change
            with self.assertRaises(ConfigError):normalize(c)
        c=example();c['features']['usb_net']=True
        with self.assertRaisesRegex(ConfigError,'drivers'):normalize(c)
        c=example();c['packages']=['kmod-usb-net-rtl8152']
        with self.assertRaisesRegex(ConfigError,'kernel packages'):normalize(c)

    def test_other_profiles_cannot_replace_kernel(self):
        c=example();c['profile']='generic'
        with self.assertRaisesRegex(ConfigError,'generic ARM64 box'):normalize(c)

    def test_recipe_requires_exact_source_before_patch(self):
        with self.assertRaisesRegex(ConfigError,'fixed source'):patched_recipe('find_openwrt() {\nsource user-file\n}\n',source_config())

    def test_patched_packer_never_sources_firmware_or_downloads_latest(self):
        source='find_openwrt() {\n source "${temp_dir}/${source_release_file}"\n}\ngit_pull_dir() {\n git clone latest\n}\ndownload_kernel() {\n curl latest\n}\n'
        result=patched_recipe(source,{'remake_blob':git_blob(source.encode())})
        self.assertNotIn('source "${temp_dir}',result);self.assertNotIn('git clone',result);self.assertNotIn('curl latest',result)
        self.assertIn('BOX_SOURCE_ROOT',result);self.assertIn('personal-rootfs.tar.gz',result)

    def test_box_rootfs_generation_removes_only_known_server_hook(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'target/linux/armsr/image/Makefile';path.parent.mkdir(parents=True)
            path.write_text('define Device/box\n DEVICE_TITLE := box\nendef\ndefine Image/Build\n if [ "$(PROFILE_SANITIZED)" == "box" ]; then cd /data/packit/amlogic-s9xxx-openwrt; . ~/packit/packit_amlogic.sh; fi\nendef\n')
            restore_rootfs_recipe(Path(temp));self.assertNotIn('Image/Build',path.read_text());self.assertIn('Device/box',path.read_text())
            with self.assertRaises(ConfigError):restore_rootfs_recipe(Path(temp))
