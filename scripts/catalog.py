"""Read-only OpenWrt metadata sync. Does not request upstream builds."""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import hashlib
import http.client
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

from scripts.builders import platforms,series

DOWNLOADS = "https://downloads.openwrt.org"
ASU = "https://sysupgrade.openwrt.org"
REGISTRY = Path(__file__).resolve().parents[1] / "configs" / "builders.json"


def fetch_bytes(url,limit=32*1024**2):
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'OpenWrt-Personal-Builder/0.1'})
            with urllib.request.urlopen(request,timeout=90) as response:
                length=response.headers.get('Content-Length');expected=int(length) if length and length.isdigit() else None
                if expected is not None and expected>limit:raise ValueError('Upstream metadata exceeds size limit')
                raw=response.read(limit+1)
                if len(raw)>limit:raise ValueError('Upstream metadata exceeds size limit')
                if expected is not None and len(raw)!=expected:raise http.client.IncompleteRead(raw,expected-len(raw))
                return raw
        except (http.client.IncompleteRead,urllib.error.URLError,TimeoutError,ConnectionError) as error:
            if isinstance(error,urllib.error.HTTPError) and error.code not in (408,429,500,502,503,504):raise
            if attempt==2:raise
            time.sleep(2**attempt)


def get_json(url: str):
    return json.loads(fetch_bytes(url))


def title(item):
    return str(item.get('title') or " ".join(str(item.get(k, "")) for k in ("vendor", "model", "variant"))).strip()


