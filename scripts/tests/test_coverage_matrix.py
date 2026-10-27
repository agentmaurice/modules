"""Keep the documented MiniApp matrix tied to the exact source resources."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class CoverageMatrixTest(unittest.TestCase):
    def test_every_miniapp_has_current_version_and_hash(self):
        text = (ROOT / 'docs/LANGUAGE_MIGRATION.md').read_text()
        rows = re.findall(r'\| `([^`]+)` \| `([^`]+)@([^`]+)`[^|]*\| \[([^\]]+)\]\(\.\./[^)]+\)<br>`([0-9a-f]{64})`', text)
        resources = sorted(ROOT.glob('*/agents/main/miniapps/*.json'))
        self.assertEqual(len(rows), len(resources))
        self.assertGreater(len(rows), 0)
        seen = set()
        for module, resource_id, version, name, digest in rows:
            path = ROOT / name
            self.assertNotIn(name, seen)
            seen.add(name)
            payload = json.loads(path.read_text())
            self.assertEqual(resource_id, payload['miniapp_id'])
            self.assertEqual(version, str(payload['version']))
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(module, json.loads((ROOT / path.relative_to(ROOT).parts[0] / 'module.yaml').read_text())['key'])
        self.assertEqual(seen, {p.relative_to(ROOT).as_posix() for p in resources})
        self.assertIn('proof pending', text)

    def test_matrix_workflow_targets_are_source_versions_not_guessed(self):
        text = (ROOT / 'docs/LANGUAGE_MIGRATION.md').read_text()
        workflow_versions = {}
        for path in ROOT.glob('*/agents/main/workflows/*.json'):
            workflow = json.loads(path.read_text())
            self.assertNotIn(workflow['workflow_id'], workflow_versions)
            workflow_versions[workflow['workflow_id']] = str(workflow['version'])
        rows = re.findall(r'\| `([^`]+)` \| `([^`]+)@([^`]+)`[^|]*\| \[([^\]]+)\]\(\.\./[^)]+\)<br>`[0-9a-f]{64}` \| ([^|]+) \|', text)
        for _, resource_id, _, name, targets in rows:
            app = json.loads((ROOT / name).read_text())
            expected = {event['workflow']['workflow_id'] for event in app.get('events', [])
                        if event.get('workflow', {}).get('workflow_id')}
            actual = dict(re.findall(r'`([^`@]+)@([^`]+)`', targets))
            self.assertEqual(set(actual), expected, resource_id)
            for workflow_id, version in actual.items():
                self.assertEqual(version, workflow_versions[workflow_id], resource_id + ': ' + workflow_id)


if __name__ == '__main__':
    unittest.main()
