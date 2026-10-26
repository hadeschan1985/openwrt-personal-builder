"""Delivery policy and bounded metadata; no user secrets are serialized."""
from __future__ import annotations
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil

from scripts.build import normalize, require, sha256

MAX_BYTES = 1536 * 1024 * 1024


def policy(config, env):
    if config["build_mode"] != "release":
        return
    require(env.get("REPOSITORY_PRIVATE") == "true", "正式模式只能使用私有构建仓库。")
    password = env.get("ROUTER_PASSWORD", "")
    require(config["system"]["password_secret"] and len(password) >= 12 and len(password.encode("utf-8")) <= 128 and not any(c in password for c in ":\r\n\x00"),
            "正式模式需要仓库 ROUTER_PASSWORD：至少 12 个字符、最多 128 UTF-8 字节，不能含冒号或换行。不要把密码写进配置或聊天。")
    require(config["system"]["https"], "正式模式必须启用 HTTPS。")
    require(config["target"] == "x86/64" and (config["output"]["efi"] or config["output"]["legacy"]),
            "正式模式目前只支持可自动启动验收的 x86/64 EFI/Legacy 磁盘。其他架构或仅 ROOTFS 请使用实验模式。")
    ports = [config["network"]["wan_port"], *config["network"]["lan_ports"].split()]
    require(all(not p or int(p[3:]) <= 7 for p in ports), "自动验收最多支持 eth0–eth7。")
    interface = ipaddress.IPv4Interface(config["system"]["ip"] if "/" in config["system"]["ip"] else config["system"]["ip"] + "/24")
    require(8 <= interface.network.prefixlen <= 30, "正式模式自动验收支持 /8–/30 管理网段；其他掩码请使用实验模式。")
    require(not (interface.ip.is_loopback or interface.ip.is_multicast or interface.ip.is_unspecified), "正式模式需要有效的单播管理地址。")
    require(interface.network.prefixlen > 30 or interface.ip not in (interface.network.network_address, interface.network.broadcast_address), "管理地址不能是网络地址或广播地址。")


def config():
    raw = os.environ.get("CONFIG_JSON", "").strip()
    if not raw:
        path = Path(os.environ.get("CONFIG_PATH") or "configs/x86-default.json").resolve()
        require(path.is_relative_to(Path("configs").resolve()), "Config must be under configs/")
        raw = path.read_text(encoding="utf-8")
    require(len(raw.encode()) <= 60000, "Config exceeds 60 KB")
    return normalize(json.loads(raw))


def file_group(name):
    if name.endswith("combined-efi.img.gz"):
        return "efi"
    if name.endswith("combined.img.gz"):
        return "legacy"
    if ".vmdk" in name:
        return "vmdk"
    if name.endswith("rootfs.tar.gz"):
        return "rootfs"
    return "reports"


def prepare_downloads(files, output, destination):
    """One disk file per download. Keep VMDK boot variants separate too."""
    groups = {}
    for item in files:
        group = item['group']
        if group == 'vmdk':
            require(re.search(r'combined(?:-efi)?\.vmdk(?:\.zip)?$', item['name']), 'Unknown VMDK download layout')
            group = 'efi-vmdk' if '-efi.vmdk' in item['name'] else 'legacy-vmdk'
        groups.setdefault(group, []).append(item)
    for group, items in groups.items():
        require(group == 'reports' or len(items) == 1, 'Each firmware download must contain exactly one image')
        directory = destination / group
        directory.mkdir(parents=True, exist_ok=True)
        for item in items:
            source, target = output / item['name'], directory / item['name']
            require(source.is_file() and not source.is_symlink() and not target.exists(), 'Invalid or duplicate download payload')
            try:
                os.link(source, target)
            except OSError:
                shutil.copyfile(source, target)
    return sorted(groups)


