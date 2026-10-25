import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import delivery as d, delivery_vm as vm
from scripts.build import normalize


def configuration():
    raw = json.loads(Path("configs/x86-default.json").read_text())
    raw["build_mode"] = "release"
    raw["system"]["password_secret"] = True
    return normalize(raw)


class DeliveryTests(unittest.TestCase):
    def test_release_requires_private_repository_and_strong_password_and_https(self):
        c = configuration()
        good = {"REPOSITORY_PRIVATE": "true", "ROUTER_PASSWORD": "test-only-password"}
        d.policy(c, good)
        for env in ({}, {**good, "REPOSITORY_PRIVATE": "false"}, {**good, "ROUTER_PASSWORD": "root"}, {**good, "ROUTER_PASSWORD": "a" * 12 + "\n"}):
            with self.assertRaises(ValueError):
                d.policy(c, env)
        c["system"]["https"] = False
        with self.assertRaises(ValueError):
            d.policy(c, good)

    def test_experiment_is_explicit_and_not_a_release_claim(self):
        c = configuration()
        c["build_mode"] = "experiment"
        d.policy(c, {})
        self.assertEqual(normalize({**c, "build_mode": "experiment"})["build_mode"], "experiment")

    def test_release_management_subnet_cannot_hang_isolated_verification(self):
        good = {"REPOSITORY_PRIVATE":"true", "ROUTER_PASSWORD":"test-only-password"}
        for address in ['127.0.0.1','224.0.0.1','0.0.0.0','192.168.1.0','192.168.1.255','192.168.1.1/32','10.0.0.1/0']:
            c=configuration();c['system']['ip']=address
            with self.assertRaises(ValueError):d.policy(c,good)
        c=configuration();c['system']['ip']='192.168.1.129/25';d.policy(c,good)

    def test_private_record_writer_preserves_base_and_never_forces_branch(self):
        from scripts import upstream
        value={'schema_version':1,'run_id':'123','run_number':'6','source_commit':'a'*40,'config':configuration(),'vm':{'status':'passed'},'files':[{'name':'disk-combined.img.gz','bytes':10,'sha256':'b'*64,'group':'legacy'}]}
        responses=[{'private':True},{'object':{'sha':'old-head'}},{'tree':{'sha':'existing-private-base'}},{'sha':'new-tree'},{'sha':'new-commit'},{}]
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'GH_TOKEN':'not-serialized','GITHUB_RUN_ID':'123','GITHUB_SHA':'a'*40}),patch.object(upstream,'api',side_effect=responses) as api:
            file=Path(folder)/'record.json';file.write_text(json.dumps(value));d.save_record(file)
            tree=api.call_args_list[3].args[3];self.assertEqual(tree['base_tree'],'existing-private-base');self.assertEqual(len(tree['tree']),1);self.assertEqual(tree['tree'][0]['path'],'records/123.json')
            self.assertNotIn('not-serialized',tree['tree'][0]['content']);self.assertFalse(api.call_args_list[-1].args[3]['force'])

    def test_nic_mapping_and_disk_modes_follow_actual_configuration(self):
        c = configuration()
        c["network"].update(wan_port="eth0", lan_ports="eth2 eth3")
        self.assertEqual(vm.topology(c), (4, 2))
        c["network"]["lan_ports"] = "eth9"
        with self.assertRaises(ValueError):
            vm.topology(c)
        c = configuration()
        c["output"]["vmdk"] = True
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name in ("a-combined-efi.img.gz", "a-combined.img.gz", "a-combined-efi.vmdk", "a-combined.vmdk"):
                (output / name).touch()
            self.assertEqual({mode for _, mode in vm.images(c, output)}, {"uefi", "bios", "vmdk-uefi", "vmdk-bios"})

    def test_password_never_appears_in_ssh_arguments(self):
        with patch.object(vm.subprocess, "run") as run:
            vm.ssh("test true", "never-in-argv")
        self.assertNotIn("never-in-argv", " ".join(run.call_args.args[0]))
        self.assertEqual(run.call_args.kwargs["env"]["SSHPASS"], "never-in-argv")

    def test_file_groups_are_deterministic(self):
        self.assertEqual(d.file_group("a-combined-efi.img.gz"), "efi")
        self.assertEqual(d.file_group("a-combined.img.gz"), "legacy")
        self.assertEqual(d.file_group("a-combined-efi.vmdk.zip"), "vmdk")
        self.assertEqual(d.file_group("a-rootfs.tar.gz"), "rootfs")
        self.assertEqual(d.file_group("SHA256SUMS"), "reports")

    def test_unverified_release_record_and_unsafe_filenames_rejected(self):
        c = configuration()
        value = {"schema_version": 1, "run_id": "123", "run_number": "6", "source_commit": "a" * 40,
                 "config": c, "vm": {"status": "passed"}, "files": [{"name": "a-combined.img.gz", "bytes": 10, "sha256": "b" * 64, "group": "legacy"}]}
        d.validate_record(value)
        value["vm"]["status"] = "failed"
        with self.assertRaises(ValueError):
            d.validate_record(value)
        value["vm"]["status"] = "passed"
        value["files"][0]["name"] = "../../unsafe"
        with self.assertRaises(ValueError):
            d.validate_record(value)


if __name__ == "__main__":
    unittest.main()
