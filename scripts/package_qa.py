"""Bounded, isolated package-combination regression; no subscription or user secrets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from scripts import smoke
from scripts.build import normalize, package_plan, require

CASES = Path(__file__).resolve().parents[1] / "configs/package-qa.json"


def scenario(name):
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    require(name in cases, "Unknown package QA scenario")
    spec = cases[name]
    source = spec["source"]
    raw = json.loads((CASES.parent / "x86-default.json").read_text())
    raw.update(builder=source, packages=spec.get("packages", []), proxies=spec.get("proxies", []),
        remove_packages=spec.get("remove_packages", []))
    raw["system"]["default_theme"] = spec.get("theme", "argon" if source == "kwrt" else "bootstrap")
    raw["themes"] = sorted({"luci-theme-bootstrap", "luci-theme-" + re.sub(r"^(argon|bootstrap)-(?:light|dark)$", r"\1", raw["system"]["default_theme"])})
    if source == "kwrt":
        raw["version"] = "kwrt-25.12-20261012"
        raw["features"].update(istoreos=True, routerdog=True)
        raw["system"]["theme_mode"] = "nas"
    raw["output"].update(efi=False, legacy=True, vmdk=False, rootfs=False,
        rootfs_size_mb=768, filesystem=spec.get("filesystem", "squashfs"))
    config = normalize(raw)
    # Local indexed preflight; the build still resolves against its actual feed.
    metadata = CASES.parent.parent / "site/data/targets" / config["version"] / (config["target"] + ".json")
    available = set(json.loads(metadata.read_text(encoding="utf-8"))["packages"])
    require(all(p in available for p in package_plan(config) if not p.startswith("-")), "QA scenario contains unavailable package")
    return config


def prepare(name):
    config = scenario(name)
    smoke.prepare(config["builder"], "package-combination")
    prepared = json.loads((smoke.QA / "config.json").read_text())
    for field in ("packages", "proxies", "themes", "remove_packages", "output"):
        prepared[field] = config[field]
    prepared["system"]["default_theme"] = config["system"]["default_theme"]
    prepared = normalize(prepared)
    for path in (smoke.QA / "config.json", Path("configs/qa-generated.json")):
        path.write_text(json.dumps(prepared), encoding="utf-8")
    spec = {"name": name, "packages": sorted(set(prepared["packages"] + prepared["proxies"] + prepared["themes"])),
        "remove_packages": prepared["remove_packages"]}
    (smoke.QA / "package-spec.json").write_text(json.dumps(spec), encoding="utf-8")
    print("Prepared package combination:", name, "explicit package count:", len(spec["packages"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "plan"])
    parser.add_argument("--case", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.case)
    else:
        print(json.dumps(scenario(args.case), indent=2))
