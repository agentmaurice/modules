"""Offline tests of scripts/catalog.py: the fingerprint shared with the One, the public-content filter, the entry
rules and the derived facts, on small synthetic repositories (nothing here reads the published modules)."""
import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[3] / 'scripts' / 'catalog.py'
spec = importlib.util.spec_from_file_location('module_catalog_script', SCRIPT)
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)

# Digest of the fixture below as computed by ComputeModuleDirectoryHash of chatserver
# (internal/business/apps/module_manifest.go), run on the same files on 2026-11-02.
ONE_VECTOR = 'f86081e73b1ef490b9f0545d3b954db73f1025c37ec9d920672a7cd813777062'


def write(root, relative, content):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))


def fixture(root):
    write(root, 'a/one.txt', 'hello\n')
    write(root, 'empty.txt', '')
    write(root, 'a/b/z.json', '{"k":1}\n')
    write(root, 'é.txt', 'é\n')
    write(root, '.git/config', 'ignored\n')


class TreeHashTest(unittest.TestCase):
    def test_matches_the_digest_the_one_computes(self):
        with tempfile.TemporaryDirectory() as root:
            fixture(root)
            self.assertEqual(ONE_VECTOR, catalog.tree_sha256(root))

    def test_ignores_git_and_depends_on_every_other_byte_and_path(self):
        with tempfile.TemporaryDirectory() as root:
            fixture(root)
            write(root, '.git/HEAD', 'other')
            self.assertEqual(ONE_VECTOR, catalog.tree_sha256(root))
            write(root, 'a/one.txt', 'hello!\n')
            self.assertNotEqual(ONE_VECTOR, catalog.tree_sha256(root))
            write(root, 'a/one.txt', 'hello\n')
            os.rename(Path(root) / 'empty.txt', Path(root) / 'vide.txt')
            self.assertNotEqual(ONE_VECTOR, catalog.tree_sha256(root))

    def test_refuses_symlinks_like_the_one(self):
        with tempfile.TemporaryDirectory() as root:
            fixture(root)
            os.symlink(Path(root) / 'empty.txt', Path(root) / 'link')
            with self.assertRaisesRegex(ValueError, 'symlinks are forbidden'):
                catalog.tree_sha256(root)


class PublicTextTest(unittest.TestCase):
    def test_clean_text_passes(self):
        self.assertEqual([], catalog.text_problems('t', "Mémoire d'entreprise : capturer, proposer, relire."))

    def test_each_forbidden_shape_is_refused(self):
        internal = 'kraf' + 'tek'
        for text in ('voir https://exemple.org/x', 'écrire à nom@exemple.org', 'hôte 100.64.1.2', 'poste machine.ts.net',
                     'chez ' + internal.capitalize(), 'chez ' + internal.upper(), 'sur gitlab.com', 'clé sk-ant-' + 'a' * 30, 'jeton ghp_' + 'A' * 36,
                     '-----BEGIN RSA PRIVATE' + ' KEY-----', '/Us' + 'ers/jean/code', 'eyJ' + 'a' * 20 + '.' + 'b' * 20 + '.' + 'c' * 20):
            self.assertTrue(catalog.text_problems('t', text), text)

    def test_empty_and_long_texts_are_refused(self):
        self.assertTrue(catalog.text_problems('t', ''))
        self.assertTrue(catalog.text_problems('t', None))
        self.assertTrue(catalog.text_problems('t', 'x' * (catalog.TEXT_MAX + 1)))


def entry(**changes):
    value = {'schema': catalog.ENTRY_SCHEMA, 'description': {'fr': 'Un module.', 'en': 'A module.'},
             'capabilities': ['memory', 'search'], 'credentials': [], 'price': {'model': 'free'}}
    value.update(changes)
    return value


class EntryRulesTest(unittest.TestCase):
    def test_valid_entry(self):
        self.assertEqual([], catalog.entry_problems('m', entry()))

    def test_invalid_entries(self):
        for change in ({'schema': 'x'}, {'extra': 1}, {'description': {'fr': 'seul'}}, {'description': {'fr': 'a', 'en': 'b', 'de': 'c'}},
                       {'capabilities': []}, {'capabilities': ['a'] * 2}, {'capabilities': ['Bad Cap']}, {'capabilities': [str(i) + 'x' for i in range(13)]},
                       {'credentials': ['dup', 'dup']}, {'credentials': ['Bad']}, {'price': {'model': 'paid'}}, {'price': {'model': 'free', 'amount': 1}},
                       {'price': 'free'}):
            self.assertTrue(catalog.entry_problems('m', entry(**change)), change)


