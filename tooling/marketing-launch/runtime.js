const NS='cib-launch-marketing';
function payload(response) { const x=response&&response.data?response.data:response; if (!x || typeof x!=='object') throw Error('broker_payload_invalid'); return x; }
async function invoke(operation,args) { return payload(await callTool('recipe--application_data_v1',{operation,...args})); }
function checked(item,ns,key) {
  if (!item || item.namespace!==ns || item.key!==key || !item.data || !Number.isSafeInteger(item.revision) || item.revision<1) throw Error('broker_identity_revision_invalid');
  if (!item.permissions || ['can_read','can_write','can_manage'].some(k=>typeof item.permissions[k]!=='boolean')) throw Error('broker_permissions_invalid');
  if (ns===NS) {validateLaunchRecord(item.data);if (recordKey(item.data.jeu,item.data.kind,item.data.id)!==key) throw Error('stored_identity_invalid');}
  return item;
}
async function load(game,kind,key) { const target=recordKey(game,kind,key);return checked((await invoke('read',{namespace:NS,record_key:target})).record,NS,target); }
async function foreign(ns,key,revision) { const x=checked((await invoke('read',{namespace:ns,record_key:id(key,'source_id')})).record,ns,key);if(x.revision!==expectedRevision(revision))throw Error('source_revision_changed');return {...x.data,revision:x.revision}; }
function prefill(item,form) {
  const r=item.data;
  const common={jeu:r.jeu,kind:r.kind,id:r.id,expected_revision:String(item.revision),confirmation_manuelle:'non',subject_user_id:'',permission:'read'};
  if(form==='campaign')return {...common,campaign_id:r.id,objectif:r.objectif,audience:r.audience,promesse:r.promesse,canal:r.canal,responsable:r.responsable,echeance:r.echeance,critere_fin:r.critere_fin};
  if(form==='content')return {...common,campaign_id:r.id,veille_ref:r.veille_ref,veille_revision:String(r.veille_revision||''),contenu_ref:r.contenu_ref,contenu_revision:String(r.contenu_revision||''),preuve_ref:r.preuve_ref};
  if(form==='request')return {...common,campaign_id:r.kind==='campaign'?r.id:r.campaign_id,campaign_revision:String(r.kind==='campaign'?item.revision:r.campaign_revision),trial_id:r.kind==='trial'?r.id:'',personne_ref:r.personne_ref||'',besoin:r.besoin||'',objectif:r.objectif};
  if(form==='support')return {...common,trial_id:r.id,phase:r.phase==='demande'?'en_cours':r.phase,accompagnement_ref:r.accompagnement_ref||'',accompagnement_revision:String(r.accompagnement_revision||''),date_confirmation:r.date_confirmation||'',confirmation_resultat:'non'};
  return common;
}
const phaseLabels={brouillon:'Draft',contenu_pret:'Content ready',demande:'Requested',en_cours:'In progress',bloque:'Blocked',premier_resultat_confirme:'First result confirmed'};
const kindLabels={campaign:'Campaign',trial:'Trial'};
function result(extra={}) {return {record:null,revision:0,owner_user_id:'',permissions:{},permissions_summary:'',shares:[],share_count:0,rows:[],items:[],people:[],selected_target:null,summary:null,prefill:{},effects:[],replayed:false,message:'',scope:'internal_only',validation_mode:'manual_attestation',external_effect:false,...extra};}
function view(item,form,message='',open=false) {
  const p=item.permissions, shares=Array.isArray(item.shares)?item.shares:[], bag=prefill(item,form);
  return result({record:item.data,revision:item.revision,owner_user_id:item.owner_user_id||'',permissions:p,permissions_summary:'Read: '+(p.can_read?'yes':'no')+' · Write: '+(p.can_write?'yes':'no')+' · Share: '+(p.can_manage?'yes':'no'),shares,share_count:shares.length,prefill:bag,rows:[{jeu:item.data.jeu,kind:item.data.kind,id:item.data.id,phase:item.data.phase,revision:item.revision,objectif:item.data.objectif}],message,effects:open?[{type:'open_form',payload:{form_id:form,submit_event:'save',prefill:bag}}]:[]});
}
async function persist(data,revision,form,message) { const key=recordKey(data.jeu,data.kind,data.id);const item=checked((await invoke('save',{namespace:NS,record_key:key,data,expected_revision:revision})).record,NS,key);return view(item,form,message,true); }
async function accessible(game,filterKind) {
  jeu(game);if(filterKind && !['all','campaign','trial'].includes(filterKind))throw Error('kind_invalid');
  const p=await invoke('list',{namespace:NS,prefix:game+'/'});
  if (!Array.isArray(p.items) || !Number.isSafeInteger(p.total) || p.total!==p.items.length) throw Error('bounded_list_incomplete');
  const items=p.items.map(x=>{const key=x.record_key||x.key;const data=x.data||x.record;if(typeof key!=='string'||!key.startsWith(game+'/'))throw Error('list_identity_invalid');validateLaunchRecord(data);if(recordKey(data.jeu,data.kind,data.id)!==key)throw Error('list_identity_invalid');return {data,revision:x.revision,permissions:x.permissions};});
  return items.filter(x=>!filterKind||filterKind==='all'||x.data.kind===filterKind);
}
async function execute(operation,x) {
  object(x,'input');
  if(operation==='campaign-save') {const data=normalizeCampaign(x);return persist(data,expectedRevision(x.expected_revision??0,true),'campaign','Campaign saved. Any brief change requires content to be linked again.');}
  if(operation==='content-link') {
    manual(x.confirmation_manuelle);const c=await load(x.jeu,'campaign',x.campaign_id);if(c.revision!==expectedRevision(x.expected_revision))throw Error('campaign_revision_changed');
    const v=await foreign('cib-veille',x.veille_ref,x.veille_revision), d=await foreign('cib-contenu',x.contenu_ref,x.contenu_revision);
    return persist(linkContent(c.data,x,v,d),c.revision,'content','Watch and Content references linked to the revisions read. Internal draft only.');
  }
  if(operation==='request') {
    manual(x.confirmation_manuelle);const c=await load(x.jeu,'campaign',x.campaign_id);if(c.revision!==expectedRevision(x.campaign_revision))throw Error('campaign_revision_changed');
    // Revalidate the pinned sources; a changed draft requires a new review/link.
    const v=await foreign('cib-veille',c.data.veille_ref,c.data.veille_revision), d=await foreign('cib-contenu',c.data.contenu_ref,c.data.contenu_revision);linkContent(c.data,{...c.data,confirmation_manuelle:'oui'},v,d);
    const data={...createTrial(c.data,x),campaign_revision:c.revision};
    let existing=null;
    try {existing=await load(data.jeu,'trial',data.id);} catch(error) {if(!String(error?.message||error).includes('[NOT_FOUND]'))throw error;}
    if(existing) {
      const same=['campaign_id','campaign_revision','personne_ref','besoin','objectif','contenu_ref','contenu_revision'].every(k=>existing.data[k]===data[k]);if(!same)throw Error('request_id_conflict');
      return {...view(existing,'request','Request already recorded: no duplicate creation or reset.',true),replayed:true};
    }
    return persist(data,0,'request','Private internal request created. Explicitly share this record with the support person.');
  }
  if(operation==='progress') {
    manual(x.confirmation_manuelle);const t=await load(x.jeu,'trial',x.trial_id);if(t.revision!==expectedRevision(x.expected_revision))throw Error('trial_revision_changed');
    const support=await foreign('cib-accompagnement',x.accompagnement_ref,x.accompagnement_revision);
    return persist(progressTrial(t.data,x,support),t.revision,'support',x.phase==='premier_resultat_confirme'?'First result attested internally with evidence. No commercial conversion inferred.':'Internal progress updated.');
  }
  if(operation==='read') {if(!['campaign','content','request','support','sharing'].includes(x.form_id))throw Error('form_invalid');return view(await load(x.jeu,x.kind,x.id),x.form_id,'Accessible record reviewed.');}
  if(operation==='list'||operation==='summary') {
    const items=await accessible(x.jeu,operation==='summary'?'all':x.kind);
    const rows=items.map(({data:r,revision})=>({jeu:r.jeu,kind:r.kind,kind_label:kindLabels[r.kind]||r.kind,id:r.id,phase:r.phase,phase_label:phaseLabels[r.phase]||r.phase,revision,objectif:r.objectif,prochaine_etape:r.prochaine_etape||'Prepare or review content.'}));
    return result({items:rows,rows,summary:summarize(items.map(r=>r.data)),message:'View limited to records accessible to your identity. Results are internal attestations; no conversion rate or gain is inferred.'});
  }
  if(operation==='people') {
    const item=await load(x.jeu,x.kind,x.id);const p=await invoke('people',{namespace:NS,record_key:recordKey(x.jeu,x.kind,x.id)});
    if(!Array.isArray(p.people))throw Error('broker_people_invalid');const people=p.people.map(p=>({user_id:text(p.user_id,'member_id',256),display_name:text(p.display_name,'member_name',256)}));
    const target=x.subject_user_id?people.find(p=>p.user_id===x.subject_user_id):null;if(x.subject_user_id&&!target)throw Error('external_target');
    const bag={...prefill(item,'sharing'),subject_user_id:target?.user_id||''};
    return {...view(item,'sharing','Existing members; no permissions changed.'),people,selected_target:target,effects:target?[{type:'open_form',payload:{form_id:'sharing',submit_event:'save',prefill:bag}}]:[]};
  }
  if(operation==='share') {
    manual(x.confirmation_manuelle);if(!['read','write','none'].includes(x.permission))throw Error('permission_invalid');const subject=text(x.subject_user_id,'subject_user_id',256);if(/[\s/\\]/.test(subject))throw Error('subject_user_id_invalid');
    const key=recordKey(x.jeu,x.kind,x.id);const item=checked((await invoke('share',{namespace:NS,record_key:key,expected_revision:expectedRevision(x.expected_revision),subject_user_id:subject,permission:x.permission})).record,NS,key);
    return view(item,'sharing','Individual sharing updated. Service and sharing permissions remain distinct.',true);
  }
  throw Error('operation_invalid');
}
