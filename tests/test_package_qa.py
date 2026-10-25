import json
from pathlib import Path
import unittest

from scripts.build import ConfigError, package_plan
from scripts.package_qa import CASES, scenario
from scripts.smoke import package_checks, theme_path


class PackageQATests(unittest.TestCase):
    def test_all_nine_combinations_pass_index_and_schema_preflight(self):
        cases = json.loads(CASES.read_text())
        self.assertEqual(len(cases), 9)
        for name in cases:
            with self.subTest(name=name):
                config = scenario(name)
                self.assertTrue(config["output"]["legacy"])
                self.assertFalse(config["output"]["vmdk"])
                self.assertTrue(package_plan(config))

    def test_guest_database_assertions_include_both_package_managers_and_removals(self):
        script = package_checks({"packages": ["luci-app-ddns"], "remove_packages": ["nano"]})
        self.assertIn("apk info -e luci-app-ddns", script)
        self.assertIn("opkg status luci-app-ddns", script)
        self.assertIn("then exit 81", script)
        with self.assertRaises(ConfigError):
            package_checks({"packages": ["hello; false"]})

    def test_theme_aliases_match_actual_paths(self):
        self.assertEqual(theme_path("argon-light"), "/luci-static/argon")
        self.assertEqual(theme_path("openwrt-2020"), "/luci-static/openwrt2020")


if __name__ == "__main__":
    unittest.main()
