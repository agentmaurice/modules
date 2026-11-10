#!/usr/bin/env python3
"""Generate the document-studio Module resources (manifest, Workflows, MiniApp).

No rendering engine lives in the Module: rendering goes through the MCP tool
`artifact_render_v1`. The five reference templates (quote,
meeting-minutes, dashboard, support-reply and launch-newsletter) are embedded as text in the Workflows that render; they are
the files of document-studio/examples/templates, pinned by contract/PIN.json.
A template whose manifest declares the `message` profile (e-mail, engine mjml) is rendered
to its declared outputs (html, txt, eml), one engine call each, with no page preview and no
sending; every other template renders to a PDF with page previews.
Code steps are plain JavaScript (code_execution). The code never contains a
double-brace sequence: the Workflow engine would read it as a template action,
so template files are embedded with escaped braces (see js_embed).
Run this script after any change; the offline tests check that the published
resources match its output byte for byte.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULE = ROOT.parents[1] / 'document-studio'
DEST = MODULE / 'agents/main'
TEMPLATES_DIR = MODULE / 'examples/templates'
VERSION = '0.5.0'
RENDER_TOOL = 'artifact_render_v1'
STORAGE_TOOLS = ['read_file', 'write_file', 'list_files']
RENDER_TOOLS = STORAGE_TOOLS + [RENDER_TOOL]
BROKER = 'recipe--application_data_v1'
SHARE_TOOLS = ['read_file', BROKER]
NAMESPACE = 'cib-documents'
COMPARE_TOOL = 'office_compare_v1'
INSPECT_TOOL = 'office_inspect_v1'
VERSION_TOOLS = STORAGE_TOOLS + [COMPARE_TOOL, INSPECT_TOOL]
I18N = json.loads((ROOT / 'contract/i18n.fr.json').read_text(encoding='utf-8'))

# Draft data of a quote: numbers, never formatted amounts and never totals.
# The Workflow computes amounts and totals from the lines (integer cents).
QUOTE_DRAFT_SCHEMA = {
    'type': 'object',
    'required': ['customer', 'lines', 'valid_until', 'terms', 'payment_terms'],
    'properties': {
        'reference': {'type': 'string'},
        'customer': {
            'type': 'object', 'required': ['name'],
            'properties': {'name': {'type': 'string', 'minLength': 1},
                           'address_lines': {'type': 'array', 'items': {'type': 'string'}},
                           'contact': {'type': 'string'}}},
        'lines': {
            'type': 'array', 'minItems': 1, 'maxItems': 40,
            'items': {
                'type': 'object', 'required': ['description', 'quantity', 'unit_price_ht', 'vat_rate'],
                'properties': {
                    'description': {'type': 'string', 'minLength': 1},
                    'quantity': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 1000000, 'description': 'At most 3 decimals'},
                    'unit': {'type': 'string'},
                    'unit_price_ht': {'type': 'number', 'minimum': 0, 'maximum': 1000000000, 'description': 'At most 2 decimals'},
                    'vat_rate': {'type': 'number', 'minimum': 0, 'maximum': 100, 'description': 'One of 0, 2.1, 5.5, 10, 20'}}}},
        'valid_until': {'type': 'string', 'format': 'date'},
        'terms': {'type': 'array', 'items': {'type': 'string'}},
        'payment_terms': {'type': 'string'}},
}
TEMPLATE_META = {
    'quote': {'prefix': 'DEV', 'label': 'Devis', 'draft_schema': QUOTE_DRAFT_SCHEMA,
              'summary': 'Devis : client, lignes (description, quantité, unité, prix unitaire HT, taux de TVA), validité, conditions, règlement. Les montants et les totaux sont calculés, jamais saisis.'},
    'meeting-minutes': {'prefix': 'CR', 'label': 'Compte rendu de réunion', 'draft_schema': None,
                        'summary': 'Compte rendu de réunion : réunion, participants, ordre du jour, décisions, actions (responsable, échéance).'},
    'dashboard': {'prefix': 'TB', 'label': 'Tableau de bord', 'draft_schema': None,
                  'summary': 'Tableau de bord : six graphiques (barres, lignes, camembert, Gantt, organigramme, processus) à partir de données chart/v1 ; le moteur les trace, rien n\'est calculé par le modèle.'},
    'support-reply': {'prefix': 'REP', 'label': 'Réponse du support', 'draft_schema': None,
                      'summary': 'E-mail transactionnel de réponse à un ticket de support : client, paragraphes, étapes à suivre, lien vers le ticket, signature. Rendu html, txt et eml, sans envoi.'},
    'launch-newsletter': {'prefix': 'NL', 'label': 'Newsletter de lancement', 'draft_schema': None,
                          'summary': 'E-mail marketing de lancement de produit : visuel, annonce, points forts, bouton d\'appel à l\'action, lien de désabonnement. URL absolues en https. Rendu html, txt et eml, sans envoi.'},
}


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def js_embed(value):
    """A JavaScript expression that rebuilds `value`, with every brace written as a unicode escape."""
    literal = json.dumps(json.dumps(value, ensure_ascii=False, sort_keys=True), ensure_ascii=False)
    return 'JSON.parse(' + literal.replace('{', '\\u007b').replace('}', '\\u007d') + ')'


def is_platform_file(rel):
    return rel.startswith('fragments/') or rel in ('brand.typ', 'values.json')


def load_templates(with_files):
    templates = {}
    for key, meta in TEMPLATE_META.items():
        directory = TEMPLATES_DIR / key
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        input_schema = json.loads((directory / 'input.schema.json').read_text(encoding='utf-8'))
        entry = {'manifest': manifest, 'input_schema': input_schema, 'prefix': meta['prefix'],
                 'title': manifest['title'], 'summary': meta['summary'],
                 'draft_schema': meta['draft_schema'] or input_schema}
        if with_files:
            # fragments/ (and brand.typ, values.json) are written by the renderer
            # itself from its pinned contract: sending them is refused
            # (reserved_file_name). The local copies serve template_check only.
            entry['files'] = {p.relative_to(directory).as_posix(): p.read_text(encoding='utf-8')
                              for p in sorted(directory.rglob('*'))
                              if p.is_file() and not is_platform_file(p.relative_to(directory).as_posix())}
        templates[key] = entry
    return templates


def message_keys():
    return [key for key, entry in load_templates(False).items() if entry['manifest'].get('profile') == 'message']


# ---------------------------------------------------------------------------
# JavaScript (Deno sandbox). No double-brace sequence anywhere in this text.
# ---------------------------------------------------------------------------
IMPORT = "import { callTool } from './tools/nats_bridge.ts';\n"

CORE = r'''
const ROOT = "/document-studio";
const ID_RE = /^[a-z0-9][a-z0-9-]{0,47}$/;
const STATUSES = ["draft", "approved", "issued", "cancelled"];

function fail(code, message) { throw new Error(message ? code + ": " + message : code); }
function isObject(v) { return v !== null && typeof v === "object" && !Array.isArray(v); }
function confirmed(v) { return v === true || v === "true" || v === "oui"; }
function requireConfirmation(input) { if (!confirmed(input.confirmation_manuelle)) fail("manual_confirmation_required", "confirmez explicitement (confirmation_manuelle = oui)"); }
// The clock can be injected by the offline test bench (globalThis.__dsNow); in a One it is always the real clock.
function clock() { return typeof globalThis.__dsNow === "string" ? new Date(globalThis.__dsNow) : new Date(); }
function today() { return clock().toISOString().slice(0, 10); }
function nowIso() { return clock().toISOString(); }
function own(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
// External data (model answer, patch, answers, profile) never carries these keys, at any depth.
function rejectUnsafeKeys(v, label) {
  if (Array.isArray(v)) { v.forEach((x) => rejectUnsafeKeys(x, label)); return; }
  if (!isObject(v)) return;
  // An object literal written as {"__proto__": ...} in generated code sets the prototype instead of a key.
  const proto = Object.getPrototypeOf(v);
  if (proto !== Object.prototype && proto !== null) fail("data_invalid", label + " : prototype inattendu");
  for (const k of Object.keys(v)) {
    if (k === "__proto__" || k === "constructor" || k === "prototype") fail("data_invalid", label + " : clé interdite " + k);
    rejectUnsafeKeys(v[k], label);
  }
}
function docIdOf(v) { if (typeof v !== "string" || !ID_RE.test(v)) fail("doc_id_invalid", "attendu : minuscules, chiffres et tirets, 48 caractères au plus"); return v; }
function slugify(text) {
  const base = String(text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40).replace(/-+$/g, "");
  return base || "doc";
}
function shortSuffix() { const bytes = new Uint8Array(3); crypto.getRandomValues(bytes); return Array.from(bytes, (x) => x.toString(16).padStart(2, "0")).join(""); }
function validDate(v) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(typeof v === "string" ? v : "");
  if (!m) return false;
  const d = new Date(v + "T00:00:00Z");
  return !Number.isNaN(d.getTime()) && d.getUTCFullYear() === Number(m[1]) && d.getUTCMonth() + 1 === Number(m[2]) && d.getUTCDate() === Number(m[3]);
}
function text(v, name, max, required) {
  if (v === undefined || v === null || v === "") { if (required) fail(name + "_required"); return ""; }
  if (typeof v !== "string" || v.length > max) fail(name + "_invalid");
  const t = v.trim();
  if (required && !t) fail(name + "_required");
  return t;
}
function canonical(v) { return Array.isArray(v) ? "[" + v.map(canonical).join(",") + "]" : isObject(v) ? "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canonical(v[k])).join(",") + "}" : JSON.stringify(v); }
async function fingerprint(v) { return sha256Hex(new TextEncoder().encode(canonical(v))); }
function b64ToBytes(b64) { const bin = atob(b64); const out = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i); return out; }
async function sha256Hex(bytes) { const d = await crypto.subtle.digest("SHA-256", bytes); return Array.from(new Uint8Array(d), (x) => x.toString(16).padStart(2, "0")).join(""); }
function parseJsonValue(v) {
  // llm_call with llm_response_format "text" yields {text, model, provider}.
  if (v && typeof v === "object" && !Array.isArray(v) && typeof v.text === "string") v = v.text;
  if (typeof v !== "string") { rejectUnsafeKeys(v, "réponse du modèle"); return v; }
  const cleaned = v.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  let parsed;
  try { parsed = JSON.parse(cleaned); } catch (e) { fail("llm_output_invalid", "réponse non JSON"); }
  rejectUnsafeKeys(parsed, "réponse du modèle");
  return parsed;
}

// Subset of JSON Schema: $ref (#/$defs), type, enum, required, properties, additionalProperties false,
// items, minItems, maxItems, minLength, pattern, format date, minimum, maximum, exclusiveMinimum, const, anyOf.
function checkSchema(schema, value, path, root, errors) {
  if (errors.length >= 8) return;
  if (schema.$ref) {
    if (!schema.$ref.startsWith("#/")) fail("schema_ref_unsupported", schema.$ref);
    let node = root;
    for (const part of schema.$ref.slice(2).split("/")) node = node ? node[part] : undefined;
    if (!node) fail("schema_ref_unknown", schema.$ref);
    return checkSchema(node, value, path, root, errors);
  }
  if (value === null) {
    if (schema.nullable === true || (Array.isArray(schema.type) && schema.type.includes("null")) || schema.type === "null") return;
    errors.push(path + " : null non autorisé");
    return;
  }
  const types = Array.isArray(schema.type) ? schema.type : (schema.type ? [schema.type] : []);
  if (types.length) {
    const ok = types.some((t) => t === "null" ? false : t === "string" ? typeof value === "string" : t === "number" ? (typeof value === "number" && Number.isFinite(value)) : t === "integer" ? Number.isInteger(value) : t === "boolean" ? typeof value === "boolean" : t === "array" ? Array.isArray(value) : t === "object" ? isObject(value) : true);
    if (!ok) { errors.push(path + " : type " + types.join("|") + " attendu"); return; }
  }
  if (schema.enum && !schema.enum.includes(value)) errors.push(path + " : valeur hors liste");
  if (schema.const !== undefined && value !== schema.const) errors.push(path + " : valeur attendue " + JSON.stringify(schema.const));
  if (Array.isArray(schema.anyOf) && !schema.anyOf.some((alt) => { const sub = []; checkSchema(alt, value, path, root, sub); return sub.length === 0; })) errors.push(path + " : aucune des variantes admises");
  if (typeof value === "string") {
    if (schema.minLength !== undefined && value.length < schema.minLength) errors.push(path + " : vide ou trop court");
    if (schema.maxLength !== undefined && value.length > schema.maxLength) errors.push(path + " : trop long");
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) errors.push(path + " : format invalide");
    if (schema.format === "date" && !validDate(value)) errors.push(path + " : date AAAA-MM-JJ invalide");
  }
  if (typeof value === "number") {
    if (schema.minimum !== undefined && value < schema.minimum) errors.push(path + " : inférieur au minimum");
    if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) errors.push(path + " : doit être supérieur à " + schema.exclusiveMinimum);
    if (schema.maximum !== undefined && value > schema.maximum) errors.push(path + " : supérieur au maximum");
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) errors.push(path + " : trop peu d'éléments");
    if (schema.maxItems !== undefined && value.length > schema.maxItems) errors.push(path + " : trop d'éléments");
    if (schema.items) value.forEach((item, i) => checkSchema(schema.items, item, path + "[" + i + "]", root, errors));
  }
  if (isObject(value)) {
    for (const key of schema.required || []) if (value[key] === undefined || value[key] === null) errors.push(path + "." + key + " : requis");
    const props = schema.properties || {};
    for (const key of Object.keys(props)) if (value[key] !== undefined) checkSchema(props[key], value[key], path + "." + key, root, errors);
    if (schema.additionalProperties === false) for (const key of Object.keys(value)) if (!own(props, key)) errors.push(path + "." + key + " : champ inconnu");
  }
}
function resolveRef(schema, root) {
  let node = schema;
  while (node && node.$ref) { let n = root; for (const part of node.$ref.slice(2).split("/")) n = n ? n[part] : undefined; node = n; }
  return node || {};
}
function isNullable(schema, root) { const n = resolveRef(schema, root); return n.nullable === true || n.type === "null" || (Array.isArray(n.type) && n.type.includes("null")); }
// An optional property set to null is removed before validation (simplest for a model); a required one stays and fails.
function stripNulls(schema, value, root) {
  const node = resolveRef(schema, root);
  if (Array.isArray(value)) return node.items ? value.map((v) => stripNulls(node.items, v, root)) : value;
  if (!isObject(value)) return value;
  const props = node.properties || {};
  const out = Object.create(null);
  for (const [key, v] of Object.entries(value)) {
    const sub = own(props, key) ? props[key] : null;
    if (v === null && !(node.required || []).includes(key) && !(sub && isNullable(sub, root))) continue;
    Object.defineProperty(out, key, {value: sub ? stripNulls(sub, v, root) : v, enumerable: true, writable: true, configurable: true});
  }
  return out;
}
function validateSchema(schema, value, label) {
  const errors = [];
  checkSchema(schema, value, "$", schema, errors);
  if (errors.length) fail("data_invalid", label + " : " + errors.join(" ; "));
}

function fmtMoney(cents) {
  const big = BigInt(cents);
  const abs = big < 0n ? -big : big;
  const grouped = String(abs / 100n).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return (big < 0n ? "-" : "") + grouped + "," + String(abs % 100n).padStart(2, "0") + " €";
}
function fmtNumber(n) { return String(n).replace(".", ","); }
const VAT_RATES = [0, 2.1, 5.5, 10, 20];
// Exact check on the shortest decimal writing of the number (the JSON literal): no tolerance, no exponent.
function decimalsAtMost(n, places) { return typeof n === "number" && Number.isFinite(n) && new RegExp("^-?\\d+(\\.\\d{1," + places + "})?$").test(String(n)); }
function checkQuoteNumbers(d) {
  const errors = [];
  d.lines.forEach((l, i) => {
    const at = "lines[" + i + "]";
    const q1000 = Math.round(l.quantity * 1000);
    const p100 = Math.round(l.unit_price_ht * 100);
    if (!decimalsAtMost(l.quantity, 3)) errors.push(at + ".quantity : 3 décimales au plus");
    else if (q1000 < 1 || q1000 > 1e9) errors.push(at + ".quantity : entre 0,001 et 1000000");
    if (!decimalsAtMost(l.unit_price_ht, 2)) errors.push(at + ".unit_price_ht : 2 décimales au plus");
    else if (p100 < 0 || p100 > 1e11) errors.push(at + ".unit_price_ht : entre 0 et 1000000000");
    if (!VAT_RATES.includes(l.vat_rate)) errors.push(at + ".vat_rate : taux autorisés 0, 2.1, 5.5, 10 ou 20");
  });
  if (!errors.length) { try { quoteAmounts(d); } catch (e) { errors.push(String(e.message).replace(/^data_invalid: /, "")); } }
  if (errors.length) fail("data_invalid", "données du gabarit quote : " + errors.slice(0, 8).join(" ; "));
}
function fmtRate(r) { return fmtNumber(r) + " %"; }

// Amounts and totals are computed here, in BigInt cents (no intermediate Number), from the lines. They are never
// taken from the model. Rounding to the cent is half up. Every amount stays under 1e16 cents (100 trillion euros).
const MAX_CENTS = 10000000000000000n;
function quoteAmounts(d) {
  const lines = [];
  let ht = 0n;
  const groups = new Map();
  for (const l of d.lines) {
    const q1000 = BigInt(Math.round(l.quantity * 1000));
    const unit = BigInt(Math.round(l.unit_price_ht * 100));
    const total = (q1000 * unit + 500n) / 1000n;
    const rate = BigInt(Math.round(l.vat_rate * 100));
    if (total > MAX_CENTS) fail("data_invalid", "totaux : montant de ligne trop grand");
    ht += total;
    groups.set(rate, (groups.get(rate) || 0n) + total);
    lines.push({l, unit, total, rate});
  }
  let vatTotal = 0n;
  const vat = Array.from(groups.entries()).sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0)).map(([rate, base]) => {
    const cents = (base * rate + 5000n) / 10000n;
    vatTotal += cents;
    return {rate, cents};
  });
  if (ht > MAX_CENTS || ht + vatTotal > MAX_CENTS) fail("data_invalid", "totaux : montant du document trop grand");
  return {lines, ht, vat, ttc: ht + vatTotal};
}
function quoteData(d) {
  const a = quoteAmounts(d);
  const lines = a.lines.map(({l, unit, total, rate}) => ({description: l.description, quantity: fmtNumber(l.quantity) + (l.unit ? " " + l.unit : ""), unit_price_ht: fmtMoney(unit), vat_rate: fmtRate(Number(rate) / 100), total_ht: fmtMoney(total)}));
  const customer = d.customer;
  return {reference: d.reference, customer: {name: customer.name, address_lines: customer.address_lines || [], contact: customer.contact || ""}, lines, totals: {total_ht: fmtMoney(a.ht), vat: a.vat.map((v) => ({rate: fmtRate(Number(v.rate) / 100), amount: fmtMoney(v.cents)})), total_ttc: fmtMoney(a.ttc)}, valid_until: d.valid_until, terms: d.terms || [], payment_terms: d.payment_terms || ""};
}
// Title of a document from its (validated) data; fallbackTitle is the same on raw model output, before validation.
// An e-mail has no title field: its subject, else its headline, else the template title.
function messageTitle(key, d) { for (const k of ["subject", "headline"]) if (isObject(d) && typeof d[k] === "string" && d[k].trim()) return d[k].trim(); return TEMPLATES[key].title; }
function documentTitle(key, d) { return MESSAGE_KEYS.includes(key) ? messageTitle(key, d) : key === "quote" ? "Devis " + d.customer.name : key === "meeting-minutes" ? d.meeting.title : d.title; }
function fallbackTitle(key, d) {
  if (MESSAGE_KEYS.includes(key)) return messageTitle(key, d);
  if (key === "quote") return "devis " + (isObject(d.customer) ? d.customer.name : "");
  if (key === "meeting-minutes") return isObject(d.meeting) ? d.meeting.title : key;
  return typeof d.title === "string" && d.title ? d.title : key;
}
function templateData(key, data) { return key === "quote" ? quoteData(data) : data; }

// Draft data: reference default, validation against the draft schema, then against the template input schema.
function normalizeData(key, data, id) {
  if (!isObject(data)) fail("data_invalid", "les données doivent être un objet");
  rejectUnsafeKeys(data, "données");
  let d = stripNulls(TEMPLATES[key].draft_schema, data, TEMPLATES[key].draft_schema);
  if (key === "quote" && (d.reference === undefined || d.reference === null || d.reference === "")) d = {...d, reference: id.toUpperCase()};
  const tpl = TEMPLATES[key];
  validateSchema(tpl.draft_schema, d, "données du gabarit " + key);
  if (key === "quote") checkQuoteNumbers(d);
  validateSchema(tpl.input_schema, templateData(key, d), "gabarit " + key);
  return d;
}

function summarize(rec) {
  const last = rec.renders.length ? rec.renders[rec.renders.length - 1] : null;
  return {doc_id: rec.doc_id, template_key: rec.template_key, title: rec.title, locale: rec.locale, status: rec.status, number: rec.number, revision: rec.revision, renders: rec.renders.length, last_render: last ? {revision: last.revision, mode: last.mode, path: last.file.path, sha256: last.file.sha256, pages: last.previews.length, outputs: isObject(last.files) ? Object.keys(last.files) : undefined} : null, issued: rec.issued};
}
function checkRecord(rec, id) {
  if (!isObject(rec) || rec.schema !== "document-studio.record/v1" || rec.doc_id !== id || !STATUSES.includes(rec.status) || !Number.isInteger(rec.revision) || !Array.isArray(rec.renders) || !Array.isArray(rec.history) || typeof rec.template_key !== "string" || !isObject(rec.data)) fail("record_invalid", id);
  return rec;
}
'''

IO = r'''
function unwrap(r) {
  if (isObject(r) && isObject(r.data) && r.content === undefined && r.file === undefined && r.status === undefined) return r.data;
  return r;
}
function isMissing(message) { return /not found|does not exist|no such/i.test(message); }
async function readText(path, extra) {
  let r;
  try { r = unwrap(await callTool("read_file", {path, ...(extra || {})})); } catch (e) {
    const message = String(e && e.message);
    if (isMissing(message)) fail("storage_not_found", path);
    fail("storage_unavailable", message.slice(0, 200));
  }
  if (typeof r === "string") return r;
  if (isObject(r) && typeof r.content === "string") return r.content;
  fail("storage_read_failed", path);
}
async function readJson(path) {
  const raw = await readText(path);
  try { return JSON.parse(raw); } catch (e) { fail("json_corrupt", path); }
}
async function writeJson(path, value, overwrite) {
  await callTool("write_file", {path, content: JSON.stringify(value, null, 2) + "\n", overwrite});
}
async function listPaths(path) {
  let r;
  try { r = unwrap(await callTool("list_files", {path})); } catch (e) {
    const message = String(e && e.message);
    if (isMissing(message)) return [];
    fail("storage_unavailable", message.slice(0, 200));
  }
  const entries = Array.isArray(r) ? r : (isObject(r) ? (r.files || r.entries || []) : []);
  return entries.map((e) => (typeof e === "string" ? e : (isObject(e) && typeof e.path === "string" ? e.path : ""))).filter(Boolean);
}
function recordPath(id) { return ROOT + "/docs/" + id + "/record.json"; }
function remember(rec) { Object.defineProperty(rec, "_loaded", {value: {revision: rec.revision, status: rec.status}, enumerable: false, writable: true, configurable: true}); return rec; }
async function loadRecord(id) {
  let rec;
  try { rec = await readJson(recordPath(id)); } catch (e) {
    const m = String(e && e.message);
    if (m.startsWith("storage_not_found")) fail("document_not_found", id);
    if (m.startsWith("json_corrupt")) fail("record_corrupt", id);
    throw e;
  }
  return remember(checkRecord(rec, id));
}
// Storage has no conditional write: the record is read again just before the write, and the write is abandoned when
// another actor changed it (revision or status). The window is small, not null.
async function saveRecord(rec) {
  let fresh;
  try { fresh = await readJson(recordPath(rec.doc_id)); } catch (e) {
    const m = String(e && e.message);
    if (m.startsWith("storage_not_found")) fail("concurrent_update", "le dossier a disparu : " + rec.doc_id);
    if (m.startsWith("json_corrupt")) fail("record_corrupt", rec.doc_id);
    throw e;
  }
  const was = rec._loaded;
  if (!isObject(fresh) || !was || fresh.revision !== was.revision || fresh.status !== was.status || fresh.status === "cancelled" && was.status !== "cancelled") fail("concurrent_update", "le dossier " + rec.doc_id + " a changé pendant l'opération ; rien n'a été écrit");
  await writeJson(recordPath(rec.doc_id), rec, true);
  remember(rec);
}
'''

PROFILE = r'''
const COLOR = /^#[0-9a-fA-F]{6}$/;
const IBAN = /^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/;
const BIC = /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/;
const COLOR_TOKENS = ["primary", "secondary", "accent", "text", "muted", "background"];
const FONT_ROLES = ["heading", "body", "mono"];
const MARGIN_SIDES = ["top", "right", "bottom", "left"];
const ADDRESS_PARTS = ["line1", "line2", "postal_code", "city", "country"];
const COMPANY_TEXT = {trade_name: 200, legal_form: 100, share_capital: 100, siren: 32, siret: 32, vat_number: 32, rcs: 200, email: 254, phone: 64, website: 300, legal_mentions: 4000};
function onlyKeys(v, allowed, name) { for (const k of Object.keys(v)) if (!allowed.includes(k)) fail(name + "_unknown_field", k); }

// Company and brand as expected by the template/v1 contract. A logo is a reference, never an upload.
function normalizeProfile(p) {
  rejectUnsafeKeys(p, "profil");
  if (!isObject(p) || (p.schema_version !== undefined && p.schema_version !== 1)) fail("profile_invalid", "schema_version 1 attendu");
  onlyKeys(p, ["schema_version", "company", "brand"], "profile");
  const c = p.company, b = p.brand;
  if (!isObject(c) || !isObject(b)) fail("profile_invalid", "company et brand sont requis");
  if (c.logo !== undefined) fail("profile_invalid", "company.logo est dérivé de brand.logo.ref");
  onlyKeys(c, ["legal_name", ...Object.keys(COMPANY_TEXT), "address", "bank"], "company");
  const company = {legal_name: text(c.legal_name, "legal_name", 200, true)};
  for (const [key, max] of Object.entries(COMPANY_TEXT)) { const v = text(c[key], key, max, false); if (v) company[key] = v; }
  if (c.address !== undefined) {
    if (!isObject(c.address)) fail("address_invalid");
    onlyKeys(c.address, ADDRESS_PARTS, "address");
    const address = {};
    for (const part of ADDRESS_PARTS) { const v = text(c.address[part], "address_" + part, 200, false); if (v) address[part] = v; }
    if (Object.keys(address).length) company.address = address;
  }
  if (c.bank !== undefined) {
    if (!isObject(c.bank)) fail("bank_invalid");
    onlyKeys(c.bank, ["account_holder", "iban", "bic", "bank_name"], "bank");
    const bank = {};
    for (const key of ["account_holder", "bank_name"]) { const v = text(c.bank[key], "bank_" + key, 200, false); if (v) bank[key] = v; }
    if (c.bank.iban !== undefined && c.bank.iban !== "") {
      const iban = typeof c.bank.iban === "string" ? c.bank.iban.replace(/\s+/g, "").toUpperCase() : "";
      if (iban.length < 15 || iban.length > 34 || !IBAN.test(iban)) fail("iban_invalid");
      bank.iban = iban;
    }
    if (c.bank.bic !== undefined && c.bank.bic !== "") {
      const bic = typeof c.bank.bic === "string" ? c.bank.bic.replace(/\s+/g, "").toUpperCase() : "";
      if (!BIC.test(bic)) fail("bic_invalid");
      bank.bic = bic;
    }
    if (Object.keys(bank).length) company.bank = bank;
  }
  onlyKeys(b, ["colors", "fonts", "logo", "page", "spacing"], "brand");
  if (!isObject(b.colors) || !isObject(b.fonts) || !isObject(b.logo) || !isObject(b.page) || !isObject(b.page.margins_mm)) fail("brand_invalid");
  const colors = {};
  for (const token of COLOR_TOKENS) { if (typeof b.colors[token] !== "string" || !COLOR.test(b.colors[token])) fail("color_" + token + "_invalid", "attendu #RRGGBB"); colors[token] = b.colors[token]; }
  const fonts = {};
  for (const role of FONT_ROLES) { if (!isObject(b.fonts[role])) fail("font_" + role + "_invalid"); fonts[role] = {family: text(b.fonts[role].family, "font_" + role, 100, true)}; }
  const ref = b.logo.ref;
  if (typeof ref !== "string" || !ref || ref.length > 500 || /\s/.test(ref) || ref.includes("..") || ref.toLowerCase().includes("secret://")) fail("logo_ref_invalid");
  if (b.page.size !== "A4" && b.page.size !== "Letter") fail("page_size_invalid");
  const margins_mm = {};
  for (const side of MARGIN_SIDES) { const m = b.page.margins_mm[side]; if (typeof m !== "number" || !Number.isFinite(m) || m < 0 || m > 100) fail("margin_" + side + "_invalid"); margins_mm[side] = m; }
  const brand = {colors, fonts, logo: {ref, alt: text(b.logo.alt, "logo_alt", 200, true)}, page: {size: b.page.size, margins_mm}};
  if (b.spacing !== undefined) {
    if (!isObject(b.spacing)) fail("spacing_invalid");
    for (const [k, v] of Object.entries(b.spacing)) if (typeof v !== "number" || v < 0) fail("spacing_invalid", k);
    brand.spacing = b.spacing;
  }
  return {schema_version: 1, company, brand};
}

// The templates read these company fields without a guard: an absent value becomes an empty string.
function projectProfile(body) {
  const company = {...body.company};
  if (!company.trade_name) company.trade_name = company.legal_name;
  for (const key of Object.keys(COMPANY_TEXT)) if (company[key] === undefined) company[key] = "";
  company.address = {line1: "", line2: "", postal_code: "", city: "", country: "", ...(company.address || {})};
  company.logo = {ref: body.brand.logo.ref};
  return {company, brand: body.brand};
}
'''

PROFILE_LOAD = r'''
// The company profile comes from the cib-profile record (native broker, same read call as cib-profile-read). When that record is
// absent, refused to this caller or unreadable, the Storage copy written by document-studio-profile-save is used, as before.
let PROFILE_SOURCE = "storage";
async function brokerProfileBody() {
  let response;
  try { response = await callTool("recipe--application_data_v1", {operation: "read", namespace: "cib-profile", record_key: "company-profile"}); } catch (e) { return null; }
  if (isObject(response) && isObject(response.error)) return null;
  const payload = response && response.data ? response.data : response;
  const item = payload && payload.record;
  if (!isObject(item) || item.namespace !== "cib-profile" || item.key !== "company-profile" || !isObject(item.data)) return null;
  const p = item.permissions;
  if (!isObject(p) || p.can_read !== true) return null;
  return item.data;
}
async function loadProfile() {
  const body = await brokerProfileBody();
  if (body !== null) {
    try { const projected = projectProfile(normalizeProfile(body)); PROFILE_SOURCE = "cib-profile"; return projected; } catch (e) { /* unreadable record: fall back to Storage */ }
  }
  PROFILE_SOURCE = "storage";
  let stored = null;
  try { stored = await readJson(ROOT + "/profile.json"); } catch (e) {
    const m = String(e && e.message);
    if (m.startsWith("json_corrupt")) fail("profile_corrupt", "profile.json illisible");
    if (!m.startsWith("storage_not_found")) throw e;
    stored = null;
  }
  if (!isObject(stored)) fail("profile_missing", "enregistrez la charte dans cib-profile ou par document-studio-profile-save");
  return projectProfile(normalizeProfile(stored));
}
'''

RENDER = r'''
// A folder per attempt: a render that loses a race never overwrites the file of another attempt.
function attemptTag(f) { const sha = typeof f.sha256 === "string" ? f.sha256.toLowerCase().replace(/[^0-9a-f]/g, "").slice(0, 12) : ""; return sha || shortSuffix(); }

function renderContext(rec, profile, number, status, revision) {
  const doc = {number: number || "BROUILLON", title: rec.title, date: today(), version: String(revision), status, locale: rec.locale};
  return {company: profile.company, brand: profile.brand, doc, i18n: I18N};
}
async function callRender(tpl, tdata, context, output, mode) {
  const raw = await callTool("artifact_render_v1", {template: {manifest: tpl.manifest, files: tpl.files}, data: tdata, context, output, mode});
  const res = unwrap(raw);
  if (isObject(res) && res.error) fail("render_failed", res.error + (res.message ? " : " + res.message : ""));
  if (!isObject(res) || res.status !== "ok") fail("render_failed", "réponse inattendue du moteur de rendu");
  return res;
}
async function renderDocument(rec, data, profile, mode, number, status, revision) {
  const tpl = TEMPLATES[rec.template_key];
  if (!tpl) fail("template_unknown", rec.template_key);
  const tdata = templateData(rec.template_key, data);
  validateSchema(tpl.input_schema, tdata, "gabarit " + rec.template_key);
  const res = await callRender(tpl, tdata, renderContext(rec, profile, number, status, revision), "pdf", mode);
  if (!isObject(res.file)) fail("render_failed", "réponse inattendue du moteur de rendu");
  return res;
}

// Message profile (e-mail, read from the manifest, never from the key): one engine call per declared output, then
// the three files are stored, read back and fingerprinted. Nothing is stored when one render fails, and nothing is sent.
const MESSAGE_FILES = {html: "text/html", txt: "text/plain", eml: "message/rfc822"};
function messageOutputs(key) {
  const outputs = TEMPLATES[key].manifest.outputs.filter((o) => own(MESSAGE_FILES, o));
  if (!outputs.length) fail("template_invalid", key + " : aucune sortie html, txt ou eml");
  return outputs;
}
function messagePrimary(key) { const outputs = messageOutputs(key); return outputs.includes("html") ? "html" : outputs[0]; }
async function renderMessage(rec, data, profile, mode, number, status, revision) {
  const tpl = TEMPLATES[rec.template_key];
  if (!tpl) fail("template_unknown", rec.template_key);
  const tdata = templateData(rec.template_key, data);
  validateSchema(tpl.input_schema, tdata, "gabarit " + rec.template_key);
  const context = renderContext(rec, profile, number, status, revision);
  const results = {};
  for (const output of messageOutputs(rec.template_key)) {
    const res = await callRender(tpl, tdata, context, output, mode);
    if (res.output !== undefined && res.output !== output) fail("render_invalid", "sortie " + output + " demandée, " + String(res.output) + " rendue");
    if (!isObject(res.file)) fail("render_output_missing", "sortie " + output + " absente de la réponse du moteur");
    results[output] = res;
  }
  return results;
}
async function storeMessage(base, results) {
  const files = {};
  for (const output of Object.keys(results)) {
    const f = results[output].file;
    if (typeof f.mime_type === "string" && !f.mime_type.startsWith(MESSAGE_FILES[output])) fail("render_invalid", "sortie " + output + " : type " + f.mime_type + " inattendu");
    const stored = await storeFile(base + "." + output, f);
    if (stored.bytes === 0) fail("render_output_missing", "sortie " + output + " vide");
    files[output] = stored;
  }
  return files;
}

// Stores one rendered file: by buffer reference when the engine gives one, else from base64.
async function storeFile(path, f) {
  const args = {path, overwrite: true};
  let sha = typeof f.sha256 === "string" ? f.sha256 : "";
  if (f.ref !== undefined && f.ref !== null && f.ref !== "") args.buffer_ref = f.ref;
  else if (typeof f.content_base64 === "string") {
    const computed = await sha256Hex(b64ToBytes(f.content_base64));
    if (sha && sha !== computed) fail("render_integrity_failed", path);
    sha = computed;
    args.content = f.content_base64;
    args.encoding = "base64";
  } else fail("render_output_missing", path);
  await callTool("write_file", args);
  // Read the stored file back whatever the mode: its fingerprint and size must match what the renderer announced.
  let stored;
  try { stored = b64ToBytes((await readText(path, {encoding: "base64"})).replace(/\s+/g, "")); } catch (e) { fail("render_integrity_failed", path + " : relecture impossible"); }
  const actual = await sha256Hex(stored);
  if (sha && sha !== actual) fail("render_integrity_failed", path + " : empreinte différente de celle annoncée");
  if (typeof f.bytes === "number" && f.bytes !== stored.length) fail("render_integrity_failed", path + " : taille différente de celle annoncée");
  sha = actual;
  return {path, sha256: sha, bytes: stored.length, mime: typeof f.mime_type === "string" ? f.mime_type : "application/octet-stream"};
}
async function storePreviews(dir, res) {
  const previews = [];
  const seen = new Set();
  const list = res.previews;
  if (!Number.isInteger(res.pages) || res.pages < 1) fail("render_invalid", "pages doit être un entier ≥ 1");
  if (!Array.isArray(list) || list.length !== res.pages) fail("render_invalid", "le rendu doit fournir exactement " + res.pages + " aperçu(s)");
  // The renderer's file names are never trusted: one fixed name per page.
  for (const p of list) {
    if (!isObject(p) || !Number.isInteger(p.page) || p.page < 1 || (Number.isInteger(res.pages) && p.page > res.pages)) fail("render_invalid", "numéro de page d'aperçu invalide");
    if (seen.has(p.page)) fail("render_invalid", "page d'aperçu en double : " + p.page);
    seen.add(p.page);
    const stored = await storeFile(dir + "/page-" + p.page + ".png", p);
    previews.push({page: p.page, path: stored.path, sha256: stored.sha256});
  }
  for (let n = 1; n <= res.pages; n++) if (!seen.has(n)) fail("render_invalid", "aperçu manquant : page " + n);
  return previews;
}
'''

NUMBERING = r'''
// Number reservation: lists the year folder, takes max + 1, writes the token without overwrite, reads it back and
// checks the owner. Not atomic: the check narrows the window, it does not close it.
async function reserveNumber(rec) {
  const year = clock().getUTCFullYear();
  const dir = ROOT + "/numbers/" + rec.template_key + "/" + year;
  let last = "";
  for (let attempt = 0; attempt < 5; attempt++) {
    const paths = await listPaths(dir);
    let max = 0;
    for (const p of paths) { const m = /(?:^|\/)(\d{4,})\.json$/.exec(p); if (m) max = Math.max(max, Number(m[1])); }
    const seq = String(max + 1).padStart(4, "0");
    const path = dir + "/" + seq + ".json";
    try { await writeJson(path, {doc_id: rec.doc_id, at: nowIso()}, false); } catch (e) { last = String(e && e.message); continue; }
    let token = null;
    try { token = await readJson(path); } catch (e) { last = String(e && e.message); if (last.startsWith("storage_unavailable")) throw e; continue; }
    if (isObject(token) && token.doc_id === rec.doc_id) return TEMPLATES[rec.template_key].prefix + "-" + year + "-" + seq;
    last = "numéro " + seq + " pris par un autre document";
  }
  fail("number_conflict", "5 essais sans numéro libre (" + last + ")");
}
'''

VERSIONS = r'''
// DOCX versions of a document. Everything lives in Storage under docs/<doc_id>/versions/: one immutable file per version
// (name carries the version number and 12 characters of the SHA-256), one redline per version (office_compare_v1 between
// the previous version and this one) and ONE manifest. The record of the document (record.json) is never written here.
const MAX_DOCX_BYTES = 20 * 1024 * 1024;
const SHA_RE = /^[0-9a-f]{64}$/;
const MANIFEST_SCHEMA = "document-studio.versions/v1";
const VERSION_STATUSES = ["draft", "authoritative", "superseded"];
function versionsDir(id) { return ROOT + "/docs/" + id + "/versions"; }
function manifestPath(id) { return versionsDir(id) + "/manifest.json"; }
function onlyInput(input, allowed) {
  if (!isObject(input)) fail("input_invalid", "objet attendu");
  for (const k of Object.keys(input)) if (!allowed.includes(k)) fail("input_unknown_field", k);
}
function optionalInteger(v, name, min) {
  if (v === undefined || v === null || v === "") return undefined;
  const n = typeof v === "string" && /^\d{1,9}$/.test(v.trim()) ? Number(v.trim()) : v;
  if (!Number.isInteger(n) || n < min) fail(name + "_invalid", "entier attendu, " + min + " au minimum");
  return n;
}
function optionalDigest(v, name) {
  if (v === undefined || v === null || v === "") return undefined;
  const d = typeof v === "string" ? v.trim().toLowerCase() : "";
  if (!SHA_RE.test(d)) fail(name + "_invalid", "empreinte SHA-256 hexadécimale attendue");
  return d;
}
function sourcePathOf(v) {
  if (typeof v !== "string" || !v.startsWith("/") || v.length > 300 || v.includes("..") || v.includes("//") || /\s$/.test(v) || !/\.docx$/i.test(v)) fail("source_invalid", "chemin Storage absolu d'un fichier .docx attendu");
  return v;
}
function lastVersion(m) { return m && m.versions.length ? m.versions[m.versions.length - 1] : null; }
function authoritativeOf(m) { return m ? (m.versions.find((e) => e.status === "authoritative") || null) : null; }
async function manifestSha(raw) { return raw === null ? null : sha256Hex(new TextEncoder().encode(raw)); }
function checkManifest(m, id) {
  if (!isObject(m) || m.schema !== MANIFEST_SCHEMA || m.doc_id !== id || !Array.isArray(m.versions) || !Array.isArray(m.history)) fail("manifest_corrupt", id);
  let authoritative = 0;
  m.versions.forEach((e, i) => {
    if (!isObject(e) || e.version !== i + 1 || typeof e.sha256 !== "string" || !SHA_RE.test(e.sha256) || typeof e.storage_ref !== "string" || typeof e.author !== "string" || typeof e.created_at !== "string" || !VERSION_STATUSES.includes(e.status) || typeof e.request_sha256 !== "string") fail("manifest_corrupt", id + " : version " + (i + 1));
    if (e.status === "authoritative") authoritative += 1;
  });
  if (authoritative > 1) fail("manifest_corrupt", id + " : plusieurs versions font foi");
  return m;
}
// Reads the manifest and keeps its raw text: the fingerprint of that text is the optimistic-concurrency token.
async function loadManifest(id) {
  let raw = null;
  try { raw = await readText(manifestPath(id)); } catch (e) {
    if (!String(e && e.message).startsWith("storage_not_found")) throw e;
  }
  if (raw === null) return {raw: null, manifest: null, sha: null};
  let parsed;
  try { parsed = JSON.parse(raw); } catch (e) { fail("manifest_corrupt", id + " : JSON illisible"); }
  try { rejectUnsafeKeys(parsed, "manifeste"); } catch (e) { fail("manifest_corrupt", id + " : " + String(e.message).slice(0, 120)); }
  return {raw, manifest: checkManifest(parsed, id), sha: await manifestSha(raw)};
}
// Storage has no conditional write (no compare-and-swap): the manifest is read again just before the write and the write is
// abandoned when its text changed since the first read. A first manifest is written without overwrite. The window between the
// second read and the write is small, not null: one writer at a time per document.
async function writeManifest(id, manifest, expectedRaw) {
  let fresh = null;
  try { fresh = await readText(manifestPath(id)); } catch (e) {
    if (!String(e && e.message).startsWith("storage_not_found")) throw e;
  }
  if (fresh !== expectedRaw) fail("concurrent_update", "le manifeste de " + id + " a changé pendant l'opération ; rien n'a été écrit dans le manifeste");
  const body = JSON.stringify(manifest, null, 2) + "\n";
  try { await callTool("write_file", {path: manifestPath(id), content: body, overwrite: expectedRaw !== null}); } catch (e) {
    if (expectedRaw === null) fail("concurrent_update", "le manifeste de " + id + " vient d'être créé par un autre acteur");
    throw e;
  }
  return sha256Hex(new TextEncoder().encode(body));
}
// Structural check of the ZIP package, without a library: end-of-central-directory record, every central directory entry
// and its local header must be readable, and the package must hold [Content_Types].xml and word/document.xml. Entry
// contents are not inflated here; the comparison engine does the full parse on every version after the first.
function docxProblem(bytes) {
  const n = bytes.length;
  if (n < 22) return "fichier trop court pour un paquet ZIP";
  const dv = new DataView(bytes.buffer, bytes.byteOffset, n);
  let eocd = -1;
  for (let i = n - 22; i >= Math.max(0, n - 22 - 65535); i--) if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
  if (eocd < 0) return "fin d'archive ZIP introuvable";
  const count = dv.getUint16(eocd + 10, true), size = dv.getUint32(eocd + 12, true), offset = dv.getUint32(eocd + 16, true);
  if (count === 0 || count === 0xffff || offset + size > eocd) return "répertoire central ZIP invalide";
  const names = new Set();
  let at = offset;
  for (let k = 0; k < count; k++) {
    if (at + 46 > eocd || dv.getUint32(at, true) !== 0x02014b50) return "entrée ZIP illisible";
    const nameLen = dv.getUint16(at + 28, true), extraLen = dv.getUint16(at + 30, true), commentLen = dv.getUint16(at + 32, true), local = dv.getUint32(at + 42, true);
    if (at + 46 + nameLen > eocd) return "nom d'entrée ZIP illisible";
    if (local + 30 > offset || dv.getUint32(local, true) !== 0x04034b50) return "en-tête local ZIP illisible";
    names.add(new TextDecoder().decode(bytes.subarray(at + 46, at + 46 + nameLen)));
    at += 46 + nameLen + extraLen + commentLen;
  }
  if (!names.has("[Content_Types].xml") || !names.has("word/document.xml")) return "ce n'est pas un DOCX ([Content_Types].xml ou word/document.xml absent)";
  return "";
}
async function readDocx(path, missingCode) {
  let encoded;
  try { encoded = (await readText(path, {encoding: "base64"})).replace(/\s+/g, ""); } catch (e) {
    if (missingCode && String(e && e.message).startsWith("storage_not_found")) fail(missingCode, path);
    throw e;
  }
  let bytes;
  try { bytes = b64ToBytes(encoded); } catch (e) { fail("docx_invalid", path + " : contenu non lisible"); }
  if (bytes.length > MAX_DOCX_BYTES) fail("docx_too_large", path + " : 20 Mio au plus");
  const why = docxProblem(bytes);
  if (why) fail("docx_invalid", path + " : " + why);
  return {b64: encoded, bytes: bytes.length, sha: await sha256Hex(bytes)};
}
// Real validation by the document engine (office_inspect_v1): the structural check above is only a fast first filter. An error,
// a refusal or an answer without a structure means the file is not a readable DOCX.
async function inspectDocx(file, label) {
  let raw;
  try { raw = await callTool("office_inspect_v1", {format: "docx", file: {content_base64: file.b64}}); } catch (e) { fail("docx_invalid", label + " : " + String(e && e.message).slice(0, 200)); }
  const res = unwrap(raw);
  if (isObject(res) && res.error) fail("docx_invalid", label + " : " + res.error + (res.message ? " : " + String(res.message).slice(0, 200) : ""));
  if (!isObject(res) || res.status !== "ok" || !isObject(res.structure) || !Number.isInteger(res.structure.blocks)) fail("docx_invalid", label + " : le moteur n'a pas pu lire le document");
}
// The version a manifest entry points at must still be the bytes it fingerprinted.
async function readVersionFile(entry, withEngine) {
  const f = await readDocx(entry.storage_ref, "version_integrity_failed");
  if (f.sha !== entry.sha256) fail("version_integrity_failed", "v" + entry.version + " : l'empreinte du fichier ne correspond plus au manifeste");
  if (withEngine) await inspectDocx(f, entry.storage_ref);
  return f;
}
// File names carry the content: the same name can only ever hold the same bytes, so a retry may overwrite it safely.
async function storeBytes(path, b64, expectedSha) {
  await callTool("write_file", {path, content: b64, encoding: "base64", overwrite: true});
  let back;
  try { back = await sha256Hex(b64ToBytes((await readText(path, {encoding: "base64"})).replace(/\s+/g, ""))); } catch (e) { fail("version_integrity_failed", path + " : relecture impossible"); }
  if (back !== expectedSha) fail("version_integrity_failed", path + " : empreinte relue différente de celle écrite");
}
function countOf(v, name) { if (!Number.isInteger(v) || v < 0) fail("compare_invalid", "décompte " + name + " invalide"); return v; }
async function compareVersions(prev, next, author, n) {
  let raw;
  try { raw = await callTool("office_compare_v1", {before: {content_base64: prev.b64}, after: {content_base64: next.b64}, author, filename: "redline-v" + n + ".docx"}); } catch (e) { fail("compare_failed", String(e && e.message).slice(0, 300)); }
  const res = unwrap(raw);
  if (isObject(res) && res.error) fail("compare_failed", res.error + (res.message ? " : " + res.message : ""));
  rejectUnsafeKeys(res, "réponse office");
  if (!isObject(res) || res.status !== "ok" || !isObject(res.file) || !isObject(res.changes)) fail("compare_invalid", "réponse inattendue de office_compare_v1");
  const changes = {insertions: countOf(res.changes.insertions, "insertions"), deletions: countOf(res.changes.deletions, "deletions"),
    changed_paragraphs: res.changes.changed_paragraphs === undefined || res.changes.changed_paragraphs === null ? null : countOf(res.changes.changed_paragraphs, "changed_paragraphs")};
  return {file: res.file, changes};
}
// The redline is stored from the buffer reference when the tool gives one, else from base64; its fingerprint is checked.
async function storeRedline(dir, n, short, f) {
  let b64, sha = typeof f.sha256 === "string" ? f.sha256.toLowerCase() : "";
  const path = dir + "/v" + n + "-redline-" + short + ".docx";
  if (f.ref !== undefined && f.ref !== null && f.ref !== "") {
    await callTool("write_file", {path, buffer_ref: f.ref, overwrite: true});
    let stored;
    try { stored = b64ToBytes((await readText(path, {encoding: "base64"})).replace(/\s+/g, "")); } catch (e) { fail("version_integrity_failed", path + " : relecture impossible"); }
    const actual = await sha256Hex(stored);
    if (sha && sha !== actual) fail("version_integrity_failed", path + " : empreinte différente de celle annoncée");
    return {path, sha256: actual};
  }
  if (typeof f.content_base64 !== "string") fail("compare_invalid", "le comparateur n'a rendu ni référence ni contenu");
  b64 = f.content_base64.replace(/\s+/g, "");
  let bytes;
  try { bytes = b64ToBytes(b64); } catch (e) { fail("compare_invalid", "contenu base64 illisible"); }
  const computed = await sha256Hex(bytes);
  if (sha && sha !== computed) fail("version_integrity_failed", path + " : empreinte annoncée différente du contenu");
  await storeBytes(path, b64, computed);
  return {path, sha256: computed};
}
function versionSummary(doc, entry, manifest, msha, replayed) {
  const auth = authoritativeOf(manifest);
  return {doc_id: doc, version: entry.version, status: entry.status, supersedes: entry.supersedes === undefined ? null : entry.supersedes, sha256: entry.sha256, storage_ref: entry.storage_ref,
    redline_ref: entry.redline_ref === undefined ? null : entry.redline_ref, changes: entry.changes === undefined ? null : entry.changes,
    authoritative_version: auth ? auth.version : null, versions: manifest.versions.length, manifest_ref: manifestPath(doc), manifest_sha256: msha, replayed};
}
'''

NEW_VERSION_CODE = r'''
const input = {{ json . }};
rejectUnsafeKeys(input, "demande");
onlyInput(input, ["doc_id", "source_path", "author", "base_version", "base_manifest_sha256"]);
const id = docIdOf(input.doc_id);
const source = sourcePathOf(input.source_path);
const author = text(input.author, "author", 200, true);
const baseVersion = optionalInteger(input.base_version, "base_version", 0);
const baseSha = optionalDigest(input.base_manifest_sha256, "base_manifest_sha256");
if (source.startsWith(versionsDir(id) + "/")) fail("source_invalid", "la source ne peut pas être un fichier du dossier des versions");
const rec = await loadRecord(id);
if (MESSAGE_KEYS.includes(rec.template_key)) fail("not_applicable_to_message", "un message n'a pas de version DOCX");
if (rec.status === "cancelled") fail("document_cancelled", "un document annulé n'accepte plus de version");
const {raw, manifest, sha: msha} = await loadManifest(id);
const latest = lastVersion(manifest);
const latestN = latest ? latest.version : 0;
const file = await readDocx(source, "source_not_found");
// The request fingerprint covers what the caller decided (document, bytes, author), never the base: a replay of ANY earlier
// write is recognised whatever the manifest became since, and writes nothing.
const request = await fingerprint({action: "new-version", doc_id: id, sha256: file.sha, author});
const replayed = manifest ? manifest.versions.find((e) => e.request_sha256 === request && (baseVersion === undefined || baseVersion === e.version - 1)) : undefined;
if (replayed) return versionSummary(id, replayed, manifest, msha, true);
if (baseVersion !== undefined && baseVersion !== latestN) fail("base_version_conflict", "la dernière version est " + latestN + ", la demande part de " + baseVersion + " ; rien n'a été écrit");
if (baseSha !== undefined && baseSha !== msha) fail("base_version_conflict", "le manifeste a changé depuis sa lecture (empreinte " + (msha || "absente") + ") ; rien n'a été écrit");
if (latest && latest.sha256 === file.sha) fail("version_unchanged", "le fichier est identique à la version " + latest.version);
// The first version never goes through office_compare_v1: the engine reads it here, before any write.
if (!latest) await inspectDocx(file, source);
const n = latestN + 1;
const dir = versionsDir(id);
const short = file.sha.slice(0, 12);
let redline = null, changes = null;
if (latest) {
  const prev = await readVersionFile(latest);
  const cmp = await compareVersions(prev, file, author, n);
  redline = await storeRedline(dir, n, short, cmp.file);
  changes = cmp.changes;
}
const path = dir + "/v" + n + "-" + short + ".docx";
await storeBytes(path, file.b64, file.sha);
const entry = {version: n, sha256: file.sha, bytes: file.bytes, storage_ref: path, redline_ref: redline ? redline.path : null, redline_sha256: redline ? redline.sha256 : null,
  changes, author, created_at: nowIso(), status: "draft", supersedes: null, base_version: latest ? latest.version : null, request_sha256: request};
const next = {schema: MANIFEST_SCHEMA, doc_id: id, versions: (manifest ? manifest.versions : []).concat([entry]),
  history: (manifest ? manifest.history : []).concat([{at: entry.created_at, action: "version_added", version: n, author, note: latest ? "comparée à la version " + latest.version : "première version"}])};
const written = await writeManifest(id, next, raw);
return versionSummary(id, entry, next, written, false);
'''

MARK_AUTHORITATIVE_CODE = r'''
const input = {{ json . }};
requireConfirmation(input);
rejectUnsafeKeys(input, "demande");
onlyInput(input, ["doc_id", "version", "confirmation_manuelle", "approved_by", "base_manifest_sha256"]);
const id = docIdOf(input.doc_id);
const version = optionalInteger(input.version, "version", 1);
if (version === undefined) fail("version_required");
const approvedBy = text(input.approved_by, "approved_by", 200, false);
const baseSha = optionalDigest(input.base_manifest_sha256, "base_manifest_sha256");
const rec = await loadRecord(id);
if (MESSAGE_KEYS.includes(rec.template_key)) fail("not_applicable_to_message", "un message n'a pas de version DOCX");
if (rec.status === "cancelled") fail("document_cancelled", "un document annulé n'accepte plus de version qui fait foi");
const {raw, manifest, sha: msha} = await loadManifest(id);
if (!manifest) fail("manifest_not_found", "aucune version enregistrée pour " + id);
const entry = manifest.versions.find((e) => e.version === version);
if (!entry) fail("version_not_found", "version " + version);
// Replay: the version already is authoritative, nothing is written.
if (entry.status === "authoritative") return versionSummary(id, entry, manifest, msha, true);
if (baseSha !== undefined && baseSha !== msha) fail("base_version_conflict", "le manifeste a changé depuis sa lecture (empreinte " + msha + ") ; rien n'a été écrit");
if (entry.status !== "draft") fail("status_invalid", "la version " + version + " est " + entry.status + " : ajoutez une nouvelle version au lieu de la rétablir");
const current = authoritativeOf(manifest);
if (current && current.version > version) fail("status_invalid", "la version " + current.version + " fait foi et est plus récente : ajoutez une nouvelle version");
await readVersionFile(entry, true);
const at = nowIso();
const versions = manifest.versions.map((e) => {
  if (e.version === version) return {...e, status: "authoritative", supersedes: current ? current.version : null, authoritative_at: at, ...(approvedBy ? {approved_by: approvedBy} : {})};
  if (current && e.version === current.version) return {...e, status: "superseded", superseded_by: version, superseded_at: at};
  return e;
});
const next = {schema: MANIFEST_SCHEMA, doc_id: id, versions, history: manifest.history.concat([{at, action: "marked_authoritative", version, supersedes: current ? current.version : null, ...(approvedBy ? {approved_by: approvedBy} : {}), note: "confirmation manuelle donnée"}])};
const written = await writeManifest(id, next, raw);
return versionSummary(id, versions[version - 1], next, written, false);
'''


BROKER_LIB = r"""
const NAMESPACE = "cib-documents";

