"""Offline regression for portable MCP requirements and fail-closed composition."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPOSER = Path(__file__).resolve().parents[1] / 'compose.py'

class ComposeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.agent = self.root / 'agents/memory'
        self.agent.mkdir(parents=True)
        (self.root/'agentmaurice.project.json').write_text(json.dumps({'agents':[{'agent_alias':'memory','path':'agents/memory'}]}))
        self.spec = self.agent/'agent-spec.json'
        self.original = {'schema_version':2,'agent_alias':'memory','agent_id':'test-agent','identity':{'name':'Keep identity'},'mcp_requirements':[{'registry_name':'other','required_tools':['other.query']}]}
        self.spec.write_text(json.dumps(self.original))

    def compose(self, write=False):
        return subprocess.run([sys.executable,str(COMPOSER),'--consumer-dir',str(self.root),'--agent-alias','memory']+(['--write'] if write else []),text=True,capture_output=True)

    def test_dry_run_then_replay_preserves_identity_and_requirements(self):
        before=self.spec.read_bytes()
        self.assertEqual(self.compose().returncode,0)
        self.assertEqual(self.spec.read_bytes(),before)
        self.assertFalse((self.agent/'workflows').exists())
        result=self.compose(True)
        self.assertEqual(result.returncode,0,result.stderr)
        spec=json.loads(self.spec.read_text())
        self.assertEqual(spec['identity'],self.original['identity'])
        req={r['registry_name']:r for r in spec['mcp_requirements']}
        self.assertEqual(req['other'],self.original['mcp_requirements'][0])
        self.assertIn('memory.query',req['company_memory']['required_tools'])
        self.assertIn('brain.keyword',req['brain']['required_tools'])
        written=self.spec.read_bytes()
        self.assertEqual(self.compose(True).returncode,0)
        self.assertEqual(self.spec.read_bytes(),written)

    def test_conflicting_resource_does_not_write_spec_or_resources(self):
        (self.agent/'workflows').mkdir()
        conflict=self.agent/'workflows/memory-health.json'
        conflict.write_text('{}')
        before=self.spec.read_bytes()
        self.assertNotEqual(self.compose(True).returncode,0)
        self.assertEqual(self.spec.read_bytes(),before)
        self.assertEqual(list((self.agent/'workflows').iterdir()),[conflict])

    def test_conflicting_provider_rejected_before_copy(self):
        self.original['mcp_requirements']=[{'registry_name':'brain','runtime_provider':'vm'}]
        self.spec.write_text(json.dumps(self.original))
        self.assertNotEqual(self.compose(True).returncode,0)
        self.assertFalse((self.agent/'workflows').exists())

if __name__ == '__main__':
    unittest.main()
