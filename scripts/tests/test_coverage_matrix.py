"""Keep the documented MiniApp matrix tied to the exact source resources."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class CoverageMatrixTest(unittest.TestCase):
    def test_documentary_inventory_v2_maps_v1_provenance_without_changing_catalogues(self):
        spec = importlib.util.spec_from_file_location('inventory_generator', ROOT / 'scripts/inventory.py')
        inventory = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(inventory)
        with tempfile.TemporaryDirectory(prefix='inventory-schema-') as directory:
            root = Path(directory)
            package = root / 'company-memory'
            package.mkdir()
            (package / 'module.yaml').write_text(json.dumps({'key':'company-memory', 'version':'0.3.1'}))
            with patch.object(inventory, 'ROOT', root):
                documents = inventory.render()
            self.assertEqual(documents['inventory/modules.json']['schema_version'], 2)
            self.assertEqual(documents['modules.json']['schema_version'], 1)
            self.assertEqual(documents['templates/company-in-a-box/modules.json']['schema_version'], 1)
            source = documents['inventory/modules.json']['modules'][0]['source']
            # This is the legacy v1 meaning, not a claim about current bytes.
            old_v1 = {'repository':'gitlab.com/mcpchatui/pilote-maurice',
                      'commit':'8cb35a14b825dcdae4515d46e3b4c5149c154901',
                      'old_path':'solutions/company-memory/module'}
            self.assertEqual({key:source['historical_baseline'][key] for key in old_v1}, old_v1)
            self.assertEqual(source['historical_baseline']['version_basis'], '0.3.0')
            self.assertEqual(source['current']['repository'], 'github.com/agentmaurice/modules')
            self.assertEqual(source['current']['package_path'], 'company-memory')
            self.assertEqual(source['current']['version'], '0.3.1')
            self.assertNotIn('commit', source['current'])
            self.assertIn('not provenance of the current package bytes', source['historical_baseline']['role'])

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
