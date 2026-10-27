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


if __name__ == '__main__':
    unittest.main()
