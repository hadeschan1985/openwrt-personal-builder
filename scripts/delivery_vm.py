"""Boot the exact delivered x86 images, without adding test keys or changing them.

Only loopback forwards; all guest outbound traffic is disabled. Guest commands
run on QEMU snapshots. Never export serial/SSH output or repository passwords.
"""
from __future__ import annotations
import gzip
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.parse
import zipfile

from scripts.build import require, package_plan, PACKAGE, q
from scripts.delivery import config as load_config, policy


def topology(config):
    lan = config["network"]["lan_ports"].split() or ["eth0"]
    wan = config["network"]["wan_port"] or "eth1"
    count = max(1, *(int(p[3:]) for p in [*lan, wan])) + 1
    require(count <= 8, "VM verification supports at most eight NICs")
    return count, int(lan[0][3:])


def ssh(command, password, timeout=30):
    # sshpass reads the secret from the child environment, never argv or logs.
    return subprocess.run(["sshpass", "-e", "ssh", "-p", "2222", "-o", "PreferredAuthentications=password",
        "-o", "PubkeyAuthentication=no", "-o", "NumberOfPasswordPrompts=1", "-o", "ConnectTimeout=4",
        "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
        "root@127.0.0.1", "sh"], input=command, capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "SSHPASS": password})


def web(config, password):
    ip = config["system"]["ip"].split("/")[0]
    connection = http.client.HTTPSConnection("127.0.0.1", 18443, context=ssl._create_unverified_context(), timeout=20)
    try:
        headers = {"Host": ip, "Content-Type": "application/x-www-form-urlencoded"}
        connection.request("GET", "/cgi-bin/luci/", headers={"Host": ip})
        response = connection.getresponse()
        body = response.read(1024 * 512).decode(errors="replace")
        require(response.status in (200, 403) and "luci_password" in body, "LuCI password login page missing")
        connection.request("POST", "/cgi-bin/luci/", body=urllib.parse.urlencode({"luci_username": "root", "luci_password": password}), headers=headers)
        response = connection.getresponse()
        body = response.read(1024 * 512).decode(errors="replace")
        cookie = response.getheader("Set-Cookie", "").split(";", 1)[0]
        for _ in range(5):
            if response.status not in (301, 302, 303, 307, 308):
                break
            location = urllib.parse.urlsplit(response.getheader("Location", "/cgi-bin/luci/"))
            require(not location.netloc or location.hostname == ip, "Unexpected login redirect")
            connection.request("GET", location.path + ("?" + location.query if location.query else ""), headers={"Host": ip, "Cookie": cookie})
            response = connection.getresponse()
            body = response.read(1024 * 512).decode(errors="replace")
        require(response.status == 200 and "luci_password" not in body and cookie.startswith("sysauth"), "Authenticated LuCI failed")
        match = re.search(r'''["']?ubuspath["']?\s*:\s*("(?:[^"\\]|\\.)*"|'[^']*')''', body)
        rpc_path = json.loads(match.group(1)) if match and match.group(1).startswith('"') else match.group(1).strip("'") if match else "/ubus/"
        require(rpc_path.startswith("/") and not rpc_path.startswith("//"), "Invalid local RPC path")
        request = {"jsonrpc": "2.0", "id": 1, "method": "call", "params": [cookie.split("=", 1)[1], "system", "board", {}]}
        connection.request("POST", rpc_path, body=json.dumps(request), headers={"Host": ip, "Cookie": cookie, "Content-Type": "application/json"})
        response = connection.getresponse()
        data = json.loads(response.read(1024 * 512))
        require(response.status == 200 and data.get("result", [1])[0] == 0 and data["result"][1].get("hostname") == config["system"]["hostname"], "Authenticated board RPC mismatch")
        return {"https_login": "passed", "board_rpc": "passed"}
    finally:
        connection.close()


def command_check(name, command, password, timeout=60):
    answer = ssh("set -eu\n" + command + "\nprintf PB_CHECK_PASSED\n", password, timeout)
    require(answer.returncode == 0 and "PB_CHECK_PASSED" in answer.stdout, name + f" 未通过（退出码 {answer.returncode}）；原始命令输出不会保存，以免泄露私人配置。")
    return name


