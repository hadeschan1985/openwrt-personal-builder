import json
from pathlib import Path
import tempfile
import unittest
from scripts.device_audit import audit

class BaselineSnapshotTests(unittest.TestCase):
    def test_complete_snapshot_is_offline_and_matches_all_pinned_platforms(self):
        with tempfile.TemporaryDirectory() as folder:
            report=audit(Path('site/data'),Path(folder)/'audit.json')
            self.assertEqual(report['device_profiles'],865);self.assertEqual(report['platforms'],24)

    def test_metadata_changes_fail_before_publishing_even_if_package_name_is_valid(self):
        catalog=json.loads(Path('site/data/catalog.json').read_text(encoding='utf-8'))
        device=next(d for d in catalog['devices'] if d.get('builder')=='kwrt' and d['target']=='airoha/an7581')
        data=json.loads((Path('site/data')/device['metadata']).read_text(encoding='utf-8'));data['packages'].append('tampered-package')
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'catalog.json').write_text(json.dumps({'devices':[device]}),encoding='utf-8')
            destination=root/device['metadata'];destination.parent.mkdir(parents=True);destination.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'digest mismatch'):audit(root,root/'report.json')
