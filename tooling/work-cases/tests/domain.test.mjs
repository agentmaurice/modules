import assert from 'node:assert/strict';
import fs from 'node:fs';
import { normalizeCase, validateStored, summarize, validateExpectedRevision } from '../domain.js';

const base = {jeu:'usage',case_id:'case-1',objectif:'Objectif',critere_fin:'Preuve interne',service:'marketing',responsable_role:'veille',priorite:'normale',statut:'en_cours',prochaine_action:'Relire',blocage:'',veille_ref:'veille-1',veille_version:'1',contenu_ref:'',contenu_version:'',accompagnement_ref:'',accompagnement_version:'',memoire_ref:'',preuve_ref:'',revue_manuelle:'non',confirmation_manuelle:'oui'};
assert.equal(normalizeCase(base).scope, 'internal_only');
assert.equal(validateExpectedRevision(0), 0);
assert.equal(validateExpectedRevision(undefined), 0);
assert.equal(validateExpectedRevision(''), 0);
assert.equal(validateExpectedRevision('3'), 3);
assert.throws(() => validateExpectedRevision(-1), /expected_revision_invalid/);
assert.throws(() => validateExpectedRevision(1.5), /expected_revision_invalid/);
assert.throws(() => normalizeCase({...base, jeu:'other'}), /jeu_invalid/);
assert.throws(() => normalizeCase({...base, case_id:'../secret'}), /case_id_invalid/);
assert.throws(() => normalizeCase({...base, confirmation_manuelle:'non'}), /manual_confirmation_required/);
assert.throws(() => normalizeCase({...base, veille_ref:'../secret', veille_version:'1'}), /veille_ref_invalid/);
assert.throws(() => normalizeCase({...base, veille_version:''}), /veille_version_invalid/);
assert.throws(() => normalizeCase({...base, veille_ref:'veille-1', veille_version:'0'}), /veille_version_invalid/);
assert.throws(() => normalizeCase({...base, preuve_ref:'secret://x'}), /preuve_ref_invalid/);
assert.throws(() => normalizeCase({...base, statut:'bloque'}), /blocage_required/);
assert.throws(() => normalizeCase({...base, statut:'termine_interne', revue_manuelle:'non', preuve_ref:'proof'}), /internal_closure/);
assert.throws(() => normalizeCase({...base, veille_ref:'', veille_version:'1'}), /pair_required/);
const closed = normalizeCase({...base, statut:'termine_interne', revue_manuelle:'oui', preuve_ref:'proof-1'});
assert.equal(validateStored(closed, 'usage', 'case-1').case_id, 'case-1');
assert.throws(() => validateStored(closed, 'qualification', 'case-1'), /stored_identity_mismatch/);
const result = summarize([base, {...base, case_id:'case-2', statut:'bloque', blocage:'Attente', prochaine_action:'Decide'}]);
assert.deepEqual(result.counts, {en_cours:1, bloque:1});
assert.deepEqual(result.blocked, ['case-2']);
assert.deepEqual(result.ready, []);
assert.deepEqual(result.next_actions.map(x => x.case_id), ['case-1','case-2']);

const root = new URL('../../../work-cases/agents/main/workflows/', import.meta.url);
const read = JSON.parse(fs.readFileSync(new URL('cib-case-read.json', root)));
const list = JSON.parse(fs.readFileSync(new URL('cib-case-list.json', root)));
const save = JSON.parse(fs.readFileSync(new URL('cib-case-save.json', root)));
const share = JSON.parse(fs.readFileSync(new URL('cib-case-share.json', root)));
const people = JSON.parse(fs.readFileSync(new URL('cib-case-people.json', root)));
const brief = JSON.parse(fs.readFileSync(new URL('cib-direction-brief.json', root)));
const workflows = [save, read, list, brief, share, people];
for (const workflow of workflows) {
  const text = JSON.stringify(workflow);
  assert.doesNotMatch(text, /read_file|write_file|list_files/);
  if (workflow.workflow_id !== 'cib-direction-brief') assert.match(text, /recipe--application_data_v1/);
}
assert.match(save.actions[1].code, /operation:"save"/);
assert.match(read.actions[1].code, /operation:"read"/);
assert.match(list.actions[1].code, /operation:"list"/);
const listCode = list.actions[1].code
  .replace("import { callTool } from './tools/nats_bridge.ts';", '')
  .replace('{{ json .request }}', JSON.stringify({jeu:'usage'}));
const runList = new (Object.getPrototypeOf(async function(){}).constructor)('callTool', listCode);
const listing = await runList(async () => ({items:[{record_key:'usage/case-1',data:base,revision:1}],total:1}));
assert.equal(listing.items[0].statut, 'en_cours');
assert.equal(listing.items[0].status_label, 'In progress');
assert.equal(listing.items[0].responsable_role, 'veille');
assert.equal(listing.items[0].role_label, 'Watch');
assert.match(share.actions[0].code, /operation:"share"/);
assert.match(people.actions[1].code, /operation:"people"/);
assert.match(save.actions[1].code, /expected_revision/);
assert.match(share.actions[0].code, /manual_confirmation_required/);
assert.equal(JSON.parse(fs.readFileSync(new URL('../../../work-cases/module.yaml', import.meta.url))).version, '0.2.3');
console.log('domain and generated contract tests passed');
