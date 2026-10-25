"""Detect, test and atomically approve upstream DATA, never merge upstream code.

The candidate/QA jobs have read-only tokens. Only the separate publisher gets
Contents write; it neither downloads nor executes upstream builders.
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request

from scripts import catalog
from scripts.build import require

ROOT = Path(__file__).resolve().parents[1]
APPROVED = "updates/approved.json"
REGISTRY = "configs/builders.json"
KWRT_BASE = "https://dl.openwrt.ai/releases/targets/x86/64"
KWRT_ARCHIVE = "kwrt-imagebuilder-x86-64.Linux-x86_64.tar.zst"
SHA = re.compile(r"[a-f0-9]{64}")
OFFICIAL_VERSION = re.compile(r"\d{2}\.\d{2}\.\d+")
KWRT_VERSION = re.compile(r"kwrt-25\.12-\d{8}(?:-[a-f0-9]{8})?")
LIMIT = 4 * 1024 * 1024


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_json(path):
    require(path.stat().st_size <= LIMIT, "Upstream data exceeds size limit")
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(value), encoding="utf-8")


def builder_checksum(base, archive):
    request = urllib.request.Request(base + "/sha256sums", headers={"User-Agent": "OpenWrt-Personal-Builder/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read(1024 * 1024).decode()
    matches = [line.split()[0] for line in text.splitlines()
               if len(line.split()) == 2 and line.split()[1].lstrip("*") == archive]
    require(len(matches) == 1 and SHA.fullmatch(matches[0]), "Missing unique builder SHA256")
    return matches[0]


def validate_candidate(candidate):
    require(candidate.get("schema_version") == 1, "Unsupported upstream schema")
    sources, registry = candidate.get("sources"), candidate.get("registry")
    require(isinstance(sources, list) and [s.get("source") for s in sources] == ["official", "kwrt"], "Unexpected upstream sources")
    require(isinstance(registry, dict) and 1 <= len(registry) <= 512, "Invalid or oversized registry; archive old pins before adding more")
    for version, spec in registry.items():
        require(KWRT_VERSION.fullmatch(version), "Unexpected Kwrt release family")
        require(spec["target"] == "x86/64" and spec["base"] == KWRT_BASE and spec["archive"] == KWRT_ARCHIVE, "Untrusted builder location")
        require(SHA.fullmatch(spec["sha256"]), "Invalid builder digest")
        require(spec["feeds"] == "https://dl.openwrt.ai/releases/25.12/packages/x86_64", "Unexpected Kwrt feeds")
        require(re.fullmatch(r"https://dl\.openwrt\.ai/releases/25\.12/targets/x86/64/\d+\.\d+\.\d+", spec["kernel_feed"]), "Unexpected kernel feed")
        require(spec["exclude_defaults"] == ["kmod-i40evf", "kmod-usb-net-rtl8152-vendor", "luci-app-fan"]
                and spec["replacement_packages"] == ["kmod-iavf", "kmod-usb-net-rtl8152"], "Unexpected compatibility policy")
    for source in sources:
        name, version, metadata = source["source"], source["version"], source["metadata"]
        require((OFFICIAL_VERSION if name == "official" else KWRT_VERSION).fullmatch(version), "Unpinned upstream version")
        require(SHA.fullmatch(source["builder_sha256"]), "Invalid builder checksum")
        require(metadata["profiles"]["target"] == "x86/64" and metadata["profiles"]["arch_packages"] == "x86_64", "Upstream target mismatch")
        require("generic" in metadata["profiles"]["profiles"], "Missing generic profile")
        require(not metadata.get("package_metadata_errors") and len(metadata.get("packages", [])) > 100, "Incomplete package index")
        require(all(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+_.-]{0,120}", p) for p in metadata["packages"]), "Invalid package names")
        if name == "kwrt":
            require(version in registry and source["builder_sha256"] == registry[version]["sha256"], "Registry checksum mismatch")
    require(candidate.get("fingerprint") == digest({"sources": sources, "registry": registry}), "Candidate fingerprint mismatch")
    require(len(canonical(candidate).encode()) <= LIMIT, "Candidate too large")
    return candidate


def discover(registry):
    stable = catalog.get_json(catalog.DOWNLOADS + "/.versions.json")["stable_version"]
    require(OFFICIAL_VERSION.fullmatch(stable), "Stable version is not a final release")
    official = catalog.target_data(stable, "x86/64")
    base = f"{catalog.DOWNLOADS}/releases/{stable}/targets/x86/64"
    archive = f"openwrt-imagebuilder-{stable}-x86-64.Linux-x86_64.tar.zst"
    official_sha = builder_checksum(base, archive)
    profiles = catalog.get_json(KWRT_BASE + "/profiles.json")
    require(profiles["version_number"] == "25.12-SNAPSHOT", "New Kwrt release family requires compatibility review")
    kernel = profiles["linux_kernel"]["version"]
    require(re.fullmatch(r"\d+\.\d+\.\d+", kernel), "Invalid kernel version")
    kwrt_sha = builder_checksum(KWRT_BASE, KWRT_ARCHIVE)
    # Reuse an existing pinned ID; different bytes on the same date get a new ID.
    existing = next((v for v, s in registry.items() if s["sha256"] == kwrt_sha), None)
    date = dt.datetime.fromtimestamp(profiles["source_date_epoch"], dt.timezone.utc).strftime("%Y%m%d")
    version = existing or f"kwrt-25.12-{date}-{kwrt_sha[:8]}"
    spec = copy.deepcopy(next(iter(registry.values())))
    spec.update(label=f"Kwrt 25.12 · {date} · {kwrt_sha[:8]}（自动验证）", sha256=kwrt_sha,
                kernel_feed=f"https://dl.openwrt.ai/releases/25.12/targets/x86/64/{kernel}")
    if existing:
        spec["label"] = registry[existing]["label"]
    registry = {**registry, version: spec}
    sources = [
        {"source": "official", "version": stable, "label": f"OpenWrt {stable}（自动验证）", "builder_sha256": official_sha, "metadata": official},
        {"source": "kwrt", "version": version, "label": spec["label"], "builder_sha256": kwrt_sha, "metadata": catalog.kwrt_data(spec)},
    ]
    result = {"schema_version": 1, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "sources": sources, "registry": registry}
    result["fingerprint"] = digest({"sources": sources, "registry": registry})
    return validate_candidate(result)


def detect(destination):
    candidate = discover(read_json(ROOT / REGISTRY))
    previous = read_json(ROOT / APPROVED) if (ROOT / APPROVED).exists() else {}
    changed = previous.get("fingerprint") != candidate["fingerprint"]
    write_json(destination, candidate)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
            stream.write(f"changed={str(changed).lower()}\n")
    print("Upstream change detected; build and isolated boot tests required." if changed else "Upstream unchanged; keep the approved version, skip expensive builds.")


def guard(config):
    """Normal builds fail closed if a tested rolling feed changes again."""
    path = ROOT / APPROVED
    require(path.exists(), "上游首次验证尚未完成，请在主页查看自动跟进状态后重试。")
    approved = read_json(path)
    selected = next((s for s in approved["sources"] if s["source"] == config["builder"] and s["version"] == config["version"]), None)
    if not selected or config["target"] != "x86/64":
        print("Historical/other-target build: outside automatic upstream boot approval coverage.")
        return
    if config["builder"] == "kwrt":
        spec = read_json(ROOT / REGISTRY)[config["version"]]
        metadata = catalog.kwrt_data(spec)
        checksum = builder_checksum(spec["base"], spec["archive"])
    else:
        metadata = catalog.target_data(config["version"], "x86/64")
        base = f"{catalog.DOWNLOADS}/releases/{config['version']}/targets/x86/64"
        checksum = builder_checksum(base, f"openwrt-imagebuilder-{config['version']}-x86-64.Linux-x86_64.tar.zst")
    require(checksum == selected["builder_sha256"] and digest(metadata) == digest(selected["metadata"]),
            "上游构建器或软件源已变化，暂停本次构建。请等待自动跟进测试通过后重新提交；不会偷偷使用未验证更新。")
    print("Approved upstream builder and feed fingerprint verified.")


def prepare(candidate_path, source):
    candidate = validate_candidate(read_json(candidate_path))
    write_json(ROOT / REGISTRY, candidate["registry"])
    selected = next(s for s in candidate["sources"] if s["source"] == source)
    from scripts import smoke
    smoke.prepare(source)
    from scripts.build import normalize
    config = read_json(Path("configs/qa-generated.json"))
    config["version"] = selected["version"]
    config = normalize(config)
    write_json(Path("configs/qa-generated.json"), config)
    write_json(Path("work/qa/config.json"), config)


def attest(candidate_path, source, destination):
    candidate = validate_candidate(read_json(candidate_path))
    selected = next(s for s in candidate["sources"] if s["source"] == source)
    report = read_json(Path("work/qa/boot-report.json"))
    require(report["builder"] == source and report["version"] == selected["version"], "Wrong QA version")
    expected = {"bios", "uefi", "native-vmdk-bios" if source == "kwrt" else "vmdk-bios"}
    require({r["mode"] for r in report["results"]} == expected and all(r["status"] == "passed" for r in report["results"]), "Incomplete boot tests")
    # Re-read upstream after build/boot: rolling feeds must not change mid-test.
    current = discover(candidate["registry"])
    require(current["fingerprint"] == candidate["fingerprint"], "Upstream changed during QA; retry on next check")
    write_json(destination, {"source": source, "version": selected["version"], "fingerprint": candidate["fingerprint"],
                             "run_id": os.environ.get("GITHUB_RUN_ID", ""), "report": report})


def approval(candidate, evidence, run_id, commit):
    validate_candidate(candidate)
    require(set(evidence) == {"official", "kwrt"}, "Both source test reports required")
    result = {"schema_version": 1, "fingerprint": candidate["fingerprint"],
              "approved_at": dt.datetime.now(dt.timezone.utc).isoformat(), "run_id": str(run_id),
              "source_commit": commit, "sources": []}
    for selected in candidate["sources"]:
        source = selected["source"]
        proof = evidence[source]
        require(proof["fingerprint"] == candidate["fingerprint"] and proof["source"] == source
                and proof["version"] == selected["version"] and proof["run_id"] == str(run_id), "Mismatched test evidence")
        report = proof["report"]
        expected = {"bios", "uefi", "native-vmdk-bios" if source == "kwrt" else "vmdk-bios"}
        require(report["builder"] == source and report["version"] == selected["version"]
                and len(report["results"]) == 3 and {r["mode"] for r in report["results"]} == expected
                and all(r["status"] == "passed" and r.get("web", {}).get("authenticated_status") == 200 for r in report["results"]), "Boot authentication tests not passed")
        result["sources"].append({**selected, "tested_modes": sorted(expected)})
    return result


def api(path, token, method="GET", body=None):
    repo = os.environ["GITHUB_REPOSITORY"]
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo), "Invalid repository")
    request = urllib.request.Request(f"https://api.github.com/repos/{repo}{path}",
        data=canonical(body).encode() if body is not None else None, method=method,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def publish(candidate_path, reports):
    candidate = validate_candidate(read_json(candidate_path))
    evidence = {source: read_json(reports / f"{source}.json") for source in ("official", "kwrt")}
    approved = approval(candidate, evidence, os.environ["GITHUB_RUN_ID"], os.environ["GITHUB_SHA"])
    token = os.environ["GH_TOKEN"]
    ref = api("/git/ref/heads/main", token)
    parent = ref["object"]["sha"]
    require(parent == os.environ["GITHUB_SHA"], "Branch changed during QA; do not overwrite newer work. Next daily check will retry.")
    base = api("/git/commits/" + parent, token)["tree"]["sha"]
    entries = [{"path": path, "mode": "100644", "type": "blob", "content": canonical(value)}
               for path, value in ((REGISTRY, candidate["registry"]), (APPROVED, approved))]
    tree = api("/git/trees", token, "POST", {"base_tree": base, "tree": entries})["sha"]
    commit = api("/git/commits", token, "POST", {"message": "Approve tested upstream " + candidate["fingerprint"][:12], "tree": tree, "parents": [parent]})["sha"]
    api("/git/refs/heads/main", token, "PATCH", {"sha": commit, "force": False})
    print("Approved upstream data committed atomically. Existing private files preserved.")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as stream:
            stream.write("## Upstream approved\n\n" + "\n".join(f"- {s['version']}: EFI / Legacy / VMDK boot + authenticated LuCI passed" for s in approved["sources"]) + "\n\nNo user firmware was published or flashed.\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["detect", "prepare", "attest", "publish", "guard"])
    parser.add_argument("--candidate", type=Path, default=Path("work/upstream/candidate.json"))
    parser.add_argument("--source", choices=["official", "kwrt"])
    parser.add_argument("--reports", type=Path, default=Path("work/upstream/reports"))
    args = parser.parse_args()
    if args.action == "detect":
        detect(args.candidate)
    elif args.action == "prepare":
        prepare(args.candidate, args.source)
    elif args.action == "attest":
        attest(args.candidate, args.source, args.reports / f"{args.source}.json")
    elif args.action == "guard":
        for source in read_json(ROOT / APPROVED)["sources"]:
            guard({"builder": source["source"], "version": source["version"], "target": "x86/64"})
    else:
        publish(args.candidate, args.reports)


if __name__ == "__main__":
    main()
