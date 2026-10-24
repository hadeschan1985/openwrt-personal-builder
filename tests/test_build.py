import copy
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

from scripts.build import ConfigError, normalize, package_plan, defaults_script, extract_overlay, selected_images, has_private_content

ROOT = Path(__file__).resolve().parents[1]


def example():
    return json.loads((ROOT / "configs/x86-default.json").read_text())


class ConfigurationTests(unittest.TestCase):
    def test_default_config_and_package_plan(self):
        config = normalize(example())
        self.assertIn("luci-ssl", package_plan(config))
        self.assertFalse(has_private_content(config))

    def test_argument_and_package_injection_rejected(self):
        for key, value in [("profile", "generic;touch /tmp/pwn"), ("target", "../../etc"), ("version", "latest")]:
            config = example()
            config[key] = value
            with self.subTest(key=key), self.assertRaises(ConfigError):
                normalize(config)
        config = example()
        config["packages"] = ["foo $(id)"]
        with self.assertRaises(ConfigError):
            normalize(config)

    def test_cannot_remove_core_or_add_and_remove(self):
        config = example()
        config["remove_packages"] = ["base-files"]
        with self.assertRaises(ConfigError):
            normalize(config)
        config["remove_packages"] = ["luci-app-ddns"]
        with self.assertRaises(ConfigError):
            normalize(config)

    def test_boolean_strings_rejected(self):
        config = example()
        config["system"]["ipv6"] = "false"
        with self.assertRaises(ConfigError):
            normalize(config)

    def test_invalid_side_router_and_ports(self):
        config = example()
        config["network"].update(mode="side", gateway="10.0.0.1")
        with self.assertRaises(ConfigError):
            normalize(config)
        config["network"].update(gateway="192.168.1.254", wan_port="eth0", lan_ports="eth0 eth1")
        with self.assertRaises(ConfigError):
            normalize(config)

    def test_conflicting_firewall(self):
        config = example()
        config.update(firewall="iptables", proxies=["luci-app-nikki"])
        with self.assertRaises(ConfigError):
            normalize(config)

    def test_wifi_requires_password_and_rejects_open_hotspot(self):
        config = example()
        config["network"]["wifi_ssid"] = "Personal"
        with self.assertRaisesRegex(ConfigError, "open hotspots"):
            normalize(config)
        config["network"]["wifi_password_secret"] = True
        normalized = normalize(config)
        with self.assertRaisesRegex(ConfigError, "WIFI_PASSWORD"):
            defaults_script(normalized, {})
        script = defaults_script(normalized, {"WIFI_PASSWORD": "example-password"})
        self.assertIn("encryption=psk2", script)

    def test_shell_is_embedded_and_quoted(self):
        config = example()
        config["system"].update(signature="test' $(touch /tmp/unwanted)", password_secret=True)
        config["network"].update(wan_port="eth0", lan_ports="eth1", wifi_ssid="Test' $(false)", wifi_password_secret=True)
        config["defaults"] = "echo user-only"
        normalized = normalize(config)
        script = defaults_script(normalized, {"ROUTER_PASSWORD": "abc'$(false)", "WIFI_PASSWORD": "abcd'$(false)"})
        self.assertIn("'\"'\"'", script)
        self.assertIn("/tmp/unwanted", script)  # data remains in a quoted string
        self.assertIn("\\1/p", script)
        self.assertNotIn("\x01", script)
        self.assertIn("# User initialization", script)
        self.assertTrue(has_private_content(normalized))

    def test_secret_required_and_not_exported_in_configuration(self):
        config = example()
        config["system"]["password_secret"] = True
        normalized = normalize(config)
        with self.assertRaises(ConfigError):
            defaults_script(normalized, {})
        script = defaults_script(normalized, {"ROUTER_PASSWORD": "test-password"})
        self.assertIn("passwd root", script)
        self.assertNotIn("test-password", json.dumps(normalized))

    def test_output_filter_respects_filesystem_and_boot_mode(self):
        config = normalize(example())
        config["output"].update(legacy=False, rootfs=True)
        images = [
            {"name": "efi", "filesystem": "squashfs", "type": "combined-efi"},
            {"name": "legacy", "filesystem": "squashfs", "type": "combined"},
            {"name": "ext4", "filesystem": "ext4", "type": "combined-efi"},
            {"name": "rootfs", "filesystem": "targz", "type": "rootfs"},
        ]
        self.assertEqual([i["name"] for i in selected_images(images, config)], ["efi", "rootfs"])

    def test_unconfigured_kwrt_features_rejected(self):
        config = example()
        config["features"]["istoreos"] = True
        with self.assertRaises(ConfigError):
            normalize(config)


class OverlayTests(unittest.TestCase):
    def test_normal_zip_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "input.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("etc/test.conf", "hello")
            extract_overlay(archive, root / "files")
            self.assertEqual((root / "files/etc/test.conf").read_text(), "hello")

    def test_zip_traversal(self):
        for path in ["../outside", "/etc/shadow", "..\\outside", "C:/outside"]:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                archive = root / "input.zip"
                with zipfile.ZipFile(archive, "w") as output:
                    output.writestr(path, "no")
                with self.assertRaises(ConfigError):
                    extract_overlay(archive, root / "files")

    def test_tar_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "input.tgz"
            with tarfile.open(archive, "w:gz") as output:
                info = tarfile.TarInfo("escape")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc"
                output.addfile(info)
            with self.assertRaises(ConfigError):
                extract_overlay(archive, root / "files")

    def test_unimplemented_package_install_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "input.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("custom.ipk", "not a real package")
            with self.assertRaises(ConfigError):
                extract_overlay(archive, root / "files")


if __name__ == "__main__":
    unittest.main()
