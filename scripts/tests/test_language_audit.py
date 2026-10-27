"""Exercise the language screen and exact-line exception expiry offline."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class LanguageAuditTest(unittest.TestCase):
    def test_candidates_and_stale_exceptions_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='language-audit-') as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            shutil.copy(ROOT / 'scripts/language_audit.py', root / 'scripts/language_audit.py')
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            candidate = 'Exemple \u00e9tranger'
            (root / 'product.txt').write_text(candidate + '\n')
            exceptions = root / 'scripts/language_exceptions.json'
            exceptions.write_text('[]')
            def run():
                return subprocess.run([sys.executable, str(root / 'scripts/language_audit.py'), '--check'],
                                      cwd=root, capture_output=True, text=True)
            self.assertNotEqual(run().returncode, 0)
            digest = hashlib.sha256(candidate.encode()).hexdigest()
            exceptions.write_text(json.dumps([{'path': 'product.txt', 'line_sha256': digest,
                                              'reason': 'Historical test data'}]))
            self.assertEqual(run().returncode, 0)
            (root / 'product.txt').write_text(candidate + ' changed\n')
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('stale exception', result.stdout)

    def test_archive_scans_nested_ui_labels_and_rejects_duplicate_exceptions(self):
        with tempfile.TemporaryDirectory(prefix='language-archive-') as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            shutil.copy(ROOT / 'scripts/language_audit.py', root / 'scripts/language_audit.py')
            exceptions = root / 'scripts/language_exceptions.json'
            exceptions.write_text('[]')
            label = 'Iden' + 'tifiant'
            (root / 'miniapp.json').write_text(json.dumps({'column_labels': {'user_id': label}}, indent=2))
            def run():
                return subprocess.run([sys.executable, str(root / 'scripts/language_audit.py'), '--check'],
                                      cwd=root, capture_output=True, text=True)
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('scan=filesystem', result.stdout)
            line = next(line.strip() for line in (root / 'miniapp.json').read_text().splitlines() if label in line)
            item = {'path':'miniapp.json', 'line_sha256':hashlib.sha256(line.encode()).hexdigest(), 'reason':'Test fixture'}
            exceptions.write_text(json.dumps([item, item]))
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('duplicate language exception', result.stderr)

    def test_code_fragment_exception_does_not_mask_new_french_text(self):
        with tempfile.TemporaryDirectory(prefix='language-code-') as directory:
            root = Path(directory); (root / 'scripts').mkdir()
            shutil.copy(ROOT / 'scripts/language_audit.py', root / 'scripts/language_audit.py')
            fragment = 'const status = "gain_mesur\u00e9";'
            document = {'kind':'workflow', 'actions':[{'id':'validate', 'code':fragment + '\nreturn status;'}]}
            target = root / 'workflow.json'
            target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
            entry = {'path':'workflow.json', 'json_pointer':'/actions/0/code', 'action_id':'validate',
                     'fragment':fragment, 'expected_count':1, 'reason':'Stable wire status'}
            exceptions = root / 'scripts/language_exceptions.json'
            exceptions.write_text(json.dumps([entry]))
            def run():
                return subprocess.run([sys.executable, str(root / 'scripts/language_audit.py'), '--check'],
                                      cwd=root, capture_output=True, text=True)
            self.assertEqual(run().returncode, 0, run().stderr)
            document['actions'][0]['code'] += '\nconst message = "' + ('Er' + 'reur d\u00e9tect\u00e9e') + '";'
            target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
            result = run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('candidate lines', result.stdout)
            document['actions'][0]['code'] = 'return 1;'
            target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
            self.assertIn('stale code fragment', run().stderr)
            document['actions'][0]['code'] = fragment
            target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
            exceptions.write_text(json.dumps([entry, entry]))
            self.assertIn('duplicate language exception', run().stderr)

    def test_short_ui_labels_are_checked_but_wire_values_and_data_are_not(self):
        with tempfile.TemporaryDirectory(prefix='language-labels-') as directory:
            root = Path(directory); (root / 'scripts').mkdir()
            shutil.copy(ROOT / 'scripts/language_audit.py', root / 'scripts/language_audit.py')
            (root / 'scripts/language_exceptions.json').write_text('[]')
            target = root / 'miniapp.json'
            document = {'kind':'miniapp', 'ui':{'layout':[{'type':'table', 'column_labels':{'user_id':'User ID'}},
                        {'type':'text','value':'Ready'}]}, 'forms':[{'fields':[{'title':'Purpose',
                        'options':[{'value':'oui','label':'Yes'}, {'value':'non','label':'No'}]}]}],
                        'initial_state':{'user_text':'Objectif'}}
            def run():
                target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
                return subprocess.run([sys.executable, str(root / 'scripts/language_audit.py'), '--check'],
                                      cwd=root, capture_output=True, text=True)
            self.assertEqual(run().returncode, 0)
            for label in ('Oui', 'Non', 'Objectif', 'Relecture'):
                document['ui']['layout'][0]['column_labels']['user_id'] = label
                result = run()
                self.assertNotEqual(result.returncode, 0, label)
                self.assertIn('/ui/layout/0/column_labels/user_id', result.stdout)
            document['ui']['layout'][0]['column_labels']['user_id'] = 'User ID'
            document['forms'][0]['fields'][0]['options'][0]['label'] = 'Oui'
            self.assertIn('/forms/0/fields/0/options/0/label', run().stdout)
            document['forms'][0]['fields'][0]['options'][0]['label'] = 'Yes'
            document['forms'][0]['fields'][0]['title'] = 'Objectif'
            self.assertIn('/forms/0/fields/0/title', run().stdout)
            document['forms'][0]['fields'][0]['title'] = 'Purpose'
            document['ui']['layout'][1]['value'] = 'Relecture'
            self.assertIn('/ui/layout/1/value', run().stdout)
            # The receipt's two unaccented examples are presentation text;
            # technical keys and user-entered text stay outside this check.
            document['forms'][0]['fields'][0]['title'] = 'Dossier'
            document['ui']['layout'][1]['value'] = 'Lecture : non · Partage : non'
            result = run()
            self.assertIn('/forms/0/fields/0/title', result.stdout)
            self.assertIn('/ui/layout/1/value', result.stdout)
            document['forms'][0]['fields'][0]['title'] = 'Case'
            document['ui']['layout'][1]['value'] = 'The lecture starts at noon'
            document['initial_state']['user_text'] = 'Dossier'
            self.assertEqual(run().returncode, 0)

    def test_check_reports_language_failure_without_python_traceback(self):
        with tempfile.TemporaryDirectory(prefix='language-check-') as directory:
            root = Path(directory); (root / 'scripts').mkdir()
            shutil.copy(ROOT / 'scripts/check.py', root / 'scripts/check.py')
            (root / 'scripts/language_audit.py').write_text('raise SystemExit(2)\n')
            (root / 'modules.json').write_text('{"modules": []}\n')
            result = subprocess.run([sys.executable, str(root / 'scripts/check.py')],
                                    cwd=root, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('language audit failed (exit 2)', result.stderr)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
