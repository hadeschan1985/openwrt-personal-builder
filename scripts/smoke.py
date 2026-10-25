"""Isolated x86 boot regression. Never boots a user-supplied image on the host.

QA keys/passwords are ephemeral; QA firmware must not be uploaded as usable firmware.
QEMU has no host filesystem shares and no outbound network access.
"""
from __future__ import annotations

import argparse
import gzip
import http.client
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import tarfile
import time
import urllib.parse
import zipfile

from scripts.build import normalize, require

QA = Path("work/qa")


def test_ipk():
    def pack(entries):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name, data, mode in entries:
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), mode
                archive.addfile(info, io.BytesIO(data))
        return buffer.getvalue()
    control = b"Package: personal-qa-addon\nVersion: 1.0\nArchitecture: all\nDepends: libc\nDescription: Disposable device-side package regression\n"
    postinst = b'#!/bin/sh\ncase "${IPKG_INSTROOT:-}" in ""|"/") ;; *) exit 77;; esac\nprintf device-only > /etc/qa-package-script-marker\nexit 0\n'
    return pack([("./debian-binary", b"2.0\n", 0o644),
        ("./control.tar.gz", pack([("./control", control, 0o644), ("./postinst", postinst, 0o755)]), 0o644),
        ("./data.tar.gz", pack([("./etc/qa-package-file", b"QA package data\n", 0o644)]), 0o644)])


def prepare(source="official", variant="standard"):
    QA.mkdir(parents=True, exist_ok=True)
    key = QA / "identity"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
    Path("overlays").mkdir(exist_ok=True)
    overlay = Path("overlays/qa.zip")
    with zipfile.ZipFile(overlay, "w") as archive:
        archive.writestr("etc/dropbear/authorized_keys", key.with_suffix(".pub").read_bytes())
        archive.writestr("etc/qa-overlay-marker", "QA overlay applied\n")
        if source == "kwrt":
            archive.writestr("custom/personal-qa-addon.ipk", test_ipk())
    config = json.loads(Path("configs/x86-default.json").read_text())
    config["builder"] = source
    if source == "kwrt":
        config["version"] = "kwrt-25.12-20261012"
        config["proxies"] = ["luci-app-passwall"]
        config["themes"] += ["luci-theme-argon"]
        config["system"]["default_theme"] = "argon"
        config["features"].update(istoreos=True, routerdog=True)
        config["system"]["theme_mode"] = "nas"
    config["system"].update(hostname="Personal-QA", signature="Personal QA marker", password_secret=True)
    config["features"]["remove_links"] = True
    config["network"].update(wan_port="eth1", lan_ports="eth0")
    config["output"].update(rootfs_size_mb=512, vmdk=True, rootfs=True)
    if variant != "standard":
        config["output"].update(efi=False, vmdk=False, rootfs=False)
    if variant == "side-ext4":
        config["system"].update(ip="192.168.1.253", ipv6=False, https=False)
        config["network"].update(mode="side", gateway="192.168.1.254", dhcp=False)
        config["output"]["filesystem"] = "ext4"
    elif variant in ("nginx", "lighttpd", "nginx-https", "lighttpd-https"):
        config["system"].update(webserver=variant.split("-")[0], https=variant.endswith("-https"))
    elif variant == "iptables":
        config["firewall"] = "iptables"
    elif variant == "features":
        config["features"].update(docker=True, usb_net=True, usb_wireless=True, wwan=True)
        config["output"].update(filesystem="ext4", rootfs_size_mb=1024)
        config["system"]["default_theme"] = "bootstrap-dark"
    config["overlay"] = overlay.as_posix()
    config["defaults"] = "printf 'first-boot-ok\\n' > /etc/qa-init-marker"
    config = normalize(config)
    (QA / "config.json").write_text(json.dumps(config), encoding="utf-8")
    Path("configs/qa-generated.json").write_text(json.dumps(config), encoding="utf-8")
    password = secrets.token_urlsafe(24)
    # Ephemeral test-only value; no repository secret is read or copied.
    print("::add-mask::" + password)
    with open(os.environ["GITHUB_ENV"], "a") as stream:
        stream.write("ROUTER_PASSWORD=" + password + "\n")
    (QA / "test-password").write_text(password)
    print("Prepared isolated QA configuration; QA firmware will not be published.")


