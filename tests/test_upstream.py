import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import upstream as u


def candidate():
    registry = json.loads((u.ROOT / u.REGISTRY).read_text(encoding="utf-8"))
    version = next(iter(registry))
    meta = {"profiles": {"target": "x86/64", "arch_packages": "x86_64", "profiles": {"generic": {"images": []}}},
            "packages": [f"package-{i}" for i in range(110)], "package_metadata_errors": []}
    sources = [{"source": source, "version": "25.12.6" if source == "official" else version,
                "builder_sha256": "a" * 64 if source == "official" else registry[version]["sha256"],
                "metadata": copy.deepcopy(meta)} for source in ("official", "kwrt")]
    return {"schema_version": 1, "registry": registry, "sources": sources,
            "fingerprint": u.digest({"registry": registry, "sources": sources})}


def evidence(c):
    return {s["source"]: {"source": s["source"], "version": s["version"], "run_id": "123",
             "fingerprint": c["fingerprint"], "report": {"builder": s["source"], "version": s["version"],
             "results": [{"mode": mode, "status": "passed", "web": {"authenticated_status": 200}}
                         for mode in ("bios", "uefi", "vmdk-bios" if s["source"] == "official" else "native-vmdk-bios")]}}
            for s in c["sources"]}


class UpstreamTests(unittest.TestCase):
    def test_checksum_request_uses_existing_builder_user_agent(self):
        response = io.BytesIO(("a" * 64 + " *builder.tar.zst\n").encode())
        with patch.object(u.urllib.request, "urlopen", return_value=response) as opened:
            self.assertEqual(u.builder_checksum("https://dl.openwrt.ai/example", "builder.tar.zst"), "a" * 64)
            self.assertEqual(opened.call_args.args[0].get_header("User-agent"), "OpenWrt-Personal-Builder/0.1")

    def test_unchanged_upstream_skips_expensive_tests(self):
        c = candidate()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            u.write_json(root / u.APPROVED, {"fingerprint": c["fingerprint"]})
            u.write_json(root / u.REGISTRY, c["registry"])
            output = root / "job-output"
            with patch.object(u, "ROOT", root), patch.object(u, "discover", return_value=c), patch.dict("os.environ", {"GITHUB_OUTPUT": str(output)}):
                u.detect(root / "candidate.json")
            self.assertEqual(output.read_text().strip(), "changed=false")

    def test_valid_candidate_and_complete_approval(self):
        c = candidate()
        result = u.approval(c, evidence(c), "123", "b" * 40)
        self.assertEqual(len(result["sources"]), 2)
        self.assertEqual(len(result["sources"][0]["tested_modes"]), 3)

    def test_incomplete_or_failed_or_wrong_run_reports_never_promote(self):
        c = candidate()
        for mutate in (lambda e: e.pop("kwrt"), lambda e: e["kwrt"].update(run_id="999"),
                       lambda e: e["official"]["report"]["results"].pop(),
                       lambda e: e["kwrt"]["report"]["results"][0].update(status="failed"),
                       lambda e: e["kwrt"]["report"]["results"][0]["web"].update(authenticated_status=403)):
            reports = evidence(c)
            mutate(reports)
            with self.assertRaises(ValueError):
                u.approval(c, reports, "123", "b" * 40)

    def test_tampering_unknown_family_and_remote_builder_rejected(self):
        for mutation in (lambda c: c.update(fingerprint="0" * 64),
                         lambda c: c["sources"][0].update(version="SNAPSHOT"),
                         lambda c: c["sources"][1]["metadata"].update(package_metadata_errors=["offline"]),
                         lambda c: next(iter(c["registry"].values())).update(base="https://example.com/evil")):
            c = candidate()
            mutation(c)
            with self.assertRaises(ValueError):
                u.validate_candidate(c)

    def test_package_version_changes_affect_fingerprint(self):
        c = candidate()
        before = c["fingerprint"]
        c["sources"][0]["metadata"]["package_index_sha256"] = ["c" * 64]
        self.assertNotEqual(before, u.digest({"sources": c["sources"], "registry": c["registry"]}))

    def test_publish_only_data_atomic_and_no_force(self):
        c = candidate()
        calls = []
        def api(path, token, method="GET", body=None):
            calls.append((path, method, body))
            if path == "/git/ref/heads/main":
                return {"object": {"sha": "b" * 40}}
            if path.startswith("/git/commits/"):
                return {"tree": {"sha": "c" * 40}}
            return {"sha": "d" * 40}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            u.write_json(root / "candidate.json", c)
            for source, report in evidence(c).items():
                u.write_json(root / "reports" / f"{source}.json", report)
            with patch.dict("os.environ", {"GITHUB_RUN_ID": "123", "GITHUB_SHA": "b" * 40, "GH_TOKEN": "ephemeral"}), patch.object(u, "api", side_effect=api):
                u.publish(root / "candidate.json", root / "reports")
        tree = next(b for p, m, b in calls if p == "/git/trees")
        self.assertEqual({e["path"] for e in tree["tree"]}, {u.REGISTRY, u.APPROVED})
        self.assertEqual(tree["base_tree"], "c" * 40)
        self.assertFalse(calls[-1][2]["force"])
        self.assertNotIn("ephemeral", json.dumps(calls))

    def test_branch_drift_aborts_before_writes(self):
        c = candidate()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            u.write_json(root / "candidate.json", c)
            for source, report in evidence(c).items():
                u.write_json(root / "reports" / f"{source}.json", report)
            with patch.dict("os.environ", {"GITHUB_RUN_ID": "123", "GITHUB_SHA": "b" * 40, "GH_TOKEN": "ephemeral"}), patch.object(u, "api", return_value={"object": {"sha": "c" * 40}}) as api:
                with self.assertRaisesRegex(ValueError, "Branch changed"):
                    u.publish(root / "candidate.json", root / "reports")
                self.assertEqual(api.call_count, 1)


if __name__ == "__main__":
    unittest.main()
