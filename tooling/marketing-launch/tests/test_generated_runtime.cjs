'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const WORKFLOWS = path.join(ROOT, '..', '..', 'marketing-launch', 'agents', 'main', 'workflows');
const INTERNAL = 'cib-launch-marketing';
const WORKFLOW_IDS = [
  'cib-launch-campaign-save', 'cib-launch-content-link', 'cib-launch-request',
  'cib-launch-progress', 'cib-launch-read', 'cib-launch-list',
  'cib-launch-people', 'cib-launch-share', 'cib-launch-summary',
];

const campaignInput = {
  jeu: 'qualification', id: 'campagne-runtime-1',
  objectif: 'Qualifier une demande d’essai', audience: 'makers',
  promesse: 'Premier résultat vérifiable', canal: 'contenu', responsable: 'contenu',
  echeance: '2026-11-15', critere_fin: 'Preuve relue par une personne',
  confirmation_manuelle: 'oui', expected_revision: 0,
};
const veille = {
  id: 'veille-runtime-1', role: 'veille', revision: 3, etat: 'pret_a_revoir',
  decision: { research: { verdict: 'sufficient' } }, external_effect: false,
  preuve_ref: 'fixture:veille-runtime-1',
};
const contenu = {
  id: 'contenu-runtime-1', role: 'contenu', revision: 4,
  decision: { decision: 'accepted' }, review_scope: 'internal_draft_only',
  source_ref: 'fixture:veille-runtime-1', brouillon: 'Brouillon interne',
  external_effect: false, preuve_ref: 'fixture:contenu-runtime-1',
};
const support = {
  id: 'accompagnement-runtime-1', role: 'accompagnement', revision: 2,
  objectif: 'Accompagner la prise en main', resultat_observe: 'Résultat observé',
  preuve_ref: 'fixture:result-runtime-1', blocage: '',
  prochaine_etape: 'Relecture humaine', confirmation_manuelle: true,
  external_effect: false,
};

function key(game, kind, id) { return `${game}/${kind}/${id}`; }

function makeBroker() {
  const records = new Map();
  const requests = [];
  const foreign = new Map([
    ['cib-veille/veille-runtime-1', { namespace: 'cib-veille', key: 'veille-runtime-1', data: veille, revision: 3 }],
    ['cib-contenu/contenu-runtime-1', { namespace: 'cib-contenu', key: 'contenu-runtime-1', data: contenu, revision: 4 }],
    ['cib-accompagnement/accompagnement-runtime-1', { namespace: 'cib-accompagnement', key: 'accompagnement-runtime-1', data: support, revision: 2 }],
  ]);
  const broker = {
    records, requests, foreign, malformed: null, incompleteList: false,
    async callTool(tool, args) {
      assert.equal(tool, 'recipe--application_data_v1');
      assert.ok(args && typeof args === 'object');
      assert.equal('caller' in args, false);
      assert.equal('user_id' in args, false);
      assert.equal('admin_recovery' in args, false);
      const { operation } = args;
      assert.ok(['read', 'save', 'list', 'people', 'share'].includes(operation));
      requests.push({ operation, args: { ...args } });
      if (this.malformed === operation) {
        this.malformed = null;
        return { record: { namespace: INTERNAL, key: 'wrong-key', data: {}, revision: 0, permissions: {} } };
      }
      if (args.namespace !== INTERNAL && operation !== 'read') throw Error('foreign_operation_denied');
      if (operation === 'read') {
        const foreignItem = this.foreign.get(`${args.namespace}/${args.record_key}`);
        if (foreignItem) return { record: this.item(foreignItem) };
        const item = this.records.get(args.record_key);
        if (!item) throw Error('[NOT_FOUND]');
        return { record: this.item(item) };
      }
      if (operation === 'save') {
        const old = this.records.get(args.record_key);
        const expected = Number(args.expected_revision);
        if (!Number.isSafeInteger(expected) || expected < 0) throw Error('CAS_INVALID');
        if (old && old.revision !== expected) throw Error('CAS_CONFLICT');
        if (!old && expected !== 0) throw Error('CAS_CONFLICT');
        const item = { namespace: INTERNAL, key: args.record_key, data: args.data,
          revision: old ? old.revision + 1 : 1, owner_user_id: 'owner-a',
          shares: old ? old.shares : [] };
        this.records.set(args.record_key, item);
        return { record: this.item(item) };
      }
      if (operation === 'list') {
        const items = [...this.records.values()].filter(item => item.key.startsWith(args.prefix));
        return { items: items.map(item => ({ record_key: item.key, data: item.data,
          revision: item.revision, permissions: this.permissions(item) })),
          total: this.incompleteList ? items.length + 1 : items.length };
      }
      if (operation === 'people') {
        return { people: [{ user_id: 'person-b', display_name: 'Personne B' }] };
      }
      if (operation === 'share') {
        const item = this.records.get(args.record_key);
        if (!item) throw Error('[NOT_FOUND]');
        if (item.revision !== Number(args.expected_revision)) throw Error('CAS_CONFLICT');
        item.shares = item.shares.filter(s => s.user_id !== args.subject_user_id);
        if (args.permission !== 'none') item.shares.push({ user_id: args.subject_user_id, permission: args.permission });
        item.revision += 1;
        return { record: this.item(item) };
      }
      throw Error('unexpected_operation');
    },
    permissions(item) { return { can_read: true, can_write: true, can_manage: true }; },
    item(item) { return { ...item, permissions: this.permissions(item) }; },
  };
  return broker;
}