def ssh(command, timeout=30):
    return subprocess.run(["ssh", "-i", str(QA / "identity"), "-p", "2222",
        "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR", "root@127.0.0.1", "sh"],
        input=command, text=True, capture_output=True, timeout=timeout)


def free_ports():
    for port in (2222, 18080, 18443):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", port))


def web_probe(https, password, ip):
    if https:
        connection = http.client.HTTPSConnection("127.0.0.1", 18443,
            context=ssl._create_unverified_context(), timeout=20)
    else:
        connection = http.client.HTTPConnection("127.0.0.1", 18080, timeout=20)
    try:
        # Preserve the guest's private Host header. OpenWrt's RFC1918 filter
        # correctly rejects private-network requests addressed to localhost.
        connection.request("GET", "/cgi-bin/luci/", headers={"Host": ip})
        response = connection.getresponse()
        body = response.read(1024 * 512).decode(errors="replace")
        login_status = response.status
        login_form = "luci_username" in body and "luci_password" in body
        # LuCI deliberately returns 403 with the unauthenticated login form.
        require(response.status == 200 or (response.status == 403 and login_form), f"LuCI returned HTTP {response.status}: {body[-400:]}")
        require("luci" in body.lower(), "LuCI login page was not returned")
        require("personal-footer.js" in body, "Promotion filter was not included in LuCI footer")
        require(login_form, "Password-protected LuCI login form was not returned")
        connection.request("POST", "/cgi-bin/luci/", body=urllib.parse.urlencode({"luci_username": "root", "luci_password": password}),
            headers={"Host": ip, "Content-Type": "application/x-www-form-urlencoded"})
        response = connection.getresponse()
        body = response.read(1024 * 512).decode(errors="replace")
        cookie = response.getheader("Set-Cookie", "").split(";", 1)[0]
        for _ in range(5):
            if response.status not in (301, 302, 303, 307, 308):
                break
            location = urllib.parse.urlsplit(response.getheader("Location", "/cgi-bin/luci/"))
            path = location.path + ("?" + location.query if location.query else "")
            connection.request("GET", path, headers={"Host": ip, "Cookie": cookie})
            response = connection.getresponse()
            body = response.read(1024 * 512).decode(errors="replace")
        require(response.status == 200 and "luci_password" not in body and "luci" in body.lower(),
                f"Authenticated LuCI page failed: HTTP {response.status}")
        require(cookie.startswith("sysauth") and "=" in cookie, "LuCI did not issue an authenticated session cookie")
        match = re.search(r'''["']?ubuspath["']?\s*:\s*("(?:[^"\\]|\\.)*"|'[^']*')''', body)
        ubuspath = json.loads(match.group(1)) if match and match.group(1).startswith('"') else match.group(1).strip("'") if match else "/ubus/"
        require(ubuspath.startswith("/") and not ubuspath.startswith("//"), "Unexpected LuCI RPC path")
        request = {"jsonrpc": "2.0", "id": 1, "method": "call",
            "params": [cookie.split("=", 1)[1], "system", "board", {}]}
        connection.request("POST", ubuspath, body=json.dumps(request),
            headers={"Host": ip, "Cookie": cookie, "Content-Type": "application/json"})
        rpc = connection.getresponse()
        payload = rpc.read(1024 * 512)
        require(rpc.status == 200, f"LuCI RPC endpoint failed: HTTP {rpc.status} at {ubuspath}")
        answer = json.loads(payload)
        require(answer.get("result", [1])[0] == 0 and answer["result"][1].get("hostname") == "Personal-QA",
                "LuCI RPC did not return the expected guest board")
        return {"protocol": "https" if https else "http", "login_status": login_status,
                "authenticated_status": response.status, "rpc_status": rpc.status, "bytes": len(body)}
    finally:
        connection.close()


