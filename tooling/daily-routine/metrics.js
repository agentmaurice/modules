const ID = /^[a-z0-9][a-z0-9-]{0,63}$/;
const DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const PHASES = new Set(["reference", "assiste"]);
const GAMES = new Set(["qualification", "usage"]);
const COMPLEXITIES = new Set(["courte", "standard", "complexe"]);
const QUALITIES = new Set(["a_revoir", "valide", "rejete"]);

function requiredString(value, name, max) {
  if (typeof value !== "string" || !value.trim() || value.length > max) {
    throw new TypeError(`${name}_invalid`);
  }
  if (name === "mesure_ref" && /secret:\/\//i.test(value)) {
    throw new TypeError(`${name}_invalid`);
  }
  return value;
}

function strictDate(value) {
  if (typeof value !== "string") throw new TypeError("date_invalid");
  const match = DATE.exec(value);
  if (!match) throw new TypeError("date_invalid");
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime()) || date.getUTCFullYear() !== Number(match[1]) ||
      date.getUTCMonth() + 1 !== Number(match[2]) || date.getUTCDate() !== Number(match[3])) {
    throw new TypeError("date_invalid");
  }
  return value;
}

function minutes(value, name) {
  if (typeof value === "boolean" || value === null || value === undefined || Array.isArray(value) || (typeof value === "object" && value !== null)) {
    throw new TypeError(`${name}_invalid`);
  }
  const text = typeof value === "string" ? value.trim() : value;
  if (text === "") throw new TypeError(`${name}_invalid`);
  const number = Number(text);
  if (!Number.isFinite(number) || number < 0 || number > 480) {
    throw new TypeError(`${name}_invalid`);
  }
  return number;
}

function confirmed(value) {
  if (value === true || value === "true" || value === "oui") return true;
  throw new TypeError("confirmation_manuelle_required");
}

export function validateEntry(x) {
  if (!x || typeof x !== "object" || Array.isArray(x)) throw new TypeError("entry_invalid");
  for (const field of ["session_id", "comparaison_id", "dossier_id"]) {
    if (typeof x[field] !== "string" || !ID.test(x[field])) throw new TypeError(`${field}_invalid`);
  }
  if (!GAMES.has(x.jeu)) throw new TypeError("jeu_invalid");
  if (!PHASES.has(x.phase)) throw new TypeError("phase_invalid");
  const date = strictDate(x.date);
  const categorie = requiredString(x.categorie, "categorie", 80);
  if (!COMPLEXITIES.has(x.complexite)) throw new TypeError("complexite_invalid");
  const critere = requiredString(x.critere_qualite, "critere_qualite", 500);
  if (!QUALITIES.has(x.qualite)) throw new TypeError("qualite_invalid");
  const mesure = requiredString(x.mesure_ref, "mesure_ref", 512);
  const prochaine = requiredString(x.prochaine_etape, "prochaine_etape", 500);
  confirmed(x.confirmation_manuelle);
  confirmed(x.temps_observe);

  const measured = {};
  for (const field of ["execution_minutes", "relecture_minutes", "correction_minutes", "supervision_minutes", "maintenance_minutes", "installation_minutes"]) {
    measured[field] = minutes(x[field], field);
  }
  const recurring = ["execution_minutes", "relecture_minutes", "correction_minutes", "supervision_minutes", "maintenance_minutes"]
    .reduce((sum, field) => sum + measured[field], 0);
  if (recurring + measured.installation_minutes > 1440) throw new TypeError("minutes_total_invalid");

  return {
    session_id: x.session_id,
    comparaison_id: x.comparaison_id,
    dossier_id: x.dossier_id,
    jeu: x.jeu,
    phase: x.phase,
    date,
    categorie,
    complexite: x.complexite,
    critere_qualite: critere,
    qualite: x.qualite,
    mesure_ref: mesure,
    prochaine_etape: prochaine,
    confirmation_manuelle: true,
    temps_observe: true,
    ...measured,
    temps_humain_minutes: recurring,
    updated_at: new Date().toISOString(),
    schema_version: 1,
    manual_only: true,
    external_effect: false,
  };
}

function exclusion(comparaison_id, reason, rows = []) {
  return { comparaison_id, reason, dossier_ids: rows.map((row) => row.dossier_id).filter(Boolean) };
}