def configuration_checks(config):
    plan = package_plan(config)
    requested = sorted(p for p in plan if not p.startswith('-'))
    removed = sorted(p[1:] for p in plan if p.startswith('-'))
    interface = ipaddress.IPv4Interface(config['system']['ip'] if '/' in config['system']['ip'] else config['system']['ip']+'/24')
    checks = f'test "$(uci -q get system.@system[0].hostname)" = {q(config["system"]["hostname"])}\n'
    checks += f'test "$(uci -q get network.lan.ipaddr)" = {q(interface.ip)}\n'
    checks += f'test "$(uci -q get network.lan.netmask)" = {q(interface.netmask)}\n'
    for package in requested:
        require(PACKAGE.fullmatch(package), "Invalid package name")
        checks += f"if command -v apk >/dev/null; then apk info -e {package} >/dev/null; else opkg status {package} | grep -q 'Status: install ok installed'; fi\n"
    for package in removed:
        require(PACKAGE.fullmatch(package), "Invalid removed package name")
        checks += f"if command -v apk >/dev/null; then ! apk info -e {package} >/dev/null 2>&1; else ! opkg status {package} 2>/dev/null | grep -q 'Status: install ok installed'; fi\n"
    network=config['network']
    checks += f'test "$(uci -q get dhcp.lan.ignore)" = {"0" if network["dhcp"] else "1"}\n'
    if network['wan_port']:
        checks += f'test "$(uci -q get network.wan.device)" = {q(network["wan_port"])}\n'
    if network['lan_ports']:
        checks += "found_bridge=0\nfor section in $(uci show network | sed -n 's/^network\\.\\([^=]*\\)=device$/\\1/p'); do\n"
        checks += 'if [ "$(uci -q get network.$section.name)" = br-lan ]; then\n'
        checks += f'test "$(uci -q get network.$section.ports)" = {q(network["lan_ports"])}\nfound_bridge=1\nfi\ndone\ntest "$found_bridge" = 1\n'
    if network['mode']=='side':
        checks += f'test "$(uci -q get network.lan.gateway)" = {q(network["gateway"])}\n'
        checks += "if uci -q get network.wan >/dev/null; then test \"$(uci -q get network.wan.auto)\" = 0; fi\n"
    if not config['system']['ipv6']:
        for field in ['ra','dhcpv6','ndp']:
            checks += f'test "$(uci -q get dhcp.lan.{field})" = disabled\n'
    if config['system']['password_secret']:
        checks += '''case "$(awk -F: '$1=="root" {print $2}' /etc/shadow)" in '$6$'*) ;; *) exit 1;; esac\n'''
    if config['firewall']=='iptables':
        checks += "iptables -V | grep -q legacy\n"
    else:
        checks += "for attempt in 1 2 3 4 5 6 7 8 9 10; do nft list table inet fw4 >/dev/null 2>&1 && break; sleep 1; done\nnft list table inet fw4 >/dev/null\n"
    return checks, requested, removed


