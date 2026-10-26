"""User-triggered, bounded private Release archive. Never deletes old releases.

Archive job executes no firmware, package or user initialization script. It
checks ZIP digests, safe names and per-file digests before preserving bytes.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from scripts.build import require, sha256
from scripts.delivery import MAX_BYTES, validate_record
from scripts.upstream import api


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def requested_run(path=Path('requests/split-download.json')):
    """An explicit private source request can dispatch without a browser PAT."""
    require(os.environ.get('GITHUB_EVENT_NAME') == 'push' and path.is_file() and path.stat().st_size <= 1024, 'Missing explicit split request')
    value = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(value, dict) and set(value) == {'run_id'} and isinstance(value['run_id'], str) and re.fullmatch(r'[1-9][0-9]{0,19}', value['run_id']), 'Invalid split request; expected one successful build ID')
    return value['run_id']


def download(artifact, path, token):
    repo = os.environ["GITHUB_REPOSITORY"]
    require(type(artifact["id"]) is int and not artifact["expired"], "下载包已到期，不能再归档；已有归档不受影响。")
    require(0 < artifact["size_in_bytes"] <= MAX_BYTES, "Archive size outside safe limit")
    require(re.fullmatch(r"sha256:[a-f0-9]{64}", artifact.get("digest", "")), "Artifact has no trusted ZIP digest")
    request = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/artifacts/{artifact['id']}/zip", headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"})
    try:
        response = urllib.request.build_opener(NoRedirect()).open(request, timeout=60)
    except urllib.error.HTTPError as error:
        require(error.code in (301, 302, 303, 307, 308), "无法获取私有下载包，请检查 Actions 权限和产物期限。")
        location = error.headers["Location"]
        parsed = urllib.parse.urlsplit(location)
        require(parsed.scheme == "https" and parsed.hostname and (parsed.hostname.endswith(".blob.core.windows.net") or parsed.hostname.endswith(".githubusercontent.com")), "Untrusted artifact redirect")
        # IMPORTANT: the API credential is not forwarded to blob storage.
        response = urllib.request.urlopen(urllib.request.Request(location), timeout=120)
    size, digest = 0, hashlib.sha256()
    with response, path.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            require(size <= artifact["size_in_bytes"] and size <= MAX_BYTES, "Artifact exceeded declared size")
            digest.update(chunk)
            output.write(chunk)
    require(size == artifact["size_in_bytes"] and "sha256:" + digest.hexdigest() == artifact["digest"], "ZIP 下载包校验失败，不归档。")


def extract(archive, destination, expected):
    result = []
    with zipfile.ZipFile(archive) as package:
        require(len(package.infolist()) <= 100 and sum(m.file_size for m in package.infolist()) <= MAX_BYTES, "Oversized artifact contents")
        for member in package.infolist():
            if member.is_dir():
                continue
            name = member.filename
            require(Path(name).name == name and re.fullmatch(r"[A-Za-z0-9_.+-]{1,180}", name), "Unsafe artifact file name")
            require((member.external_attr >> 16) & 0o170000 != 0o120000, "Archive links are not allowed")
            require(name in expected and not (destination / name).exists(), "Unexpected or duplicate artifact file")
            info = expected[name]
            require(member.file_size == info["bytes"], "File size mismatch")
            path = destination / name
            with package.open(member) as src, path.open("wb") as dst:
                while chunk := src.read(1024 * 1024):
                    dst.write(chunk)
            require(sha256(path) == info["sha256"], "固件 SHA256 不一致，不归档。")
            result.append(path)
    return result


def legacy_manifest(path):
    """Validate a historical all-in-one ZIP before splitting; never execute it."""
    with zipfile.ZipFile(path) as package:
        members = package.infolist()
        names = [m.filename for m in members]
        require(len(members) <= 100 and len(names) == len(set(names)) and sum(m.file_size for m in members) <= MAX_BYTES, 'Invalid or oversized historical bundle')
        for member in members:
            require(not member.is_dir() and re.fullmatch(r'[A-Za-z0-9_.+-]{1,180}', member.filename), 'Unsafe historical bundle path')
            require((member.external_attr >> 16) & 0o170000 != 0o120000 and not member.flag_bits & 1, 'Historical bundle links/encryption are not allowed')
        require({'build-summary.json', 'SHA256SUMS'} <= set(names), '旧下载包缺少构建摘要或 SHA256SUMS，不能安全拆分。')
        require(package.getinfo('build-summary.json').file_size <= 256*1024 and package.getinfo('SHA256SUMS').file_size <= 32*1024, 'Historical metadata too large')
        summary = json.loads(package.read('build-summary.json'))
        files = summary.get('files')
        require(isinstance(files, list) and 1 <= len(files) <= 98, 'Invalid historical file list')
        expected = {}
        for item in files:
            name = item['name']
            require(re.fullmatch(r'[A-Za-z0-9_.+-]{1,180}', name) and name not in expected and name not in ('build-summary.json','SHA256SUMS'), 'Invalid historical file name')
            require(type(item['bytes']) is int and 0 <= item['bytes'] <= MAX_BYTES and re.fullmatch(r'[a-f0-9]{64}', item['sha256']), 'Invalid historical file integrity')
            expected[name] = item
        sums = {}
        for line in package.read('SHA256SUMS').decode('utf-8').splitlines():
            match = re.fullmatch(r'([a-f0-9]{64})\s+\*?([A-Za-z0-9_.+-]{1,180})', line)
            require(match and match[2] not in sums, 'Invalid or duplicate historical checksum')
            sums[match[2]] = match[1]
        require(set(sums) == set(expected) and all(sums[n] == expected[n]['sha256'] for n in sums), 'Historical summary and SHA256SUMS disagree')
        require(set(names) == set(expected) | {'build-summary.json','SHA256SUMS'}, 'Unexpected unverified files in historical bundle')
        for name in ('build-summary.json', 'SHA256SUMS'):
            payload = package.read(name)
            expected[name] = {'name':name, 'bytes':len(payload), 'sha256':hashlib.sha256(payload).hexdigest()}
        return expected


def upload(release, file, token):
    repo = os.environ["GITHUB_REPOSITORY"]
    checksum = "sha256:" + sha256(file)
    existing = next((a for a in release.get("assets", []) if a["name"] == file.name), None)
    if existing:
        require(existing["size"] == file.stat().st_size and existing.get("digest") == checksum, "Existing archive asset differs; no overwrite performed")
        return
    # http.client streams the file; do not load a GiB image into memory.
    import http.client
    connection = http.client.HTTPSConnection("uploads.github.com", timeout=300)
    path = f"/repos/{repo}/releases/{release['id']}/assets?name={urllib.parse.quote(file.name)}"
    try:
        connection.putrequest("POST", path)
        for key, value in {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "User-Agent": "OpenWrt-Personal-Builder", "Content-Type": "application/octet-stream", "Content-Length": str(file.stat().st_size)}.items():
            connection.putheader(key, value)
        connection.endheaders()
        with file.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                connection.send(chunk)
        response = connection.getresponse()
        payload = response.read(1024 * 1024)
        require(response.status == 201, "私有归档上传失败；草稿保留，可重新运行，不覆盖既有归档。")
        asset = json.loads(payload)
        require(asset["size"] == file.stat().st_size and asset.get("digest") == checksum, "GitHub archive integrity mismatch")
    finally:
        connection.close()


def archive(run_id):
    require(re.fullmatch(r"\d+", run_id), "Invalid build ID")
    token = os.environ["GH_TOKEN"]
    require(api("", token)["private"], "归档只能保存到私有仓库，禁止公开个人固件。")
    run = api("/actions/runs/" + run_id, token)
    require(run["path"] == ".github/workflows/build.yml" and run["conclusion"] == "success", "Only a successful personal build may be archived")
    number = run["run_number"]
    tag = f"personal-build-{number}-{run_id}"
    releases = api("/releases?per_page=100", token)
    release = next((r for r in releases if r["tag_name"] == tag), None)
    if release and not release["draft"]:
        print("This build is already privately archived.")
        return
    require(release or len([r for r in releases if re.fullmatch(r"personal-build-\d+-\d+", r["tag_name"])]) < 5,
            "最多收藏五个版本。请先在 GitHub 手动管理旧收藏；本项目不会自动删除你的固件。")
    artifacts = api(f"/actions/runs/{run_id}/artifacts?per_page=100", token)["artifacts"]
    prefix = f"firmware-{number}"
    artifacts = [a for a in artifacts if a["name"] == prefix or re.fullmatch(re.escape(prefix) + r"-(efi|legacy|vmdk|efi-vmdk|legacy-vmdk|rootfs|reports)", a["name"])]
    if any(a["name"] == prefix for a in artifacts):
        artifacts = [a for a in artifacts if a["name"] == prefix]
    require(artifacts and all(not a["expired"] for a in artifacts), "本次构建的下载包缺失或已到期，无法新建收藏。")
    require(sum(a["size_in_bytes"] for a in artifacts) <= MAX_BYTES, "收藏超过 1.5 GiB 上限")
    record = None
    try:
        content = api(f"/contents/records/{run_id}.json?ref=main", token)
        require(content["size"] <= 256 * 1024 and content["encoding"] == "base64", "Invalid private record")
        record = validate_record(json.loads(base64.b64decode(content["content"])))
        require(record["run_id"] == run_id and record["source_commit"] == run["head_sha"], "Record source mismatch")
    except urllib.error.HTTPError as error:
        require(error.code == 404, "Cannot read private build record")
    directory = Path("work/private-archive")
    directory.mkdir(parents=True, exist_ok=True)
    assets = []
    for item in artifacts:
        path = directory / (item["name"] + ".zip")
        download(item, path, token)
        if record:
            expected = {f["name"]: f for f in record["files"]}
            assets.extend(extract(path, directory, expected))
        else:
            require(item['name'] == prefix and len(artifacts) == 1, '旧任务缺少完整记录，无法确认分包是否齐全；原下载保留。')
            expected = legacy_manifest(path)
            assets.extend(extract(path, directory, expected))
    if record:
        require({p.name for p in assets} == {f['name'] for f in record['files']}, "映像或报告分包不完整，不发布残缺收藏。")
        metadata = directory / "build-record.json"
        metadata.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        assets.append(metadata)
    status = "已通过本次映像虚拟机验收；不是实体硬件验收。" if record and record["vm"]["status"] == "passed" else "实验/旧版固件，未通过本流程启动验收，不应直接刷机。"
    body = f"个人私有收藏 · 构建 #{number}\n\n{status}\n\n按文件单独下载，无需下载所有映像；每个上传文件均核对原始 SHA256。没有重新编译、执行固件或改写原始下载包。\n\n来源任务：https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{run_id}\n\n固件原始代码提交：`{run['head_sha']}`。收藏标签用于保存下载，指向归档时的 main；不是重新构建的固件来源。\n\n固件可能包含私人配置，请勿转发。"
    if not release:
        label = "内部验收样品（勿刷机）" if re.search(r" · qa-internal-[A-Za-z0-9-]+$", run.get("display_title", "")) else "私有固件"
        # A tag at an unreferenced historical workflow commit needs Workflows
        # write. Archive at an existing branch instead; retain actual firmware
        # provenance above/in the record, with no additional token permission.
        release = api("/releases", token, "POST", {"tag_name": tag, "target_commitish": "main", "name": f"{label} #{number}", "body": body, "draft": True, "make_latest": "false"})
    for asset in assets:
        upload(release, asset, token)
    api(f"/releases/{release['id']}", token, "PATCH", {"draft": False, "body": body, "make_latest": "false"})
    print("Private archive verified and completed. No existing version was deleted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    value = parser.parse_args().run_id
    archive(value or requested_run())
