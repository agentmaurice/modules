import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('compose_memory',ROOT/'compose.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

def assert_local_pins(test, directory):
    definitions = {}
    for file in directory.glob('*.json'):
        definition = json.loads(file.read_text())
        if 'workflow_id' in definition:
            definitions[definition['workflow_id']] = definition
    count = 0
    def visit(value):
        nonlocal count
        if isinstance(value, dict):
            if value.get('type') == 'workflow_call' and 'workflow_id' in value and 'workflow_version' in value:
                target = value['workflow_id']
                test.assertIn(target, definitions, f'missing local target {target}')
                test.assertEqual(str(value['workflow_version']), str(definitions[target]['version']), target)
                count += 1
            for item in value.values(): visit(item)
        elif isinstance(value, list):
            for item in value: visit(item)
    for definition in definitions.values(): visit(definition)
    return count

class CompositionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        for index,alias in enumerate((*module.ROLES,'memory')):
            p=self.root/'agents'/alias;p.mkdir(parents=True);(p/'workflows').mkdir()
            (p/'agent-spec.json').write_text(json.dumps({'schema_version':2,'agent_alias':alias,'agent_id':'c'+str(index)*19,'identity':{'instructions':'preserve me'}}))
            names=[x[0] for x in module.CONTRACTS.values()] if alias=='memory' else [alias+'-read',alias+'-save']
            for n in names:(p/'workflows'/f'{n}.json').write_text('{}')
            if alias=='contenu':(p/'workflows/review_completion.json').write_text(json.dumps({'workflow_id':'review_completion','version':'2'}))
    def test_scoped_portable_idempotent(self):
        outputs=module.compose(self.root)
        memory=json.loads(outputs[self.root/'agents/memory/agent-spec.json'])
        self.assertEqual(len(memory['capabilities']),4)
        self.assertEqual(memory['identity']['instructions'],'preserve me')
        for c in memory['capabilities']:
            self.assertEqual(len(c['allowed_agent_ids']),3)
            self.assertNotIn(c['workflow_id'],['memory-review-update','memory-index-revision'])
        for p,data in outputs.items():p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.assertEqual(outputs,module.compose(self.root))
        for p in (path for name in ('watch-memory', 'content-memory', 'support-memory') for path in (ROOT.parents[1]/name/'agents/main').rglob('*.json')):
            text=p.read_text();self.assertNotIn('agent_id',text);self.assertNotIn('"target"',text)
    def test_composed_consumer_resolves_every_explicit_local_workflow_pin(self):
        for role, folder in [('veille','watch'),('contenu','content'),('accompagnement','support')]:
            source=ROOT.parents[1]/folder/'agents/main/workflows'
            destination=self.root/'agents'/role/'workflows'
            for file in source.glob('*.json'): shutil.copyfile(file, destination/file.name)
        for path,data in module.compose(self.root).items():
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        total=sum(assert_local_pins(self,self.root/'agents'/role/'workflows') for role in module.ROLES)
        self.assertEqual(total,18)
        bridge=self.root/'agents/veille/workflows/company-memory-query.json'
        definition=json.loads(bridge.read_text());definition['version']='1';bridge.write_bytes(module.encoded(definition))
        with self.assertRaises(AssertionError):
            assert_local_pins(self,self.root/'agents/veille/workflows')
    def test_write_rejects_missing_or_incompatible_local_pin_atomically(self):
        target=self.root/'agents/contenu/workflows/review_completion.json'
        for case, contents in [('old', {'workflow_id':'review_completion','version':'1'}), ('wrong-id', {'workflow_id':'other','version':'2'}), ('missing', None)]:
            with self.subTest(case=case):
                if contents is None: target.unlink()
                else: target.write_text(json.dumps(contents))
                before={str(p.relative_to(self.root)):p.read_bytes() if p.is_file() else None for p in self.root.rglob('*')}
                run=subprocess.run([sys.executable,str(ROOT/'compose.py'),'--consumer-dir',str(self.root),'--write'],capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
                self.assertNotEqual(run.returncode,0)
                self.assertIn('local Workflow review_completion',run.stderr)
                after={str(p.relative_to(self.root)):p.read_bytes() if p.is_file() else None for p in self.root.rglob('*')}
                self.assertEqual(before,after)
        target.write_text(json.dumps({'workflow_id':'review_completion','version':'2'}))
        run=subprocess.run([sys.executable,str(ROOT/'compose.py'),'--consumer-dir',str(self.root),'--write'],capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
        self.assertEqual(run.returncode,0,run.stderr)
        draft=json.loads((self.root/'agents/contenu/workflows/contenu-memory-draft.json').read_text())
        call=next(a for a in draft['actions'] if a.get('workflow_id')=='review_completion')
        self.assertEqual(call['workflow_version'],'2')
        bridge=json.loads((self.root/'agents/contenu/workflows/company-memory-query.json').read_text())
        self.assertEqual(bridge['actions'][0]['target']['version'],'1')

    def test_conflict_does_not_write(self):
        p=self.root/'agents/veille/workflows/company-memory-query.json';p.write_text('{"custom":true}')
        with self.assertRaisesRegex(ValueError,'overwrite divergent'):module.compose(self.root)
        self.assertEqual(p.read_text(),'{"custom":true}')
        self.assertNotIn('capabilities',json.loads((self.root/'agents/memory/agent-spec.json').read_text()))
    def test_missing_role_and_duplicate_identity(self):
        p=self.root/'agents/contenu/agent-spec.json';v=json.loads(p.read_text());v['agent_id']='c'+'0'*19;p.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'distinct'):module.compose(self.root)
    def test_broad_existing_grant_not_replaced(self):
        p=self.root/'agents/memory/agent-spec.json';v=json.loads(p.read_text());v['capabilities']=[{'name':'company-memory-query','allowed_agent_ids':['*']}];p.write_text(json.dumps(v))
        with self.assertRaisesRegex(ValueError,'conflicting existing'):module.compose(self.root)
    def test_upgrade_exact_old_bridges_and_capabilities(self):
        outputs=module.compose(self.root)
        for p,data in outputs.items():
            p.parent.mkdir(parents=True,exist_ok=True)
            if p.name.startswith('company-memory-') and p.parent.name=='workflows':
                value=json.loads(data);value['version']='1';value['title']=value['title'].replace('Memory — ','Mémoire — ',1);data=module.encoded(value)
            elif p==self.root/'agents/memory/agent-spec.json':
                value=json.loads(data)
                for cap in value['capabilities']:
                    cap['description']=cap['description'].replace('Manual memory integration: ','Raccordement manuel mémoire : ',1)
                data=module.encoded(value)
            p.write_bytes(data)
        upgraded=module.compose(self.root)
        bridge=json.loads(upgraded[self.root/'agents/veille/workflows/company-memory-query.json'])
        self.assertEqual(bridge['version'],'2')
        self.assertEqual(bridge['actions'][0]['target']['version'],'1')
        capability=json.loads(upgraded[self.root/'agents/memory/agent-spec.json'])['capabilities'][0]
        self.assertEqual(capability['version'],'1')
        self.assertEqual(len(capability['allowed_agent_ids']),3)
    def test_modified_old_bridge_is_not_treated_as_known(self):
        path=self.root/'agents/veille/workflows/company-memory-query.json'
        value=json.loads(module.compose(self.root)[path]);value['version']='1';value['title']='Mémoire — query';value['output']['extra']='changed'
        path.write_bytes(module.encoded(value))
        with self.assertRaisesRegex(ValueError,'overwrite divergent'):module.compose(self.root)
    def test_upgrade_known_old_module_resource_by_fingerprint(self):
        path=self.root/'agents/veille/miniapps/veille-memory-search-console.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((ROOT/'tests/fixtures/veille-memory-search-console-0.2.0.json').read_bytes())
        upgraded=module.compose(self.root)
        self.assertEqual(json.loads(upgraded[path])['version'],'2')
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'overwrite divergent'):module.compose(self.root)
if __name__=='__main__':unittest.main()