export function summarize(rows, filter = {}) {
  if (!Array.isArray(rows)) throw new TypeError("rows_invalid");
  if (rows.length > 100) throw new TypeError("rows_limit_exceeded");
  const selected = rows.filter((row) => {
    if (filter.jeu && row && row.jeu !== filter.jeu) return false;
    if (filter.date_debut && row && row.date < filter.date_debut) return false;
    if (filter.date_fin && row && row.date > filter.date_fin) return false;
    return true;
  });
  const exclusions = [];
  const groups = new Map();
  const items = [];
  const sessionIds = new Set();
  for (const raw of selected) {
    let row;
    try { row = validateEntry(raw); } catch (error) {
      exclusions.push(exclusion(raw?.comparaison_id ?? "", `ligne_invalide:${error.message}`, raw ? [raw] : []));
      continue;
    }
    if (sessionIds.has(row.session_id)) {
      exclusions.push(exclusion(row.comparaison_id, "session_id_dupliqué", [row]));
      continue;
    }
    sessionIds.add(row.session_id);
    if (Object.prototype.hasOwnProperty.call(raw, "updated_at")) row.updated_at = raw.updated_at;
    items.push(row);
    if (!groups.has(row.comparaison_id)) groups.set(row.comparaison_id, []);
    groups.get(row.comparaison_id).push(row);
  }
  const pairs = [];
  for (const [comparison, group] of groups) {
    const reference = group.filter((row) => row.phase === "reference");
    const assisted = group.filter((row) => row.phase === "assiste");
    if (reference.length !== 1 || assisted.length !== 1) {
      exclusions.push(exclusion(comparison, "paire_ambiguë_ou_incomplète", group));
      continue;
    }
    const ref = reference[0];
    const assist = assisted[0];
    if (ref.qualite !== "valide" || assist.qualite !== "valide") {
      exclusions.push(exclusion(comparison, "qualité_non_validée", group));
      continue;
    }
    if (ref.jeu !== assist.jeu) {
      exclusions.push(exclusion(comparison, "jeu_mélangé", group));
      continue;
    }
    if (ref.categorie !== assist.categorie || ref.complexite !== assist.complexite || ref.critere_qualite !== assist.critere_qualite) {
      exclusions.push(exclusion(comparison, "référence_assisté_incomparable", group));
      continue;
    }
    if (ref.temps_humain_minutes <= 0) {
      exclusions.push(exclusion(comparison, "référence_sans_temps", group));
      continue;
    }
    const gain = ref.temps_humain_minutes - assist.temps_humain_minutes;
    pairs.push({
      comparaison_id: comparison,
      categorie: ref.categorie,
      complexite: ref.complexite,
      critere_qualite: ref.critere_qualite,
      reference_minutes: ref.temps_humain_minutes,
      assiste_minutes: assist.temps_humain_minutes,
      installation_minutes: ref.installation_minutes + assist.installation_minutes,
      gain_minutes: gain,
      gain_percent: (gain / ref.temps_humain_minutes) * 100,
      status: "gain_mesuré",
    });
  }
  const referenceTotal = pairs.reduce((sum, pair) => sum + pair.reference_minutes, 0);
  const gainTotal = pairs.reduce((sum, pair) => sum + pair.gain_minutes, 0);
  const recurringTotal = items.reduce((sum, row) => sum + row.temps_humain_minutes, 0);
  const setupTotal = items.reduce((sum, row) => sum + row.installation_minutes, 0);
  const summary = {
    count: pairs.length,
    valid_rows: items.length,
    total_temps_humain_minutes: recurringTotal,
    gain_minutes: pairs.length ? gainTotal : null,
    gain_percent: pairs.length ? (gainTotal / referenceTotal) * 100 : null,
    installation_minutes: setupTotal,
    status: pairs.length ? "gain_mesuré" : "gain_non_mesure",
  };
  const message = pairs.length
    ? `${pairs.length} paire(s) comparée(s), temps récurrent et temps de mise en place séparés : gain/perte ${gainTotal.toFixed(2)} minute(s), résultat provisoire.`
    : "Aucune paire comparable : gain non mesuré ; temps et mise en place restent séparés, résultat provisoire.";
  return { items, pairs, exclusions, summary, message: (filter.jeu === "qualification" ? "Données de test : aucun gain réel démontré. " : "") + message };
}
