#!/usr/bin/env python3
"""Copie contrôlée de ressources V2, sans appel runtime. Dry-run par défaut."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--consumer-dir',required=True,type=Path)
p.add_argument('--agent-alias',required=True)
p.add_argument('--write',action='store_true')
a=p.parse_args()
root=Path(__file__).resolve().parent
project=a.consumer_dir.resolve()
manifest=json.loads((project/'agentmaurice.project.json').read_text())
entry=next((x for x in manifest['agents'] if x['agent_alias']==a.agent_alias),None)
if entry is None: raise SystemExit('Agent alias absent: run spec init first')
agent=(project/entry['path']).resolve()
if not agent.is_relative_to(project): raise SystemExit('Agent path must stay inside consumer')
spec=json.loads((agent/'agent-spec.json').read_text())
if spec.get('schema_version')!=2 or spec.get('agent_alias')!=a.agent_alias or not spec.get('agent_id'): raise SystemExit('Expected initialized Agent Spec V2')
module=json.loads((root/'module/module.yaml').read_text())
requirements={}
for requirement in spec.get('mcp_requirements',[]):
 name=requirement['registry_name']
 if name in requirements: raise SystemExit('Duplicate MCP requirement: '+name)
 requirements[name]=dict(requirement)
for requirement in module.get('requires',{}).get('mcp',[]):
 name=requirement['name']
 existing=requirements.get(name,{'registry_name':name,'runtime_provider':'docker'})
 if existing.get('runtime_provider','docker')!='docker': raise SystemExit('Conflicting MCP provider: '+name)
 existing['required_tools']=sorted(set(existing.get('required_tools',[]))|set(requirement.get('required_tools',[])))
 requirements[name]=existing
spec['mcp_requirements']=list(requirements.values())
spec_bytes=(json.dumps(spec,ensure_ascii=False,indent=2)+'\n').encode()
files=[]
for kind in ['workflows','miniapps']:
 for src in sorted((root/'module/agents/main'/kind).glob('*.json')): files.append((src,agent/kind/src.name))
files.append((root/'tests/test-plan.json',agent/'tests/test-plan.json'))
for src,dst in files:
 if dst.exists() and dst.read_bytes()!=src.read_bytes(): raise SystemExit('Refusing different existing file: '+str(dst))
for src,dst in files:
 digest=hashlib.sha256(src.read_bytes()).hexdigest()
 if a.write:
  dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
  if hashlib.sha256(dst.read_bytes()).hexdigest()!=digest:raise SystemExit('Copy verification failed')
 print(json.dumps({'file':str(src.relative_to(root)),'sha256':digest,'written':a.write}))
if a.write:
 (agent/'agent-spec.json').write_bytes(spec_bytes)
print(json.dumps({'file':'agent-spec.json','mcp_requirements':spec['mcp_requirements'],'sha256':hashlib.sha256(spec_bytes).hexdigest(),'written':a.write}))
