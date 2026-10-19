#!/usr/bin/env python3
"""Tests locaux sans réseau ni One ; les générateurs travaillent dans une copie temporaire."""
import os,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PYTHON_SUITES=['company-in-a-box/template/tests','company-memory/tests','company-in-a-box/memory-integration/tests','company-in-a-box/daily-routine/tests','company-in-a-box/common-dossier/tests','company-in-a-box/enterprise-admin/tests','company-in-a-box/marketing-launch/tests']
NODE_TESTS=['company-in-a-box/memory-integration/tests/test_publication.mjs','company-in-a-box/daily-routine/tests/metrics.test.mjs','company-in-a-box/common-dossier/tests/domain.test.mjs','company-in-a-box/marketing-launch/tests/test_domain.cjs','company-in-a-box/marketing-launch/tests/test_generated_runtime.cjs']
def main():
 env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
 with tempfile.TemporaryDirectory(prefix='cib-offline-') as temp:
  work=Path(temp);shutil.copytree(ROOT/'solutions',work/'solutions')
  subprocess.run([sys.executable,str(work/'solutions/company-in-a-box/modules/veille/test_acl_contract.py')],env=env,cwd=work,check=True)
  for name in PYTHON_SUITES:
   subprocess.run([sys.executable,'-m','unittest','discover','-s',str(work/'solutions'/name),'-p','test_*.py','-v'],env=env,cwd=work,check=True)
  for name in NODE_TESTS:
   subprocess.run(['node',str(work/'solutions'/name)],env=env,cwd=work,check=True)
 print('PASS: 7 suites unittest, contrat ACL Python et 5 contrôles Node, sans réseau ni runtime.')
if __name__=='__main__':main()
