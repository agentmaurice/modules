import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
for(const role of ['veille','contenu','accompagnement']) {
 const wf=JSON.parse(fs.readFileSync(`${root}/../../${{veille:'watch-memory',contenu:'content-memory',accompagnement:'support-memory'}[role]}/agents/main/workflows/${role}-memory-contribute.json`));
 const validate=wf.actions.find(x=>x.id==='validate').code;
 const input={confirmation_manuelle:'oui',dossier_id:'demo',proposal_id:'demo-1',selected_excerpt:'preuve',review_due:'2099-12-31'};
 await assert.rejects(new AsyncFunction(validate.replace('{{ json . }}',JSON.stringify(input)))(), /company_memory_publication_confirmation_required/);
 const check=wf.actions.find(x=>x.id==='read-local').code.replace("import { callTool } from './tools/nats_bridge.ts';\n",'').replace('{{ json .request }}',JSON.stringify({dossier_id:'demo'}));
 let calls=0;
 await assert.rejects(new AsyncFunction('callTool',check)(async()=>{calls++;return {record:{permissions:{can_read:true,can_manage:false},data:{secret:'private'}}}}), /only_owner_may_publish/);
 assert.equal(calls,1);
 const result=await new AsyncFunction('callTool',check)(async(name,args)=>{assert.equal(name,'recipe--application_data_v1');assert.equal(args.namespace,`cib-${role}`);return {record:{permissions:{can_manage:true},data:{id:'demo'}}}});
 assert.equal(result.data.record.id,'demo');
 const actions=wf.forms[0].actions_on_submit;
 assert.ok(actions.indexOf('read-local')<actions.indexOf('capture'));
}
console.log('Publication commune : accord explicite et propriétaire requis pour les trois rôles');
