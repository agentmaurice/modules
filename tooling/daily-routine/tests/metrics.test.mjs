import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../metrics.js", import.meta.url), "utf8");
const { summarize, validateEntry } = await import(`data:text/javascript,${encodeURIComponent(source)}`);

const base = (overrides = {}) => ({
  session_id: "session-1", comparaison_id: "cmp-1", dossier_id: "dossier-1",
  jeu: "qualification", phase: "reference", date: "2026-10-11",
  categorie: "onboarding", complexite: "standard", critere_qualite: "validated result",
  qualite: "valide", mesure_ref: "clock-manuel", prochaine_etape: "relecture",
  confirmation_manuelle: "oui", temps_observe: "oui",
  execution_minutes: 20, relecture_minutes: 5, correction_minutes: 2,
  supervision_minutes: 3, maintenance_minutes: 1, installation_minutes: 10,
  ...overrides,
});

const record = (overrides = {}) => validateEntry(base(overrides));

assert.equal(record().temps_humain_minutes, 31);
assert.equal(record({ execution_minutes: "30", installation_minutes: "0" }).temps_humain_minutes, 41);
for (const field of ["execution_minutes", "relecture_minutes", "correction_minutes", "supervision_minutes", "maintenance_minutes", "installation_minutes"]) {
  assert.throws(() => record({ [field]: "" }), /_invalid/);
  assert.throws(() => record({ [field]: Infinity }), /_invalid/);
  assert.throws(() => record({ [field]: true }), /_invalid/);
  assert.throws(() => record({ [field]: [] }), /_invalid/);
  assert.throws(() => record({ [field]: {} }), /_invalid/);
}
assert.throws(() => record({ execution_minutes: 480, relecture_minutes: 480, correction_minutes: 480, supervision_minutes: 1, maintenance_minutes: 1, installation_minutes: 1 }), /minutes_total_invalid/);
assert.throws(() => record({ date: "2026-02-30" }), /date_invalid/);
assert.throws(() => record({ mesure_ref: "secret://token" }), /mesure_ref_invalid/);
assert.equal(record({ confirmation_manuelle: true, temps_observe: true }).external_effect, false);

const ref = record({ execution_minutes: 30, relecture_minutes: 0, correction_minutes: 0, supervision_minutes: 0, maintenance_minutes: 0, installation_minutes: 10 });
const assist = record({ session_id: "session-2", phase: "assiste", dossier_id: "dossier-2", execution_minutes: 20, relecture_minutes: 0, correction_minutes: 0, supervision_minutes: 0, maintenance_minutes: 5, installation_minutes: 2 });
let result = summarize([ref, assist]);
assert.equal(result.summary.gain_minutes, 5);
assert.equal(result.summary.gain_percent, 16.666666666666664);
assert.equal(result.summary.installation_minutes, 12);

result = summarize([ref, record({ session_id: "session-3", phase: "assiste", dossier_id: "dossier-2", execution_minutes: 40, relecture_minutes: 0, correction_minutes: 0, supervision_minutes: 0, maintenance_minutes: 0, installation_minutes: 0 })]);
assert.equal(result.summary.gain_minutes, -10);
assert.equal(result.summary.status, "gain_mesuré");

assert.equal(summarize([record({ phase: "reference", qualite: "a_revoir" }), assist]).summary.gain_minutes, null);
assert.equal(summarize([ref]).summary.status, "gain_non_mesure");
assert.equal(summarize([ref, assist, record({ session_id: "session-3", phase: "assiste", dossier_id: "dossier-3", comparaison_id: "cmp-1" })]).exclusions[0].reason, "paire_ambiguë_ou_incomplète");
assert.equal(summarize([ref, record({ session_id: "session-3", phase: "assiste", dossier_id: "dossier-2", categorie: "autre" })]).exclusions[0].reason, "référence_assisté_incomparable");
assert.equal(summarize([ref, record({ session_id: "session-3", phase: "assiste", dossier_id: "dossier-2", jeu: "usage" })]).summary.status, "gain_non_mesure");
assert.equal(summarize([ref, assist], { jeu: "usage" }).summary.status, "gain_non_mesure");
assert.equal(summarize([ref, assist], { date_debut: "2026-10-12" }).summary.status, "gain_non_mesure");

const timestamped = { ...ref, updated_at: "2026-01-01T00:00:00.000Z" };
assert.equal(summarize([timestamped]).items[0].updated_at, timestamped.updated_at);
assert.throws(() => summarize(Array.from({ length: 101 }, (_, index) => record({ session_id: `session-${index}`, dossier_id: `dossier-${index}` }))), /rows_limit_exceeded/);

const duplicate = { ...assist, session_id: ref.session_id, dossier_id: "dossier-duplicate" };
result = summarize([ref, assist, duplicate]);
assert.equal(result.items.length, 2);
assert.equal(result.exclusions.at(-1).reason, "session_id_dupliqué");
assert.equal(result.exclusions.at(-1).reason_label, "Duplicate measurement ID");
assert.equal(result.items[1].phase, "assiste");
assert.equal(result.items[1].phase_label, "Assisted");
assert.equal(result.items[1].qualite, "valide");
assert.equal(result.items[1].quality_label, "Validated");

const noPair = record({ session_id: "session-4", comparaison_id: "cmp-no-pair", dossier_id: "dossier-no-pair", installation_minutes: 7 });
result = summarize([ref, assist, noPair]);
assert.equal(result.summary.total_temps_humain_minutes, ref.temps_humain_minutes + assist.temps_humain_minutes + noPair.temps_humain_minutes);
assert.equal(result.summary.installation_minutes, ref.installation_minutes + assist.installation_minutes + noPair.installation_minutes);
assert.equal(result.items.length, 3);

const setupOnly = summarize([ref, record({ session_id: "session-3", phase: "assiste", dossier_id: "dossier-2", execution_minutes: 30, relecture_minutes: 0, correction_minutes: 0, supervision_minutes: 0, maintenance_minutes: 0, installation_minutes: 20 })]);
assert.equal(setupOnly.summary.gain_minutes, 0);
assert.equal(setupOnly.summary.installation_minutes, 30);

console.log("metrics tests passed");