def target_data(version, target):
    data = get_json(f"{DOWNLOADS}/releases/{version}/targets/{target}/profiles.json")
    branch = ".".join(version.split(".")[:2])
    packages = {}
    errors = []
    digests = []
    for url, nested in (
        (f"{ASU}/json/v1/releases/{version}/targets/{target}/index.json", True),
        (f"{ASU}/json/v1/releases/packages-{branch}/{data['arch_packages']}-index.json", False),
    ):
        try:
            index = get_json(url)
            digests.append(hashlib.sha256(json.dumps(index, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
            packages.update(index.get("packages", {}) if nested else index)
        except Exception as error:
            errors.append(f"Package metadata unavailable: {type(error).__name__}")
    return {"profiles": data, "packages": sorted(packages), "package_metadata_errors": errors,
            "package_index_sha256": digests}


def kwrt_data(spec):
    profiles = json.loads(json.dumps(get_json(spec['base']+'/'+spec.get('profiles_file','profiles.json'))))
    profiles["default_packages"] = sorted((set(profiles.get("default_packages", [])) - set(spec["exclude_defaults"])) | set(spec["replacement_packages"]))
    if spec.get('metadata_source')=='selector':
        arch=profiles['arch_packages']
        branch=series(spec)
        urls=[f"https://openwrt.ai/json/v1/releases/{branch}/targets/{spec['target']}/index.json",f"https://openwrt.ai/json/v1/releases/packages-{branch}/{arch}-index.json"]
        indexes=[get_json(url) for url in urls]
        packages=set(indexes[0]['packages'])|set(indexes[1])
        digests=[hashlib.sha256(json.dumps(index,sort_keys=True,separators=(',',':')).encode()).hexdigest() for index in indexes]
        result={'profiles':profiles,'packages':sorted(packages),'package_metadata_errors':[],'image_base':spec['base'],'builder_sha256':spec['sha256'],'package_index_sha256':digests,'compatibility_adjustments':{'excluded_defaults':spec['exclude_defaults'],'replacements':spec['replacement_packages']}}
        if spec.get('blocked_reason'):result['build_blocked']=spec['blocked_reason']
        if spec.get('compatibility_recipe'):
            from scripts.n1_compat import metadata
            result=metadata(result,spec)
        return result
    urls = [spec["kernel_feed"] + "/Packages"] + [spec["feeds"] + "/" + feed + "/Packages"
        for feed in ("base", "packages", "luci", "routing", "video", "kiddin9")]
    def names(url):
        raw=fetch_bytes(url)
        return re.findall(r"^Package: (\S+)$", raw.decode(), re.MULTILINE), hashlib.sha256(raw).hexdigest()
    packages = set()
    digests = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for names_found, digest in pool.map(names, urls):
            packages.update(names_found)
            digests.append(digest)
    return {"profiles": profiles, "packages": sorted(packages), "package_metadata_errors": [],
            "image_base": spec["base"], "builder_sha256": spec["sha256"], "package_index_sha256": digests,
            "compatibility_adjustments": {"excluded_defaults": spec["exclude_defaults"], "replacements": spec["replacement_packages"]}}


def sync(destination: Path, versions=None, preload=("x86/64",)):
    releases = get_json(f"{DOWNLOADS}/.versions.json")
    versions = versions or [releases["stable_version"], releases["oldstable_version"]]
    result = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(),
              "source": DOWNLOADS, "default_version": releases["stable_version"],
              "versions": [], "version_labels": {}, "devices": []}
    for version in dict.fromkeys(versions):
        overview = get_json(f"{DOWNLOADS}/releases/{version}/.overview.json")
        result["versions"].append(version)
        for profile in overview["profiles"]:
            names = [title(t) for t in profile.get("titles", [])]
            result["devices"].append({"id": profile["id"], "target": profile["target"],
                "version": version, "name": names[0] if names else profile["id"],
                "aliases": names, "metadata": f"targets/{version}/{profile['target']}.json"})
    destination.mkdir(parents=True, exist_ok=True)
    tasks = [(v, t) for v in result["versions"] for t in preload]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(target_data, v, t): (v, t) for v, t in tasks}
        for future in concurrent.futures.as_completed(futures):
            version, target = futures[future]
            data = future.result()
            path = destination / "targets" / version / f"{target}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"Metadata: {version} {target}, {len(data['packages'])} packages")
    for version, family in json.loads(REGISTRY.read_text(encoding="utf-8")).items():
        result['versions'].append(version)
        result['version_labels'][version]=family['label']
        for target,spec in platforms(family):
            add_kwrt_target(result,destination,version,target,spec)
    (destination / "catalog.json").write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Catalog: {len(result['devices'])} version/profile entries")


def add_kwrt_target(result,destination,version,target,spec):
        data = kwrt_data(spec)
        if spec.get('metadata_fingerprint') and hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=spec['metadata_fingerprint']:
            raise ValueError('Pinned platform metadata changed: '+target)
        path = destination / "targets" / version / f"{target}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        for profile_id, profile in data["profiles"]["profiles"].items():
            names = [title(t) for t in profile.get("titles", [])]
            result["devices"].append({"id": profile_id, "target": target, "builder": "kwrt",
                "version": version, "name": names[0] if names else profile_id, "aliases": names,
                "metadata": f"targets/{version}/{target}.json"})
        print(f"Metadata: {version} {target}, {len(data['packages'])} packages")


def extend_pinned(destination):
    """Extend the checked-in official baseline; do not select an untested release."""
    result=json.loads((destination/'catalog.json').read_text(encoding='utf-8'))
    result['devices']=[d for d in result['devices'] if d.get('builder')!='kwrt']
    for version,family in json.loads(REGISTRY.read_text(encoding='utf-8')).items():
        if version not in result['versions']:result['versions'].append(version)
        result['version_labels'][version]=family['label']
        for target,spec in platforms(family):add_kwrt_target(result,destination,version,target,spec)
    result['updated']=dt.datetime.now(dt.timezone.utc).isoformat()
    (destination/'catalog.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=Path("site/data"))
    parser.add_argument("--version", action="append")
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument('--extend-pinned',action='store_true')
    args = parser.parse_args()
    extend_pinned(args.destination) if args.extend_pinned else sync(args.destination, args.version, args.target or ('x86/64',))