async function runWorkflow(id, input, broker) {
  const document = JSON.parse(fs.readFileSync(path.join(WORKFLOWS, `${id}.json`), 'utf8'));
  const action = document.actions.find(item => item.type === 'code_execution');
  assert.ok(action, `${id} must contain generated code_execution`);
  assert.match(action.code, /import \{ callTool \} from '\.\/tools\/nats_bridge\.ts';/);
  // Replace only the generated input marker and the known import. Other
  // template-like text remains untouched so this catches accidental broad
  // substitutions in the harness itself.
  const code = action.code
    .replace("import { callTool } from './tools/nats_bridge.ts';\n", '')
    .replace('const input={{ json . }};', `const input=${JSON.stringify(input)};`);
  assert.doesNotMatch(code, /\{\{ json \. \}\}/);
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  return new AsyncFunction('callTool', code)(broker.callTool.bind(broker));
}

function rejects(promise, pattern) {
  return assert.rejects(promise, pattern);
}

(async () => {
  for (const id of WORKFLOW_IDS) assert.ok(fs.existsSync(path.join(WORKFLOWS, `${id}.json`)), id);
  const broker = makeBroker();

  const campaign = await runWorkflow('cib-launch-campaign-save', campaignInput, broker);
  assert.equal(campaign.revision, 1);
  assert.equal(broker.records.size, 1);

  const linked = await runWorkflow('cib-launch-content-link', {
    jeu: 'qualification', campaign_id: campaign.record.id, expected_revision: 1,
    veille_ref: veille.id, veille_revision: 3, contenu_ref: contenu.id,
    contenu_revision: 4, preuve_ref: 'fixture:content-review-runtime-1',
    confirmation_manuelle: 'oui',
  }, broker);
  assert.equal(linked.record.phase, 'contenu_pret');
  assert.equal(linked.revision, 2);

  const requestInput = {
    jeu: 'qualification', campaign_id: campaign.record.id, campaign_revision: 2,
    trial_id: 'trial-runtime-1', personne_ref: 'personne-alias-opaque',
    besoin: 'Tester le parcours', objectif: 'Obtenir un premier résultat',
    confirmation_manuelle: 'oui',
  };
  const requested = await runWorkflow('cib-launch-request', requestInput, broker);
  assert.equal(requested.record.phase, 'demande');
  assert.equal(requested.revision, 1);
  const sizeBeforeReplay = broker.records.size;
  const replayed = await runWorkflow('cib-launch-request', requestInput, broker);
  assert.equal(replayed.replayed, true);
  assert.equal(broker.records.size, sizeBeforeReplay);
  assert.equal(replayed.revision, requested.revision);

  const started = await runWorkflow('cib-launch-progress', {
    jeu: 'qualification', trial_id: requested.record.id, expected_revision: 1,
    phase: 'en_cours', accompagnement_ref: support.id, accompagnement_revision: 2,
    confirmation_manuelle: 'oui', confirmation_resultat: 'non', date_confirmation: '',
  }, broker);
  assert.equal(started.record.phase, 'en_cours');
  assert.equal(started.record.resultat_manual_attestation, false);
  const finished = await runWorkflow('cib-launch-progress', {
    jeu: 'qualification', trial_id: requested.record.id, expected_revision: 2,
    phase: 'premier_resultat_confirme', accompagnement_ref: support.id,
    accompagnement_revision: 2, confirmation_manuelle: 'oui', confirmation_resultat: 'oui',
    date_confirmation: '2026-11-02',
  }, broker);
  assert.equal(finished.record.resultat_manual_attestation, true);
  assert.equal(finished.record.conversion_commerciale, false);

  const read = await runWorkflow('cib-launch-read', {
    jeu: 'qualification', kind: 'campaign', id: campaign.record.id, form_id: 'campaign',
  }, broker);
  assert.equal(read.record.id, campaign.record.id);
  const listed = await runWorkflow('cib-launch-list', {
    jeu: 'qualification', kind: 'trial',
  }, broker);
  assert.equal(listed.items.length, 1);
  const people = await runWorkflow('cib-launch-people', {
    jeu: 'qualification', kind: 'campaign', id: campaign.record.id,
  }, broker);
  assert.equal(people.people.length, 1);

  const summary = await runWorkflow('cib-launch-summary', { jeu: 'qualification' }, broker);
  assert.equal(summary.summary.demandes_accessibles, 1);
  assert.equal(summary.summary.premiers_resultats_confirmes, 1);
  assert.equal(summary.summary.conversion_rate, null);
  assert.equal(summary.summary.conversion_commerciale, false);

  const callsBeforeManualShare = broker.requests.length;
  await rejects(runWorkflow('cib-launch-share', {
    jeu: 'qualification', kind: 'campaign', id: campaign.record.id,
    expected_revision: 2, subject_user_id: 'person-b', permission: 'read',
    confirmation_manuelle: 'non',
  }, broker), /manual_confirmation_required/);
  assert.equal(broker.requests.length, callsBeforeManualShare);
  await rejects(runWorkflow('cib-launch-share', {
    jeu: 'qualification', kind: 'campaign', id: campaign.record.id,
    expected_revision: 1, subject_user_id: 'person-b', permission: 'read',
    confirmation_manuelle: 'oui',
  }, broker), /CAS_CONFLICT/);

  broker.malformed = 'read';
  await rejects(runWorkflow('cib-launch-read', {
    jeu: 'qualification', kind: 'campaign', id: campaign.record.id, form_id: 'campaign',
  }, broker), /broker_identity_revision_invalid/);
  broker.incompleteList = true;
  await rejects(runWorkflow('cib-launch-list', { jeu: 'qualification', kind: 'trial' }, broker), /bounded_list_incomplete/);

  assert.ok(broker.requests.every(request => request.operation !== 'admin_recovery'));
  assert.ok(broker.requests.every(request => request.args.namespace === INTERNAL || request.operation === 'read'));
  console.log(`generated runtime tests passed (${WORKFLOW_IDS.length} workflows, ${broker.requests.length} broker calls)`);
})().catch(error => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