function brokerItem(response, id) {
  const payload = response && response.data ? response.data : response;
  const item = payload && payload.record;
  if (!isObject(item) || item.namespace !== NAMESPACE || item.key !== id) fail("broker_record_identity_invalid");
  if (!Number.isSafeInteger(item.revision) || item.revision < 0) fail("broker_revision_invalid");
  const p = item.permissions;
  if (!isObject(p) || typeof p.can_read !== "boolean" || typeof p.can_write !== "boolean" || typeof p.can_manage !== "boolean") fail("broker_permissions_invalid");
  return item;
}
function brokerView(item) {
  const p = item.permissions;
  const shares = Array.isArray(item.shares) ? item.shares : [];
  return {record: isObject(item.data) ? item.data : null, revision: item.revision, owner_user_id: typeof item.owner_user_id === "string" ? item.owner_user_id : "", permissions: p, permissions_summary: "Lecture : " + (p.can_read ? "oui" : "non") + " · Modification : " + (p.can_write ? "oui" : "non") + " · Partage : " + (p.can_manage ? "oui" : "non"), shares, share_count: shares.length};
}
"""

SHARE_IO = r"""
async function readIssuedRecord(id) {
  let raw;
  try {
    const r = await callTool("read_file", {path: ROOT + "/docs/" + id + "/record.json"});
    raw = typeof r === "string" ? r : (isObject(r) && typeof r.content === "string" ? r.content : (isObject(r) && isObject(r.data) && typeof r.data.content === "string" ? r.data.content : null));
  } catch (e) {
    const message = String(e && e.message);
    if (/not found|does not exist|no such/i.test(message)) fail("document_not_found", id);
    fail("storage_unavailable", message.slice(0, 200));
  }
  if (raw === null) fail("storage_read_failed", id);
  let rec;
  try { rec = JSON.parse(raw); } catch (e) { fail("record_corrupt", id); }
  return checkRecord(rec, id);
}
"""

SHARE_CODE = r"""
const input = {{ json . }};
requireConfirmation(input);
const id = docIdOf(input.doc_id);
let expected = input.expected_revision;
if (expected === undefined || expected === null || expected === "") expected = 0;
if (typeof expected === "string" && /^[0-9]+$/.test(expected)) expected = Number(expected);
if (!Number.isSafeInteger(expected) || expected < 0) fail("expected_revision_invalid");
const subject = input.share_subject_user_id === undefined || input.share_subject_user_id === null ? "" : input.share_subject_user_id;
if (typeof subject !== "string" || subject.length > 256 || /[\/\s]/.test(subject)) fail("subject_user_id_invalid");
const permission = input.share_permission === undefined || input.share_permission === null || input.share_permission === "" ? "read" : input.share_permission;
if (!["read", "none"].includes(permission)) fail("permission_invalid", "lecture ou retrait seulement");
if (permission === "none" && !subject) fail("subject_user_id_required", "indiquez le membre dont retirer l'accès");
let revision = expected;
let item = null;
if (permission !== "none") {
  const rec = await readIssuedRecord(id);
  if (MESSAGE_KEYS.includes(rec.template_key)) fail("not_applicable_to_message", "la référence partagée désigne un PDF : un message émis ne se partage pas");
  if (rec.status !== "issued" || !isObject(rec.issued) || !isObject(rec.issued.file) || typeof rec.issued.file.path !== "string" || typeof rec.issued.file.sha256 !== "string") fail("status_invalid", "seul un document émis se partage (statut actuel : " + rec.status + ")");
  const data = {schema: "document-studio.shared/v1", doc_id: rec.doc_id, title: String(rec.title || ""), template_key: rec.template_key, number: rec.number, version: rec.revision, path: rec.issued.file.path, sha256: rec.issued.file.sha256, issued_at: rec.issued.at};
  item = brokerItem(await callTool("recipe--application_data_v1", {operation: "save", namespace: NAMESPACE, record_key: id, data, expected_revision: expected}), id);
  revision = item.revision;
}
if (subject) {
  if (revision < 1) fail("expected_revision_invalid", "révision du record partagé requise pour retirer un accès");
  item = brokerItem(await callTool("recipe--application_data_v1", {operation: "share", namespace: NAMESPACE, record_key: id, expected_revision: revision, subject_user_id: subject.trim(), permission}), id);
}
const view = brokerView(item);
return {...view, doc_id: id, shared_with: subject ? subject.trim() : "", message: subject ? "Partage mis à jour par le broker natif. Partager un document ne donne pas accès au service." : (view.share_count > 0 ? "Référence du document republiée ; partagée avec " + view.share_count + " membre(s), partages inchangés." : "Référence du document publiée, visible de son propriétaire seul tant qu'aucun membre n'est ajouté."), external_effect: false};
"""

READ_CODE = r"""
const input = {{ json . }};
const wantPdf = (() => {
  const v = input.include_pdf;
  if (v === undefined || v === null || v === "" || v === false || v === "non" || v === "false") return false;
  if (v === true || v === "oui" || v === "true") return true;
  return fail("include_pdf_invalid", "oui ou non attendu");
})();
const MAX_PDF_BYTES = 5 * 1024 * 1024;
if (input.doc_id === undefined || input.doc_id === null || input.doc_id === "") {
  if (wantPdf) fail("include_pdf_requires_doc_id", "indiquez le document dont lire le PDF");
  const response = await callTool("recipe--application_data_v1", {operation: "list", namespace: NAMESPACE, prefix: ""});
  const payload = response && response.data ? response.data : response;
  if (!payload || !Array.isArray(payload.items) || !Number.isSafeInteger(payload.total) || payload.total !== payload.items.length) fail("broker_list_invalid");
  const items = payload.items.map((view) => {
    const key = typeof view.record_key === "string" ? view.record_key : view.key;
    if (typeof key !== "string" || !ID_RE.test(key)) fail("broker_list_key_invalid");
    const d = isObject(view.data) ? view.data : (isObject(view.record) ? view.record : {});
    return {doc_id: key, title: d.title === undefined ? "" : d.title, template_key: d.template_key === undefined ? "" : d.template_key, number: d.number === undefined ? "" : d.number, version: d.version === undefined ? null : d.version, path: d.path === undefined ? "" : d.path, sha256: d.sha256 === undefined ? "" : d.sha256, revision: view.revision, owner_user_id: typeof view.owner_user_id === "string" ? view.owner_user_id : "", permissions: isObject(view.permissions) ? view.permissions : {}};
  });
  return {items, total: payload.total, record: null, revision: null, owner_user_id: "", permissions: null, permissions_summary: "", shares: [], share_count: 0, pdf_base64: null, pdf_sha256: null, pdf_bytes: null};
}
const id = docIdOf(input.doc_id);
const item = brokerItem(await callTool("recipe--application_data_v1", {operation: "read", namespace: NAMESPACE, record_key: id}), id);
if (!isObject(item.data)) fail("broker_record_data_invalid");
const out = {...brokerView(item), items: [], total: 1, pdf_base64: null, pdf_sha256: null, pdf_bytes: null};
if (wantPdf) {
  // Only after the broker read succeeded: the ACL of the record, not the Storage rights of the member, opens the PDF.
  const path = item.data.path;
  const prefix = ROOT + "/docs/" + id + "/issued/";
  if (typeof path !== "string" || !path.startsWith(prefix) || path.length > 300 || path.includes("..") || path.includes("//") || path.slice(prefix.length).includes("/") || !path.endsWith(".pdf")) fail("invalid_path", "le PDF doit être un document émis de " + ROOT);
  if (typeof item.data.sha256 !== "string" || !/^[0-9a-f]{64}$/.test(item.data.sha256)) fail("broker_record_data_invalid", "empreinte absente");
  let r;
  try { r = await callTool("read_file", {path, encoding: "base64"}); } catch (e) { fail("storage_unavailable", String(e && e.message).slice(0, 200)); }
  if (isObject(r) && isObject(r.data) && r.content === undefined) r = r.data;
  const encoded = typeof r === "string" ? r : (isObject(r) && typeof r.content === "string" ? r.content : null);
  if (encoded === null) fail("storage_read_failed", path);
  const clean = encoded.replace(/\s+/g, "");
  if (clean.length > Math.ceil(MAX_PDF_BYTES / 3) * 4) fail("pdf_too_large", "au plus 5 Mio");
  const bytes = b64ToBytes(clean);
  if (bytes.length > MAX_PDF_BYTES) fail("pdf_too_large", "au plus 5 Mio");
  const sha = await sha256Hex(bytes);
  if (sha !== item.data.sha256) fail("pdf_integrity_failed", "l'empreinte du PDF lu ne correspond pas au record partagé");
  out.pdf_base64 = clean; out.pdf_sha256 = sha; out.pdf_bytes = bytes.length;
}
return out;
"""


def code(*parts):
    body = ''.join(parts)
    assert '{{' not in body.replace('{{ json . }}', ''), 'a double-brace sequence in the JavaScript'
    return body


def node(action_id, source, output_key, tools=None):
    data = {'id': action_id, 'type': 'code_execution'}
    if tools:
        data['context'] = {'allowed_tools': tools}
    data.update({'code': source, 'output_key': output_key})
    return data


def lib(*, templates=None, io=False, profile=False, render=False, numbering=False, load_profile=False, versions=False):
    parts = [IMPORT if io else '']
    if templates is not None:
        parts.append('const TEMPLATES = ' + js_embed(load_templates(templates == 'full')) + ';\nObject.setPrototypeOf(TEMPLATES, null);\n')
    if render:
        parts.append('const I18N = ' + js_embed(I18N) + ';\n')
    # Keys of the templates that declare the message profile (e-mail), read from their manifests by this generator.
    parts.append('const MESSAGE_KEYS = ' + json.dumps(message_keys()) + ';\n')
    parts.append(CORE)
    if profile:
        parts.append(PROFILE)
    if io:
        parts.append(IO)
    if load_profile:
        parts.append(PROFILE_LOAD)
    if render:
        parts.append(RENDER)
    if numbering:
        parts.append(NUMBERING)
    if versions:
        parts.append(VERSIONS)
    return ''.join(parts)


def text(description, **extra):
    return {'type': 'string', 'description': description, **extra}


def schema(required, **props):
    return {'type': 'object', 'required': required, 'additionalProperties': False, 'properties': props}


DOC_ID = text('Document identifier: lowercase letters, digits and hyphens', pattern='^[a-z0-9][a-z0-9-]{0,47}$')
CONFIRM = {'type': ['boolean', 'string'], 'description': 'Manual confirmation: oui (or true) to proceed'}
LOCALE = text('Document language; fr only in V0', enum=['fr'])
TEMPLATE_KEY = text('Template key', enum=list(TEMPLATE_META))
TEMPLATE_OPTIONS = [{'value': key, 'label': meta['label']} for key, meta in TEMPLATE_META.items()]
SUMMARY_OUT = {'doc_id': '{{ result.doc_id }}', 'template_key': '{{ result.template_key }}', 'title': '{{ result.title }}',
               'status': '{{ result.status }}', 'number': '{{ result.number }}', 'revision': '{{ result.revision }}',
               'renders': '{{ result.renders }}', 'last_render': '{{ result.last_render }}', 'issued': '{{ result.issued }}'}
CONFIRM_FIELD = {'name': 'confirmation_manuelle', 'title': 'Confirmation manuelle', 'type': 'select', 'required': True,
                 'options': [{'value': 'non', 'label': 'Non'}, {'value': 'oui', 'label': 'Oui'}], 'default': 'non'}


def workflow(workflow_id, title, description, input_schema, actions, output, forms=None):
    data = {'$schema': 'agentmaurice.workflow/v2', 'schema_version': 2, 'workflow_id': workflow_id, 'kind': 'workflow',
            'title': title, 'version': '1', 'description': description, 'input_schema': input_schema}
    if forms:
        data['forms'] = forms
    data.update({'actions': actions, 'output': output})
    dump(DEST / 'workflows' / f'{workflow_id}.json', data)
    return data


def form(form_id, title, fields, actions):
    return {'id': form_id, 'title': title, 'fields': fields, 'actions_on_submit': actions}


def field(name, title, kind, required, **extra):
    return {'name': name, 'title': title, 'type': kind, 'required': required, **extra}


def llm(action_id, prompt_ref, system, output_key, tokens):
    return {'id': action_id, 'type': 'llm_call', 'llm_prompt': prompt_ref, 'llm_system_prompt': system,
            'llm_temperature': 0.2, 'llm_max_tokens': tokens, 'llm_response_format': 'text',
            'output_key': output_key}


SYSTEM = 'Tu es un assistant de rédaction de documents professionnels. Tu réponds uniquement par un objet JSON, sans texte autour.'

PLAN_PREPARE = r'''
const input = {{ json . }};
const brief = text(input.brief, "brief", 8000, true);
let key = null;
if (input.template_key !== undefined && input.template_key !== null && input.template_key !== "") { key = input.template_key; if (!TEMPLATES[key]) fail("template_unknown", String(key)); }
const locale = input.locale || "fr";
if (locale !== "fr") fail("locale_unsupported", "seul fr est disponible en V0");
const catalogue = Object.keys(TEMPLATES).map((k) => ({template_key: k, title: TEMPLATES[k].title, summary: TEMPLATES[k].summary, data_schema: TEMPLATES[k].draft_schema}));
const prompt = "Brief du demandeur :\n" + brief + "\n\n" + (key ? "Gabarit imposé : " + key + "\n\n" : "") + "Gabarits disponibles (avec le schéma JSON des données attendues) :\n" + JSON.stringify(catalogue) + "\n\nChoisis le gabarit adapté, propose un titre court et liste ce qui manque dans le brief pour remplir toutes les données requises du schéma. Ne remplis aucune donnée. Réponds par un objet JSON : {\"template_key\": string, \"title\": string, \"missing\": [string], \"questions\": [string]}. \"missing\" nomme les données absentes, \"questions\" les formule en questions au demandeur, en français.";
return {prompt, template_key: key, locale};
'''
PLAN_NORMALIZE = r'''
const input = {{ json . }};
const prep = input.prep;
const out = parseJsonValue(input.plan_draft);
if (!isObject(out)) fail("llm_output_invalid", "objet attendu");
if (out.template_key !== undefined && out.template_key !== null && typeof out.template_key !== "string") fail("llm_output_invalid", "template_key doit être une chaîne");
const key = prep.template_key || out.template_key;
if (typeof key !== "string" || !TEMPLATES[key]) fail("template_unknown", String(key));
const list = (v, name) => {
  if (v === undefined || v === null) return [];
  if (!Array.isArray(v) || !v.every((x) => typeof x === "string")) fail("llm_output_invalid", name + " doit être un tableau de chaînes");
  return v.filter((x) => x.trim()).map((x) => x.trim().slice(0, 300)).slice(0, 20);
};
if (out.title !== undefined && out.title !== null && typeof out.title !== "string") fail("llm_output_invalid", "title doit être une chaîne");
const title = typeof out.title === "string" && out.title.trim() ? out.title.trim().slice(0, 120) : TEMPLATES[key].title;
return {template_key: key, title, locale: prep.locale, missing: list(out.missing, "missing"), questions: list(out.questions, "questions")};
'''

DRAFT_PREPARE = r'''
const input = {{ json . }};
const brief = text(input.brief, "brief", 8000, true);
const key = input.template_key;
if (typeof key !== "string" || !TEMPLATES[key]) fail("template_unknown", String(key));
const locale = input.locale || "fr";
if (locale !== "fr") fail("locale_unsupported", "seul fr est disponible en V0");
if (input.doc_id !== undefined && input.doc_id !== null && input.doc_id !== "") docIdOf(input.doc_id);
if (input.answers !== undefined && input.answers !== null && !isObject(input.answers)) fail("answers_invalid", "objet attendu");
rejectUnsafeKeys(input.answers, "answers");
const prompt = "Brief du demandeur :\n" + brief + "\n\n" + (input.answers && Object.keys(input.answers).length ? "Réponses complémentaires du demandeur :\n" + JSON.stringify(input.answers) + "\n\n" : "") + "Date du jour : " + today() + ".\n\nRemplis les données du document \"" + key + "\" selon ce schéma JSON :\n" + JSON.stringify(TEMPLATES[key].draft_schema) + "\n\nRègles : réponds par l'objet de données seul, conforme au schéma. N'invente ni client, ni prix, ni date, ni participant : si une donnée requise manque, réponds uniquement {\"missing\": [\"description de ce qui manque\"]}. Ne calcule aucun total ni montant TTC. Dates au format AAAA-MM-JJ. Texte en français.";
return {prompt, template_key: key, locale};
'''
DRAFT_CREATE = r'''
const input = {{ json . }};
const prep = input.prep;
const key = prep.template_key;
let data = parseJsonValue(input.draft);
if (!isObject(data)) fail("llm_output_invalid", "objet attendu");
if (Array.isArray(data.missing) && data.missing.length) fail("data_missing", data.missing.filter((x) => typeof x === "string").join(" ; "));
let title = typeof input.title === "string" && input.title.trim() ? input.title.trim().slice(0, 120) : "";
const given = input.doc_id !== undefined && input.doc_id !== null && input.doc_id !== "";
const id = given ? docIdOf(input.doc_id) : slugify(title || fallbackTitle(key, data)) + "-" + shortSuffix();
data = normalizeData(key, data, id);
if (!title) title = documentTitle(key, data);
title = title.slice(0, 120);
const at = nowIso();
const rec = {schema: "document-studio.record/v1", doc_id: id, template_key: key, template_version: TEMPLATES[key].manifest.version, title, locale: prep.locale, status: "draft", number: null, revision: 1, data, history: [{at, action: "created", note: "brouillon créé depuis un brief"}], renders: [], issued: null};
try { await writeJson(recordPath(id), rec, false); } catch (e) { fail("document_create_failed", id + " : " + String(e && e.message)); }
return {...summarize(rec), data, computed: templateData(key, data)};
'''

RENDER_CODE = r'''
const input = {{ json . }};
const id = docIdOf(input.doc_id);
const rec = await loadRecord(id);
if (rec.status === "issued" || rec.status === "cancelled") fail("document_locked", "un document " + (rec.status === "issued" ? "émis" : "annulé") + " ne se rend plus");
let data = rec.data;
if (input.data_patch !== undefined && input.data_patch !== null) {
  if (!isObject(input.data_patch)) fail("data_patch_invalid", "objet attendu");
  rejectUnsafeKeys(input.data_patch, "data_patch");
  data = {...rec.data, ...input.data_patch};
}
data = normalizeData(rec.template_key, data, id);
const profile = await loadProfile();
const revision = rec.revision + 1;
let res, file, files = null, previews, what;
if (MESSAGE_KEYS.includes(rec.template_key)) {
  const results = await renderMessage(rec, data, profile, "preview", null, "draft", revision);
  res = results[messagePrimary(rec.template_key)];
  files = await storeMessage(ROOT + "/docs/" + id + "/r" + revision + "-" + attemptTag(res.file) + "/document", results);
  file = files[messagePrimary(rec.template_key)];
  previews = [];
  what = Object.keys(files).join("+");
} else {
  res = await renderDocument(rec, data, profile, "preview", null, "draft", revision);
  const dir = ROOT + "/docs/" + id + "/r" + revision + "-" + attemptTag(res.file);
  file = await storeFile(dir + "/document.pdf", res.file);
  previews = await storePreviews(dir, res);
  what = (Number.isInteger(res.pages) ? res.pages : previews.length) + " page(s)";
}
const at = nowIso();
if (rec.status === "approved") rec.history.push({at, action: "reopened", note: "nouveau rendu : l'approbation est à renouveler"});
rec.history.push({at, action: "rendered", note: "r" + revision + ", " + what});
rec.status = "draft";
rec.data = data;
rec.revision = revision;
const entry = {revision, mode: "preview", profile_sha256: await fingerprint(profile), data_sha256: await fingerprint(data), file, previews, provenance: res.provenance === undefined ? null : res.provenance};
if (files) entry.files = files;
rec.renders.push(entry);
await saveRecord(rec);
return {...summarize(rec), profile_source: PROFILE_SOURCE};
'''

FINALIZE_CODE = r'''
const input = {{ json . }};
requireConfirmation(input);
const id = docIdOf(input.doc_id);
const rec = await loadRecord(id);
if (rec.status !== "draft") fail("status_invalid", "seul un brouillon s'approuve (statut actuel : " + rec.status + ")");
const last = rec.renders.length ? rec.renders[rec.renders.length - 1] : null;
if (!last || last.revision !== rec.revision) fail("render_required", "rendez la révision courante avant de l'approuver");
rec.status = "approved";
rec.revision += 1;
rec.history.push({at: nowIso(), action: "approved", note: "rendu r" + last.revision + " approuvé"});
await saveRecord(rec);
return summarize(rec);
'''

PUBLISH_CODE = r'''
const input = {{ json . }};
requireConfirmation(input);
const id = docIdOf(input.doc_id);
const rec = await loadRecord(id);
if (rec.status !== "approved") fail("status_invalid", "seul un document approuvé s'émet (statut actuel : " + rec.status + ")");
const profile = await loadProfile();
// What was approved is what is issued: the last render carries the fingerprints of its brand and data.
const approved = rec.renders.length ? rec.renders[rec.renders.length - 1] : null;
if (!approved || typeof approved.profile_sha256 !== "string" || typeof approved.data_sha256 !== "string") fail("render_outdated", "ce rendu ne porte pas d'empreintes : rendez et approuvez à nouveau");
if (approved.profile_sha256 !== await fingerprint(profile)) fail("profile_changed", "la charte a changé depuis le rendu approuvé : rendez et approuvez à nouveau");
if (approved.data_sha256 !== await fingerprint(normalizeData(rec.template_key, rec.data, id))) fail("data_changed", "les données ont changé depuis le rendu approuvé : rendez et approuvez à nouveau");
if (rec.number) {
  // A number reserved in a previous year is abandoned, never reused: a new one is reserved in the current year.
  const m = /^[A-Z]+-(\d{4})-\d+$/.exec(String(rec.number));
  if (!m || Number(m[1]) !== clock().getUTCFullYear()) {
    rec.history.push({at: nowIso(), action: "number_abandoned", note: String(rec.number)});
    rec.number = null;
  } else {
    // The token must still name this document: the reservation is not atomic, so it is read back on every retry.
    const seqm = /-(\d{4,})$/.exec(String(rec.number));
    let token = null;
    try { token = await readJson(ROOT + "/numbers/" + rec.template_key + "/" + m[1] + "/" + seqm[1] + ".json"); }
    catch (e) { if (!String(e && e.message).startsWith("storage_not_found") && !String(e && e.message).startsWith("json_corrupt")) throw e; }
    if (!isObject(token) || token.doc_id !== rec.doc_id) {
      rec.history.push({at: nowIso(), action: "number_abandoned", note: String(rec.number) + " (jeton d'un autre document)"});
      rec.number = null;
    }
  }
}
if (!rec.number) {
  rec.number = await reserveNumber(rec);
  rec.revision += 1;
  rec.history.push({at: nowIso(), action: "number_reserved", note: rec.number});
  await saveRecord(rec);
}
const data = normalizeData(rec.template_key, rec.data, id);
const revision = rec.revision + 1;
const dir = ROOT + "/docs/" + id;
let res, file, files = null, previews;
if (MESSAGE_KEYS.includes(rec.template_key)) {
  // Issuing a message numbers and freezes its files; it sends nothing.
  const results = await renderMessage(rec, data, profile, "final", rec.number, "issued", revision);
  res = results[messagePrimary(rec.template_key)];
  files = await storeMessage(dir + "/issued/" + rec.number + "-" + attemptTag(res.file), results);
  file = files[messagePrimary(rec.template_key)];
  previews = [];
} else {
  res = await renderDocument(rec, data, profile, "final", rec.number, "issued", revision);
  file = await storeFile(dir + "/issued/" + rec.number + "-" + attemptTag(res.file) + ".pdf", res.file);
  previews = await storePreviews(dir + "/r" + revision + "-" + attemptTag(res.file), res);
}
const at = nowIso();
rec.status = "issued";
rec.revision = revision;
const entry = {revision, mode: "final", profile_sha256: approved.profile_sha256, data_sha256: approved.data_sha256, file, previews, provenance: res.provenance === undefined ? null : res.provenance};
if (files) entry.files = files;
rec.renders.push(entry);
rec.issued = {number: rec.number, file: {path: file.path, sha256: file.sha256}, at};
if (files) rec.issued.files = Object.fromEntries(Object.entries(files).map(([o, f]) => [o, {path: f.path, sha256: f.sha256}]));
rec.history.push({at, action: "issued", note: rec.number});
await saveRecord(rec);
return {...summarize(rec), profile_source: PROFILE_SOURCE};
'''

CANCEL_CODE = r'''
const input = {{ json . }};
requireConfirmation(input);
const id = docIdOf(input.doc_id);
const reason = text(input.reason, "reason", 500, true);
const rec = await loadRecord(id);
if (rec.status === "cancelled") fail("status_invalid", "document déjà annulé");
rec.status = "cancelled";
rec.revision += 1;
rec.history.push({at: nowIso(), action: "cancelled", note: reason});
await saveRecord(rec);
return summarize(rec);
'''

EXPORT_CODE = r'''
const input = {{ json . }};
const id = docIdOf(input.doc_id);
const dest = input.destination_path;
if (typeof dest !== "string" || !dest.startsWith("/") || dest.length > 300 || dest.includes("..") || dest.includes("//") || /\s$/.test(dest) || dest.endsWith("/")) fail("destination_invalid", "chemin Storage absolu attendu");
if (dest === ROOT || dest.startsWith(ROOT + "/")) fail("destination_invalid", "la destination doit être hors de " + ROOT);
const rec = await loadRecord(id);
if (rec.status === "cancelled") fail("document_cancelled", "un document annulé ne s'exporte pas");
const last = rec.renders.length ? rec.renders[rec.renders.length - 1] : null;
// A message record carries one file per output (html, txt, eml); any other record carries one PDF.
const files = rec.issued && isObject(rec.issued.files) ? rec.issued.files : (!rec.issued && last && isObject(last.files) ? last.files : null);
const format = input.format === undefined || input.format === null || input.format === "" ? (files ? "eml" : "pdf") : input.format;
if (!["pdf", "html", "txt", "eml"].includes(format)) fail("format_invalid", String(format));
if (!files && format !== "pdf") fail("format_not_applicable", "seul un message s'exporte en html, txt ou eml");
if (files && format === "pdf") fail("format_not_applicable", "un message n'a pas de PDF : html, txt ou eml");
if (files && !isObject(files[format])) fail("format_unavailable", "ce message n'a pas de fichier " + format);
const source = files ? files[format] : (rec.issued ? rec.issued.file : (last ? last.file : null));
if (!source) fail("no_render", "aucun rendu à exporter");
const encoded = await readText(source.path, {encoding: "base64"});
const bytes = b64ToBytes(encoded.replace(/\s+/g, ""));
const sha = await sha256Hex(bytes);
if (sha !== source.sha256) fail("export_integrity_failed", "l'empreinte du fichier lu ne correspond pas au rendu");
await callTool("write_file", {path: dest, content: encoded.replace(/\s+/g, ""), encoding: "base64", overwrite: false});
return {doc_id: id, destination_path: dest, source_path: source.path, format, sha256: sha, bytes: bytes.length, draft: !rec.issued, warning: rec.issued ? "" : "document non émis : copie du dernier rendu, marquée brouillon"};
'''

PROFILE_SAVE_CODE = r'''
const input = {{ json . }};
requireConfirmation(input);
const body = normalizeProfile(input.profile);
await callTool("write_file", {path: ROOT + "/profile.json", content: JSON.stringify(body, null, 2) + "\n", overwrite: true});
return {path: ROOT + "/profile.json", legal_name: body.company.legal_name, colors: body.brand.colors, message: "Charte enregistrée dans Storage."};
'''

LIST_CODE = r'''
const input = {{ json . }};
if (input.status !== undefined && input.status !== null && input.status !== "" && !STATUSES.includes(input.status)) fail("status_invalid", String(input.status));
const paths = await listPaths(ROOT + "/docs");
const ids = [];
for (const p of paths) { const m = /document-studio\/docs\/([a-z0-9][a-z0-9-]{0,47})(?:\/|$)/.exec(p); if (m && !ids.includes(m[1])) ids.push(m[1]); }
if (ids.length > 1000) fail("too_many_documents", "plus de 1000 documents : archivez");
const items = [];
for (const id of ids.sort()) {
  let rec;
  try { rec = await loadRecord(id); } catch (e) { if (String(e && e.message).startsWith("document_not_found")) continue; throw e; }
  if (input.status && rec.status !== input.status) continue;
  if (input.template_key && rec.template_key !== input.template_key) continue;
  const s = summarize(rec);
  items.push({doc_id: s.doc_id, title: s.title, template_key: s.template_key, status: s.status, number: s.number, revision: s.revision, sha256: s.issued ? s.issued.file.sha256 : (s.last_render ? s.last_render.sha256 : null)});
}
const total = items.length;
return {count: Math.min(total, 200), total, truncated: total > 200, items: items.slice(0, 200)};
'''

REVIEW_CODE = r'''
const input = {{ json . }};
const id = docIdOf(input.doc_id);
const rec = await loadRecord(id);
const last = rec.renders.length ? rec.renders[rec.renders.length - 1] : null;
// A message shows its plain text (txt, read back and checked against the fingerprint) and the paths of its files, never its HTML.
let body = "", files = {};
if (last && isObject(last.files)) {
  files = Object.fromEntries(Object.entries(last.files).map(([o, f]) => [o, {path: f.path, sha256: f.sha256, bytes: f.bytes}]));
  if (isObject(last.files.txt)) {
    const bytes = b64ToBytes((await readText(last.files.txt.path, {encoding: "base64"})).replace(/\s+/g, ""));
    if (bytes.length > 1048576) fail("message_text_too_large", "1 Mio au plus");
    if (await sha256Hex(bytes) !== last.files.txt.sha256) fail("render_integrity_failed", last.files.txt.path + " : empreinte différente de celle enregistrée");
    body = new TextDecoder().decode(bytes);
  }
}
return {doc_id: id, title: rec.title, template_key: rec.template_key, status: rec.status, number: rec.number === null ? "" : rec.number, revision: rec.revision, pages: last ? last.previews.length : 0, previews: last ? last.previews : [], files, text: body, renders: rec.renders.map((r) => ({revision: r.revision, mode: r.mode, sha256: r.file.sha256, path: r.file.path})), history: rec.history, issued: rec.issued, record: rec};
'''

TEMPLATE_READ_CODE = r'''
const input = {{ json . }};
if (input.template_key === undefined || input.template_key === null || input.template_key === "") {
  return {templates: Object.keys(TEMPLATES).map((k) => ({template_key: k, title: TEMPLATES[k].title, version: TEMPLATES[k].manifest.version, prefix: TEMPLATES[k].prefix, summary: TEMPLATES[k].summary})), template: null};
}
const tpl = TEMPLATES[input.template_key];
if (!tpl) fail("template_unknown", String(input.template_key));
return {templates: [], template: {template_key: input.template_key, title: tpl.title, version: tpl.manifest.version, prefix: tpl.prefix, summary: tpl.summary, manifest: tpl.manifest, input_schema: tpl.input_schema, draft_schema: tpl.draft_schema}};
'''


def build():
    out_summary = dict(SUMMARY_OUT)
    workflow('document-studio-plan', 'Plan a document',
             'Chooses the template for a brief, proposes a title and lists the missing data with questions. Writes nothing.',
             schema(['brief'], brief=text('Brief of the document'), template_key=TEMPLATE_KEY, locale=LOCALE),
             [node('prepare', code(lib(templates='meta'), PLAN_PREPARE), 'prep'),
              llm('plan-llm', '{{ prep.prompt }}', SYSTEM, 'plan_draft', 2000),
              node('normalize', code(lib(templates='meta'), PLAN_NORMALIZE), 'result')],
             {'template_key': '{{ result.template_key }}', 'title': '{{ result.title }}', 'missing': '{{ result.missing }}',
              'questions': '{{ result.questions }}'},
             forms=[form('plan', 'Planifier un document', [
                 field('brief', 'Brief', 'text', True), field('template_key', 'Gabarit (facultatif)', 'select', False, options=TEMPLATE_OPTIONS)],
                 ['prepare', 'plan-llm', 'normalize'])])

    workflow('document-studio-draft', 'Draft a document',
             'Fills the data of a template from a brief (model call, then strict validation; quote totals are computed '
             'here from the lines) and creates the record in Storage with status draft. Nothing is rendered yet.',
             schema(['brief', 'template_key'], brief=text('Brief of the document'), template_key=TEMPLATE_KEY,
                    title=text('Document title; derived from the data when absent'), doc_id=DOC_ID,
                    answers={'type': 'object', 'description': 'Answers to the questions of the plan'}, locale=LOCALE),
             [node('prepare', code(lib(templates='meta'), DRAFT_PREPARE), 'prep'),
              llm('draft-llm', '{{ prep.prompt }}', SYSTEM, 'draft', 6000),
              node('create', code(lib(templates='meta', io=True), DRAFT_CREATE), 'result', tools=STORAGE_TOOLS)],
             {**out_summary, 'data': '{{ result.data }}', 'computed': '{{ result.computed }}'},
             forms=[form('draft', 'Rédiger un brouillon', [
                 field('brief', 'Brief', 'text', True),
                 field('template_key', 'Gabarit', 'select', True, options=TEMPLATE_OPTIONS),
                 field('title', 'Titre (facultatif)', 'string', False), field('doc_id', 'Identifiant (facultatif)', 'string', False)],
                 ['prepare', 'draft-llm', 'create'])])

    workflow('document-studio-render', 'Render a document preview',
             'Renders the current data with the company profile through the artifact tool (mode preview), stores the PDF '
             'and its page previews in Storage and appends a revision. An e-mail template (message profile) renders html, txt and eml '
             'instead (three engine calls, each file stored and read back, no page preview, nothing sent). An issued or cancelled document is locked.',
             schema(['doc_id'], doc_id=DOC_ID, data_patch={'type': 'object', 'description': 'Shallow merge into the draft data, then revalidated'}),
             [node('render', code(lib(templates='full', io=True, profile=True, render=True, load_profile=True), RENDER_CODE), 'result', tools=RENDER_TOOLS + [BROKER])],
             {**out_summary, 'profile_source': '{{ result.profile_source }}'},
             forms=[form('render', 'Nouveau rendu', [field('doc_id', 'Identifiant du document', 'string', True)], ['render'])])

    workflow('document-studio-finalize', 'Approve a document',
             'Moves a rendered draft to approved. Requires a render of the current revision and a manual confirmation.',
             schema(['doc_id', 'confirmation_manuelle'], doc_id=DOC_ID, confirmation_manuelle=CONFIRM),
             [node('finalize', code(lib(io=True), FINALIZE_CODE), 'result', tools=STORAGE_TOOLS)],
             out_summary,
             forms=[form('approve', 'Approuver un document', [field('doc_id', 'Identifiant du document', 'string', True), CONFIRM_FIELD], ['finalize'])])

    workflow('document-studio-publish', 'Issue a document',
             'Reserves the next number of the template for the year, renders the final PDF (mode final) and stores it as the '
             'issued file (an e-mail template issues its html, txt and eml files; nothing is sent). Requires an approved document '
             'and a manual confirmation. The reservation is not atomic.',
             schema(['doc_id', 'confirmation_manuelle'], doc_id=DOC_ID, confirmation_manuelle=CONFIRM),
             [node('publish', code(lib(templates='full', io=True, profile=True, render=True, numbering=True, load_profile=True), PUBLISH_CODE), 'result', tools=RENDER_TOOLS + [BROKER])],
             {**out_summary, 'profile_source': '{{ result.profile_source }}'},
             forms=[form('issue', 'Émettre un document', [field('doc_id', 'Identifiant du document', 'string', True), CONFIRM_FIELD], ['publish'])])

    workflow('document-studio-cancel', 'Cancel a document',
             'Marks a document cancelled with a reason. An issued number is never reused.',
             schema(['doc_id', 'confirmation_manuelle', 'reason'], doc_id=DOC_ID, confirmation_manuelle=CONFIRM, reason=text('Reason of the cancellation')),
             [node('cancel', code(lib(io=True), CANCEL_CODE), 'result', tools=STORAGE_TOOLS)],
             out_summary,
             forms=[form('cancel', 'Annuler un document', [field('doc_id', 'Identifiant du document', 'string', True),
                                                           field('reason', 'Motif', 'text', True), CONFIRM_FIELD], ['cancel'])])

    workflow('document-studio-export', 'Export a document',
             'Copies the issued PDF (or the last render, flagged as a draft) to a Storage path outside /document-studio/. '
             'An e-mail document exports its eml (default), html or txt file. Sending by mail or SFTP is out of scope.',
             schema(['doc_id', 'destination_path'], doc_id=DOC_ID, destination_path=text('Absolute Storage path of the copy, outside /document-studio/'),
                    format=text('E-mail documents only: file to copy, eml (default), html or txt', enum=['eml', 'html', 'txt'])),
             [node('export', code(lib(io=True), EXPORT_CODE), 'result', tools=STORAGE_TOOLS)],
             {'doc_id': '{{ result.doc_id }}', 'destination_path': '{{ result.destination_path }}', 'source_path': '{{ result.source_path }}', 'format': '{{ result.format }}',
              'sha256': '{{ result.sha256 }}', 'bytes': '{{ result.bytes }}', 'draft': '{{ result.draft }}', 'warning': '{{ result.warning }}'},
             forms=[form('export', 'Exporter un document', [field('doc_id', 'Identifiant du document', 'string', True),
                                                            field('destination_path', 'Chemin de destination', 'string', True),
                                                            field('format', 'Format (e-mail : eml, html ou txt)', 'select', False,
                                                                  options=[{'value': 'eml', 'label': 'eml'}, {'value': 'html', 'label': 'html'}, {'value': 'txt', 'label': 'txt'}])], ['export'])])

    VERSION_OUT = {k: '{{ result.%s }}' % k for k in ('doc_id', 'version', 'status', 'supersedes', 'sha256', 'storage_ref', 'redline_ref', 'changes',
                                                       'authoritative_version', 'versions', 'manifest_ref', 'manifest_sha256', 'replayed')}
    INT_OR_STRING = {'type': ['integer', 'string'], 'description': ''}
    workflow('document-studio-new-version', 'Add a DOCX version',
             'Adds a new DOCX version of a document from a Storage file: fingerprints it, compares it with the previous version through '
             'office_compare_v1 (a redline DOCX of tracked changes is stored) and appends it to the per-document versions manifest. '
             'Never modifies an existing version. Not atomic: one writer at a time per document; the write is refused when the base version '
             'or the manifest read is no longer the latest.',
             schema(['doc_id', 'source_path', 'author'], doc_id=DOC_ID,
                    source_path=text('Absolute Storage path of the new DOCX version'),
                    author=text('Author of the version, recorded on the tracked changes'),
                    base_version={**INT_OR_STRING, 'description': 'Version number the request starts from (0 for the first version); refused when it is no longer the latest'},
                    base_manifest_sha256=text('SHA-256 of the manifest as read by the caller; refused when the manifest changed since')),
             [node('new-version', code(lib(io=True, versions=True), NEW_VERSION_CODE), 'result', tools=VERSION_TOOLS)],
             VERSION_OUT,
             forms=[form('new-version', 'Ajouter une version DOCX', [field('doc_id', 'Identifiant du document', 'string', True),
                                                                       field('source_path', 'Chemin Storage du DOCX', 'string', True),
                                                                       field('author', 'Auteur', 'string', True)], ['new-version'])])

    workflow('document-studio-mark-authoritative', 'Mark a version authoritative',
             'Makes a DOCX version the authoritative one (the previous authoritative version becomes superseded). Requires a manual '
             'confirmation. No version is modified or deleted; only the status in the manifest changes.',
             schema(['doc_id', 'version', 'confirmation_manuelle'], doc_id=DOC_ID,
                    version={**INT_OR_STRING, 'description': 'Version number to make authoritative'}, confirmation_manuelle=CONFIRM,
                    approved_by=text('Person who gave the confirmation, recorded as stated (not attested)'),
                    base_manifest_sha256=text('SHA-256 of the manifest as read by the caller; refused when the manifest changed since')),
             [node('mark', code(lib(io=True, versions=True), MARK_AUTHORITATIVE_CODE), 'result', tools=VERSION_TOOLS)],
             VERSION_OUT,
             forms=[form('mark-authoritative', 'Faire foi', [field('doc_id', 'Identifiant du document', 'string', True),
                                                              field('version', 'Numéro de version', 'string', True),
                                                              field('approved_by', 'Confirmé par (facultatif)', 'string', False), CONFIRM_FIELD], ['mark'])])

    workflow('document-studio-profile-save', 'Save the company profile',
             'Validates the profile (company identity and brand tokens of the template contract) and stores it as '
             '/document-studio/profile.json. Requires a manual confirmation.',
             schema(['profile', 'confirmation_manuelle'], profile={'type': 'object', 'description': 'Body {schema_version: 1, company, brand}'},
                    confirmation_manuelle=CONFIRM),
             [node('save', code(lib(io=True, profile=True), PROFILE_SAVE_CODE), 'result', tools=STORAGE_TOOLS)],
             {'path': '{{ result.path }}', 'legal_name': '{{ result.legal_name }}', 'colors': '{{ result.colors }}', 'message': '{{ result.message }}'})

    workflow('document-studio-list', 'List documents',
             'Lists the documents of the studio: identifier, title, status, number, revision and last fingerprint.',
             schema([], status=text('Filter on a status', enum=['draft', 'approved', 'issued', 'cancelled']), template_key=TEMPLATE_KEY),
             [node('list', code(lib(io=True), LIST_CODE), 'result', tools=STORAGE_TOOLS)],
             {'count': '{{ result.count }}', 'total': '{{ result.total }}', 'truncated': '{{ result.truncated }}', 'items': '{{ result.items }}'})

    workflow('document-studio-review-read', 'Read a document for review',
             'Returns the record of a document with the previews of its last render, for the review MiniApp. For an e-mail document it '
             'returns the plain text of the message (txt) and the paths of its html, txt and eml files, never the HTML.',
             schema(['doc_id'], doc_id=DOC_ID),
             [node('read', code(lib(io=True), REVIEW_CODE), 'result', tools=STORAGE_TOOLS)],
             {k: '{{ result.%s }}' % k for k in ('doc_id', 'title', 'template_key', 'status', 'number', 'revision', 'pages', 'previews', 'files', 'text', 'renders', 'history', 'issued', 'record')},
             forms=[form('review', 'Relire un document', [field('doc_id', 'Identifiant du document', 'string', True)], ['read'])])

    workflow('document-studio-template-read', 'Read the templates',
             'Lists the available templates, or returns the manifest and the data schemas of one of them.',
             schema([], template_key=TEMPLATE_KEY),
             [node('read', code(lib(templates='meta'), TEMPLATE_READ_CODE), 'result')],
             {'templates': '{{ result.templates }}', 'template': '{{ result.template }}'})

    workflow('document-share', 'Share an issued document',
             'Publishes the reference of an issued document (identifier, title, type, number, version, Storage path and SHA-256 of '
             'the PDF; an e-mail document is refused, it has no PDF) as a record of the native application data broker, then grants or removes read access for one member. '
             'The PDF stays in Storage. A record is private to its owner until shared; sharing never gives access to the service. '
             'expected_revision is 0 for the first publication, else the revision returned by the previous call.',
             schema(['doc_id', 'confirmation_manuelle'], doc_id=DOC_ID, confirmation_manuelle=CONFIRM,
                    expected_revision={'type': ['integer', 'string'], 'description': '0 (or empty) to create the reference, else the current revision of the shared record'},
                    share_subject_user_id=text('Member to grant or remove; empty to only publish the reference'),
                    share_permission=text('Right of the member', enum=['read', 'none'])),
             [node('share', code(IMPORT, lib(), BROKER_LIB, SHARE_IO, SHARE_CODE), 'result', tools=SHARE_TOOLS)],
             {'doc_id': '{{ result.doc_id }}', 'record': '{{ result.record }}', 'revision': '{{ result.revision }}',
              'owner_user_id': '{{ result.owner_user_id }}', 'permissions': '{{ result.permissions }}',
              'permissions_summary': '{{ result.permissions_summary }}', 'shares': '{{ result.shares }}',
              'share_count': '{{ result.share_count }}', 'shared_with': '{{ result.shared_with }}',
              'message': '{{ result.message }}', 'scope': 'internal_only', 'external_effect': False},
             forms=[form('document-share', 'Partager un document émis', [
                 field('doc_id', 'Identifiant du document', 'string', True),
                 field('expected_revision', 'Révision attendue (0 pour une première publication)', 'string', True, default='0'),
                 field('share_subject_user_id', 'Membre', 'string', False),
                 field('share_permission', 'Droit', 'select', True, options=[{'value': 'read', 'label': 'Lecture'}, {'value': 'none', 'label': 'Retirer'}], default='read'),
                 CONFIRM_FIELD], ['share'])])

    workflow('document-read', 'Read shared documents',
             'Reads, through the native application data broker, the reference of one shared document (with the permissions of the '
             'caller), or lists the references the caller may read when doc_id is empty. Only the rights of the caller apply.',
             schema([], include_pdf={'type': ['boolean', 'string'], 'description': 'oui to also return the issued PDF (base64, 5 MiB at most, checked against the shared sha256); default non'}, doc_id=text('Document identifier; empty (or absent) lists the references the caller may read', pattern='^([a-z0-9][a-z0-9-]{0,47})?$')),
             [node('read', code(IMPORT, lib(), BROKER_LIB, READ_CODE), 'result', tools=['read_file', BROKER])],
             {'record': '{{ result.record }}', 'revision': '{{ result.revision }}', 'owner_user_id': '{{ result.owner_user_id }}',
              'permissions': '{{ result.permissions }}', 'permissions_summary': '{{ result.permissions_summary }}',
              'shares': '{{ result.shares }}', 'share_count': '{{ result.share_count }}', 'items': '{{ result.items }}',
              'total': '{{ result.total }}', 'pdf_base64': '{{ result.pdf_base64 }}', 'pdf_sha256': '{{ result.pdf_sha256 }}',
              'pdf_bytes': '{{ result.pdf_bytes }}'},
             forms=[form('document-read', 'Relire un document partagé', [
                 field('doc_id', 'Identifiant du document (vide pour la liste)', 'string', False),
                 field('include_pdf', 'Joindre le PDF', 'select', False, options=[{'value': 'non', 'label': 'Non'}, {'value': 'oui', 'label': 'Oui'}], default='non')], ['read'])])

    miniapp()
    manifest()


def miniapp():
    data = {
        '$schema': 'agentmaurice.miniapp/v2', 'schema_version': 2, 'miniapp_id': 'document-studio-review', 'kind': 'miniapp',
        'title': 'Document studio', 'version': '1',
        'description': 'Relire un document, relancer un rendu, l\'approuver puis l\'émettre.',
        'ui': {'renderer': 'component', 'component': 'document-studio-review', 'configuration': {'layout': [
            {'type': 'callout', 'title': 'Relecture humaine', 'tone': 'info',
             'value': 'Ouvrez le formulaire « Relire un document » et saisissez l\'identifiant (doc_id) du document : il est chargé ici. Relisez les rendus, puis approuvez et émettez avec une confirmation manuelle. '
                      'Un document émis est verrouillé et son numéro n\'est jamais réutilisé.'},
            {'type': 'button', 'label': 'Actualiser le document', 'on_click': 'load'},
            {'type': 'section', 'title': 'Document', 'children': [
                {'type': 'kpi_grid', 'items': [
                    {'label': 'Statut', 'value': {'state': 'review.status'}},
                    {'label': 'Révision', 'value': {'state': 'review.revision'}},
                    {'label': 'Numéro', 'value': {'state': 'review.number'}},
                    {'label': 'Pages', 'value': {'state': 'review.pages'}}]},
                {'type': 'stat', 'label': 'Titre', 'value': {'state': 'review.title'}},
                {'type': 'text', 'value': {'state': 'review.text'}},
                {'type': 'table', 'columns': ['revision', 'mode', 'sha256', 'path'],
                 'column_labels': {'revision': 'Révision', 'mode': 'Mode', 'sha256': 'Empreinte SHA-256', 'path': 'Chemin'},
                 'rows': {'state': 'review.renders'}}]},
            {'type': 'section', 'title': 'Actions', 'children': [
                {'type': 'button', 'label': 'Nouveau rendu', 'on_click': 'render'},
                {'type': 'text', 'value': 'Approuver et Émettre ouvrent un formulaire de confirmation manuelle dans les interactions disponibles.'},
                {'type': 'text', 'value': {'state': 'result.message'}}]},
        ]}},
        'state_schema': {'type': 'object', 'properties': {
            'doc_id': {'type': 'string'}, 'confirmation_manuelle': {'type': 'string'}, 'review': {'type': 'object'}, 'result': {'type': 'object'}}},
        'initial_state': {'doc_id': '', 'confirmation_manuelle': 'non',
                          'review': {'status': '', 'revision': 0, 'number': '', 'pages': 0, 'title': '', 'text': '', 'renders': []},
                          'result': {'message': 'Aucune action.'}},
        'events': [
            {'event_id': 'load', 'trigger': 'action.click', 'workflow': {'workflow_id': 'document-studio-review-read', 'input': {'doc_id': '{{ state.doc_id }}'}}, 'result_to_state': 'review'},
            {'event_id': 'review', 'trigger': 'form.submit', 'workflow': {'workflow_id': 'document-studio-review-read', 'input': {'doc_id': '{{ state.doc_id }}'}}, 'result_to_state': 'review'},
            {'event_id': 'render', 'trigger': 'action.click', 'workflow': {'workflow_id': 'document-studio-render', 'input': {'doc_id': '{{ state.doc_id }}'}}, 'result_to_state': 'result'},
            {'event_id': 'approve', 'trigger': 'form.submit', 'workflow': {'workflow_id': 'document-studio-finalize', 'input': {'doc_id': '{{ state.doc_id }}', 'confirmation_manuelle': '{{ state.confirmation_manuelle }}'}}, 'result_to_state': 'result'},
            {'event_id': 'issue', 'trigger': 'form.submit', 'workflow': {'workflow_id': 'document-studio-publish', 'input': {'doc_id': '{{ state.doc_id }}', 'confirmation_manuelle': '{{ state.confirmation_manuelle }}'}}, 'result_to_state': 'result'}],
    }
    dump(DEST / 'miniapps' / 'document-studio-review.json', data)


def manifest():
    def ref(key, name):
        return {'key': key, 'name': name, 'workflow_id': key, 'workflow_version': '1'}
    data = {
        '$schema': 'agentmaurice.module/v2', 'schema_version': 2, 'key': 'document-studio', 'name': 'Document studio',
        'version': VERSION,
        'provides': {
            'actions': [ref('document-studio-plan', 'Plan a document'), ref('document-studio-draft', 'Draft a document'),
                        ref('document-studio-render', 'Render a document preview'), ref('document-studio-finalize', 'Approve a document'),
                        ref('document-studio-publish', 'Issue a document'), ref('document-studio-cancel', 'Cancel a document'),
                        ref('document-studio-export', 'Export a document'), ref('document-studio-profile-save', 'Save the company profile'),
                        ref('document-share', 'Share an issued document'),
                        ref('document-studio-new-version', 'Add a DOCX version'), ref('document-studio-mark-authoritative', 'Mark a version authoritative')],
            'queries': [ref('document-studio-list', 'List documents'), ref('document-studio-review-read', 'Read a document for review'),
                        ref('document-studio-template-read', 'Read the templates'), ref('document-read', 'Read shared documents')],
            'apps': [{'key': 'document-studio-review', 'name': 'Document studio', 'miniapp_id': 'document-studio-review',
                      'miniapp_version': '1'}]},
        'requires': {},
    }
    dump(MODULE / 'module.yaml', data)


if __name__ == '__main__':
    build()
