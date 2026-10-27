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

    def compose(self, write=False, extra=()):
        args=[sys.executable,str(COMPOSER),'--consumer-dir',str(self.root),'--agent-alias','memory']+(['--write'] if write else [])+list(extra)
        return subprocess.run(args,text=True,capture_output=True)

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

    def test_update_replaces_only_module_owned_files_and_lists_them(self):
        module_file=COMPOSER.parent.parents[1]/'company-memory/agents/main/workflows/memory-health.json'
        (self.agent/'workflows').mkdir()
        owned=self.agent/'workflows/memory-health.json'
        owned.write_text('{"version":"2"}')
        extra=self.agent/'workflows/consumer-own.json'
        extra.write_text('{"consumer":true}')
        dry=self.compose(False,['--update'])
        self.assertEqual(dry.returncode,0,dry.stderr)
        self.assertIn('would_replace_files',dry.stdout)
        self.assertIn('memory-health.json',dry.stdout)
        self.assertEqual(owned.read_text(),'{"version":"2"}')
        result=self.compose(True,['--update'])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(owned.read_bytes(),module_file.read_bytes())
        self.assertEqual(extra.read_text(),'{"consumer":true}')
        self.assertIn('replaced_files',result.stdout)
        replaced=[json.loads(line) for line in result.stdout.splitlines() if 'replaced_files' in line]
        self.assertEqual(replaced,[{'replaced_files':['workflows/memory-health.json']}])
        self.assertEqual(self.compose(True,['--update']).returncode,0)

    def test_update_replaces_every_owned_conflict_in_one_run(self):
        (self.agent/'workflows').mkdir()
        (self.agent/'miniapps').mkdir()
        workflow=self.agent/'workflows/memory-health.json'
        workflow.write_text('{"version":"2"}')
        miniapp=self.agent/'miniapps/memory-query-console.json'
        miniapp.write_text('{"version":"3"}')
        result=self.compose(True,['--update'])
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(workflow.read_bytes(),(COMPOSER.parent.parents[1]/'company-memory/agents/main/workflows/memory-health.json').read_bytes())
        self.assertEqual(miniapp.read_bytes(),(COMPOSER.parent.parents[1]/'company-memory/agents/main/miniapps/memory-query-console.json').read_bytes())
        replaced=[json.loads(line) for line in result.stdout.splitlines() if 'replaced_files' in line][0]['replaced_files']
        self.assertEqual(sorted(replaced),['miniapps/memory-query-console.json','workflows/memory-health.json'])

    def test_retired_workflow_is_reported_and_never_deleted(self):
        (self.agent/'workflows').mkdir()
        retired=self.agent/'workflows/memory-resolve-candidate.json'
        retired.write_text('{"version":"6"}')
        self.assertFalse((COMPOSER.parent.parents[1]/'company-memory/agents/main/workflows/memory-resolve-candidate.json').exists())
        for write in (False,True):
            result=self.compose(write,['--update'])
            self.assertEqual(result.returncode,0,result.stderr)
            notices=[json.loads(line) for line in result.stdout.splitlines() if 'retired_files_present' in line]
            self.assertEqual([n['retired_files_present'] for n in notices],[['workflows/memory-resolve-candidate.json']])
            self.assertEqual(retired.read_text(),'{"version":"6"}')
        retired.unlink()
        self.assertNotIn('retired_files_present',self.compose(True,['--update']).stdout)

if __name__ == '__main__':
    unittest.main()
