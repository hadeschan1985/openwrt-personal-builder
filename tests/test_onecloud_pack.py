import os
import gzip
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from scripts.build import ConfigError
from scripts.onecloud_pack import partitions,restore_native_recipe,clean_env,native_disk


class OneCloudPackTests(unittest.TestCase):
    def test_partition_bounds_and_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'disk.img';header=bytearray(512);header[510:]=b'\x55\xaa'
            for n,(kind,start,size) in enumerate([(0xc,2048,2048),(0x83,4096,2048)]):
                header[450+n*16]=kind;struct.pack_into('<II',header,454+n*16,start,size)
            with path.open('wb') as out:out.write(header);out.truncate(3*1024**2)
            self.assertEqual([x['name'] for x in partitions(path)],['boot','rootfs'])
            struct.pack_into('<I',header,470,3000)
            with path.open('r+b') as out:out.write(header)
            with self.assertRaises(ConfigError):partitions(path)

    def test_compressed_publisher_output_is_not_delivered_as_burn(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);directory=root/'bin';directory.mkdir();work=root/'packing'
            header=bytearray(3*1024**2);header[510:512]=b'\x55\xaa'
            for n,(kind,start,size) in enumerate([(0xc,2048,2048),(0x83,4096,2048)]):
                header[450+n*16]=kind;struct.pack_into('<II',header,454+n*16,start,size)
            (directory/'native.img.gz').write_bytes(gzip.compress(header))
            raw=native_disk(root,directory,'native.img',work)
            self.assertEqual(raw.read_bytes(),header)
            self.assertEqual(len(partitions(raw)),2)

    def test_only_known_host_hook_is_removed(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'target/linux/amlogic/image/meson8b.mk';path.parent.mkdir(parents=True)
            source='define Build/run-host-script\n cd /data/packit/openwrt-onecloud; . ~/packit/packit_onecloud1.sh || true\nendef\nIMAGE := boot-script onecloud | emmc-common $$(DEVICE_NAME) | run-host-script\n'
            path.write_text(source);restore_native_recipe(Path(temp))
            self.assertNotIn('run-host-script',path.read_text());self.assertIn('emmc-common',path.read_text())
            with self.assertRaises(ConfigError):restore_native_recipe(Path(temp))
            path.write_text(source.replace('Build/run-host-script','Image/Build').replace(' | run-host-script',''))
            restore_native_recipe(Path(temp));self.assertNotIn('Image/Build',path.read_text())

    def test_host_tool_never_receives_tokens_or_router_secrets(self):
        with patch.dict(os.environ,{'GH_TOKEN':'hidden','GITHUB_TOKEN':'hidden','ROUTER_PASSWORD':'hidden','ACTIONS_ID_TOKEN_REQUEST_TOKEN':'hidden','CONFIG_JSON':'private'}):
            env=clean_env()
        for key in ('GH_TOKEN','GITHUB_TOKEN','ROUTER_PASSWORD','ACTIONS_ID_TOKEN_REQUEST_TOKEN','CONFIG_JSON'):self.assertNotIn(key,env)
