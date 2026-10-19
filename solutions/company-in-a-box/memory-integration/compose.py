#!/usr/bin/env python3
"""Compose local memory bindings; dry-run first, no runtime call or approval.

The three role Modules are copied byte-for-byte. Instance IDs occur only in
consumer Agent Specs and generated company-memory-* bridge Workflows.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROLES = ('veille', 'contenu', 'accompagnement')
CONTRACTS = {
    'query': ('memory-query', ['proposal_id'], ['answer','citations','status','proposal_id','warning','checked_at','expires_at']),
    'search': ('memory-search', ['query'], ['results','summary','candidate_count','suppressed_count','status','warning','search_mode']),
    'capture': ('memory-capture-source', ['source_id','source_ref','content','source_date','confirmation_manuelle'], ['source','path','status']),
    'propose': ('memory-propose-update', ['proposal_id','source_id','title','content','evidence_quote','review_due','previous_revision','confirmation_manuelle'], ['proposal','path','status']),
}

def read(path):
    return json.loads(path.read_text())

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()

def compose(consumer, memory_alias='memory'):
    if not re.fullmatch(r'[a-z][a-z0-9_-]*', memory_alias):
        raise ValueError('invalid memory alias')
    specs = {r: read(consumer/'agents'/r/'agent-spec.json') for r in (*ROLES,memory_alias)}
    ids = [s.get('agent_id','') for s in specs.values()]
    if len(set(ids))!=4 or any(not re.fullmatch(r'[0-9a-v]{20}',x) for x in ids):
        raise ValueError('four distinct real Agent IDs are required')
    for alias,spec in specs.items():
        if spec.get('agent_alias')!=alias or spec.get('schema_version')!=2:
            raise ValueError('consumer Agent Spec identity mismatch: '+alias)
    memory=specs[memory_alias]; memory_id=memory['agent_id']
    for workflow,_,_ in CONTRACTS.values():
        if not (consumer/'agents'/memory_alias/'workflows'/f'{workflow}.json').is_file():
            raise ValueError('required memory Workflow missing: '+workflow)
    planned={}
    for role in ROLES:
        root=consumer/'agents'/role
        for required in [role+'-read']+(['contenu-save'] if role=='contenu' else []):
            if not (root/'workflows'/f'{required}.json').is_file():
                raise ValueError('required role Workflow missing: '+required)
        for file in (Path(__file__).parent/'modules'/role/'agents/main').rglob('*.json'):
            dest=root/file.relative_to(Path(__file__).parent/'modules'/role/'agents/main')
            planned[dest]=file.read_bytes()
        for op,(_,inputs,outputs) in CONTRACTS.items():
            target={'agent_id':memory_id,'capability':'company-memory-'+op,'version':'1'}
            bridge={'$schema':'agentmaurice.workflow/v2','schema_version':2,'kind':'workflow','workflow_id':'company-memory-'+op,'version':'1','title':'Mémoire — '+op,'actions':[{'id':'call','type':'workflow_call','target':target,'execution':'sync','input':{n:'{{ '+n+' }}' for n in inputs},'output_key':'memory'}],'output':{n:'{{ memory.data.'+n+' }}' for n in outputs}}
            planned[root/'workflows'/('company-memory-'+op+'.json')]=encoded(bridge)
            deps=specs[role].setdefault('dependencies',[])
            prior=[x for x in deps if x.get('capability')==target['capability']]
            if prior and prior!=[target]:
                raise ValueError('conflicting memory dependency: '+role+'/'+op)
            if not prior:deps.append(target)
    grants=[specs[r]['agent_id'] for r in ROLES]
    caps=memory.setdefault('capabilities',[])
    for op,(workflow,_,_) in CONTRACTS.items():
        cap={'name':'company-memory-'+op,'version':'1','workflow_id':workflow,'description':'Raccordement manuel mémoire : '+op,'allowed_agent_ids':grants}
        prior=[x for x in caps if x.get('name')==cap['name']]
        if prior and prior!=[cap]:raise ValueError('conflicting existing memory capability: '+op)
        if not prior:caps.append(cap)
    for dest,data in planned.items():
        if dest.exists() and dest.read_bytes()!=data:
            relative=dest.relative_to(consumer/'agents')
            pieces=relative.parts
            source_key=str(Path('modules')/pieces[0]/'agents/main'/Path(*pieces[1:]))
            legacy=read(Path(__file__).parent/'legacy-resource-hashes.json')
            if legacy.get(source_key)==hashlib.sha256(dest.read_bytes()).hexdigest():
                continue
            raise ValueError('refusing to overwrite divergent resource: '+str(dest))
    for alias,spec in specs.items():planned[consumer/'agents'/alias/'agent-spec.json']=encoded(spec)
    return planned

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--consumer-dir',required=True,type=Path);p.add_argument('--memory-alias',default='memory');p.add_argument('--write',action='store_true');a=p.parse_args()
    try: planned=compose(a.consumer_dir.resolve(),a.memory_alias)
    except (ValueError,OSError) as e:p.error(str(e))
    for dest,data in planned.items():
        changed=not dest.exists() or dest.read_bytes()!=data
        print(('WRITE ' if a.write else 'PLAN ')+str(dest)+(' [changed]' if changed else ' [identical]'))
        if a.write and changed:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
    print('No runtime mutation. Deploy memory first, then each role with the governed Agent Spec rail.')
if __name__=='__main__':main()
