"""Offline checks of the image-studio Module: pins, graph, profiles, sources.

The Go action has its own native tests, run by `maurice module wasm test` in
the isolated builder that supplies the workflow SDK; they are not run here.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / 'image-studio'
TOOLING = ROOT / 'tooling/image-studio'
WORKFLOWS = MODULE / 'agents/main/workflows'


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def actions(workflow):
    return workflow.get('actions', [])


class ImageStudioModuleTest(unittest.TestCase):
    def setUp(self):
        self.workflows = {p.stem: load(p) for p in WORKFLOWS.glob('*.json')}
        self.artifact = load(TOOLING / 'artifact.json')

    def test_every_code_step_runs_the_pinned_wasm_action(self):
        self.assertRegex(self.artifact['sha256'], r'^[0-9a-f]{64}$')
        self.assertGreater(self.artifact['size'], 0)
        count = 0
        for name, wf in self.workflows.items():
            for action in actions(wf):
                if action['type'] == 'code_execution':
                    count += 1
                    self.assertEqual(action.get('runtime'), 'wasm', name)
                    self.assertNotIn('code', action, name)
                    self.assertEqual(action['artifact'], {'sha256': self.artifact['sha256'], 'size': self.artifact['size']}, name)
                    self.assertIn('op', action['context'], name)
        self.assertGreaterEqual(count, 10)

    def test_manifest_lists_every_resource(self):
        manifest = load(MODULE / 'module.yaml')
        refs = {r['workflow_id'] for kind in ('actions', 'queries') for r in manifest['provides'][kind]}
        self.assertEqual(refs, set(self.workflows))
        apps = {r['miniapp_id'] for r in manifest['provides']['apps']}
        self.assertEqual(apps, {p.stem for p in (MODULE / 'agents/main/miniapps').glob('*.json')})

    def test_workflow_targets_exist_and_decision_fallback_writes_nothing(self):
        for name, wf in self.workflows.items():
            for action in actions(wf):
                for target in [action] + action.get('choices', []) + ([action['fallback']] if 'fallback' in action else []):
                    if 'workflow_id' in target:
                        self.assertIn(target['workflow_id'], self.workflows, f'{name}: {target["workflow_id"]}')
                if action['type'] == 'decision':
                    fallback = self.workflows[action['fallback']['workflow_id']]
                    self.assertEqual(actions(fallback), [], 'a decision fallback must have no effect')

    def test_optional_inputs_use_default_pipes(self):
        optional = {'theme', 'root', 'max_assets', 'title', 'category', 'placement'}
        for name, wf in self.workflows.items():
            text = json.dumps(wf)
            for key in optional:
                self.assertNotIn('{{ %s }}' % key, text, f'{name}: {key} must use | default ""')

    def test_attempts_are_bounded_to_two(self):
        produce = self.workflows['image-studio-produce-asset']
        retry = self.workflows['image-studio-asset-retry']
        tools = [a['tool'] for wf in (produce, retry) for a in actions(wf) if a['type'] == 'tool_call']
        self.assertEqual(tools.count('multimodal--multimodal_image_generate_v1'), 2)
        self.assertFalse(any(a['type'] in ('decision', 'for_each', 'workflow_call') for a in actions(retry)))
        judge = [a for a in actions(retry) if a.get('context', {}).get('op') == 'verdict']
        self.assertEqual(judge[0]['context']['final'], True)

    def test_profiles_are_consistent(self):
        for path in (MODULE / 'profiles').glob('*.json'):
            p = load(path)
            self.assertEqual(p['schema'], 'image-studio.profile/v1', path.name)
            self.assertEqual(p['key'], path.stem)
            export = p['export']
            if export['kind'] == 'pixel-grid':
                letters = export['letters']
                self.assertFalse(set('SsDLK') & set(letters), 'S, s, D and L are reserved; K is the outline')
                self.assertEqual(len(set(letters)), len(letters))
                self.assertGreaterEqual(len(letters), export['max_colors'])
                for category in p['planning']['categories']:
                    keys = [category['key']] + [f"{category['key']}:{pl}" for pl in category.get('placements', [])]
                    for key in keys:
                        box = export['boxes'][key]
                        self.assertTrue(0 <= box['x'] and box['x'] + box['w'] <= export['size'], key)
                        self.assertTrue(0 <= box['y'] and box['y'] + box['h'] <= export['size'], key)
                self.assertRegex(export['outline'], r'^#[0-9a-f]{6}$')
            else:
                self.assertEqual(export['kind'], 'raster')
                self.assertIn(export['fit'], ('cover', 'contain'))

    def test_ribin_profile_documents_fit_cosmetic_schema_1_0_0(self):
        p = load(MODULE / 'profiles/ribin-avatar-item.json')
        doc = p['document']
        keys = set(doc['template']) | set(doc['fields'])
        for values in doc['by_attribute']['rarity'].values():
            keys |= set(values)
        allowed = {'item_id', 'kind', 'slot', 'title', 'rarity', 'theme', 'audiences', 'animated', 'art', 'author',
                   'license', 'art_version'}
        required = allowed - {'title', 'slot'}
        self.assertLessEqual(keys, allowed)
        self.assertLessEqual(required, keys)
        self.assertEqual(p['planning']['attributes']['rarity'], ['common', 'rare', 'epic', 'legendary'])
        for rarity, values in doc['by_attribute']['rarity'].items():
            self.assertEqual('kids' in values['audiences'], rarity == 'common', 'kids is only allowed for common items')
        self.assertEqual({c['key'] for c in p['planning']['categories']}, {'hat', 'top', 'accessory'})
        self.assertLessEqual(p['planning']['max_assets'], 20)

    def test_go_source_carries_no_sdk(self):
        source = MODULE / 'wasm/studio'
        self.assertFalse((source / 'vendor').exists())
        go_mod = (source / 'go.mod').read_text(encoding='utf-8')
        self.assertEqual(re.findall(r'^require (.+)$', go_mod, re.M), ['github.com/agentmaurice/chatserver v0.0.0'])
        for path in source.glob('*.go'):
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('package workflow', text, path.name)

    def test_planner_schema_matches_plan_workflow(self):
        plan = self.workflows['image-studio-plan']
        llm = [a for a in actions(plan) if a['type'] == 'llm_call'][0]
        self.assertEqual(llm['llm_response_schema'], load(TOOLING / 'planner-schema.json'))


if __name__ == '__main__':
    unittest.main()
