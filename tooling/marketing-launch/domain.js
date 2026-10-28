// Business rules only. Identity, record ACLs and CAS remain in the AM broker.
const ID = /^[a-z0-9][a-z0-9-]{0,63}$/;
const GAMES = new Set(['usage', 'qualification']);
const KINDS = new Set(['campaign', 'trial']);
const PHASES = new Set(['demande', 'en_cours', 'bloque', 'premier_resultat_confirme']);
function object(x, name) { if (!x || typeof x !== 'object' || Array.isArray(x)) throw Error(name + '_invalid'); return x; }
function text(x, name, max=4000, optional=false) { if (optional && (x == null || x === '')) return ''; if (typeof x !== 'string' || !x.trim() || x.length > max) throw Error(name + '_invalid'); return x.trim(); }
function id(x, name) { if (typeof x !== 'string' || !ID.test(x)) throw Error(name + '_invalid'); return x; }
function jeu(x) { if (!GAMES.has(x)) throw Error('jeu_invalid'); return x; }
function manual(x) { if (x !== true && x !== 'oui') throw Error('manual_confirmation_required'); }
function internal(x) { if (x.external_effect != null && x.external_effect !== false) throw Error('external_effect_invalid'); if (x.scope != null && x.scope !== 'internal_only') throw Error('scope_invalid'); }
function reference(x, name, optional=false) { const value=text(x,name,256,optional); if (value && (!/^[a-zA-Z0-9][a-zA-Z0-9:_./-]*$/.test(value) || value.includes('..') || /secret:\/\//i.test(value))) throw Error(name+'_invalid'); return value; }
function date(x, name, optional=false) { if (optional && (x == null || x === '')) return ''; if (typeof x !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(x)) throw Error(name+'_date_invalid'); const d=new Date(x+'T00:00:00Z'); if (!Number.isFinite(d.getTime()) || d.toISOString().slice(0,10)!==x) throw Error(name+'_date_invalid'); return x; }
export function expectedRevision(x, allowZero=false) { if (typeof x==='string' && /^[0-9]+$/.test(x)) x=Number(x); if (!Number.isSafeInteger(x) || x < (allowZero ? 0 : 1)) throw Error('expected_revision_invalid'); return x; }
export function recordKey(game,kind,key) { jeu(game); if (!KINDS.has(kind)) throw Error('kind_invalid'); return game+'/'+kind+'/'+id(key,'id'); }
export function normalizeCampaign(input) {
  const x=object(input,'campaign'); internal(x); manual(x.confirmation_manuelle);
  if (x.phase != null && x.phase!=='brouillon') throw Error('campaign_phase_invalid');
  reference(x.preuve_ref,'preuve_ref',true);
  return {schema_version:1,kind:'campaign',jeu:jeu(x.jeu),id:id(x.id||x.campaign_id,'campaign_id'),objectif:text(x.objectif,'objectif'),audience:text(x.audience,'audience',2000),promesse:text(x.promesse,'promesse'),canal:text(x.canal,'canal',128),responsable:text(x.responsable,'responsable',256),echeance:date(x.echeance,'echeance'),critere_fin:text(x.critere_fin,'critere_fin'),phase:'brouillon',veille_ref:'',veille_revision:0,contenu_ref:'',contenu_revision:0,preuve_ref:'',scope:'internal_only',external_effect:false,validation_mode:'manual_attestation'};
}
export function linkContent(campaign,input,veille,contenu) {
  object(campaign,'campaign'); if (campaign.kind!=='campaign') throw Error('campaign_kind_invalid'); internal(input); manual(input.confirmation_manuelle);
  const vr=id(input.veille_ref,'veille_ref'), cr=id(input.contenu_ref,'contenu_ref');
  const vv=expectedRevision(input.veille_revision), cv=expectedRevision(input.contenu_revision);
  object(veille,'veille'); object(contenu,'contenu');
  if (veille.id!==vr || veille.role!=='veille' || veille.external_effect!==false || veille.etat!=='pret_a_revoir' || veille.decision?.research?.verdict!=='sufficient') throw Error('veille_reference_or_review_invalid');
  if (contenu.id!==cr || contenu.role!=='contenu' || contenu.external_effect!==false || contenu.decision?.decision!=='accepted' || contenu.review_scope!=='internal_draft_only' || !text(contenu.brouillon,'brouillon',16000)) throw Error('content_review_invalid');
  if (veille.revision!==vv || contenu.revision!==cv) throw Error('source_revision_changed');
  // Link verified references, never copy the full source into shared memory.
  return {...campaign,phase:'contenu_pret',veille_ref:vr,veille_revision:vv,contenu_ref:cr,contenu_revision:cv,preuve_ref:reference(input.preuve_ref,'preuve_ref'),scope:'internal_only',external_effect:false};
}
export function createTrial(campaign,input) {
  object(campaign,'campaign'); if (campaign.kind!=='campaign' || campaign.phase!=='contenu_pret' || !campaign.contenu_ref || !campaign.veille_ref || !campaign.preuve_ref) throw Error('campaign_content_not_ready');
  internal(input); manual(input.confirmation_manuelle);
  return {schema_version:1,kind:'trial',jeu:campaign.jeu,id:id(input.trial_id,'trial_id'),campaign_id:campaign.id,personne_ref:reference(input.personne_ref,'personne_ref'),besoin:text(input.besoin,'besoin'),objectif:text(input.objectif,'objectif'),critere_fin:campaign.critere_fin,contenu_ref:campaign.contenu_ref,contenu_revision:campaign.contenu_revision,phase:'demande',accompagnement_ref:'',accompagnement_revision:0,resultat_observe:'',preuve_ref:'',blocage:'',prochaine_etape:'Qualify the request and prepare onboarding.',date_confirmation:'',resultat_manual_attestation:false,conversion_commerciale:false,scope:'internal_only',validation_mode:'manual_attestation',external_effect:false};
}
export function progressTrial(trial,input,support) {
  object(trial,'trial'); if (trial.kind!=='trial' || !PHASES.has(trial.phase)) throw Error('trial_phase_invalid');
  internal(input); manual(input.confirmation_manuelle);
  if (!['en_cours','bloque','premier_resultat_confirme'].includes(input.phase)) throw Error('phase_invalid');
  if (trial.phase==='premier_resultat_confirme') throw Error('confirmed_result_is_terminal');
  const sr=id(input.accompagnement_ref,'accompagnement_ref'), sv=expectedRevision(input.accompagnement_revision);
  object(support,'accompagnement'); if (support.id!==sr || support.role!=='accompagnement' || support.external_effect!==false || support.confirmation_manuelle!==true) throw Error('accompagnement_reference_invalid');
  if (support.revision!=null && support.revision!==sv) throw Error('accompagnement_revision_changed');
  const result=text(support.resultat_observe,'resultat_observe',8000,true), proof=reference(support.preuve_ref,'preuve_ref',true), block=text(support.blocage,'blocage',4000,true), next=text(support.prochaine_etape,'prochaine_etape',8000);
  const final=input.phase==='premier_resultat_confirme';
  if (final && !['en_cours','bloque'].includes(trial.phase)) throw Error('direct_result_requires_en_cours');
  if (input.phase==='bloque' && !block) throw Error('blocage_required');
  if (final) { if (!result || !proof || block) throw Error('resultat_preuve_without_blockage_required'); manual(input.confirmation_resultat); date(input.date_confirmation,'date_confirmation'); }
  return {...trial,phase:input.phase,accompagnement_ref:sr,accompagnement_revision:sv,resultat_observe:result,preuve_ref:proof,blocage:block,prochaine_etape:next,date_confirmation:final?input.date_confirmation:'',resultat_manual_attestation:final,conversion_commerciale:false,scope:'internal_only',validation_mode:'manual_attestation',external_effect:false};
}
export function validateLaunchRecord(record) {
  const x=object(record,'record'); internal(x); if (x.schema_version!==1 || !KINDS.has(x.kind)) throw Error('record_schema_invalid'); recordKey(x.jeu,x.kind,x.id);
  if (x.scope!=='internal_only' || x.external_effect!==false) throw Error('stored_scope_invalid');
  if (x.kind==='campaign') {
    if (!['brouillon','contenu_pret'].includes(x.phase)) throw Error('stored_campaign_phase_invalid');
    normalizeCampaign({...x,phase:'brouillon',confirmation_manuelle:'oui'});
    if (x.phase==='contenu_pret') {id(x.veille_ref,'veille_ref');expectedRevision(x.veille_revision);id(x.contenu_ref,'contenu_ref');expectedRevision(x.contenu_revision);reference(x.preuve_ref,'preuve_ref');}
  } else {
    if (!PHASES.has(x.phase) || x.conversion_commerciale!==false) throw Error('stored_trial_phase_invalid');
    id(x.campaign_id,'campaign_id');expectedRevision(x.campaign_revision);id(x.contenu_ref,'contenu_ref');expectedRevision(x.contenu_revision);reference(x.personne_ref,'personne_ref');text(x.objectif,'objectif');text(x.besoin,'besoin');
    if (x.phase==='premier_resultat_confirme') { if (x.resultat_manual_attestation!==true || x.blocage) throw Error('stored_attestation_invalid');text(x.resultat_observe,'resultat_observe',8000);reference(x.preuve_ref,'preuve_ref');date(x.date_confirmation,'date_confirmation'); }
  }
  return x;
}
export function summarize(records) {
  if (!Array.isArray(records)) throw Error('records_invalid');
  const campaigns=records.filter(r=>r.kind==='campaign'), trials=records.filter(r=>r.kind==='trial');
  const counts={demande:0,en_cours:0,bloque:0,premier_resultat_confirme:0};for (const r of trials) {if (!PHASES.has(r.phase)) throw Error('trial_phase_invalid');counts[r.phase]++;}
  return {campagnes_accessibles:campaigns.length,contenus_prets:campaigns.filter(r=>r.phase==='contenu_pret').length,demandes_accessibles:trials.length,phases:counts,premiers_resultats_confirmes:counts.premier_resultat_confirme,visibility_scope:'accessible_records_only',validation_mode:'manual_attestation',conversion_commerciale:false,conversion_rate:null,attribution:'non_mesuree',gain_temps:null,external_effect:false};
}