def module_repo(root, with_sidecar=True, extra_sidecar=False):
    write(root, 'modules.json', json.dumps({'schema_version': 1, 'modules': [
        {'key': 'cib-demo-memory', 'version': '1.0.0', 'manifest': 'demo-memory/module.yaml', 'workflows': 1, 'miniapps': 0},
        {'key': 'cib-demo', 'version': '2.1.0', 'manifest': 'demo/module.yaml', 'workflows': 1, 'miniapps': 0}]}))
    write(root, 'demo/module.yaml', json.dumps({'key': 'cib-demo', 'name': 'Demo', 'version': '2.1.0', 'schema_version': 2,
        'provides': {'actions': [{'key': 'save', 'name': 'Save it'}, {'key': 'share'}], 'queries': [{'key': 'list'}]},
        'requires': {'mcp': [{'name': 'brain', 'required_tools': ['b.two', 'b.one']}]}}))
    write(root, 'demo/agents/main/workflows/w.json', json.dumps({'workflow_id': 'w', 'actions': [
        {'id': 'a', 'type': 'code_execution'}, {'id': 'b', 'type': 'code_execution', 'runtime': 'wasm'}, {'id': 'c', 'type': 'llm_call'}]}))
    write(root, 'demo-memory/module.yaml', json.dumps({'key': 'cib-demo-memory', 'name': 'Demo memory', 'version': '1.0.0', 'schema_version': 2, 'provides': {}}))
    write(root, 'demo-memory/agents/main/workflows/w.json', json.dumps({'workflow_id': 'w2', 'actions': []}))
    if with_sidecar:
        write(root, 'catalog/demo.yaml', json.dumps(entry(credentials=['demo-key'])))
        write(root, 'catalog/demo-memory.yaml', json.dumps(entry()))
    if extra_sidecar:
        write(root, 'catalog/ghost.yaml', json.dumps(entry()))


class RenderTest(unittest.TestCase):
    def render(self, **options):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        module_repo(root.name, **options)
        with mock.patch.object(catalog, 'ROOT', Path(root.name)):
            result = catalog.render()
        return Path(root.name), result

    def test_derives_runtimes_model_use_connectors_and_dependencies(self):
        root, (value, problems) = self.render()
        self.assertEqual([], problems)
        self.assertEqual(['cib-demo', 'cib-demo-memory'], [m['key'] for m in value['modules']])
        demo = value['modules'][0]
        self.assertEqual(['deno', 'wasm'], demo['requires']['runtimes'])
        self.assertTrue(demo['requires']['language_model'])
        self.assertEqual([{'name': 'brain', 'tools': ['b.one', 'b.two']}], demo['requires']['connectors'])
        self.assertEqual(['demo-key'], demo['requires']['credentials'])
        self.assertEqual([{'key': 'save', 'name': 'Save it'}, {'key': 'share', 'name': 'share'}], demo['actions'])
        self.assertEqual(['list'], demo['queries'])
        self.assertEqual(hashlib.sha256((root / 'demo/module.yaml').read_bytes()).hexdigest(), demo['manifest_sha256'])
        self.assertEqual(catalog.tree_sha256(root / 'demo'), demo['tree_sha256'])
        self.assertEqual('preview', demo['maturity'])

    def test_a_missing_or_stray_catalog_entry_is_a_problem(self):
        _, (_, problems) = self.render(with_sidecar=False)
        self.assertEqual(2, len(problems))
        _, (_, problems) = self.render(extra_sidecar=True)
        self.assertTrue(any('ghost' in problem for problem in problems))

    def test_check_flags_a_stale_catalog_and_accepts_a_fresh_one(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        module_repo(root.name)
        with mock.patch.object(catalog, 'ROOT', Path(root.name)):
            with mock.patch('sys.argv', ['catalog.py']):
                self.assertEqual(0, catalog.main())
            with mock.patch('sys.argv', ['catalog.py', '--check']):
                self.assertEqual(0, catalog.main())
                write(root.name, 'demo/agents/main/workflows/w.json', json.dumps({'workflow_id': 'w', 'actions': []}))
                self.assertEqual(1, catalog.main())


if __name__ == '__main__':
    unittest.main()
