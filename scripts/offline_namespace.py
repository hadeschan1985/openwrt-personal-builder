"""Verify that an offline build has local TCP but no external interface/route.

OpenWrt's fakeroot uses TCP IPC. A new network namespace starts with loopback
down, so its build tools need lo brought up without adding any external link.
This probe runs before the build, with no GitHub credential passed to it.
"""
import errno
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys


def verify():
    if not sys.platform.startswith('linux'):
        raise ValueError('Offline namespace verification requires Linux')
    if any(os.environ.get(key) for key in ('GH_TOKEN', 'GITHUB_TOKEN')):
        raise ValueError('Do not pass GitHub credentials into the offline build')
    interfaces=json.loads(subprocess.check_output(['ip','-j','address','show'],text=True))
    if len(interfaces)!=1 or interfaces[0].get('ifname')!='lo' or 'UP' not in interfaces[0].get('flags',[]):
        raise ValueError('Offline build requires exactly one active loopback interface')
    addresses=interfaces[0].get('addr_info',[])
    if not addresses or any(not ipaddress.ip_address(a['local']).is_loopback for a in addresses):
        raise ValueError('Offline namespace contains a non-loopback address')
    routes=json.loads(subprocess.check_output(['ip','-j','route','show','table','all'],text=True))
    for route in routes:
        destination=route.get('dst','default')
        if route.get('dev')!='lo' or route.get('gateway') or destination=='default' or not ipaddress.ip_network(destination,strict=False).network_address.is_loopback:
            raise ValueError('Offline namespace contains an external route')
    with socket.socket() as server:
        server.settimeout(2);server.bind(('127.0.0.1',0));server.listen(1)
        with socket.create_connection(server.getsockname(),timeout=2) as client:
            with server.accept()[0] as peer:
                peer.settimeout(2);client.sendall(b'local-only')
                if peer.recv(10)!=b'local-only':raise ValueError('Loopback TCP verification failed')
    with socket.socket() as external:
        external.settimeout(2)
        if external.connect_ex(('1.1.1.1',443)) not in (errno.ENETUNREACH,errno.EHOSTUNREACH):
            raise ValueError('External networking was not rejected as unreachable')
    report={'schema_version':1,'status':'passed','interfaces':['lo'],'loopback_tcp':'passed','external_network':'unreachable','github_token_passed':False}
    path=Path('work/offline-network-report.json');path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,sort_keys=True)+'\n',encoding='utf-8')
    print('OFFLINE_NETWORK_VERIFIED='+json.dumps(report,sort_keys=True),flush=True)
    return report


if __name__=='__main__':verify()
