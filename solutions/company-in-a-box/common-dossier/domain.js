const ID = /^[a-z0-9][a-z0-9-]{0,63}$/;
const REF = /^[a-z0-9][a-z0-9:_./-]{0,127}$/;
const GAMES = new Set(["usage", "qualification"]);
const SERVICES = new Set(["marketing", "service_client", "interne"]);
const ROLES = new Set(["veille", "contenu", "accompagnement"]);
const PRIORITIES = new Set(["haute", "normale", "basse"]);
const STATUSES = new Set(["a_qualifier", "en_cours", "bloque", "pret_a_revoir", "termine_interne", "abandonne"]);

function text(value, name, max = 8000, required = true) {
  if (value == null && !required) return "";
  if (typeof value !== "string" || value.length > max || (required && !value.trim())) throw new Error(`${name}_invalid`);
  return value.trim();
}
function id(value, name) { if (typeof value !== "string" || !ID.test(value)) throw new Error(`${name}_invalid`); return value; }
function ref(value, name, required = false) { if (value == null || value === "") { if (required) throw new Error(`${name}_invalid`); return ""; } if (typeof value !== "string" || !REF.test(value) || value.includes("..") || value.toLowerCase().includes("secret://")) throw new Error(`${name}_invalid`); return value; }
function roleRef(value, name) { if (value == null || value === "") return ""; return id(value, name); }
function optionalId(value, name) { if (value == null || value === "") return ""; return id(value, name); }
function version(value, name, paired) { if (value == null || value === "") { if (paired) throw new Error(`${name}_invalid`); return ""; } if (typeof value !== "string" || !/^[1-9][0-9]*$/.test(value)) throw new Error(`${name}_invalid`); return value; }
function yes(value, name) { if (value === true || value === "oui") return true; if (value === false || value === "non") return false; throw new Error(`${name}_invalid`); }
export function validateExpectedRevision(value) {
  if (value == null || value === "") return 0;
  if (typeof value === "string" && /^[0-9]+$/.test(value)) value = Number(value);
  if (!Number.isSafeInteger(value) || value < 0) throw new Error("expected_revision_invalid");
  return value;
}

export function normalizeCase(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error("case_invalid");
  const jeu = input.jeu; if (!GAMES.has(jeu)) throw new Error("jeu_invalid");
  const case_id = id(input.case_id, "case_id");
  const statut = input.statut; if (!STATUSES.has(statut)) throw new Error("statut_invalid");
  if (!SERVICES.has(input.service)) throw new Error("service_invalid");
  if (!ROLES.has(input.responsable_role)) throw new Error("responsable_role_invalid");
  if (!PRIORITIES.has(input.priorite)) throw new Error("priorite_invalid");
  const blocked = text(input.blocage, "blocage", 2000, false);
  if (statut === "bloque" && !blocked) throw new Error("blocage_required");
  const manualReview = yes(input.revue_manuelle, "revue_manuelle");
  const confirmation = yes(input.confirmation_manuelle, "confirmation_manuelle");
  if (!confirmation) throw new Error("manual_confirmation_required");
  const refs = {
    veille_ref: roleRef(input.veille_ref, "veille_ref"),
    veille_version: version(input.veille_version, "veille_version", !!input.veille_ref || !!input.veille_version),
    contenu_ref: roleRef(input.contenu_ref, "contenu_ref"),
    contenu_version: version(input.contenu_version, "contenu_version", !!input.contenu_ref || !!input.contenu_version),
    accompagnement_ref: roleRef(input.accompagnement_ref, "accompagnement_ref"),
    accompagnement_version: version(input.accompagnement_version, "accompagnement_version", !!input.accompagnement_ref || !!input.accompagnement_version),
    memoire_ref: optionalId(input.memoire_ref, "memoire_ref"),
    preuve_ref: ref(input.preuve_ref, "preuve_ref"),
  };
  for (const role of ROLES) if (Boolean(refs[role + "_ref"]) !== Boolean(refs[role + "_version"])) throw new Error(role + "_ref_version_pair_required");
  const roleReference = refs.veille_ref || refs.contenu_ref || refs.accompagnement_ref;
  if (statut === "termine_interne" && (!manualReview || !refs.preuve_ref || !roleReference)) throw new Error("internal_closure_requires_manual_review_proof_and_role_ref");
  return { schema_version: 1, jeu, case_id, objectif: text(input.objectif, "objectif", 4000), critere_fin: text(input.critere_fin, "critere_fin", 4000), service: input.service, responsable_role: input.responsable_role, priorite: input.priorite, statut, prochaine_action: text(input.prochaine_action, "prochaine_action", 4000), blocage: blocked, ...refs, revue_manuelle: manualReview, confirmation_manuelle: confirmation, scope: "internal_only", validation_mode: "manual_attestation" };
}

export function validateStored(record, expectedJeu, expectedId) {
  if (!record || record.schema_version !== 1) throw new Error("stored_schema_invalid");
  const value = normalizeCase(record);
  if (value.jeu !== expectedJeu || value.case_id !== expectedId) throw new Error("stored_identity_mismatch");
  return value;
}

export function summarize(items) {
  const rows = items.map((item) => ({ case_id: item.case_id, statut: item.statut, priorite: item.priorite, service: item.service, responsable_role: item.responsable_role, prochaine_action: item.prochaine_action }));
  return { total: rows.length, counts: rows.reduce((a, row) => { a[row.statut] = (a[row.statut] || 0) + 1; return a; }, {}), blocked: rows.filter((r) => r.statut === "bloque").map((r) => r.case_id), ready: rows.filter((r) => r.statut === "pret_a_revoir").map((r) => r.case_id), next_actions: rows.filter((r) => r.prochaine_action).map((r) => ({ case_id: r.case_id, action: r.prochaine_action })) };
}
