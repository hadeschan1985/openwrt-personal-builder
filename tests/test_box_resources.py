import struct
import unittest
from scripts import box_resources as b

class BoxResourceTests(unittest.TestCase):
    def test_model_identity_and_device_tree_cannot_be_shell_or_path_input(self):
        row='101:N1:s905d:meson-gxl-s905d-phicomm-n1.dtb:u-boot-n1.bin:NA:u-boot-2015-phicomm-n1.bin:2GB:stable/all:amlogic:meson-gxl:uEnv.txt:upstream:s905d:yes'
        models=b.parse_models(row);self.assertEqual(models[0]['id'],'s905d');self.assertEqual(models[0]['dtb'],'meson-gxl-s905d-phicomm-n1.dtb')
        for bad in [row.replace(':s905d:yes',':$(run):yes'),row.replace('meson-gxl-s905d-phicomm-n1.dtb','../foreign.dtb'),row+'\n'+row]:
            with self.assertRaises(ValueError):b.parse_models(bad)

    def test_real_device_tree_root_compatible_is_read_without_executing_tools(self):
        value=b'phicomm,n1\0amlogic,s905d\0';value+=b'\0'*((-len(value))%4)
        structure=struct.pack('>I',1)+b'\0'*4+struct.pack('>III',3,len(value),0)+value+struct.pack('>II',2,9)
        strings=b'compatible\0';offset=40+len(structure);size=offset+len(strings)
        data=struct.pack('>10I',0xd00dfeed,size,40,offset,0,17,16,0,len(strings),len(structure))+structure+strings
        self.assertEqual(b.dtb_compatible(data),['phicomm,n1','amlogic,s905d'])
        with self.assertRaises(ValueError):b.dtb_compatible(b'\0'*len(data))
        with self.assertRaises(ValueError):b.dtb_compatible(data[:50])

    def test_only_fixed_primary_source_repositories_and_kernel_digests_are_accepted(self):
        source=b.source_config();self.assertEqual(len(source['repositories']),5);self.assertEqual(len(source['kernels']),3)
