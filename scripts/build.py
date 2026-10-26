"""Batch ImageBuilder runner for GitHub Actions; no always-on ASU service.

Run with --plan to validate without building. Custom shell is embedded in the
firmware and never executed as a command on the runner.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import ipaddress
import io
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

if __package__:
    from .builders import resolve as kwrt_builder
else:
    from builders import resolve as kwrt_builder

BASE = "https://downloads.openwrt.org"
REGISTRY = Path(__file__).resolve().parents[1] / "configs" / "builders.json"
PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+_.-]{0,120}$")
CORE = {"base-files", "busybox", "libc", "libgcc", "libgcc1", "kernel", "netifd", "procd", "uci", "fstools"}
FEATURE_PACKAGES = {
    "docker": ["luci-app-dockerman"],
    "usb_net": ["kmod-usb-net-asix", "kmod-usb-net-rtl8152", "kmod-usb-net-cdc-ether", "kmod-usb-net-cdc-ncm"],
    "usb_wireless": ["kmod-mt76-usb", "kmod-rt2800-usb", "iw", "wpad-mbedtls"],
    "wwan": ["luci-proto-modemmanager", "modemmanager", "kmod-usb-net-qmi-wwan", "kmod-usb-serial-option"],
    "istoreos": ["luci-app-istorex"],
    "routerdog": ["luci-app-routerdog"],
    "remove_links": [],
}
KWRT_FEATURES = {"istoreos", "routerdog"}
KWRT_FEATURE_PACKAGES = {"wwan": ["luci-app-wwand", "luci-proto-wwand", "wwand-esim", "wwand-mbim", "wwand-mhi", "wwand-ncm"]}
UNSUPPORTED = set()
LANDING_MODES = {"auto", "overview", "dashboard", "istoreos", "nas", "next-nas", "router", "routerdog"}


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
    builder = raw.get("builder", "official")
    require(builder in ("official", "kwrt"), "Unknown builder")
    version = raw.get("version", "")
    if builder == "official":
        require(isinstance(version, str) and re.fullmatch(r"\d{2}\.\d{2}\.\d+(?:-rc\d+)?", version), "Use a fixed OpenWrt release")
    else:
        require(isinstance(version, str) and version in json.loads(REGISTRY.read_text(encoding="utf-8")), "Use a checksum-pinned Kwrt builder")
    target, profile = raw.get("target", ""), raw.get("profile", "")
    require(isinstance(target, str) and re.fullmatch(r"[a-z0-9_-]+/[a-z0-9_-]+", target), "Invalid target")
    require(isinstance(profile, str) and re.fullmatch(r"[A-Za-z0-9_,.+-]+", profile), "Invalid profile")
    if builder == "kwrt":
        try:kwrt_builder(version,target,json.loads(REGISTRY.read_text(encoding='utf-8')))
        except ValueError as error:raise ConfigError(str(error)) from None
    build_mode = raw.get("build_mode", "experiment")
    require(build_mode in ("release", "device", "experiment"), "Invalid build mode")
    result = {"schema_version": 1, "build_mode": build_mode, "builder": builder, "version": version, "target": target, "profile": profile}
    for key in ("packages", "remove_packages", "themes", "proxies"):
        values = raw.get(key, [])
        require(isinstance(values, list) and len(values) <= 512, f"Invalid {key}")
        require(all(isinstance(p, str) and PACKAGE.fullmatch(p) for p in values), f"Invalid package name in {key}")
        result[key] = sorted(set(values))
    require(not (CORE & set(result["remove_packages"])), "Cannot remove essential system packages")
    require(builder != "kwrt" or "my-default-settings" not in result["remove_packages"], "Kwrt requires my-default-settings")
    selected = set(result["packages"] + result["themes"] + result["proxies"])
    require(not (selected & set(result["remove_packages"])), "Package both added and removed")
    result["firewall"] = raw.get("firewall", "nftables")
    require(result["firewall"] in ("nftables", "iptables"), "Invalid firewall")
    require(not (result["firewall"] == "iptables" and selected.intersection(
        {"luci-app-homeproxy", "luci-app-homeproxy-pro", "luci-app-nikki", "luci-app-xray-status", "luci-app-fchomo"})), "Selected proxy requires nftables")
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
    require(builder == "kwrt" or webserver != "lighttpd", "Lighttpd LuCI integration requires the Kwrt builder")
    signature = system.get("signature", "")
    require(isinstance(signature, str) and len(signature) <= 120 and "\x00" not in signature, "Invalid signature")
    default_theme = system.get("default_theme", "bootstrap")
    require(isinstance(default_theme, str) and re.fullmatch(r"[a-zA-Z0-9_-]+", default_theme), "Invalid default theme")
    theme_package = re.sub(r"^(argon|bootstrap)-(?:light|dark)$", r"\1", default_theme)
    require(f"luci-theme-{theme_package}" in result["themes"], "Default theme must be installed")
    theme_mode = system.get("theme_mode", "auto")
    require(theme_mode in LANDING_MODES, "Invalid landing page mode")
    require(builder == "kwrt" or theme_mode == "auto", "Custom NAS landing pages require a Kwrt builder")
    result["system"] = {"hostname": hostname, "ip": address, "webserver": webserver,
        "signature": signature, "default_theme": default_theme, "theme_mode": theme_mode,
        "https": boolean(system, "https", True), "ipv6": boolean(system, "ipv6", True),
        "password_secret": boolean(system, "password_secret")}
    if 'password_source' in system:
        require(system['password_source'] in ('root','secret'), 'Invalid router password source')
        result['system']['password_source']=system['password_source']
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
    if wan and not lan:
        lan = "eth1" if wan == "eth0" else "eth0"
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
    for feature in KWRT_FEATURES:
        require(builder == "kwrt" or not boolean(features, feature), f"{feature} requires Kwrt")
    require(theme_mode not in ("istoreos", "nas", "next-nas", "router") or boolean(features, "istoreos"), "Selected landing page requires iStoreX")
    require(theme_mode != "routerdog" or boolean(features, "routerdog"), "Selected landing page requires RouterDog")
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
    if 'image_types' in output:
        types=output['image_types']
        require(isinstance(types,list) and len(types)<=32 and all(isinstance(t,str) and re.fullmatch(r'[A-Za-z0-9_.+-]{1,64}',t) for t in types), 'Invalid device image types')
        result['output']['image_types']=sorted(set(types))
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
    if system["webserver"] == "lighttpd":
        packages.add("openssl-util")
    if config["firewall"] == "iptables":
        remove.add("firewall4")
        packages.update(["firewall", "iptables-zz-legacy"])
    for feature, enabled in config["features"].items():
        if enabled:
            packages.update(KWRT_FEATURE_PACKAGES.get(feature, FEATURE_PACKAGES[feature]) if config["builder"] == "kwrt" else FEATURE_PACKAGES[feature])
    if config["features"]["usb_wireless"]:
        remove.update(["wpad-basic-mbedtls", "wpad-basic-wolfssl"])
    if config["builder"] == "kwrt":
        spec = kwrt_builder(config['version'],config['target'],json.loads(REGISTRY.read_text(encoding='utf-8')))
        require(not packages.intersection(spec["exclude_defaults"]), "Selected Kwrt package has missing upstream dependencies")
        remove.update(spec["exclude_defaults"])
        packages.update(p for p in spec["replacement_packages"] if p not in remove)
    require(not (packages & remove), "Generated package selections conflict")
    return sorted(packages) + [f"-{p}" for p in sorted(remove)]


def q(value):
    return shlex.quote(str(value))


def password_hash(password):
    """Use the platform crypto tool; never pass plaintext via argv or a file."""
    require(1 <= len(password.encode("utf-8")) <= 128 and not any(c in password for c in "\x00\r\n"),
            "ROUTER_PASSWORD must contain 1–128 UTF-8 bytes without line breaks")
    try:
        answer = subprocess.run(["openssl", "passwd", "-6", "-stdin"], input=password + "\n",
                                text=True, capture_output=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        raise ConfigError("Cannot securely hash ROUTER_PASSWORD; install OpenSSL on the build host. No plaintext fallback is allowed.") from None
    hashed = answer.stdout.strip()
    require(answer.returncode == 0 and re.fullmatch(r"\$6\$[./A-Za-z0-9]{1,16}\$[./A-Za-z0-9]{86}", hashed),
            "Password hashing failed; no plaintext fallback is allowed")
    return hashed


def router_password(config,env=None):
    env=os.environ if env is None else env
    return 'root' if config['system'].get('password_source')=='root' else env.get('ROUTER_PASSWORD','')


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
        lines.append("[ -z \"$(uci -q get network.wan || true)\" ] || uci -q set network.wan.auto=0")
        lines.append("[ -z \"$(uci -q get network.wan6 || true)\" ] || uci -q set network.wan6.auto=0")
    uci("dhcp.lan.ignore", "0" if net["dhcp"] else "1")
    if not system["ipv6"]:
        for key in ("ra", "dhcpv6", "ndp"):
            uci("dhcp.lan." + key, "disabled")
        lines.append("[ -z \"$(uci -q get network.wan6 || true)\" ] || uci -q set network.wan6.auto=0")
    if net["wan_port"]:
        lines.append("if ! uci -q get network.wan >/dev/null; then uci -q set network.wan=interface; uci -q set network.wan.proto=dhcp; fi")
        uci("network.wan.device", net["wan_port"])
        lines.append(f"[ -z \"$(uci -q get network.wan6 || true)\" ] || uci -q set {q('network.wan6.device=' + net['wan_port'])}")
    if net["lan_ports"]:
        lines += ["bridge_section=''", r"for section in $(uci show network | sed -n 's/^network\.\([^=]*\)=device$/\1/p'); do",
            "  if [ \"$(uci -q get network.$section.name || true)\" = 'br-lan' ]; then bridge_section=$section; break; fi", "done",
            "[ -n \"$bridge_section\" ] || exit 1",
            "uci -q delete network.$bridge_section.ports || true"]
        for port in net["lan_ports"].split():
            lines.append(f"uci -q add_list \"network.$bridge_section.ports={port}\"")
    theme_path = {"bootstrap": "/luci-static/bootstrap", "openwrt": "/luci-static/openwrt.org", "openwrt-2020": "/luci-static/openwrt2020", "argon-light": "/luci-static/argon", "argon-dark": "/luci-static/argon"}.get(system["default_theme"], "/luci-static/" + system["default_theme"])
    uci("luci.main.mediaurlbase", theme_path)
    if system["default_theme"] in ("argon-light", "argon-dark"):
        uci("argon.@global[0].mode", system["default_theme"].split("-")[1])
    if config["builder"] == "kwrt":
        uci("luci.main.landing_page", system["theme_mode"])
    if config["features"]["remove_links"]:
        uci("system.@system[0].links", "0")
        lines += ["for directory in /usr/share/ucode/luci/template/themes /usr/lib/lua/luci/view/themes; do",
            "  [ -d \"$directory\" ] || continue",
            "  find \"$directory\" -type f \\( -name 'footer*.ut' -o -name 'footer*.htm' \\) | while IFS= read -r footer; do",
            "    grep -q personal-footer.js \"$footer\" && continue",
            "    sed -i 's#</body>#<script type=\"module\" src=\"/luci-static/resources/personal-footer.js\"></script></body>#' \"$footer\"",
            "  done", "done"]
    if system["webserver"] == "uhttpd":
        uci("uhttpd.main.redirect_https", "1" if system["https"] else "0")
    elif system["webserver"] == "nginx":
        lines += ["[ ! -x /etc/init.d/uhttpd ] || /etc/init.d/uhttpd disable",
                  "[ ! -x /etc/init.d/lighttpd ] || /etc/init.d/lighttpd disable"]
        if not system["https"]:
            lines += ["uci -q delete nginx._redirect2ssl || true", "uci -q add_list 'nginx._lan.listen=80'", "uci -q add_list 'nginx._lan.listen=[::]:80'"]
    elif system["webserver"] == "lighttpd":
        uci("luci.main.ubuspath", "/cgi-bin/luci/admin/ubus")
        # Generate a unique key on each device, never reuse an upstream PEM.
        lines += ["mkdir -p /etc/lighttpd/conf.d", "umask 077",
            "openssl req -x509 -newkey rsa:2048 -nodes -keyout /tmp/personal-tls.key -out /tmp/personal-tls.crt -days 3650 -subj /CN=OpenWrt-Personal >/dev/null 2>&1",
            "cat /tmp/personal-tls.key /tmp/personal-tls.crt > /etc/lighttpd/conf.d/server.pem",
            "rm -f /tmp/personal-tls.key /tmp/personal-tls.crt"]
        if system["https"]:
            lines.append("sed -i 's/^[ \\t]*# url.redirect/        url.redirect/' /etc/lighttpd/conf.d/82-https.conf")
        else:
            lines.append("sed -i 's/^[ \\t]*url.redirect/        # url.redirect/' /etc/lighttpd/conf.d/82-https.conf")
    if system["signature"]:
        lines.append(f"printf '%s\\n' {q(system['signature'])} >> /etc/banner")
    def secret(name):
        value = env.get(name, "")
        require(bool(value) and "\x00" not in value and "\n" not in value and "\r" not in value, f"Missing or invalid repository secret: {name}")
        return value
    if system["password_secret"]:
        password = router_password(config,env)
        require(bool(password), 'Missing router password')
        require(":" not in password, "ROUTER_PASSWORD cannot contain a colon")
        hashed = password_hash(password)
        # The read-only firmware must not retain the plaintext router password.
        # Only replace root's hash; preserve every other shadow field/account.
        lines += ["test -f /etc/shadow", f"sed -i {q('s|^root:[^:]*:|root:' + hashed + ':|')} /etc/shadow",
                  "chmod 600 /etc/shadow",
                  f"test \"$(awk -F: '$1==\"root\" {{print $2}}' /etc/shadow)\" = {q(hashed)}"]
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


def extract_overlay(archive: Path, destination: Path, allow_ipk=False):
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
            actual = 0
            while chunk := stream.read(65536):
                actual += len(chunk)
                require(actual <= size and actual <= 128 * 1024 * 1024, "Archive entry exceeds declared size")
                out.write(chunk)
            require(actual == size, "Archive entry size mismatch")
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
    elif archive.name.endswith(".7z"):
        seven = shutil.which("7zz") or shutil.which("7z")
        require(bool(seven), "7-Zip is not installed on the build runner")
        listing = subprocess.run([seven, "l", "-slt", "-ba", "--", str(archive.resolve())],
            text=True, capture_output=True, timeout=30, check=True).stdout
        for block in re.split(r"\r?\n\r?\n", listing.strip()):
            fields = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
            require("Path" in fields, "Unexpected 7z listing")
            name = fields["Path"]
            safe_member(name)
            require(not any(c in name for c in "\r\n\x00"), "Unsupported archive filename")
            attributes = fields.get("Attributes", "")
            require(not any(k in fields for k in ("Symbolic Link", "Hard Link")) and not re.search(r"(?:^|\s)l[rwx-]", attributes), "Overlay links are not supported")
            require(fields.get("Encrypted", "-") == "-", "Encrypted archives are not supported")
            if fields.get("Folder") == "+" or attributes.startswith("D"):
                continue
            require(fields.get("Size", "").isdigit(), "Invalid 7z entry size")
            size = int(fields["Size"])
            require(size <= 128 * 1024 * 1024, "Expanded overlay exceeds limits")
            process = subprocess.Popen([seven, "x", "-so", "-spd", "--", str(archive.resolve()), name],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                write(name, size, process.stdout)
                require(process.wait(timeout=30) == 0, "7z extraction failed")
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
    else:
        raise ConfigError("Unsupported overlay archive format")
    require(not list(destination.rglob("*.apk")), "Custom APK installation is not supported; use repository package names")
    require(allow_ipk or not list(destination.rglob("*.ipk")), "Custom IPK packages require the Kwrt/opkg builder")


def ipk_control(path,architecture='x86_64'):
    raw = path.read_bytes()
    if raw.startswith(b"!<arch>\n"):
        offset, control = 8, None
        while offset + 60 <= len(raw):
            header = raw[offset:offset + 60]
            require(header[58:60] == b"`\n", "Invalid IPK ar header")
            size = int(header[48:58].strip())
            name = header[:16].decode().strip().rstrip("/")
            offset += 60
            require(0 <= size <= len(raw) - offset, "Truncated IPK")
            if name == "control.tar.gz":
                control = raw[offset:offset + size]
            offset += size + size % 2
    else:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as outer:
            member = next((m for m in outer if m.name.removeprefix("./") == "control.tar.gz"), None)
            require(member is not None and member.isfile() and member.size <= 1024 * 1024, "Invalid IPK control archive")
            control = outer.extractfile(member).read()
    require(control is not None and len(control) <= 1024 * 1024, "IPK lacks control metadata")
    with tarfile.open(fileobj=io.BytesIO(control), mode="r:gz") as inner:
        member = next((m for m in inner if m.name.removeprefix("./") == "control"), None)
        require(member is not None and member.isfile() and member.size <= 64000, "Invalid IPK control metadata")
        fields = dict(line.split(": ", 1) for line in inner.extractfile(member).read().decode().splitlines() if ": " in line and not line.startswith(" "))
    require(PACKAGE.fullmatch(fields.get("Package", "")) is not None, "Invalid custom IPK package name")
    require(fields["Package"] not in CORE and not fields["Package"].startswith("kmod-"), "Use the builder's own core and kernel-module packages")
    require(fields.get("Architecture") in ("all", architecture), "IPK architecture does not match the selected device builder")
    return fields


def prepare_custom_ipks(overlay,architecture='x86_64'):
    """Stage packages for device-side installation, never host-side scripts."""
    packages, dependencies, staged = [], set(), []
    for path in sorted(overlay.rglob("*.ipk")):
        fields = ipk_control(path,architecture)
        name = fields["Package"]
        require(name not in {p["name"] for p in packages}, "Duplicate custom IPK package")
        packages.append({"name": name, "version": fields.get("Version", ""), "sha256": sha256(path),
                         "installation": "first-boot-on-device"})
        for dep in fields.get("Depends", "").split(","):
            if not dep.strip():
                continue
            dependency = dep.strip().split()[0]
            require(PACKAGE.fullmatch(dependency) is not None, "Unsupported custom IPK dependency")
            dependencies.add(dependency)
        destination = overlay / "root" / "personal-packages" / (sha256(path) + ".ipk.payload")
        destination.parent.mkdir(parents=True, exist_ok=True)
        path.rename(destination)
        staged.append("/root/personal-packages/" + destination.name)
    if packages:
        script = overlay / "etc" / "uci-defaults" / "98-personal-packages"
        script.parent.mkdir(parents=True, exist_ok=True)
        install_paths = [p.removesuffix(".payload") for p in staged]
        renames = "".join("if [ -f " + q(src) + " ]; then mv " + q(src) + " " + q(dst) + "; fi\n" for src, dst in zip(staged, install_paths))
        script.write_text("#!/bin/sh\nset -eu\n# Runs on the router, never the Actions host.\n" + renames +
            "opkg install " + " ".join(q(p) for p in install_paths) + "\n"
            "rm -f " + " ".join(q(p) for p in install_paths) + "\nexit 0\n", encoding="utf-8")
        script.chmod(0o755)
    return packages, dependencies - {p["name"] for p in packages}


def download(url, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "OpenWrt-Personal-Builder/0.1"})
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "OpenWrt-Personal-Builder/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def selected_images(images, config):
    out = config["output"]
    matches = []
    for image in images:
        fs, kind = image.get("filesystem"), image.get("type")
        if fs == "targz":
            if out["rootfs"]:
                matches.append(image)
        elif fs == out['filesystem'] or (not config['target'].startswith('x86/') and not fs and kind in out.get('image_types',[])):
            if config["target"].startswith("x86/"):
                if not image.get("name", "").endswith(".vmdk.zip") and ((kind == "combined" and out["legacy"]) or (kind == "combined-efi" and out["efi"])):
                    matches.append(image)
            elif kind in (out.get('image_types') or ("sysupgrade", "factory", "sdcard", "sdcard-sysupgrade", "combined", "combined-efi", "emmc_burn", "bin", "trx", "firmware", "nand-sysupgrade", "nand-factory")):
                matches.append(image)
    return matches


def translation_alias(workspace, name, dependency):
    """The publisher embeds zh-cn data but leaves obsolete split-package deps.

    This explicitly labelled metadata-only compatibility package depends on the
    real runtime package. Presence of the actual translation is checked later.
    """
    control = (f"Package: {name}\nVersion: 1.0+pb1\nArchitecture: all\nDepends: {dependency}\n"
        "Section: luci\nDescription: Personal Builder compatibility alias; Chinese translation is embedded in the runtime package.\n")
    def member_tar(members):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for path, data in members.items():
                info = tarfile.TarInfo(path)
                info.size = len(data)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(data))
        return buffer.getvalue()
    payload = member_tar({"./debian-binary": b"2.0\n", "./control.tar.gz": member_tar({"./control": control.encode()}),
                          "./data.tar.gz": member_tar({})})
    destination = workspace / "packages" / (name + "_1.0+pb1_all.ipk")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def prepare_kwrt(workspace):
    """Adapt the published server-oriented builder without weakening failures."""
    repositories = workspace / "repositories.conf"
    source = repositories.read_text()
    require("file://www/wwwroot/dl.openwrt.ai/" in source, "Kwrt repository layout changed; review required")
    source = source.replace("file://www/wwwroot/dl.openwrt.ai/", "https://dl.openwrt.ai/")
    for line in source.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            parts = line.split()
            require(len(parts) == 3 and (parts[2].startswith("https://dl.openwrt.ai/") or parts[2] == "file:packages"), "Unexpected Kwrt repository URL")
    repositories.write_text(source)
    makefile = workspace / "Makefile"
    source = makefile.read_text()
    permissive = "$(OPKG) install --force-maintainer $(BUILD_PACKAGES) luci-i18n-base-zh-cn || true"
    require(source.count(permissive) == 1, "Kwrt package installer layout changed; review required")
    source = source.replace(permissive, permissive.removesuffix(" || true"))
    automatic = ('\t$(if $(USER_FILES), \\\n\tfind $(USER_FILES) -name "*.ipk" -print0 | \\\n'
        "\twhile IFS= read -r -d '' ipk; do \\\n\t\t$(OPKG) install \"$$ipk\" && rm -f \"$$ipk\" || true; \\\n\tdone; \\\n\t)\n")
    source = source.replace(automatic, "\t# Personal IPKs are staged for device-side first boot, never host installation.\n")
    require('find $(USER_FILES) -name "*.ipk"' not in source, "Unsafe Kwrt host-side custom IPK installer could not be disabled")
    makefile.write_text(source)
    translation_alias(workspace, "luci-i18n-base-zh-cn", "luci-base")
    translation_alias(workspace, "luci-i18n-ttyd-zh-cn", "luci-app-ttyd")


def manifest_packages(text):
    """Only accept package-manager manifest rows, not make command echo."""
    return {m.group(1) for line in text.splitlines()
            if (m := re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9+_.-]*)\s+-\s+\S+", line.strip()))}


def run_logged(command, workspace, log, secrets):
    process = subprocess.Popen(command, cwd=workspace, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, errors="replace")
    lines = []
    for line in process.stdout:
        for value in secrets:
            line = line.replace(value, "***")
        print(line, end="", flush=True)
        log.write(line)
        lines.append(line)
    return process.wait(), "".join(lines)


def dependency_preflight(workspace, profile, packages, log, secrets):
    print("依赖预检：使用所选 ImageBuilder 的包管理器解析实际依赖。", flush=True)
    code, text = run_logged(["make", "manifest", "PROFILE=" + profile,
                            "PACKAGES=" + " ".join(packages), "STRIP_ABI=1"], workspace, log, secrets)
    require(code == 0, "依赖预检失败：软件包缺失、依赖冲突或软件源下载失败；请查看 build.log，尚未生成映像")
    installed = manifest_packages(text)
    requested = {p for p in packages if not p.startswith("-")}
    missing = requested - installed
    require(not missing, "依赖预检未找到请求的软件包：" + ", ".join(sorted(missing)))
    restored = {p[1:] for p in packages if p.startswith("-")} & installed
    require(not restored, "依赖预检：已移除的软件包被依赖重新加入：" + ", ".join(sorted(restored)))
    print(f"依赖预检通过：解析出 {len(installed)} 个软件包。", flush=True)
    return installed


def build(config, root=Path(".")):
    require(sys.platform.startswith("linux"), "Real ImageBuilder builds require Linux / GitHub Actions")
    root = root.resolve()
    workspace = root / "work" / "builder"
    require(not workspace.exists(), "Build directory already exists; use a fresh workspace")
    kwrt = kwrt_builder(config['version'],config['target'],json.loads(REGISTRY.read_text(encoding='utf-8'))) if config['builder']=='kwrt' else None
    require(not kwrt or not kwrt.get('blocked_reason'),kwrt.get('blocked_reason','') if kwrt else '')
    base = kwrt["base"] if kwrt else f"{BASE}/releases/{config['version']}/targets/{config['target']}"
    metadata = get_json(base+'/'+(kwrt.get('profiles_file','profiles.json') if kwrt else 'profiles.json'))
    require(config["profile"] in metadata["profiles"], "Profile not found in the selected target")
    available_images = metadata["profiles"][config["profile"]]["images"]
    require(selected_images(available_images, config) or (kwrt and config["target"] == "x86/64" and config["output"]["filesystem"] == "ext4"), "Requested output is unavailable in this builder")
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
    if kwrt:
        candidates = [kwrt["archive"]]
        require(expected.get(kwrt["archive"]) == kwrt["sha256"], "Kwrt upstream builder changed; pinned registry needs review")
    else:
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
    if kwrt:
        prepare_kwrt(workspace)
    overlay = workspace / "personal-files"
    if config["overlay"]:
        extract_overlay(root / config["overlay"], overlay, allow_ipk=bool(kwrt))
    custom_packages, dependencies = prepare_custom_ipks(overlay,metadata['arch_packages']) if kwrt else ([], set())
    custom_names = {p["name"] for p in custom_packages}
    factory = set(metadata.get("default_packages", [])) | set(metadata["profiles"][config["profile"]].get("device_packages", []))
    existing = (factory | {p for p in package_plan(config) if not p.startswith("-")}) - set(config["remove_packages"])
    require(not custom_names.intersection(existing), "Remove a conflicting factory/repository package before adding its custom IPK")
    require(not dependencies.intersection(config["remove_packages"]), "Custom IPK needs a package selected for removal")
    build_packages = package_plan(config) + sorted(dependencies - set(package_plan(config)))
    if config["features"]["remove_links"]:
        asset = overlay / "www" / "luci-static" / "resources" / "personal-footer.js"
        asset.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REGISTRY.parent.parent / "firmware-assets" / "personal-footer.js", asset)
    defaults = overlay / "etc" / "uci-defaults" / "99-personal-builder"
    defaults.parent.mkdir(parents=True, exist_ok=True)
    defaults.write_text(defaults_script(config), encoding="utf-8", newline="\n")
    defaults.chmod(0o755)
    command = ["make", "image", "PROFILE=" + config["profile"],
        "PACKAGES=" + " ".join(build_packages), "FILES=" + str(overlay)]
    if config["target"].startswith("x86/"):
        command.append("ROOTFS_PARTSIZE=" + str(config["output"]["rootfs_size_mb"]))
        if config["output"]["filesystem"] == "ext4":
            command.append("CONFIG_TARGET_ROOTFS_EXT4FS=y")
        if kwrt and config["output"]["vmdk"]:
            command.append("CONFIG_VMDK_IMAGES=y")
    elif kwrt:
        command.append('CONFIG_TARGET_ROOTFS_TARGZ=y')
    # Filesystem filtering is done on produced images as older builders do not
    # necessarily implement ROOTFS_FILESYSTEM. All selected outputs are checked.
    outputs = root / "outputs"
    outputs.mkdir(exist_ok=True)
    log_path = outputs / "build.log"
    secrets = [v for k, v in os.environ.items() if k in {"ROUTER_PASSWORD", "PPPOE_USERNAME", "PPPOE_PASSWORD", "WIFI_PASSWORD"} and v]
    with log_path.open("w", encoding="utf-8") as log:
        resolved = dependency_preflight(workspace, config["profile"], build_packages, log, secrets)
        log.write("\n=== Dependency preflight passed; generating images ===\n")
        code, _ = run_logged(command, workspace, log, secrets)
        require(code == 0, "映像生成失败：依赖预检已通过，请检查 build.log 中的空间、下载或映像错误")
    manifests = list((workspace / "bin" / "targets").glob("*/*/profiles.json"))
    require(len(manifests) == 1, "Build produced no unique profiles.json")
    produced = json.loads(manifests[0].read_text())
    if kwrt:
        roots = [i for i in produced["profiles"][config["profile"]]["images"] if i.get("filesystem") == "targz"]
        require(len(roots) == 1, "Kwrt translation compatibility verification needs ROOTFS output")
        with tarfile.open(manifests[0].parent / roots[0]["name"], "r:gz") as root_archive:
            names = {m.name.removeprefix("./") for m in root_archive}
        require("usr/lib/lua/luci/i18n/base.zh-cn.lmo" in names, "Kwrt embedded Chinese translation missing")
        require(all("root/personal-packages/" + p["sha256"] + ".ipk.payload" in names for p in custom_packages), "Custom IPK payload was lost before device-side installation")
        if "usr/lib/opkg/info/luci-i18n-ttyd-zh-cn.control" in names:
            require("usr/lib/lua/luci/i18n/ttyd.zh-cn.lmo" in names, "Kwrt ttyd translation compatibility check failed")
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
        native_vmdks = [i for i in produced["profiles"][config["profile"]]["images"]
            if i.get("name", "").endswith(".vmdk.zip") and i.get("filesystem") == out["filesystem"] and
            i.get("type") in {x["type"] for x in images if x["type"] in ("combined", "combined-efi")}]
        if kwrt:
            require(len(native_vmdks) == sum(i["type"] in ("combined", "combined-efi") for i in images), "Kwrt native ESXi VMDK output missing")
            for image in native_vmdks:
                filename = image["name"]
                require(PurePosixPath(filename).name == filename, "Unexpected VMDK archive filename")
                source = manifests[0].parent / filename
                with zipfile.ZipFile(source) as archive_zip:
                    require(archive_zip.testzip() is None, "Kwrt VMDK archive is corrupt")
                    require(all(PurePosixPath(n).name == n and n.endswith(".vmdk") for n in archive_zip.namelist()), "Unexpected native VMDK archive layout")
                shutil.copy2(source, outputs / filename)
        for image in ([] if kwrt else images):
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
    require(not custom_names.intersection(installed), "A custom IPK was unexpectedly installed on the build host")
    removed = {p[1:] for p in package_plan(config) if p.startswith("-")}
    require(not (removed & installed), "Removed packages are still installed")
    files = [{"name": p.name, "bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(outputs.iterdir()) if p.is_file()]
    (outputs / "SHA256SUMS").write_text("".join(f"{f['sha256']}  {f['name']}\n" for f in files), encoding="utf-8")
    summary = {"schema_version": 1, "status": "built-not-boot-tested", "version": config["version"],
        "target": config["target"], "profile": config["profile"], "builder": config["builder"], "builder_sha256": expected[archive.name],
        "packages": requested, "files": files, "private_content": has_private_content(config),
        "dependency_preflight": {"status": "passed", "resolved_package_count": len(resolved)},
        "provenance": {"source_commit": os.environ.get("GITHUB_SHA", ""), "run_id": os.environ.get("GITHUB_RUN_ID", ""),
                       "configuration_sha256": hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}}
    if kwrt:
        summary["compatibility_adjustments"] = {"excluded_broken_defaults": kwrt["exclude_defaults"],
            "replacement_packages": kwrt["replacement_packages"], "translation_aliases": "zh-cn data verified inside rootfs"}
    summary["custom_packages"] = custom_packages
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
            if os.environ.get("ENFORCE_APPROVED_UPSTREAM") == "true":
                from scripts.upstream import guard
                guard(config)
            build(config)
            if os.environ.get("ENFORCE_APPROVED_UPSTREAM") == "true":
                guard(config)
    except (ConfigError, ValueError, OSError, tarfile.TarError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
