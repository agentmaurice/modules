#!/usr/bin/env python3
"""Prepare service gates for a reviewed published surface; no runtime call."""
import argparse,json
from pathlib import Path

ROLES={"veille":"cib_marketing","contenu":"cib_marketing","accompagnement":"cib_service_client","memory":"cib_admin"}

def prepare(surface,environment):
    wrapped="public_surface" in surface
    result=json.loads(json.dumps(surface["public_surface"] if wrapped else surface))
    agents={x['agent_id']:x['agent_alias'] for x in environment['agents']}
    for ref in result.get('workflows',[]):
        name=ref['workflow_id']
        if name.startswith('cib-admin-'): role='cib_admin'
        elif name.startswith('cib-case-'): role='cib_dossiers'
        elif name.startswith('cib-direction-'): role='cib_direction'
        else: role=ROLES.get(agents.get(ref['agent_id']))
        if role:
            old=ref.get('required_role')
            if old and old!=role: raise ValueError('Existing role differs; explicit reconciliation required: '+name)
            ref['required_role']=role
    return {**surface,"public_surface":result} if wrapped else {"public_surface":result}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--surface',type=Path,required=True);p.add_argument('--environment',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    value=prepare(json.loads(a.surface.read_text()),json.loads(a.environment.read_text()))
    if a.output.exists():p.error('refusing existing output')
    a.output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print('Prepared service gates only; review and publish through the native Application rail.')
