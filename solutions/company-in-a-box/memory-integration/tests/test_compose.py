import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('compose_memory',ROOT/'compose.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CompositionTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        for index,alias in enumerate((*module.ROLES,'memory')):
            p=self.root/'agents'/alias;p.mkdir(parents=True);(p/'workflows').mkdir()
            (p/'agent-spec.json').write_text(json.dumps({'schema_version':2,'agent_alias':alias,'agent_id':'c'+str(index)*19,'identity':{'instructions':'preserve me'}}))
            names=[x[0] for x in module.CONTRACTS.values()] if alias=='memory' else [alias+'-read',alias+'-save']
            for n in names:(p/'workflows'/f'{n}.json').write_text('{}')
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
        for p in ROOT.glob('modules/*/agents/main/**/*.json'):
            text=p.read_text();self.assertNotIn('agent_id',text);self.assertNotIn('"target"',text)
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
if __name__=='__main__':unittest.main()
