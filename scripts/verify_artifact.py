"""Offline integrity check only: never boots, mounts or writes a disk image."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import zipfile


def disk_partitions(header):
    if len(header) < 1024 or header[510:512] != b"\x55\xaa":
        raise ValueError("Missing x86 disk boot signature")
    result = []
    if header[512:520] == b"EFI PART":
        table_lba, count, entry_size = struct.unpack_from("<QII", header, 512 + 72)
        if count > 1024 or not 128 <= entry_size <= 1024:
            raise ValueError("Unexpected GPT layout")
        for index in range(count):
            offset = table_lba * 512 + index * entry_size
            entry = header[offset:offset + entry_size]
            if len(entry) != entry_size:
                raise ValueError("GPT exceeds inspected header")
            if entry[:16] == bytes(16):
                continue
            start, end = struct.unpack_from("<QQ", entry, 32)
            if end < start:
                raise ValueError("Invalid GPT partition")
            result.append({"number": index + 1, "start_sector": start, "bytes": (end - start + 1) * 512})
        return "GPT", result
    for index in range(4):
        offset = 446 + index * 16
        start, sectors = struct.unpack_from("<II", header, offset + 8)
        if header[offset + 4] and sectors:
            result.append({"number": index + 1, "start_sector": start, "bytes": sectors * 512})
    return "MBR", result


def verify(path, expected_archive_sha=None, expected_rootfs_mb=None):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if expected_archive_sha and digest != expected_archive_sha.lower():
        raise ValueError("GitHub artifact archive digest mismatch")
    report = {"archive": path.name, "archive_sha256": digest, "status": "integrity-verified-not-boot-tested", "files": [], "disks": []}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate artifact entries")
        summary = json.loads(archive.read("build-summary.json"))
        sums = {}
        for line in archive.read("SHA256SUMS").decode().splitlines():
            checksum, name = line.split(maxsplit=1)
            sums[name.lstrip("*")] = checksum
        if not sums or set(sums) != {item["name"] for item in summary["files"]}:
            raise ValueError("Checksum list and build summary disagree")
        for item in summary["files"]:
            name = item["name"]
            with archive.open(name) as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != sums[name] or actual != item["sha256"] or archive.getinfo(name).file_size != item["bytes"]:
                raise ValueError("Artifact file mismatch: " + name)
            report["files"].append({"name": name, "bytes": item["bytes"], "sha256": actual})
            if summary["target"].startswith("x86/") and name.endswith(".img.gz"):
                with archive.open(name) as compressed, gzip.GzipFile(fileobj=compressed) as disk:
                    header, size = b"", 0
                    while block := disk.read(1024 * 1024):
                        if not header:
                            header = block[:256 * 1024]
                        size += len(block)
                        if size > 8 * 1024 ** 3:
                            raise ValueError("Disk exceeds verification size limit")
                table, partitions = disk_partitions(header)
                root = next((p for p in partitions if p["number"] == 2), None)
                if expected_rootfs_mb is not None and (not root or root["bytes"] != expected_rootfs_mb * 1024 ** 2):
                    raise ValueError("Unexpected root partition size: " + name)
                if any(p["start_sector"] * 512 + p["bytes"] > size for p in partitions):
                    raise ValueError("Partition extends beyond disk")
                report["disks"].append({"name": name, "table": table, "uncompressed_bytes": size, "partitions": partitions})
        installed = set()
        for name in names:
            if name.endswith(".manifest"):
                installed.update(line.split()[0] for line in archive.read(name).decode().splitlines() if line.strip())
        if set(summary["packages"]) - installed:
            raise ValueError("Manifest is missing requested packages")
        report.update(version=summary["version"], target=summary["target"], profile=summary["profile"], requested_packages=summary["packages"])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--expected-archive-sha")
    parser.add_argument("--expected-rootfs-mb", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.archive, args.expected_archive_sha, args.expected_rootfs_mb)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