def boot(image: Path, mode: str, config):
    free_ports()
    log = QA / f"serial-{mode}.log"
    ip = config["system"]["ip"]
    command = ["qemu-system-x86_64", "-accel", "tcg,thread=multi", "-cpu", "max", "-smp", "2",
        "-m", "768", "-display", "none", "-monitor", "none", "-serial", f"file:{log}",
        "-no-reboot", "-snapshot", "-drive", f"file={image.resolve()},format={'vmdk' if image.suffix == '.vmdk' else 'raw'},if=virtio",
        "-netdev", "user,id=lan,net=192.168.1.0/24,host=192.168.1.2,restrict=on,"
            f"hostfwd=tcp:127.0.0.1:2222-{ip}:22,hostfwd=tcp:127.0.0.1:18080-{ip}:80,"
            f"hostfwd=tcp:127.0.0.1:18443-{ip}:443",
        "-device", "virtio-net-pci,netdev=lan", "-netdev", "user,id=wan,restrict=on",
        "-device", "virtio-net-pci,netdev=wan"]
    if mode == "uefi":
        code = Path("/usr/share/OVMF/OVMF_CODE_4M.fd")
        variables = QA / "OVMF_VARS_4M.fd"
        shutil.copyfile("/usr/share/OVMF/OVMF_VARS_4M.fd", variables)
        command += ["-drive", f"if=pflash,format=raw,readonly=on,file={code}",
                    "-drive", f"if=pflash,format=raw,file={variables}"]
    started = time.monotonic()
    with (QA / f"qemu-{mode}.log").open("w") as stderr:
        process = subprocess.Popen(command, stdout=stderr, stderr=stderr)
        try:
            deadline = started + 300
            while time.monotonic() < deadline:
                require(process.poll() is None, f"QEMU exited unexpectedly in {mode}")
                probe = ssh("test ! -f /etc/uci-defaults/99-personal-builder && test -f /etc/qa-init-marker\n")
                if probe.returncode == 0:
                    break
                time.sleep(5)
            else:
                diagnostic = ssh("uci show network; uci show system; ls -l /etc/uci-defaults/; ls -l /etc/qa-*; logread | tail -80\n")
                (QA / f"guest-{mode}.log").write_text("Last readiness check: " + probe.stderr + "\n" + diagnostic.stdout + diagnostic.stderr)
                raise RuntimeError(f"SSH/first boot did not become ready in {mode}; inspect serial log")
            checks = """set -eu
test "$(uci -q get system.@system[0].hostname)" = Personal-QA
test "$(uci -q get network.lan.ipaddr)" = HOST_IP
test "$(uci -q get network.wan.device)" = eth1
test "$(uci -q get dhcp.lan.ignore)" = DHCP_IGNORE
grep -q 'Personal QA marker' /etc/banner
grep -q first-boot-ok /etc/qa-init-marker
grep -q 'QA overlay applied' /etc/qa-overlay-marker
test "$(uci -q get luci.main.mediaurlbase)" = THEME_PATH
test ! -f /etc/uci-defaults/99-personal-builder
test "$(awk -F: '$1=="root" {print $2}' /etc/shadow)" != ''
ubus call system board
df -h /
echo ALL_GUEST_ASSERTIONS_PASSED
"""
            theme = "/luci-static/" + config["system"]["default_theme"]
            if config["system"]["webserver"] == "uhttpd":
                checks += 'test "$(uci -q get uhttpd.main.redirect_https)" = ' + ("1" if config["system"]["https"] else "0") + "\n"
            if config["network"]["mode"] == "side":
                checks += 'test "$(uci -q get network.wan.auto)" = 0\ntest "$(uci -q get dhcp.lan.ra)" = disabled\n'
                checks += 'test "$(uci -q get network.lan.gateway)" = 192.168.1.254\n'
            if config["firewall"] == "iptables":
                checks += "iptables --version | grep -q legacy\ntest ! -x /sbin/fw4\n"
            if config["features"]["wwan"]:
                for package in ("luci-app-wwand", "luci-proto-wwand", "wwand-esim", "wwand-mbim", "wwand-mhi", "wwand-ncm"):
                    checks += "opkg status " + package + " | grep -q 'Status: install ok installed'\n"
            if config["features"]["docker"]:
                checks += 'docker_ok=0\nfor attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do if docker info > /tmp/qa-docker-info 2>/dev/null; then docker_ok=1; break; fi; sleep 5; done\ntest "$docker_ok" = 1\n'
            if config["builder"] == "kwrt":
                checks += "test \"$(uci -q get luci.main.landing_page)\" = nas\n"
                checks += "test -f /usr/lib/lua/luci/controller/istorex.lua\ntest -f /usr/lib/lua/luci/controller/routerdog.lua\n"
                checks += "test ! -f /etc/uci-defaults/98-personal-packages\ngrep -q device-only /etc/qa-package-script-marker\ngrep -q 'QA package data' /etc/qa-package-file\n"
            result = ssh(checks.replace("THEME_PATH", theme).replace("HOST_IP", ip).replace("DHCP_IGNORE", "0" if config["network"]["dhcp"] else "1"), timeout=150)
            (QA / f"guest-{mode}.log").write_text(result.stdout + result.stderr)
            if result.returncode != 0:
                diagnostic = ssh("uci -q get luci.main.landing_page; ls -l /usr/lib/lua/luci/controller/istorex.lua /usr/lib/lua/luci/controller/routerdog.lua; ls -l /etc/uci-defaults/98* /etc/qa-*; opkg status personal-qa-addon; logread | grep -Ei 'opkg|personal|lighttpd|uci-defaults' | tail -40\n")
                with (QA / f"guest-{mode}.log").open("a") as log:
                    log.write("\nFAILURE_DIAGNOSTICS\n" + diagnostic.stdout + diagnostic.stderr)
            require(result.returncode == 0 and "ALL_GUEST_ASSERTIONS_PASSED" in result.stdout,
                f"Guest assertions failed in {mode}: {result.stderr[-1000:]}")
            web = web_probe(config["system"]["https"], (QA / "test-password").read_text(), ip)
            # Authenticate to ubus using the random test password without logging it.
            login = json.dumps({"username": "root", "password": (QA / "test-password").read_text()})
            import shlex
            authenticated = ssh("ubus call session login " + shlex.quote(login) + "\n")
            require(authenticated.returncode == 0 and '"ubus_rpc_session"' in authenticated.stdout,
                    f"Root password login failed in {mode}")
            return {"mode": mode, "status": "passed", "seconds": round(time.monotonic() - started, 1),
                "checks": ["boot", "first-boot-script", "overlay", "hostname", "lan-ip", "wan-port", "dhcp", "theme", "authenticated-luci", "root-password"], "web": web}
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def run():
    config = json.loads((QA / "config.json").read_text())
    results = []
    images = []
    for path in sorted(Path("outputs").glob("*combined*.img.gz")):
        disk = QA / path.name.removesuffix(".gz")
        with gzip.open(path, "rb") as src, disk.open("wb") as dst:
            shutil.copyfileobj(src, dst)
        images.append((disk, "uefi" if "combined-efi" in path.name else "bios"))
    vmdks = sorted(Path("outputs").glob("*combined.vmdk"))
    expected_modes = int(config["output"]["efi"]) + int(config["output"]["legacy"])
    require(len(images) == expected_modes, "QA is missing a requested disk image")
    if config["output"]["vmdk"]:
        if config["builder"] == "kwrt":
            archives = sorted(Path("outputs").glob("*squashfs-combined.vmdk.zip"))
            require(len(archives) == 1, "QA is missing native Kwrt VMDK")
            native = QA / "native-vmdk"
            native.mkdir(exist_ok=True)
            with zipfile.ZipFile(archives[0]) as archive:
                for member in archive.infolist():
                    require(Path(member.filename).name == member.filename and member.filename.endswith(".vmdk"), "Unsafe VMDK archive member")
                    with archive.open(member) as src, (native / member.filename).open("wb") as dst:
                        shutil.copyfileobj(src, dst)
            descriptors = [p for p in native.glob("*.vmdk") if not p.name.endswith("-flat.vmdk")]
            require(len(descriptors) == 1, "Native VMDK descriptor missing")
            images.append((descriptors[0], "native-vmdk-bios"))
        else:
            require(bool(vmdks), "QA is missing VMDK")
            images.append((vmdks[0], "vmdk-bios"))
        expected_modes += 1
    try:
        for image, mode in images:
            print("Boot regression:", mode, flush=True)
            results.append(boot(image, mode, config))
            print("Passed:", mode, flush=True)
    finally:
        report = {"builder": config["builder"], "version": config["version"], "results": results,
            "hardware_tested": False, "network": "isolated; outbound disabled; loopback forwards only"}
        (QA / "boot-report.json").write_text(json.dumps(report, indent=2))
    require(len(results) == expected_modes, "Not all boot modes passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "run"])
    parser.add_argument("--source", default="official", choices=["official", "kwrt"])
    parser.add_argument("--variant", default="standard", choices=["standard", "side-ext4", "nginx", "lighttpd", "nginx-https", "lighttpd-https", "iptables", "features"])
    args = parser.parse_args()
    prepare(args.source, args.variant) if args.action == "prepare" else run()
