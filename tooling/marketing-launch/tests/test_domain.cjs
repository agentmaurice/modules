'use strict';

const assert = require('node:assert/strict');

async function loadDomain() {
  // domain.js is authored by the parent agent; keep this test usable whether
  // the worktree is configured as CommonJS or as an ES module package.
  return import('../domain.js');
}

function rejectsCall(fn, pattern) {
  assert.throws(fn, pattern, `expected rejection matching ${pattern}`);
}

function campaign(overrides = {}) {
  return {
    schema_version: 1,
    kind: 'campaign',
    jeu: 'qualification',
    id: 'campagne-essai-1',
    objectif: 'Obtain a traceable trial request',
    audience: 'makers',
    promesse: 'Prepare a verifiable first result',
    canal: 'contenu',
    responsable: 'contenu',
    echeance: '2026-11-15',
    critere_fin: 'Result declared and reviewed by a person',
    phase: 'brouillon',
    veille_ref: '',
    veille_revision: 0,
    contenu_ref: '',
    contenu_revision: 0,
    preuve_ref: '',
    external_effect: false,
    scope: 'internal_only',
    confirmation_manuelle: 'oui',
    ...overrides,
  };
}

function veilleRecord(overrides = {}) {
  return {
    id: 'veille-essai-1',
    role: 'veille',
    revision: 3,
    etat: 'pret_a_revoir',
    external_effect: false,
    decision: { research: { verdict: 'sufficient' } },
    preuve_ref: 'fixture:veille-1',
    ...overrides,
  };
}

function contenuRecord(overrides = {}) {
  return {
    id: 'contenu-essai-1',
    role: 'contenu',
    revision: 4,
    decision: { decision: 'accepted' },
    review_scope: 'internal_draft_only',
    external_effect: false,
    source_ref: 'fixture:veille-1',
    brouillon: 'Brouillon interne',
    preuve_ref: 'fixture:contenu-1',
    ...overrides,
  };
}

function accompanimentRecord(overrides = {}) {
  return {
    id: 'accompagnement-essai-1',
    role: 'accompagnement',
    objectif: 'Help the person achieve a first result',
    resultat_observe: 'Observed and declared result',
    preuve_ref: 'fixture:result-1',
    blocage: '',
    prochaine_etape: 'Relecture humaine',
    external_effect: false,
    confirmation_manuelle: true,
    ...overrides,
  };
}

