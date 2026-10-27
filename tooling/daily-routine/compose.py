#!/usr/bin/env python3
"""Compose the same daily routine Module in three existing Agents; no API call."""
import argparse,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ROLES=('veille','contenu','accompagnement')
def encoded(x):return (json.dumps(x,ensure_ascii=False,indent=2)+'\n').encode()
def compose(consumer):
    planned={}
    for role in ROLES:
        root=consumer/'agents'/role
        spec=json.loads((root/'agent-spec.json').read_text())
        if spec.get('agent_alias')!=role or spec.get('schema_version')!=2:raise ValueError('invalid consumer Agent '+role)
        for required in [role+'-read','company-memory-query']:
            if not (root/'workflows'/(required+'.json')).is_file():raise ValueError('missing existing workflow '+required)
        bridge_path=root/'workflows/company-memory-query.json'
        try: memory_bridge=json.loads(bridge_path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:raise ValueError('invalid company-memory-query bridge for '+role) from exc
        if not isinstance(memory_bridge,dict) or memory_bridge.get('workflow_id')!='company-memory-query' or memory_bridge.get('version')!='2':
            raise ValueError('company-memory-query bridge must be workflow version 2 for '+role)
        source=ROOT.parents[1]/'daily-routine/agents/main'
        for path in sorted(source.rglob('*.json')):planned[root/path.relative_to(source)]=path.read_bytes()
        code = "import { callTool } from './tools/nats_bridge.ts';\n" + 'const x={{ json . }}; if(typeof x.dossier_id!=="string"||!/^[a-z0-9][a-z0-9-]{0,63}$/.test(x.dossier_id)) throw Error("invalid_dossier_id"); const value=await callTool("recipe--application_data_v1",{operation:"read",namespace:"cib-'+role+'",record_key:x.dossier_id}); return {data:{record:value.record.data}};'
        action={'id':'read','type':'code_execution','context':{'allowed_tools':['recipe--application_data_v1']},'code':code,'output_key':'local'}
        bridge={'$schema':'agentmaurice.workflow/v2','schema_version':2,'kind':'workflow','workflow_id':'daily-role-read','version':'3','title':'Routine — view local case','actions':[action],'output':{'record':'{{ local.data.record }}'}}
        planned[root/'workflows/daily-role-read.json']=encoded(bridge)
        context=json.loads((source/'workflows/daily-context.json').read_text())
        context['version']='3'
        context['actions'][0]={**action,'id':'dossier'}
        planned[root/'workflows/daily-context.json']=encoded(context)
    legacy=json.loads((ROOT/'legacy-resource-hashes.json').read_text())
    for dest,data in planned.items():
        if dest.exists() and dest.read_bytes()!=data:
            relative=str(dest.relative_to(consumer))
            known=legacy.get(relative, [])
            if isinstance(known,str):known=[known]
            if hashlib.sha256(dest.read_bytes()).hexdigest() not in known:
                raise ValueError('refusing divergent resource '+str(dest))
    return planned

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--consumer-dir',type=Path,required=True);p.add_argument('--write',action='store_true');a=p.parse_args()
    try:planned=compose(a.consumer_dir.resolve())
    except (ValueError,OSError)as e:p.error(str(e))
    for dest,data in planned.items():
        changed=not dest.exists() or dest.read_bytes()!=data
        if a.write and changed:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        print(('WRITE 'if a.write else'PLAN ')+str(dest)+(' [new]'if changed else' [identical]'))
    print('No runtime mutation. Review and deploy each Agent Spec, then publish the local Application surface.')
if __name__=='__main__':main()