def services(packages, password, temporary):
    results = []
    if "xray-core" in packages:
        results.append(command_check("Xray 配置检查", "printf '%s' '{\"inbounds\":[],\"outbounds\":[{\"protocol\":\"freedom\"}]}' > /tmp/pb-xray.json\nxray run -test -config /tmp/pb-xray.json", password))
    if "sing-box" in packages:
        results.append(command_check("sing-box 配置检查", "printf '%s' '{\"inbounds\":[],\"outbounds\":[{\"type\":\"direct\",\"tag\":\"direct\"}]}' > /tmp/pb-sing-box.json\nsing-box check -c /tmp/pb-sing-box.json", password))
    if "luci-app-aria2" in packages or "aria2" in packages:
        results.append(command_check("Aria2 本地 HTTPS 下载", "mkdir -p /tmp/pb-download\nprintf 'personal-builder-download-test' > /www/pb-qa-payload.txt\naria2c --no-conf --check-certificate=false --file-allocation=none --max-tries=1 --timeout=10 --connect-timeout=5 --dir=/tmp/pb-download --out=payload https://127.0.0.1/pb-qa-payload.txt >/dev/null 2>&1\ncmp /www/pb-qa-payload.txt /tmp/pb-download/payload", password))
    if "luci-app-smartdns" in packages or "smartdns" in packages:
        # Test DNS inside the disposable guest: this isolates service behavior
        # from slirp UDP forwarding. Never change DNS on a physical device.
        command_check("SmartDNS 本地域名服务启动", "/etc/init.d/dnsmasq stop\n/etc/init.d/smartdns stop\nprintf '%s\\n' 'bind 127.0.0.1:53' 'address /qa.invalid/192.0.2.123' 'server 127.0.0.1:9' 'cache-size 0' 'speed-check-mode none' 'dualstack-ip-selection no' > /tmp/pb-smartdns.conf\nsmartdns -c /tmp/pb-smartdns.conf -p /tmp/pb-smartdns.pid >/tmp/pb-smartdns.log 2>&1\nfor attempt in 1 2 3 4 5 6 7 8 9 10; do test ! -s /tmp/pb-smartdns.pid || break; sleep 1; done\ntest -s /tmp/pb-smartdns.pid\nkill -0 \"$(cat /tmp/pb-smartdns.pid)\"", password)
        results.append(command_check("SmartDNS 本地域名解析", "nslookup qa.invalid 127.0.0.1 2>/dev/null | grep -F '192.0.2.123' >/dev/null\nkill -0 \"$(cat /tmp/pb-smartdns.pid)\"", password))
    if "luci-app-samba4" in packages or "samba4-server" in packages:
        command_check("Samba 临时共享启动", "mkdir -p /tmp/pb-share\nchmod 777 /tmp/pb-share\nuci set samba4.pbqa=sambashare\nuci set samba4.pbqa.name=pbqa\nuci set samba4.pbqa.path=/tmp/pb-share\nuci set samba4.pbqa.read_only=no\nuci set samba4.pbqa.guest_ok=yes\nuci set samba4.pbqa.force_root=1\nuci commit samba4\n/etc/init.d/samba4 restart\nsleep 4", password)
        payload = temporary / "smb-payload"
        payload.write_bytes(secrets.token_bytes(128))
        downloaded = temporary / "smb-return"
        for _ in range(10):
            answer = subprocess.run(["smbclient", "//127.0.0.1/pbqa", "-p", "1445", "-N", "-U", "guest", "-c", f'put "{payload}" payload; get payload "{downloaded}"'], capture_output=True, timeout=20)
            if answer.returncode == 0 and downloaded.exists():
                break
            time.sleep(2)
        require(downloaded.exists() and downloaded.read_bytes() == payload.read_bytes(), "Samba 临时共享读写不一致")
        results.append("Samba 临时共享读写")
    return results


