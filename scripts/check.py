#!/usr/bin/env python3
"""Static checks for the distributable package, without network or secret access."""
import json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS={'.local','__pycache__','node_modules','.venv','evidence','backups'}
FORBIDDEN_SUFFIXES={'.db','.sqlite','.sqlite3','.duckdb','.parquet','.pem','.key','.pyc','.log','.png','.jpg','.zip','.tar','.gz'}
PATTERNS={
 'private-key':r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
 'github-token':r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',
 'provider-key':r'\bsk-(?:ant-[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{24,})',
 'jwt':r'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}',
 'runtime-instance-id':r'\bdb[0-9a-v]{18}\b',
 'private-home-path':r'/(?:Users|home)/[a-zA-Z][^\s/]+/',
}
def main():
 errors=[];count=0
 for p in sorted(ROOT.rglob('*')):
  rel=p.relative_to(ROOT)
  if '.git' in rel.parts:continue
  if p.is_symlink():errors.append(f'{rel}: symlink forbidden');continue
  if not p.is_file():continue
  count+=1
  if set(rel.parts)&FORBIDDEN_PARTS or p.suffix in FORBIDDEN_SUFFIXES or p.name.startswith('.env') or p.name in ['user-test.txt','config.yaml','agentmaurice.lock.json','runtime.db']:errors.append(f'{rel}: non-distributable file')
  try:t=p.read_text(encoding='utf-8')
  except UnicodeError:errors.append(f'{rel}: binary forbidden');continue
  for label,pattern in PATTERNS.items():
   if re.search(pattern,t):errors.append(f'{rel}: forbidden pattern {label}')
  if p.suffix=='.json' or p.name=='module.yaml':
   try:json.loads(t)
   except ValueError:errors.append(f'{rel}: invalid JSON')
  if p.suffix=='.md':
   for target in re.findall(r'\]\(([^)]+)\)',t):
    if target.startswith(('http:','https:','mailto:','#')):continue
    path=target.split('#')[0].strip('<>')
    if path and not (p.parent/path).exists():errors.append(f'{rel}: missing local link {path}')
 index=json.loads((ROOT/'modules.json').read_text())['modules'];manifests=list(ROOT.glob('*/module.yaml'))
 if {str(p.relative_to(ROOT)) for p in manifests}!={entry['manifest'] for entry in index}:errors.append('Module inventory incomplete or inconsistent')
 workflows=apps=0;keys=set()
 for entry in index:
  p=ROOT/entry['manifest'];mod=json.loads(p.read_text());base=p.parent/'agents/main'
  if mod['key'] in keys:errors.append(f'{p}: duplicate Module')
  keys.add(mod['key'])
  if entry['key']!=mod['key'] or entry['version']!=mod['version']:errors.append(f'{p}: inventory mismatch')
  wf=list((base/'workflows').glob('*.json'));ma=list((base/'miniapps').glob('*.json'));workflows+=len(wf);apps+=len(ma)
  if (len(wf),len(ma))!=(entry['workflows'],entry['miniapps']):errors.append(f'{p}: count mismatch')
  for ref in mod['provides'].get('actions',[])+mod['provides'].get('queries',[])+mod['provides'].get('apps',[]):
   kind='workflow' if 'workflow_id' in ref else 'miniapp';key=ref[kind+'_id'];resource=base/(kind+'s')/(key+'.json')
   if not resource.exists():errors.append(f'{p}: missing resource {key}');continue
   value=json.loads(resource.read_text())
   if value.get(kind+'_id')!=key or value.get('schema_version')!=2 or str(value.get('version'))!=str(ref[kind+'_version']):errors.append(f'{p}: invalid resource reference {key}')
 if errors:raise SystemExit('\n'.join(errors))
 subprocess.run([sys.executable, str(ROOT/'scripts/language_audit.py'), '--check'], cwd=ROOT, check=True)
 print(f'PASS: {count} text files, {len(index)} Modules, {workflows} Workflows, {apps} MiniApps ; links and distribution checks valid.')
if __name__=='__main__':main()
