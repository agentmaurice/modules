#!/usr/bin/env python3
"""Tests locaux hors réseau et One dans une copie temporaire du dépôt."""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PYTHON_SUITES = ['templates/company-in-a-box/tests'] + [f'tooling/{name}/tests' for name in ('company-memory', 'memory-integration', 'daily-routine', 'work-cases', 'enterprise-admin', 'marketing-launch', 'image-studio', 'profile', 'catalog')]
NODE_TESTS = [f'tooling/{path}' for path in ('memory-integration/tests/test_publication.mjs', 'daily-routine/tests/metrics.test.mjs', 'work-cases/tests/domain.test.mjs', 'marketing-launch/tests/test_domain.cjs', 'marketing-launch/tests/test_generated_runtime.cjs')]
def main():
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
    with tempfile.TemporaryDirectory(prefix='modules-offline-') as temp:
        work = Path(temp)
        for name in ('templates', 'tooling', 'scripts'):
            shutil.copytree(ROOT / name, work / name)
        for manifest in ROOT.glob('*/module.yaml'):
            shutil.copytree(manifest.parent, work / manifest.parent.name)
        subprocess.run([sys.executable, str(work / 'tooling/roles/test_acl_contract.py')], env=env, cwd=work, check=True)
        for name in PYTHON_SUITES:
            subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(work / name), '-p', 'test_*.py', '-v'], env=env, cwd=work, check=True)
        for name in NODE_TESTS:
            subprocess.run(['node', str(work / name)], env=env, cwd=work, check=True)
        for name in ('work-cases', 'daily-routine', 'enterprise-admin', 'marketing-launch', 'image-studio', 'profile'):
            module = work / name
            before = {p.relative_to(module): p.read_bytes() for p in module.rglob('*') if p.is_file()}
            extras = [work / 'templates/company-in-a-box/tests/marketing-launch-plan.json', work / 'tooling/marketing-launch/service-gates.json'] if name == 'marketing-launch' else []
            extra_before = {p: p.read_bytes() for p in extras}
            subprocess.run([sys.executable, str(work / 'tooling' / name / 'build.py')], env=env, cwd=work, check=True)
            after = {p.relative_to(module): p.read_bytes() for p in module.rglob('*') if p.is_file()}
            if before != after or any(p.read_bytes() != data for p, data in extra_before.items()):
                raise SystemExit(f'{name}: le générateur ne reproduit pas les ressources publiées')

    print('PASS: 10 suites unittest, contrat ACL Python et 5 contrôles Node et 6 reconstructions à octets identiques, sans réseau ni runtime.')
if __name__ == '__main__': main()
