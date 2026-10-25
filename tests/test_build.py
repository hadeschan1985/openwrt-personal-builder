import copy
import io
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile

from scripts.build import ConfigError, normalize, package_plan, defaults_script, extract_overlay, selected_images, has_private_content, prepare_kwrt, translation_alias, prepare_custom_ipks

ROOT = Path(__file__).resolve().parents[1]


def example():
    return json.loads((ROOT / "configs/x86-default.json").read_text())


class ConfigurationTests(unittest.TestCase):
    def test_firewall_checks_custom_package_box_and_homeproxy_pro(self):
        for field in ("packages", "proxies"):
            for package in ("luci-app-homeproxy", "luci-app-homeproxy-pro", "luci-app-nikki"):
                config = example()
                config.update(builder="kwrt", version="kwrt-25.12-20261012", firewall="iptables")
                config[field] = [package]
                with self.subTest(field=field, package=package), self.assertRaisesRegex(ConfigError, "requires nftables"):
                    normalize(config)

    def test_theme_or_proxy_cannot_also_be_removed(self):
        for field, package in (("themes", "luci-theme-bootstrap"), ("proxies", "luci-app-passwall2")):
            config = example()
            config[field] = [package]
            config["remove_packages"] = [package]
            with self.subTest(field=field), self.assertRaisesRegex(ConfigError, "both added and removed"):
                normalize(config)

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

    def test_eth0_wan_automatically_uses_another_lan_port(self):
        config = example()
        config["network"].update(wan_port="eth0", lan_ports="")
        self.assertEqual(normalize(config)["network"]["lan_ports"], "eth1")
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

    def test_kwrt_builder_is_pinned_and_cannot_cross_targets(self):
        config = example()
        config.update(builder="kwrt", version="kwrt-25.12-20261012")
        self.assertEqual(normalize(config)["builder"], "kwrt")
        for key, value in [("version", "kwrt-latest"), ("target", "mediatek/filogic")]:
            bad = copy.deepcopy(config)
            bad[key] = value
            with self.assertRaises(ConfigError):
                normalize(bad)

    def test_kwrt_repositories_are_relocated_and_install_failure_not_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "repositories.conf").write_text("src base file://www/wwwroot/dl.openwrt.ai/releases/25.12/packages/x86_64/base\nsrc imagebuilder file:packages\n")
            (root / "Makefile").write_text("\t$(OPKG) install --force-maintainer $(BUILD_PACKAGES) luci-i18n-base-zh-cn || true\n")
            prepare_kwrt(root)
            self.assertIn("https://dl.openwrt.ai/releases/", (root / "repositories.conf").read_text())
            self.assertNotIn("|| true", (root / "Makefile").read_text())

    def test_kwrt_native_vmdk_is_not_selected_as_raw_disk(self):
        config = normalize(example())
        images = [{"name": "kwrt-squashfs-combined.img.gz", "filesystem": "squashfs", "type": "combined"},
                  {"name": "kwrt-squashfs-combined.vmdk.zip", "filesystem": "squashfs", "type": "combined"}]
        self.assertEqual(len(selected_images(images, config)), 1)

    def test_https_toggle_is_explicit_in_both_directions(self):
        config = normalize(example())
        self.assertIn("redirect_https=1", defaults_script(config))
        config["system"]["https"] = False
        self.assertIn("redirect_https=0", defaults_script(config))

    def test_lighttpd_uses_authenticated_luci_cgi_rpc_and_device_generated_key(self):
        config = example()
        config.update(builder="kwrt", version="kwrt-25.12-20261012")
        config["system"]["webserver"] = "lighttpd"
        script = defaults_script(normalize(config))
        self.assertIn("luci.main.ubuspath=/cgi-bin/luci/admin/ubus", script)
        self.assertIn("openssl req -x509", script)
        self.assertIn("openssl-util", package_plan(normalize(config)))

    def test_kwrt_landing_page_requires_its_package(self):
        config = example()
        config.update(builder="kwrt", version="kwrt-25.12-20261012")
        config["system"]["theme_mode"] = "routerdog"
        with self.assertRaises(ConfigError):
            normalize(config)
        config["features"]["routerdog"] = True
        normalized = normalize(config)
        self.assertIn("luci-app-routerdog", package_plan(normalized))
        self.assertIn("luci.main.landing_page=routerdog", defaults_script(normalized))

    def test_kwrt_broken_factory_defaults_are_explicitly_replaced(self):
        config = example()
        config.update(builder="kwrt", version="kwrt-25.12-20261012")
        plan = package_plan(normalize(config))
        self.assertIn("-kmod-i40evf", plan)
        self.assertIn("kmod-iavf", plan)
        self.assertIn("kmod-usb-net-rtl8152", plan)


class OverlayTests(unittest.TestCase):
    def test_custom_ipk_is_staged_for_device_install_not_executed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            translation_alias(root, "personal-test-addon", "luci-base")
            packages, dependencies = prepare_custom_ipks(root)
            self.assertEqual(packages[0]["name"], "personal-test-addon")
            self.assertEqual(packages[0]["installation"], "first-boot-on-device")
            self.assertIn("luci-base", dependencies)
            self.assertTrue((root / "etc/uci-defaults/98-personal-packages").is_file())
            self.assertEqual(len(list((root / "root/personal-packages").glob("*.ipk.payload"))), 1)

    @unittest.skipUnless(shutil.which("7zz") or shutil.which("7z"), "7-Zip is verified on the Linux runner")
    def test_normal_7z_overlay(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "marker.txt").write_text("hello seven")
            seven = shutil.which("7zz") or shutil.which("7z")
            subprocess.run([seven, "a", str(root / "input.7z"), "marker.txt"], cwd=root, check=True, capture_output=True)
            extract_overlay(root / "input.7z", root / "files")
            self.assertEqual((root / "files/marker.txt").read_text(), "hello seven")

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