(async () => {
  const {
    normalizeCampaign,
    linkContent,
    createTrial,
    progressTrial,
    summarize,
    expectedRevision,
    recordKey,
  } = await loadDomain();

  const draft = normalizeCampaign(campaign());
  assert.equal(draft.schema_version, 1);
  assert.equal(draft.kind, 'campaign');
  assert.equal(draft.phase, 'brouillon');
  assert.equal(draft.scope, 'internal_only');
  assert.equal(draft.external_effect, false);
  assert.equal('caller' in draft, false);
  assert.equal('user_id' in draft, false);
  assert.equal('userid' in draft, false);

  rejectsCall(() => normalizeCampaign(campaign({ jeu: 'usage/../secret' })), /jeu|invalid/i);
  rejectsCall(() => normalizeCampaign(campaign({ id: '../secret' })), /id|invalid/i);
  rejectsCall(() => normalizeCampaign(campaign({ echeance: '2026-02-30' })), /date|echeance|invalid/i);
  rejectsCall(() => normalizeCampaign(campaign({ echeance: '2026-1-2' })), /date|echeance|invalid/i);
  rejectsCall(() => normalizeCampaign(campaign({ confirmation_manuelle: 'non' })), /confirmation|manual/i);
  rejectsCall(() => normalizeCampaign(campaign({ preuve_ref: 'secret://campaign' })), /preuve|secret|invalid/i);
  rejectsCall(() => normalizeCampaign(campaign({ external_effect: true })), /external|effect|invalid/i);
  rejectsCall(() => normalizeCampaign(campaign({ scope: 'public' })), /scope|internal|invalid/i);
  rejectsCall(() => normalizeCampaign(campaign({ phase: 'terminee' })), /phase|invalid/i);

  const linked = linkContent(
    draft,
    {
      veille_ref: 'veille-essai-1',
      veille_revision: 3,
      contenu_ref: 'contenu-essai-1',
      contenu_revision: 4,
      preuve_ref: 'fixture:content-review-1',
      confirmation_manuelle: 'oui',
    },
    veilleRecord(),
    contenuRecord(),
  );
  assert.equal(linked.phase, 'contenu_pret');
  assert.equal(linked.veille_ref, 'veille-essai-1');
  assert.equal(linked.veille_revision, 3);
  assert.equal(linked.contenu_ref, 'contenu-essai-1');
  assert.equal(linked.contenu_revision, 4);
  assert.equal(linked.external_effect, false);
  assert.equal(linked.scope, 'internal_only');

  rejectsCall(() => linkContent(draft, {
    veille_ref: 'veille-essai-1', veille_revision: 0,
    contenu_ref: 'contenu-essai-1', contenu_revision: 4,
    confirmation_manuelle: 'oui',
  }, veilleRecord(), contenuRecord()), /revision|invalid/i);
  rejectsCall(() => linkContent(draft, {
    veille_ref: 'veille-essai-1', veille_revision: 3,
    contenu_ref: 'contenu-essai-1', contenu_revision: 4,
    preuve_ref: '', confirmation_manuelle: 'oui',
  }, veilleRecord(), contenuRecord()), /preuve|evidence|invalid/i);
  rejectsCall(() => linkContent(draft, {
    veille_ref: 'veille-essai-1', veille_revision: 3,
    contenu_ref: 'contenu-essai-1', contenu_revision: 4,
    confirmation_manuelle: 'oui',
  }, veilleRecord({ role: 'contenu' }), contenuRecord()), /role|veille|invalid/i);
  rejectsCall(() => linkContent(draft, {
    veille_ref: 'veille-essai-1', veille_revision: 3,
    contenu_ref: 'contenu-essai-1', contenu_revision: 4,
    confirmation_manuelle: 'oui',
  }, veilleRecord(), contenuRecord({ decision: { decision: 'rework' } })), /review|decision|accepted|invalid/i);
  rejectsCall(() => linkContent(draft, {
    veille_ref: 'veille-essai-1', veille_revision: 3,
    contenu_ref: 'contenu-essai-1', contenu_revision: 4,
    confirmation_manuelle: 'oui',
  }, veilleRecord({ id: 'other-veille' }), contenuRecord()), /id|match|reference|invalid/i);
  rejectsCall(() => linkContent(linked, {
    veille_ref: 'veille-essai-1', veille_revision: 3,
    contenu_ref: 'contenu-essai-1', contenu_revision: 4,
    confirmation_manuelle: 'non',
  }, veilleRecord(), contenuRecord()), /confirmation|manual/i);

  const trial = createTrial(linked, {
    trial_id: 'trial-essai-1',
    personne_ref: 'personne-alias-opaque',
    besoin: 'Tester le parcours Marketing',
    objectif: 'Achieve a first result',
    confirmation_manuelle: 'oui',
  });
  assert.equal(trial.kind, 'trial');
  assert.equal(trial.phase, 'demande');
  assert.equal(trial.campaign_id, linked.id);
  assert.equal(trial.contenu_ref, linked.contenu_ref);
  assert.equal(trial.contenu_revision, linked.contenu_revision);
  assert.equal('email' in trial, false);
  assert.equal('caller' in trial, false);
  assert.equal('user_id' in trial, false);

  rejectsCall(() => createTrial(draft, {
    trial_id: 'trial-no-content', personne_ref: 'opaque', besoin: 'B',
    objectif: 'O', confirmation_manuelle: 'oui',
  }), /phase|campaign|content|ready|invalid/i);
  rejectsCall(() => createTrial(linked, {
    trial_id: 'trial-email@example.com', personne_ref: 'opaque', besoin: 'B',
    objectif: 'O', confirmation_manuelle: 'oui',
  }), /trial|email|id|invalid/i);
  rejectsCall(() => createTrial(linked, {
    trial_id: 'trial-no-confirm', personne_ref: 'opaque', besoin: 'B',
    objectif: 'O', confirmation_manuelle: 'non',
  }), /confirmation|manual/i);

  rejectsCall(() => progressTrial(trial, {
    phase: 'premier_resultat_confirme', accompagnement_ref: 'accompagnement-essai-1',
    accompagnement_revision: 1, date_confirmation: '2026-11-01',
    confirmation_resultat: 'oui', confirmation_manuelle: 'oui',
  }, accompanimentRecord()), /en_cours|bloque|phase|direct/i);

  const started = progressTrial(trial, {
    phase: 'en_cours', accompagnement_ref: 'accompagnement-essai-1',
    accompagnement_revision: 2, date_confirmation: '', confirmation_resultat: 'non',
    confirmation_manuelle: 'oui',
  }, accompanimentRecord({ resultat_observe: '' }));
  assert.equal(started.phase, 'en_cours');
  assert.equal(started.resultat_manual_attestation, false);

  const confirmed = progressTrial(started, {
    phase: 'premier_resultat_confirme', accompagnement_ref: 'accompagnement-essai-1',
    accompagnement_revision: 3, date_confirmation: '2026-11-02',
    confirmation_resultat: 'oui', confirmation_manuelle: 'oui',
  }, accompanimentRecord());
  assert.equal(confirmed.phase, 'premier_resultat_confirme');
  assert.equal(confirmed.resultat_manual_attestation, true);
  assert.equal(confirmed.conversion_commerciale, false);
  assert.equal(confirmed.external_effect, false);
  rejectsCall(() => progressTrial(confirmed, {
    phase: 'premier_resultat_confirme', accompagnement_ref: 'accompagnement-essai-1',
    accompagnement_revision: 4, date_confirmation: '2026-11-03',
    confirmation_resultat: 'oui', confirmation_manuelle: 'oui',
  }, accompanimentRecord()), /phase|terminal|progress|invalid/i);

  rejectsCall(() => progressTrial(started, {
    phase: 'premier_resultat_confirme', accompagnement_ref: 'accompagnement-essai-1',
    accompagnement_revision: 3, date_confirmation: '2026-11-02',
    confirmation_resultat: 'oui', confirmation_manuelle: 'oui',
  }, accompanimentRecord({ resultat_observe: '', preuve_ref: '' })), /resultat|preuve|invalid/i);
  rejectsCall(() => progressTrial(started, {
    phase: 'premier_resultat_confirme', accompagnement_ref: 'accompagnement-essai-1',
    accompagnement_revision: 3, date_confirmation: '2026-11-02',
    confirmation_resultat: 'oui', confirmation_manuelle: 'oui',
  }, accompanimentRecord({ preuve_ref: 'secret://result' })), /preuve|secret|invalid/i);
  rejectsCall(() => progressTrial(started, {
    phase: 'premier_resultat_confirme', accompagnement_ref: 'accompagnement-essai-1',
    accompagnement_revision: 3, date_confirmation: '2026-11-02',
    confirmation_resultat: 'non', confirmation_manuelle: 'oui',
  }, accompanimentRecord()), /confirmation|resultat|invalid/i);
  rejectsCall(() => progressTrial(started, {
    phase: 'premier_resultat_confirme', accompagnement_ref: 'accompagnement-essai-1',
    accompagnement_revision: 3, date_confirmation: '2026-02-30',
    confirmation_resultat: 'oui', confirmation_manuelle: 'oui',
  }, accompanimentRecord()), /date|invalid/i);
  rejectsCall(() => progressTrial(started, {
    phase: 'bloque', accompagnement_ref: 'accompagnement-essai-1',
    accompagnement_revision: 3, date_confirmation: '',
    confirmation_resultat: 'non', confirmation_manuelle: 'non',
  }, accompanimentRecord()), /confirmation|manual/i);

  assert.equal(expectedRevision(1), 1);
  assert.equal(expectedRevision('7'), 7);
  assert.equal(expectedRevision(0, true), 0);
  rejectsCall(() => expectedRevision(0), /revision|invalid/i);
  rejectsCall(() => expectedRevision('0'), /revision|invalid/i);
  rejectsCall(() => expectedRevision('secret://revision'), /revision|invalid/i);

  const key = recordKey('qualification', 'campaign', 'campagne-essai-1');
  assert.equal(typeof key, 'string');
  assert.match(key, /qualification/);
  assert.match(key, /campaign/);
  assert.match(key, /campagne-essai-1/);
  assert.notEqual(recordKey('qualification', 'campaign', 'campagne-essai-1'),
    recordKey('usage', 'campaign', 'campagne-essai-1'));
  rejectsCall(() => recordKey('qualification', 'campaign', '../secret'), /id|path|invalid/i);
  rejectsCall(() => recordKey('qualification', 'campaign', 'secret://x'), /id|path|secret|invalid/i);

  const summary = summarize([
    { kind: 'campaign', id: 'c1', phase: 'brouillon' },
    { kind: 'campaign', id: 'c2', phase: 'contenu_pret' },
    { kind: 'trial', id: 't1', phase: 'demande' },
    { kind: 'trial', id: 't2', phase: 'premier_resultat_confirme' },
  ]);
  assert.equal(summary.campagnes_accessibles, 2);
  assert.equal(summary.contenus_prets, 1);
  assert.equal(summary.demandes_accessibles, 2);
  assert.equal(summary.phases.demande, 1);
  assert.equal(summary.phases.premier_resultat_confirme, 1);
  assert.equal(summary.visibility_scope, 'accessible_records_only');
  assert.equal(summary.conversion_rate, null);
  assert.equal(summary.gain_temps, null);
  assert.equal(summary.conversion_commerciale, false);

  console.log('marketing domain tests passed');
})().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
