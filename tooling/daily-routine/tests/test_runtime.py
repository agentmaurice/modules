"""Execute generated report and context code with synthetic inputs."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / 'daily-routine/agents/main/workflows'


def run_code(workflow, action_id, substitutions):
    definition = json.loads((WORKFLOWS / (workflow + '.json')).read_text())
    code = next(action['code'] for action in definition['actions'] if action['id'] == action_id)
    for marker, value in substitutions.items():
        code = code.replace(marker, json.dumps(value))
    program = 'const result = (() => {\n' + code + '\n})(); process.stdout.write(JSON.stringify(result));'
    result = subprocess.run(['node', '-e', program], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


class GeneratedRuntimeTest(unittest.TestCase):
    def test_report_validation_executes_real_date_check(self):
        result = run_code('daily-report', 'validate', {
            '{{ json . }}': {'jeu': 'qualification', 'date_debut': '2026-10-01', 'date_fin': '2026-10-31'},
        })
        self.assertEqual(result['date_debut'], '2026-10-01')

    def test_context_checks_finite_expiry_and_preserves_record(self):
        result = run_code('daily-context', 'context', {
            '{{ json .local }}': {'data': {'record': {'objectif': 'Synthetic case'}}},
            '{{ json .memory }}': {'data': {'status': 'validated', 'answer': 'Synthetic fact',
                                           'citations': ['source'], 'expires_at': '2099-01-01T00:00:00Z',
                                           'proposal_id': 'synthetic'}},
        })
        self.assertTrue(result['ready'])
        self.assertEqual(result['dossier']['objectif'], 'Synthetic case')
        self.assertEqual(result['memory_answer'], 'Synthetic fact')


if __name__ == '__main__':
    unittest.main()
