"""Exercise orchestration and provenance without running third-party binaries."""
import contextlib
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import tarfile

from scripts.build import build, normalize, package_plan, REGISTRY


class PipelineTests(unittest.TestCase):
    def test_official_and_kwrt_complete_pipeline_writes_consistent_summary(self):
        template = json.loads((REGISTRY.parent / "x86-default.json").read_text())
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        for builder in ("official", "kwrt"):
            with self.subTest(builder=builder), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                raw = dict(template, builder=builder)
                if builder == "kwrt":
                    raw["version"] = "kwrt-25.12-20261012"
                config = normalize(raw)
                archive_name = (registry[raw["version"]]["archive"] if builder == "kwrt" else
                    "openwrt-imagebuilder-25.12.6-x86-64.Linux-x86_64.tar.zst")
                digest = registry[raw["version"]]["sha256"] if builder == "kwrt" else "a" * 64
                images = [{"name": "fixture-squashfs-combined.img.gz", "filesystem": "squashfs", "type": "combined"},
                    {"name": "fixture-squashfs-combined-efi.img.gz", "filesystem": "squashfs", "type": "combined-efi"},
                    {"name": "fixture-targz-rootfs.tar.gz", "filesystem": "targz", "type": "rootfs"}]
                metadata = {"profiles": {"generic": {"images": images}}}
                def download(url, destination):
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(digest + "  " + archive_name if destination.name == "sha256sums" else "test archive")
                def run(command, **kwargs):
                    self.assertEqual(command[0], "tar")
                    extracted = root / "work/extracted/fixture-builder"
                    extracted.mkdir(parents=True)
                    (extracted / "Makefile").write_text("\t$(OPKG) install --force-maintainer $(BUILD_PACKAGES) luci-i18n-base-zh-cn || true\n")
                    (extracted / "repositories.conf").write_text("src base file://www/wwwroot/dl.openwrt.ai/releases/25.12/packages/x86_64/base\nsrc imagebuilder file:packages\n")
                    (extracted / "packages").mkdir()
                class Process:
                    stdout = ["Synthetic ImageBuilder output\n"]
                    @staticmethod
                    def wait():
                        return 0
                def popen(command, cwd, **kwargs):
                    self.assertEqual(command[:2], ["make", "image"])
                    target = cwd / "bin/targets/x86/64"
                    target.mkdir(parents=True)
                    (target / "profiles.json").write_text(json.dumps(metadata))
                    for image in images[:2]:
                        (target / image["name"]).write_bytes(gzip.compress(b"fixture disk"))
                    with tarfile.open(target / images[2]["name"], "w:gz") as archive:
                        item = tarfile.TarInfo("./usr/lib/lua/luci/i18n/base.zh-cn.lmo")
                        item.size = 1
                        archive.addfile(item, io.BytesIO(b"x"))
                    (target / "fixture.manifest").write_text("\n".join(p + " - fixture" for p in package_plan(config) if not p.startswith("-")))
                    return Process()
                def checksum(path):
                    return digest if path.name == archive_name else hashlib.sha256(path.read_bytes()).hexdigest()
                with patch("scripts.build.sys.platform", "linux"), patch("scripts.build.get_json", return_value=metadata), \
                     patch("scripts.build.download", side_effect=download), patch("scripts.build.sha256", side_effect=checksum), \
                     patch("scripts.build.subprocess.run", side_effect=run), patch("scripts.build.subprocess.Popen", side_effect=popen), \
                     patch.dict("os.environ", {"REPOSITORY_PRIVATE": "true"}), contextlib.redirect_stdout(io.StringIO()):
                    build(config, root)
                summary = json.loads((root / "outputs/build-summary.json").read_text())
                self.assertEqual(summary["builder_sha256"], digest)
                self.assertEqual(summary["builder"], builder)
                self.assertEqual(len(list((root / "outputs").glob("*.img.gz"))), 2)
                for line in (root / "outputs/SHA256SUMS").read_text().splitlines():
                    expected, name = line.split("  ")
                    self.assertEqual(checksum(root / "outputs" / name), expected)


if __name__ == "__main__":
    unittest.main()
