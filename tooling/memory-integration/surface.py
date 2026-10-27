#!/usr/bin/env python3
"""Render an Application surface draft from a fresh app-get snapshot; never apply."""
import argparse
import json
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--consumer-dir',type=Path,required=True);p.add_argument('--application-snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
app=json.loads(a.application_snapshot.read_text());surface=app['public_surface']
# Server owns version/content_hash; preserve all existing resources and entrypoints.
result={'workflows':list(surface.get('workflows',[])),'miniapps':list(surface.get('miniapps',[]))}
for role in ('veille','contenu','accompagnement'):
 root=a.consumer_dir/'agents'/role;agent=json.loads((root/'agent-spec.json').read_text())['agent_id']
 for kind in ('workflows','miniapps'):
  idkey='workflow_id' if kind=='workflows' else 'miniapp_id'
  for f in sorted((root/kind).glob(role+'-memory-*.json')):
   resource=json.loads(f.read_text());entry={'agent_id':agent,idkey:resource[idkey],'version':resource['version']}
   current=[x for x in result[kind] if x.get('agent_id')==agent and x.get(idkey)==entry[idkey]]
   if current and current!=[entry]:raise ValueError('conflicting surface resource: '+entry[idkey])
   if not current:result[kind].append(entry)
a.output.write_text(json.dumps({'public_surface':result},ensure_ascii=False,indent=2)+'\n')
print('Surface draft written; review, set and publish through the existing AM rail.')
