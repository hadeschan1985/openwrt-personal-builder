"""Read-only diagnostics for the explicitly configured public package origin."""
import urllib.error
import urllib.request

URLS = [
    "https://dl.openwrt.ai/releases/targets/x86/64/profiles.json",
    "https://dl.openwrt.ai/releases/targets/x86/64/sha256sums",
    "https://dl.openwrt.ai/releases/targets/x86/64/kwrt-imagebuilder-x86-64.Linux-x86_64.tar.zst",
    "https://dl.openwrt.ai/releases/25.12/packages/x86_64/kiddin9/Packages",
]
for url in URLS:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "OpenWrt-Personal-Builder/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            print(url, response.status, response.headers.get("Server", ""), response.headers.get("Content-Length", ""))
    except urllib.error.HTTPError as error:
        print(url, error.code, dict(error.headers), error.read(1000).decode(errors="replace"))
