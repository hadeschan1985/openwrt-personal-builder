"""Prepare disposable credentials/config only; never touch repository secrets."""
import argparse
import json
import zipfile
from pathlib import Path
from scripts import smoke
from scripts.build import normalize


def prepare(source, scenario='standard'):
    smoke.prepare(source)
    config = json.loads(Path("configs/qa-generated.json").read_text())
    # The delivery gate authenticates by ephemeral password only. Unlike the
    # older smoke harness, its QA images contain no injected SSH test key.
    overlay = Path(config["overlay"])
    with zipfile.ZipFile(overlay) as archive:
        entries = [(item, archive.read(item)) for item in archive.infolist() if item.filename != 'etc/dropbear/authorized_keys']
    with zipfile.ZipFile(overlay, 'w') as archive:
        for item, data in entries:
            archive.writestr(item, data)
    config["build_mode"] = "release"
    config["packages"] = (["luci-app-samba4", "luci-app-aria2", "luci-app-ddns"] if source == "official" else
                          ["luci-app-smartdns", "luci-app-aria2", "xray-core", "sing-box", "ca-bundle"])
    if source == "kwrt":
        config["proxies"] = ["luci-app-passwall2"]
    config["output"]["rootfs_size_mb"] = 768
    if scenario == 'hardening':
        config['system'].update(ip='192.168.27.129/25', ipv6=False, webserver='nginx' if source=='official' else 'lighttpd')
        config['network'].update(mode='side', gateway='192.168.27.254', dhcp=False, wan_port='eth0', lan_ports='eth2')
        config['output'].update(efi=False, legacy=True, vmdk=False, rootfs=False, filesystem='ext4', rootfs_size_mb=1024)
        if source=='kwrt':
            config['proxies']=[]
            config['firewall']='iptables'
            config['features'].update(docker=True,usb_net=True)
    config = normalize(config)
    Path("configs/qa-generated.json").write_text(json.dumps(config), encoding="utf-8")
    print("Prepared release-mode QA with ephemeral password; real image verification follows.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["official", "kwrt"], required=True)
    parser.add_argument('--scenario',choices=['standard','hardening'],default='standard')
    args=parser.parse_args()
    prepare(args.source,args.scenario)