def boot(image, mode, config, temporary):
    for port, kind in ((2222, socket.SOCK_STREAM), (18443, socket.SOCK_STREAM), (1445, socket.SOCK_STREAM)):
        with socket.socket(socket.AF_INET, kind) as sock:
            sock.bind(("127.0.0.1", port))
    ip = config["system"]["ip"].split("/")[0]
    prefix = config["system"]["ip"].split("/")[1] if "/" in config["system"]["ip"] else "24"
    subnet = ipaddress.IPv4Network(ip + "/" + prefix, strict=False)
    host = next(str(address) for address in subnet.hosts() if str(address) != ip)
    count, lan = topology(config)
    command = ["qemu-system-x86_64", "-accel", "tcg,thread=multi", "-cpu", "max", "-smp", "2", "-m", "1536",
               "-display", "none", "-monitor", "none", "-serial", f"file:{temporary / 'serial.log'}", "-no-reboot", "-snapshot",
               "-drive", f"file={image.resolve()},format={'vmdk' if image.suffix == '.vmdk' else 'raw'},if=virtio"]
    for n in range(count):
        network = f"user,id=n{n},restrict=on"
        if n == lan:
            network += f",net={subnet},host={host},hostfwd=tcp:127.0.0.1:2222-{ip}:22,hostfwd=tcp:127.0.0.1:18443-{ip}:443,hostfwd=tcp:127.0.0.1:1445-{ip}:445"
        command += ["-netdev", network, "-device", f"virtio-net-pci,netdev=n{n}"]
    if mode.endswith("uefi"):
        shutil.copyfile("/usr/share/OVMF/OVMF_VARS_4M.fd", temporary / "OVMF_VARS.fd")
        command += ["-drive", "if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd", "-drive", f"if=pflash,format=raw,file={temporary / 'OVMF_VARS.fd'}"]
    from scripts.build import router_password
    password = router_password(config)
    started = time.monotonic()
    with (temporary / "qemu.log").open("wb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log)
        try:
            while time.monotonic() - started < 300:
                require(process.poll() is None, "VM exited before verification")
                answer = ssh("test ! -f /etc/uci-defaults/99-personal-builder\n", password)
                if answer.returncode == 0:
                    break
                time.sleep(5)
            else:
                raise ValueError("本次固件未在五分钟内完成启动和 SSH 密码认证；不会标记验收成功。")
            checks, requested, removed = configuration_checks(config)
            command_check("本次配置和完整软件安装清单", checks, password, timeout=90)
            verified = ["boot", "root-password", "salted-password-hash", "hostname", "management-ip", "netmask", "dhcp", "firewall", "all-planned-packages", "all-planned-removals"]
            if config['network']['wan_port'] or config['network']['lan_ports']: verified.append('port-mapping')
            if config['network']['mode']=='side': verified.append('side-gateway')
            if not config['system']['ipv6']: verified.append('ipv6-disabled-policy')
            result = {"mode": mode, "status": "passed", "checks": verified, **web(config, password)}
            if config['features']['docker']:
                command_check('Docker daemon', 'for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do docker info >/dev/null 2>&1 && break; sleep 2; done\ndocker info >/dev/null 2>&1', password, timeout=90)
                result['checks'].append('docker-daemon')
            result["services"] = services(set(requested), password, temporary)
            result["seconds"] = round(time.monotonic() - started, 1)
            return result
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def images(config, output):
    result = [(p, "uefi" if "combined-efi" in p.name else "bios") for p in sorted(output.glob("*combined*.img.gz"))]
    expected = int(config["output"]["efi"]) + int(config["output"]["legacy"])
    require(len(result) == expected, "Missing a selected disk image")
    if config["output"]["vmdk"]:
        vmdks = sorted(output.glob("*.vmdk")) + sorted(output.glob("*.vmdk.zip"))
        require(bool(vmdks), "Missing VMDK output")
        result.extend((p, "vmdk-uefi" if "combined-efi" in p.name else "vmdk-bios") for p in vmdks)
    return result


def run(config, output=Path("outputs")):
    policy(config, os.environ)
    require(config["build_mode"] == "release", "VM delivery gate requires release mode")
    report = {"schema_version": 1, "status": "failed", "version": config["version"], "results": [], "hardware_tested": False,
              "network": "outbound disabled; loopback-only forwarding", "images_modified": False}
    Path("work").mkdir(exist_ok=True)
    try:
        for image, mode in images(config, output):
            print("Verify actual delivered image:", mode, flush=True)
            with tempfile.TemporaryDirectory(prefix="delivery-vm-", dir="work") as directory:
                temporary = Path(directory)
                disk = image
                if image.name.endswith(".img.gz"):
                    disk = temporary / "disk.img"
                    with gzip.open(image, "rb") as src, disk.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
                elif image.name.endswith(".vmdk.zip"):
                    with zipfile.ZipFile(image) as archive:
                        require(len(archive.infolist()) <= 4 and sum(m.file_size for m in archive.infolist()) <= 6500 * 1024 * 1024, "Oversized VMDK archive")
                        for member in archive.infolist():
                            require(Path(member.filename).name == member.filename and member.filename.endswith(".vmdk") and not member.is_dir(), "Unsafe VMDK member")
                            with archive.open(member) as src, (temporary / member.filename).open("wb") as dst:
                                shutil.copyfileobj(src, dst)
                    disks = [p for p in temporary.glob("*.vmdk") if not p.name.endswith("-flat.vmdk")]
                    require(len(disks) == 1, "VMDK descriptor not unique")
                    disk = disks[0]
                    if disk.stat().st_size < 1024 * 1024:
                        text = disk.read_text(errors="replace")
                        require("parentFileNameHint" not in text and all(Path(name).name == name and (temporary / name).exists() for name in re.findall(r'(?:FLAT|SPARSE)\s+"([^"]+)"', text)), "External VMDK extent rejected")
                report["results"].append(boot(disk, mode, config, temporary))
                print("Passed actual image:", mode, flush=True)
        report["status"] = "passed"
    finally:
        (output / "vm-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    run(load_config())
