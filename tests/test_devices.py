import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import struct
import zlib
import unittest
from unittest.mock import patch

from scripts import builders,build,delivery,image_verify
from scripts.platform_qa import output_options

class DeviceTests(unittest.TestCase):
    def config(self):
        raw=json.loads(Path('configs/x86-default.json').read_text())
        raw.update(builder='kwrt',version='kwrt-25.12-20261012',target='mediatek/filogic',profile='xiaomi_redmi-router-ax6000',build_mode='device')
        raw['system'].update(password_secret=True,password_source='root')
        raw['output'].update(efi=False,legacy=False,image_types=['sysupgrade'])
        return build.normalize(raw)

    def test_all_platforms_are_individually_pinned_and_host_restricted(self):
        family=json.loads(builders.REGISTRY.read_text(encoding='utf-8'))['kwrt-25.12-20261012']
        pins=list(builders.platforms(family));self.assertEqual(len(pins),24)
        for target,pin in pins:
            self.assertEqual(builders.resolve('kwrt-25.12-20261012',target),pin)
            bad=copy.deepcopy(pin);bad['base']='https://example.com/'+target
            with self.assertRaises(ValueError):builders.validate_spec(bad)

    def test_root_password_is_explicit_and_does_not_require_or_overwrite_a_secret(self):
        c=self.config();env={'REPOSITORY_PRIVATE':'true','ROUTER_PASSWORD':'different-existing-secret'}
        delivery.policy(c,env);self.assertEqual(build.router_password(c,env),'root');self.assertEqual(env['ROUTER_PASSWORD'],'different-existing-secret')
        c['system']['password_source']='secret'
        with self.assertRaises(ValueError):delivery.policy(c,{'REPOSITORY_PRIVATE':'true','ROUTER_PASSWORD':'root'})

    def test_no_password_or_public_device_delivery_is_rejected(self):
        for field,value in [('password_secret',False),('https',False)]:
            c=self.config();c['system'][field]=value
            with self.assertRaises(ValueError):delivery.policy(c,{'REPOSITORY_PRIVATE':'true'})
        with self.assertRaises(ValueError):delivery.policy(self.config(),{'REPOSITORY_PRIVATE':'false'})

    def test_device_format_priority_excludes_auxiliary_bootloaders(self):
        images=[{'name':'loader.fip','filesystem':'','type':'bl31-uboot.fip'},{'name':'factory.bin','filesystem':'squashfs','type':'factory'},{'name':'sysupgrade.bin','filesystem':'squashfs','type':'sysupgrade'}]
        self.assertEqual(output_options(images),('squashfs',['sysupgrade']))
        c=self.config();self.assertEqual([i['name'] for i in build.selected_images(images,c)],['sysupgrade.bin'])

    def test_onecloud_ext4_and_nonstandard_types_can_be_selected(self):
        c=self.config();c['output'].update(filesystem='ext4',image_types=['emmc_burn'])
        images=[{'name':'one.img','filesystem':'ext4','type':'emmc_burn'}]
        self.assertEqual(build.selected_images(images,c),images)
        self.assertEqual(builders.resolve(c['version'],'amlogic/meson8b')['profiles_file'],'profiles.json.b')

    def test_each_device_file_gets_its_own_artifact_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);files=[]
            for name in ['factory.bin','sysupgrade.bin','emmc.img']:
                (root/name).write_bytes(b'firmware');files.append({'name':name,'group':delivery.file_group(name)})
            groups=delivery.prepare_downloads(files,root,root/'separate')
            self.assertEqual(groups,['device-01','device-02','device-03'])
            self.assertTrue(all(len(list((root/'separate'/g).iterdir()))==1 for g in groups))

    def test_container_validation_does_not_claim_device_boot(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);c=self.config();data=gzip.compress(b'firmware')
            (root/'sysupgrade.img.gz').write_bytes(data)
            summary={k:c[k] for k in ['version','target','profile','builder']}
            summary.update(dependency_preflight={'status':'passed'},files=[{'name':'sysupgrade.img.gz','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}])
            (root/'build-summary.json').write_text(json.dumps(summary))
            report=image_verify.verify(c,root);self.assertFalse(report['boot_tested']);self.assertFalse(report['hardware_tested']);self.assertEqual(report['status'],'passed')
            summary['files'][0]['name']='../outside';(root/'build-summary.json').write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError,'Unsafe'):image_verify.verify(c,root)

    def test_tampered_device_container_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);c=self.config();data=gzip.compress(b'firmware')[:-3]
            (root/'image.img.gz').write_bytes(data)
            summary={k:c[k] for k in ['version','target','profile','builder']}
            summary.update(dependency_preflight={'status':'passed'},files=[{'name':'image.img.gz','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}])
            (root/'build-summary.json').write_text(json.dumps(summary))
            with self.assertRaises((EOFError,OSError,ValueError)):image_verify.verify(c,root)

    def test_box_image_requires_matching_model_kernel_and_file_proof(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);c=self.config();c.update(target='armsr/armv8',profile='box',box={'model':'s905d','kernel':'stable-6.12.114'})
            data=gzip.compress(b'fixture');name='personal-box-s905d-6.12.114.img.gz';(root/name).write_bytes(data)
            item={'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            summary={k:c[k] for k in ['version','target','profile','builder']};summary.update(dependency_preflight={'status':'passed'},files=[item]);(root/'build-summary.json').write_text(json.dumps(summary))
            with self.assertRaises(FileNotFoundError):image_verify.verify(c,root)
            proof={'status':'passed','model':'s905d','kernel':'stable-6.12.114','filesystem':'btrfs','module_vermagic_checked':20,'boot_tested':False,'hardware_tested':False,'file':item}
            path=root/'box-pack-report.json';path.write_text(json.dumps(proof));self.assertEqual(image_verify.verify(c,root)['box_packaging']['kernel'],c['box']['kernel'])
            proof['file']={**item,'sha256':'0'*64};path.write_text(json.dumps(proof))
            with self.assertRaisesRegex(ValueError,'different image'):image_verify.verify(c,root)

    def test_onecloud_output_cannot_skip_partition_roundtrip_proof(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);c=self.config();c.update(target='amlogic/meson8b',profile='thunder-onecloud')
            data=gzip.compress(b'fixture');name='kwrt-onecloud-ext4-emmc_burn.img.gz';(root/name).write_bytes(data)
            item={'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            summary={k:c[k] for k in ['version','target','profile','builder']};summary.update(dependency_preflight={'status':'passed'},files=[item]);(root/'build-summary.json').write_text(json.dumps(summary))
            proof={'status':'passed','container_crc':'verified-by-AmlImg','hardware_tested':False,'partitions':[{'name':'boot','roundtrip':'identical'},{'name':'rootfs','roundtrip':'changed'}],'file':item};(root/'onecloud-pack-report.json').write_text(json.dumps(proof))
            with self.assertRaisesRegex(ValueError,'partition verification'):image_verify.verify(c,root)

    def test_gzip_with_openwrt_metadata_checks_both_crcs_and_rejects_unknown_tails(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'sysupgrade.img.gz'
            prefix=gzip.compress(b'firmware')+bytes(8)+b'{"supported_devices":["test"]}'
            size=len(bytes(8)+b'{"supported_devices":["test"]}')+16
            trailer=struct.pack('>IIB3xI',0x46577830,zlib.crc32(prefix)^0xffffffff,1,size)
            path.write_bytes(prefix+trailer);self.assertEqual(image_verify.gzip_image(path),'gzip-crc-and-fwtool-checked')
            path.write_bytes(prefix[:-1]+b'x'+trailer)
            with self.assertRaisesRegex(ValueError,'CRC'):image_verify.gzip_image(path)
            path.write_bytes(gzip.compress(b'firmware')+b'unrecognized')
            with self.assertRaises(ValueError):image_verify.gzip_image(path)
