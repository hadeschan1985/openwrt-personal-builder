"""Batch ImageBuilder runner for GitHub Actions; no always-on ASU service.

Run with --plan to validate without building. Custom shell is embedded in the
firmware and never executed as a command on the runner.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

BASE = "https://downloads.openwrt.org"
PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+_.-]{0,120}$")
CORE = {"base-files", "busybox", "libc", "libgcc", "kernel", "netifd", "procd", "uci", "fstools"}
FEATURE_PACKAGES = {
    "docker": ["luci-app-dockerman"],
    "usb_net": ["kmod-usb-net-asix", "kmod-usb-net-rtl8152", "kmod-usb-net-cdc-ether", "kmod-usb-net-cdc-ncm"],
    "usb_wireless": ["kmod-mt76-usb", "kmod-rt2800-usb", "iw", "wpad-mbedtls"],
    "wwan": ["luci-proto-modemmanager", "modemmanager", "kmod-usb-net-qmi-wwan", "kmod-usb-serial-option"],
}
UNSUPPORTED = {"istoreos", "routerdog", "remove_links"}


class ConfigError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ConfigError(message)


def boolean(obj, key, default=False):
    value = obj.get(key, default)
    require(type(value) is bool, f"{key} must be true or false")
    return value


def normalize(raw):
    require(isinstance(raw, dict), "Configuration must be a JSON object")
    require(raw.get("schema_version") == 1, "Unsupported schema_version")
    require(raw.get("builder", "official") == "official", "Kwrt/custom builders are not configured yet")
    version = raw.get("version", "")
    require(isinstance(version, str) and re.fullmatch(r"\d{2}\.\d{2}\.\d+(?:-rc\d+)?", version), "Use a fixed OpenWrt release")
    target, profile = raw.get("target", ""), raw.get("profile", "")
    require(isinstance(target, str) and re.fullmatch(r"[a-z0-9_-]+/[a-z0-9_-]+", target), "Invalid target")
    require(isinstance(profile, str) and re.fullmatch(r"[A-Za-z0-9_,.+-]+", profile), "Invalid profile")
    result = {"schema_version": 1, "builder": "official", "version": version, "target": target, "profile": profile}
    for key in ("packages", "remove_packages", "themes", "proxies"):
        values = raw.get(key, [])
        require(isinstance(values, list) and len(values) <= 512, f"Invalid {key}")
        require(all(isinstance(p, str) and PACKAGE.fullmatch(p) for p in values), f"Invalid package name in {key}")
        result[key] = sorted(set(values))
    require(not (CORE & set(result["remove_packages"])), "Cannot remove essential system packages")
    require(not (set(result["packages"]) & set(result["remove_packages"])), "Package both added and removed")
    result["firewall"] = raw.get("firewall", "nftables")
    require(result["firewall"] in ("nftables", "iptables"), "Invalid firewall")
    require(not (result["firewall"] == "iptables" and any(x in result["proxies"] for x in
        ["luci-app-homeproxy", "luci-app-nikki", "luci-app-xray-status", "luci-app-fchomo"])), "Selected proxy requires nftables")
    system = raw.get("system", {})
    require(isinstance(system, dict), "Invalid system settings")
    hostname = system.get("hostname", "OpenWrt")
    require(isinstance(hostname, str) and re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,61}[A-Za-z0-9])?", hostname), "Invalid hostname")
    address = system.get("ip", "192.168.1.1")
    require(isinstance(address, str), "Invalid management IPv4 address")
    try:
        ipaddress.IPv4Interface(address if "/" in address else address + "/24")
    except (ValueError, TypeError):
        raise ConfigError("Invalid management IPv4 address") from None
    webserver = system.get("webserver", "uhttpd")
    require(webserver in ("uhttpd", "nginx", "lighttpd"), "Invalid webserver")
    signature = system.get("signature", "")
    require(isinstance(signature, str) and len(signature) <= 120 and "\x00" not in signature, "Invalid signature")
    default_theme = system.get("default_theme", "bootstrap")
    require(isinstance(default_theme, str) and re.fullmatch(r"[a-zA-Z0-9_-]+", default_theme), "Invalid default theme")
    require(f"luci-theme-{default_theme}" in result["themes"], "Default theme must be installed")
    require(system.get("theme_mode", "auto") == "auto", "Custom NAS landing pages require a Kwrt builder")
    result["system"] = {"hostname": hostname, "ip": address, "webserver": webserver,
        "signature": signature, "default_theme": default_theme,
        "https": boolean(system, "https", True), "ipv6": boolean(system, "ipv6", True),
        "password_secret": boolean(system, "password_secret")}
    net = raw.get("network", {})
    require(isinstance(net, dict), "Invalid network settings")
    mode = net.get("mode", "router")
    require(mode in ("router", "side"), "Invalid network mode")
    gateway = net.get("gateway", "")
    if gateway:
        try:
            ipaddress.IPv4Address(gateway)
        except (ValueError, TypeError):
            raise ConfigError("Invalid gateway") from None
    require(mode != "side" or gateway, "Side router requires a gateway")
    if gateway:
        interface = ipaddress.IPv4Interface(address if "/" in address else address + "/24")
        require(ipaddress.IPv4Address(gateway) != interface.ip, "Gateway cannot equal management IP")
        require(mode != "side" or ipaddress.IPv4Address(gateway) in interface.network, "Gateway must be on the LAN subnet")
    wan, lan = net.get("wan_port", ""), net.get("lan_ports", "")
    require(isinstance(wan, str) and isinstance(lan, str), "Invalid port mapping")
    require(not wan or re.fullmatch(r"eth\d+", wan), "Invalid WAN port")
    require(not lan or re.fullmatch(r"eth\d+(?: eth\d+)*", lan), "Invalid LAN ports")
    require(not wan or wan not in lan.split(), "WAN and LAN ports overlap")
    require(not (wan or lan) or target.startswith("x86/"), "Custom eth port mapping is currently x86-only")
    ssid = net.get("wifi_ssid", "")
    require(isinstance(ssid, str) and len(ssid.encode()) <= 32 and "\x00" not in ssid and "\n" not in ssid, "Invalid Wi-Fi SSID")
    require(not boolean(net, "wifi_password_secret") or ssid, "Wi-Fi password needs an SSID")
    require(not ssid or boolean(net, "wifi_password_secret"), "Setting a Wi-Fi SSID requires WIFI_PASSWORD; open hotspots are not generated")
    result["network"] = {"mode": mode, "gateway": gateway, "dhcp": boolean(net, "dhcp", mode == "router"),
        "wan_port": wan, "lan_ports": lan, "wifi_ssid": ssid,
        "pppoe_secret": boolean(net, "pppoe_secret"), "wifi_password_secret": boolean(net, "wifi_password_secret")}
    require(not (mode == "side" and result["network"]["pppoe_secret"]), "PPPoE is not applicable in side-router mode")
    features = raw.get("features", {})
    require(isinstance(features, dict) and not (set(features) - (set(FEATURE_PACKAGES) | UNSUPPORTED)), "Unknown feature")
    for feature in UNSUPPORTED:
        require(not boolean(features, feature), f"{feature} needs a verified Kwrt builder")
    result["features"] = {k: boolean(features, k) for k in FEATURE_PACKAGES}
    output = raw.get("output", {})
    require(isinstance(output, dict), "Invalid output settings")
    fs = output.get("filesystem", "squashfs")
    require(fs in ("squashfs", "ext4"), "Unsupported filesystem")
    size = output.get("rootfs_size_mb", 256)
    require(type(size) is int and 64 <= size <= 6144, "Rootfs size must be 64–6144 MB")
    require(target.startswith("x86/") or size == 256, "Custom root partition size is currently x86-only")
    efi, legacy = boolean(output, "efi", True), boolean(output, "legacy", True)
    vmdk, rootfs = boolean(output, "vmdk"), boolean(output, "rootfs")
    require(not vmdk or target.startswith("x86/"), "VMDK is x86-only")
    require(not vmdk or efi or legacy, "VMDK requires a bootable disk output")
    require(not target.startswith("x86/") or efi or legacy or rootfs, "Select an output")
    result["output"] = {"filesystem": fs, "rootfs_size_mb": size, "efi": efi, "legacy": legacy, "vmdk": vmdk, "rootfs": rootfs}
    defaults = raw.get("defaults", "")
    require(isinstance(defaults, str) and len(defaults.encode()) <= 20000 and "\x00" not in defaults, "Initialization script is too large or invalid")
    result["defaults"] = defaults
    overlay = raw.get("overlay", "")
    require(isinstance(overlay, str) and (not overlay or re.fullmatch(r"overlays/[A-Za-z0-9_.-]+\.(?:zip|tar\.gz|tgz|7z)", overlay)), "Overlay must be an archive under overlays/")
    result["overlay"] = overlay
    return result


def has_private_content(config):
    return bool(config["overlay"] or config["defaults"] or config["system"]["password_secret"] or
        config["network"]["pppoe_secret"] or config["network"]["wifi_password_secret"])


def package_plan(config):
    packages = set(config["packages"] + config["themes"] + config["proxies"])
    remove = set(config["remove_packages"])
    system = config["system"]
    packages.update(["luci-ssl"] if system["webserver"] == "uhttpd" else [f"luci-{system['webserver']}"])
    if config["firewall"] == "iptables":
        remove.add("firewall4")
        packages.update(["firewall", "iptables-legacy"])
    for feature, enabled in config["features"].items():
        if enabled:
            packages.update(FEATURE_PACKAGES[feature])
    if config["features"]["usb_wireless"]:
        remove.update(["wpad-basic-mbedtls", "wpad-basic-wolfssl"])
    require(not (packages & remove), "Generated package selections conflict")
    return sorted(packages) + [f"-{p}" for p in sorted(remove)]


def q(value):
    return shlex.quote(str(value))


def defaults_script(config, env=None):
    env = os.environ if env is None else env
    system, net = config["system"], config["network"]
    lines = ["#!/bin/sh", "set -eu", "# Generated by OpenWrt Personal Builder"]
    def uci(path, value):
        lines.append(f"uci -q set {q(path + '=' + str(value))}")
    uci("system.@system[0].hostname", system["hostname"])
    interface = ipaddress.IPv4Interface(system["ip"] if "/" in system["ip"] else system["ip"] + "/24")
    uci("network.lan.ipaddr", interface.ip)
    uci("network.lan.netmask", interface.netmask)
    if net["mode"] == "side":
        uci("network.lan.gateway", net["gateway"])
        lines.append("uci -q delete network.lan.dns || true")
        lines.append(f"uci -q add_list {q('network.lan.dns=' + net['gateway'])}")
        uci("network.wan.auto", "0")
        uci("network.wan6.auto", "0")
    uci("dhcp.lan.ignore", "0" if net["dhcp"] else "1")
    if not system["ipv6"]:
        for key in ("ra", "dhcpv6", "ndp"):
            uci("dhcp.lan." + key, "disabled")
        uci("network.wan6.auto", "0")
    if net["wan_port"]:
        uci("network.wan.device", net["wan_port"])
        uci("network.wan6.device", net["wan_port"])
    if net["lan_ports"]:
        lines += ["bridge_section=''", r"for section in $(uci show network | sed -n 's/^network\.\([^=]*\)=device$/\1/p'); do",
            "  if [ \"$(uci -q get network.$section.name || true)\" = 'br-lan' ]; then bridge_section=$section; break; fi", "done",
            "[ -n \"$bridge_section\" ] || exit 1",
            "uci -q delete network.$bridge_section.ports || true"]
        for port in net["lan_ports"].split():
            lines.append(f"uci -q add_list \"network.$bridge_section.ports={port}\"")
    theme_path = {"bootstrap": "/luci-static/bootstrap", "openwrt": "/luci-static/openwrt.org", "openwrt-2020": "/luci-static/openwrt2020"}.get(system["default_theme"], "/luci-static/" + system["default_theme"])
    uci("luci.main.mediaurlbase", theme_path)
    if system["webserver"] == "uhttpd" and system["https"]:
        uci("uhttpd.main.redirect_https", "1")
    if system["signature"]:
        lines.append(f"printf '%s\\n' {q(system['signature'])} >> /etc/banner")
    def secret(name):
        value = env.get(name, "")
        require(bool(value) and "\x00" not in value and "\n" not in value and "\r" not in value, f"Missing or invalid repository secret: {name}")
        return value
    if system["password_secret"]:
        password = secret("ROUTER_PASSWORD")
        require(":" not in password, "ROUTER_PASSWORD cannot contain a colon")
        lines.append(f"printf '%s\\n%s\\n' {q(password)} {q(password)} | passwd root >/dev/null 2>&1")
    if net["pppoe_secret"]:
        uci("network.wan.proto", "pppoe")
        uci("network.wan.username", secret("PPPOE_USERNAME"))
        uci("network.wan.password", secret("PPPOE_PASSWORD"))
    if net["wifi_ssid"]:
        key = secret("WIFI_PASSWORD") if net["wifi_password_secret"] else ""
        require(not key or 8 <= len(key) <= 63, "WIFI_PASSWORD must contain 8–63 characters")
        lines.append(r"for iface in $(uci show wireless | sed -n 's/^wireless\.\([^=]*\)=wifi-iface$/\1/p'); do")
        lines.append(f"  uci set \"wireless.$iface.ssid=\"{q(net['wifi_ssid'])}")
        if key:
            lines += ["  uci set \"wireless.$iface.encryption=psk2\"", f"  uci set \"wireless.$iface.key=\"{q(key)}"]
        lines += ["  uci set \"wireless.$iface.disabled=0\"", "done"]
        lines += [r"for radio in $(uci show wireless | sed -n 's/^wireless\.\([^=]*\)=wifi-device$/\1/p'); do",
                  "  uci set \"wireless.$radio.disabled=0\"", "done"]
    lines.append("uci -q commit")
    if config["defaults"]:
        lines.extend(["# User initialization; executes on the router, not the Actions host", config["defaults"]])
    lines.append("exit 0")
    return "\n".join(lines) + "\n"


def safe_member(name):
    path = PurePosixPath(name.replace("\\", "/"))
    require(not path.is_absolute() and ".." not in path.parts and not any(":" in p for p in path.parts), "Archive path escapes overlay directory")
    return path


def extract_overlay(archive: Path, destination: Path):
    require(archive.stat().st_size <= 12 * 1024 * 1024, "Overlay archive exceeds 12 MiB")
    destination.mkdir(parents=True, exist_ok=True)
    count, total = 0, 0
    def write(name, size, stream, mode=0o644):
        nonlocal count, total
        count += 1
        total += size
        require(count <= 10000 and total <= 128 * 1024 * 1024, "Expanded overlay exceeds limits")
        path = destination.joinpath(*safe_member(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as out:
            shutil.copyfileobj(stream, out)
        path.chmod(mode & 0o777)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                safe_member(info.filename)
                require(not stat.S_ISLNK(info.external_attr >> 16), "Overlay symlinks are not supported")
                if not info.is_dir():
                    with package.open(info) as stream:
                        write(info.filename, info.file_size, stream, (info.external_attr >> 16) or 0o644)
    elif archive.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(archive, "r:gz") as package:
            for info in package:
                safe_member(info.name)
                require(info.isfile() or info.isdir(), "Overlay links and special files are not supported")
                if info.isfile():
                    with package.extractfile(info) as stream:
                        write(info.name, info.size, stream, info.mode)
    else:
        raise ConfigError("7z overlay support is not enabled; convert it to ZIP or TAR.GZ")
    require(not list(destination.rglob("*.ipk")) and not list(destination.rglob("*.apk")),
        "Archive package installation needs a matching package-manager integration; use package names for now")


def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "OpenWrt-Personal-Builder/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def selected_images(images, config):
    out = config["output"]
    matches = []
    for image in images:
        fs, kind = image.get("filesystem"), image.get("type")
        if fs == "targz":
            if out["rootfs"]:
                matches.append(image)
        elif fs == out["filesystem"]:
            if config["target"].startswith("x86/"):
                if (kind == "combined" and out["legacy"]) or (kind == "combined-efi" and out["efi"]):
                    matches.append(image)
            elif kind in ("sysupgrade", "factory", "sdcard", "combined", "combined-efi"):
                matches.append(image)
    return matches


def build(config, root=Path(".")):
    require(sys.platform.startswith("linux"), "Real ImageBuilder builds require Linux / GitHub Actions")
    root = root.resolve()
    workspace = root / "work" / "builder"
    require(not workspace.exists(), "Build directory already exists; use a fresh workspace")
    base = f"{BASE}/releases/{config['version']}/targets/{config['target']}"
    metadata = get_json(base + "/profiles.json")
    require(config["profile"] in metadata["profiles"], "Profile not found in the selected target")
    available_images = metadata["profiles"][config["profile"]]["images"]
    require(selected_images(available_images, config), "Requested output is unavailable in this builder")
    if config["output"]["rootfs"]:
        require(any(i.get("filesystem") == "targz" for i in available_images), "This builder does not offer ROOTFS TAR.GZ")
    private = os.environ.get("REPOSITORY_PRIVATE", "true") == "true"
    require(private or not has_private_content(config), "Use a private build repository for scripts, overlays or secrets")
    sums_path = root / "work" / "sha256sums"
    download(base + "/sha256sums", sums_path)
    expected = {}
    for line in sums_path.read_text().splitlines():
        parts = line.split()
        if len(parts) == 2:
            expected[parts[1].lstrip("*")] = parts[0]
    prefix = f"openwrt-imagebuilder-{config['version']}-{config['target'].replace('/', '-')}"
    candidates = [n for n in expected if n.startswith(prefix + ".Linux-x86_64.tar.") and "/" not in n]
    require(len(candidates) == 1, "Cannot uniquely identify official ImageBuilder")
    archive = root / "work" / "downloads" / candidates[0]
    if not archive.exists() or sha256(archive) != expected[archive.name]:
        download(base + "/" + archive.name, archive)
    require(sha256(archive) == expected[archive.name], "ImageBuilder checksum mismatch")
    extract = root / "work" / "extracted"
    extract.mkdir(parents=True, exist_ok=True)
    subprocess.run(["tar", "-xf", str(archive), "-C", str(extract)], check=True)
    builders = [p for p in extract.iterdir() if p.is_dir() and (p / "Makefile").exists()]
    require(len(builders) == 1, "Unexpected ImageBuilder layout")
    builders[0].rename(workspace)
    overlay = workspace / "personal-files"
    if config["overlay"]:
        extract_overlay(root / config["overlay"], overlay)
    defaults = overlay / "etc" / "uci-defaults" / "99-personal-builder"
    defaults.parent.mkdir(parents=True, exist_ok=True)
    defaults.write_text(defaults_script(config), encoding="utf-8", newline="\n")
    defaults.chmod(0o755)
    command = ["make", "image", "PROFILE=" + config["profile"],
        "PACKAGES=" + " ".join(package_plan(config)), "FILES=" + str(overlay)]
    if config["target"].startswith("x86/"):
        command.append("ROOTFS_PARTSIZE=" + str(config["output"]["rootfs_size_mb"]))
    # Filesystem filtering is done on produced images as older builders do not
    # necessarily implement ROOTFS_FILESYSTEM. All selected outputs are checked.
    outputs = root / "outputs"
    outputs.mkdir(exist_ok=True)
    log_path = outputs / "build.log"
    secrets = [v for k, v in os.environ.items() if k in {"ROUTER_PASSWORD", "PPPOE_USERNAME", "PPPOE_PASSWORD", "WIFI_PASSWORD"} and v]
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=workspace, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
        for line in process.stdout:
            for value in secrets:
                line = line.replace(value, "***")
            print(line, end="", flush=True)
            log.write(line)
        require(process.wait() == 0, "ImageBuilder failed; inspect build.log")
    manifests = list((workspace / "bin" / "targets").glob("*/*/profiles.json"))
    require(len(manifests) == 1, "Build produced no unique profiles.json")
    produced = json.loads(manifests[0].read_text())
    images = selected_images(produced["profiles"][config["profile"]]["images"], config)
    require(bool(images), "Build produced no requested image")
    for image in images:
        filename = image["name"]
        require(PurePosixPath(filename).name == filename, "Unexpected output filename")
        shutil.copy2(manifests[0].parent / filename, outputs / filename)
    out = config["output"]
    if config["target"].startswith("x86/"):
        for required, image_type in [(out["efi"], "combined-efi"), (out["legacy"], "combined"), (out["rootfs"], "rootfs")]:
            require(not required or any(i["type"] == image_type for i in images), f"Missing requested output: {image_type}")
    if out["vmdk"]:
        for image in images:
            if image["type"] not in ("combined", "combined-efi"):
                continue
            path = outputs / image["name"]
            raw_disk = root / "work" / (path.name.removesuffix(".gz"))
            with gzip.open(path, "rb") as src, raw_disk.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            vmdk = outputs / (raw_disk.stem + ".vmdk")
            subprocess.run(["qemu-img", "convert", "-f", "raw", "-O", "vmdk", "-o", "subformat=streamOptimized", str(raw_disk), str(vmdk)], check=True)
    package_manifests = list(manifests[0].parent.glob("*.manifest"))
    require(bool(package_manifests), "No installed package manifest was generated")
    installed = set()
    for path in package_manifests:
        shutil.copy2(path, outputs / path.name)
        installed.update(line.split()[0] for line in path.read_text().splitlines() if line.strip())
    requested = [p for p in package_plan(config) if not p.startswith("-")]
    require(not (set(requested) - installed), "Installed package manifest is missing requested packages")
    require(not (set(config["remove_packages"]) & installed), "Removed packages are still installed")
    files = [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(outputs.iterdir()) if p.is_file()]
    (outputs / "SHA256SUMS").write_text("".join(f"{f['sha256']}  {f['name']}\n" for f in files), encoding="utf-8")
    summary = {"schema_version": 1, "status": "built-not-boot-tested", "version": config["version"],
        "target": config["target"], "profile": config["profile"], "builder_sha256": expected[archive.name],
        "packages": requested, "files": files, "private_content": has_private_content(config)}
    (outputs / "build-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Build complete. Firmware still requires boot/hardware verification.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/x86-default.json"))
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    try:
        raw = os.environ.get("CONFIG_JSON", "").strip()
        if not raw:
            require(args.config.resolve().is_relative_to(Path("configs").resolve()), "Config path must be under configs/")
            raw = args.config.read_text(encoding="utf-8")
        require(len(raw.encode()) <= 60000, "Config exceeds 60 KB")
        config = normalize(json.loads(raw))
        if args.plan:
            print(json.dumps({"config": config, "packages": package_plan(config), "requires_private_repository": has_private_content(config)}, ensure_ascii=False, indent=2))
        else:
            build(config)
    except (ConfigError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