def record(config, root=Path(".")):
    output = root / "outputs"
    summary = json.loads((output / "build-summary.json").read_text(encoding="utf-8"))
    vm = json.loads((output / "vm-report.json").read_text(encoding="utf-8")) if (output / "vm-report.json").exists() else {"status": "not-tested", "hardware_tested": False}
    require(config["build_mode"] != "release" or vm["status"] == "passed", "正式模式不能交付未通过启动验收的固件。")
    files = []
    for path in sorted(output.iterdir()):
        if not path.is_file():
            continue
        require(re.fullmatch(r"[A-Za-z0-9_.+-]{1,180}", path.name), "Unsafe output name")
        files.append({"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path), "group": file_group(path.name)})
    require(sum(f["bytes"] for f in files) <= MAX_BYTES, "本次产物超过 1.5 GiB 安全上限，请减少输出格式或软件数量。")
    result = {"schema_version": 1, "run_id": os.environ.get("GITHUB_RUN_ID", ""), "run_number": os.environ.get("GITHUB_RUN_NUMBER", ""),
              "source_commit": os.environ.get("GITHUB_SHA", ""), "config": config, "files": files, "vm": vm,
              "builder_sha256": summary["builder_sha256"], "hardware_tested": False}
    validate_record(result)
    path = root / "work" / "build-record.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    groups = prepare_downloads(files, output, root / 'work' / 'downloads-separated') if config['target'].startswith('x86/') else []
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
            for group in ("efi", "legacy", "vmdk", "rootfs"):
                stream.write(f"{group}={str(any(f['group'] == group for f in files)).lower()}\n")
            stream.write("x86=" + str(config["target"].startswith("x86/")).lower() + "\n")
            stream.write('download_groups=' + json.dumps(groups, separators=(',', ':')) + '\n')
    return result


def validate_record(value):
    require(value.get("schema_version") == 1 and re.fullmatch(r"\d+", str(value.get("run_id", ""))) and re.fullmatch(r"\d+", str(value.get("run_number", ""))), "Invalid record identity")
    require(re.fullmatch(r"[a-f0-9]{40}", value.get("source_commit", "")), "Invalid source commit")
    require(isinstance(value.get("files"), list) and 1 <= len(value["files"]) <= 100, "Invalid file count")
    total, names = 0, set()
    for item in value["files"]:
        require(re.fullmatch(r"[A-Za-z0-9_.+-]{1,180}", item["name"]) and item["name"] not in names, "Invalid or duplicate file name")
        require(type(item["bytes"]) is int and 0 <= item["bytes"] <= MAX_BYTES and re.fullmatch(r"[a-f0-9]{64}", item["sha256"]), "Invalid file integrity")
        require(item["group"] == file_group(item["name"]), "Invalid download group")
        names.add(item["name"])
        total += item["bytes"]
    require(total <= MAX_BYTES and len(json.dumps(value).encode()) <= 256 * 1024, "Record exceeds limits")
    clean = normalize(value["config"])
    require(clean == value["config"], "Record configuration is not normalized")
    require(clean["build_mode"] != "release" or value.get("vm", {}).get("status") == "passed", "Release did not pass VM tests")
    return value


def save_record(path):
    require(path.stat().st_size <= 256 * 1024, "Record too large")
    value = validate_record(json.loads(path.read_text(encoding="utf-8")))
    require(value["run_id"] == os.environ["GITHUB_RUN_ID"] and value["source_commit"] == os.environ["GITHUB_SHA"], "Record belongs to another run")
    from scripts.upstream import api
    token = os.environ["GH_TOKEN"]
    require(api("", token)["private"], "Never write personal build records to a public repository")
    for attempt in range(3):
        parent = api("/git/ref/heads/main", token)["object"]["sha"]
        base = api("/git/commits/" + parent, token)["tree"]["sha"]
        tree = api("/git/trees", token, "POST", {"base_tree": base, "tree": [{"path": f"records/{value['run_id']}.json", "mode": "100644", "type": "blob", "content": json.dumps(value, ensure_ascii=False, separators=(",", ":"))}]})["sha"]
        commit = api("/git/commits", token, "POST", {"message": f"Record private build {value['run_number']}", "tree": tree, "parents": [parent]})["sha"]
        try:
            api("/git/refs/heads/main", token, "PATCH", {"sha": commit, "force": False})
            print("Private build record saved; no user secret values were copied.")
            return
        except Exception:
            if attempt == 2:
                raise RuntimeError("构建记录写入遇到并发更新，请检查任务；不会强制覆盖其他提交。") from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["policy", "record", "save"])
    parser.add_argument("--path", type=Path, default=Path("work/build-record.json"))
    args = parser.parse_args()
    if args.action == "save":
        save_record(args.path)
    else:
        c = config()
        policy(c, os.environ)
        if args.action == "record":
            record(c)
