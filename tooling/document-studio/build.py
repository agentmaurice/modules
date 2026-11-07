#!/usr/bin/env python3
"""Generate the document-studio Module resources (manifest, Workflows, MiniApp).

No rendering engine lives in the Module: rendering goes through the MCP tool
`artifact_render_v1`. The two reference templates (quote and
meeting-minutes) are embedded as text in the Workflows that render; they are
the files of document-studio/examples/templates, pinned by contract/PIN.json.
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
VERSION = '0.1.0'
RENDER_TOOL = 'artifact_render_v1'
STORAGE_TOOLS = ['read_file', 'write_file', 'list_files']
RENDER_TOOLS = STORAGE_TOOLS + [RENDER_TOOL]
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
    'quote': {'prefix': 'DEV', 'draft_schema': QUOTE_DRAFT_SCHEMA,
              'summary': 'Devis : client, lignes (description, quantité, unité, prix unitaire HT, taux de TVA), validité, conditions, règlement. Les montants et les totaux sont calculés, jamais saisis.'},
    'meeting-minutes': {'prefix': 'CR', 'draft_schema': None,
                        'summary': 'Compte rendu de réunion : réunion, participants, ordre du jour, décisions, actions (responsable, échéance).'},
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
function today() { return new Date().toISOString().slice(0, 10); }
function nowIso() { return new Date().toISOString(); }
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
function b64ToBytes(b64) { const bin = atob(b64); const out = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i); return out; }
async function sha256Hex(bytes) { const d = await crypto.subtle.digest("SHA-256", bytes); return Array.from(new Uint8Array(d), (x) => x.toString(16).padStart(2, "0")).join(""); }
function parseJsonValue(v) {
  // llm_call with llm_response_format "text" yields {text, model, provider}.
  if (v && typeof v === "object" && !Array.isArray(v) && typeof v.text === "string") v = v.text;
  if (typeof v !== "string") return v;
  const cleaned = v.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
  try { return JSON.parse(cleaned); } catch (e) { fail("llm_output_invalid", "réponse non JSON"); }
}

// Subset of JSON Schema: $ref (#/$defs), type, enum, required, properties, additionalProperties false,
// items, minItems, maxItems, minLength, pattern, format date, minimum, maximum, exclusiveMinimum.
function checkSchema(schema, value, path, root, errors) {
  if (errors.length >= 8) return;
  if (schema.$ref) {
    if (!schema.$ref.startsWith("#/")) fail("schema_ref_unsupported", schema.$ref);
    let node = root;
    for (const part of schema.$ref.slice(2).split("/")) node = node ? node[part] : undefined;
    if (!node) fail("schema_ref_unknown", schema.$ref);
    return checkSchema(node, value, path, root, errors);
  }
  const t = schema.type;
  if (t) {
    const ok = t === "string" ? typeof value === "string" : t === "number" ? (typeof value === "number" && Number.isFinite(value)) : t === "integer" ? Number.isInteger(value) : t === "boolean" ? typeof value === "boolean" : t === "array" ? Array.isArray(value) : t === "object" ? isObject(value) : true;
    if (!ok) { errors.push(path + " : type " + t + " attendu"); return; }
  }
  if (schema.enum && !schema.enum.includes(value)) errors.push(path + " : valeur hors liste");
  if (typeof value === "string") {
    if (schema.minLength !== undefined && value.length < schema.minLength) errors.push(path + " : vide ou trop court");
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
    for (const key of Object.keys(props)) if (value[key] !== undefined && value[key] !== null) checkSchema(props[key], value[key], path + "." + key, root, errors);
    if (schema.additionalProperties === false) for (const key of Object.keys(value)) if (!(key in props)) errors.push(path + "." + key + " : champ inconnu");
  }
}
function validateSchema(schema, value, label) {
  const errors = [];
  checkSchema(schema, value, "$", schema, errors);
  if (errors.length) fail("data_invalid", label + " : " + errors.join(" ; "));
}

function fmtMoney(cents) {
  const abs = Math.abs(cents);
  const grouped = String(Math.floor(abs / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return (cents < 0 ? "-" : "") + grouped + "," + String(abs % 100).padStart(2, "0") + " €";
}
function fmtNumber(n) { return String(n).replace(".", ","); }
const VAT_RATES = [0, 2.1, 5.5, 10, 20];
function decimalsAtMost(n, places) { const scaled = n * Math.pow(10, places); return Math.abs(scaled - Math.round(scaled)) < 1e-6; }
function checkQuoteNumbers(d) {
  const errors = [];
  d.lines.forEach((l, i) => {
    const at = "lines[" + i + "]";
    if (!(l.quantity > 0) || l.quantity > 1000000) errors.push(at + ".quantity : doit être strictement positif et ne pas dépasser 1000000");
    else if (!decimalsAtMost(l.quantity, 3)) errors.push(at + ".quantity : 3 décimales au plus");
    if (!(l.unit_price_ht >= 0)) errors.push(at + ".unit_price_ht : positif ou nul");
    else if (!decimalsAtMost(l.unit_price_ht, 2)) errors.push(at + ".unit_price_ht : 2 décimales au plus");
    if (!VAT_RATES.includes(l.vat_rate)) errors.push(at + ".vat_rate : taux autorisés 0, 2.1, 5.5, 10 ou 20");
  });
  if (errors.length) fail("data_invalid", "données du gabarit quote : " + errors.slice(0, 8).join(" ; "));
}
function fmtRate(r) { return fmtNumber(r) + " %"; }

// Amounts and totals are computed here, in integer cents, from the lines. They are never taken from the model.
function quoteData(d) {
  const lines = [];
  let ht = 0;
  const groups = new Map();
  for (const l of d.lines) {
    const unitCents = Math.round(l.unit_price_ht * 100);
    const totalCents = Math.round(Math.round(l.quantity * 1000) * unitCents / 1000);
    const rateHundredths = Math.round(l.vat_rate * 100);
    ht += totalCents;
    groups.set(rateHundredths, (groups.get(rateHundredths) || 0) + totalCents);
    lines.push({description: l.description, quantity: fmtNumber(l.quantity) + (l.unit ? " " + l.unit : ""), unit_price_ht: fmtMoney(unitCents), vat_rate: fmtRate(rateHundredths / 100), total_ht: fmtMoney(totalCents)});
  }
  let vatTotal = 0;
  const vat = Array.from(groups.entries()).sort((a, b) => a[0] - b[0]).map(([rate, base]) => {
    const cents = Math.round(base * rate / 10000);
    vatTotal += cents;
    return {rate: fmtRate(rate / 100), amount: fmtMoney(cents)};
  });
  const customer = d.customer;
  return {reference: d.reference, customer: {name: customer.name, address_lines: customer.address_lines || [], contact: customer.contact || ""}, lines, totals: {total_ht: fmtMoney(ht), vat, total_ttc: fmtMoney(ht + vatTotal)}, valid_until: d.valid_until, terms: d.terms || [], payment_terms: d.payment_terms || ""};
}
function templateData(key, data) { return key === "quote" ? quoteData(data) : data; }

// Draft data: reference default, validation against the draft schema, then against the template input schema.
function normalizeData(key, data, id) {
  if (!isObject(data)) fail("data_invalid", "les données doivent être un objet");
  let d = data;
  if (key === "quote" && (d.reference === undefined || d.reference === null || d.reference === "")) d = {...d, reference: id.toUpperCase()};
  const tpl = TEMPLATES[key];
  validateSchema(tpl.draft_schema, d, "données du gabarit " + key);
  if (key === "quote") checkQuoteNumbers(d);
  validateSchema(tpl.input_schema, templateData(key, d), "gabarit " + key);
  return d;
}

function summarize(rec) {
  const last = rec.renders.length ? rec.renders[rec.renders.length - 1] : null;
  return {doc_id: rec.doc_id, template_key: rec.template_key, title: rec.title, locale: rec.locale, status: rec.status, number: rec.number, revision: rec.revision, renders: rec.renders.length, last_render: last ? {revision: last.revision, mode: last.mode, path: last.file.path, sha256: last.file.sha256, pages: last.previews.length} : null, issued: rec.issued};
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
async function readText(path, extra) {
  const r = unwrap(await callTool("read_file", {path, ...(extra || {})}));
  if (typeof r === "string") return r;
  if (isObject(r) && typeof r.content === "string") return r.content;
  fail("storage_read_failed", path);
}
async function readJson(path) { return JSON.parse(await readText(path)); }
async function writeJson(path, value, overwrite) {
  await callTool("write_file", {path, content: JSON.stringify(value, null, 2) + "\n", overwrite});
}
async function listPaths(path) {
  let r;
  try { r = unwrap(await callTool("list_files", {path})); } catch (e) { return []; }
  const entries = Array.isArray(r) ? r : (isObject(r) ? (r.files || r.entries || []) : []);
  return entries.map((e) => (typeof e === "string" ? e : (isObject(e) && typeof e.path === "string" ? e.path : ""))).filter(Boolean);
}
function recordPath(id) { return ROOT + "/docs/" + id + "/record.json"; }
function remember(rec) { Object.defineProperty(rec, "_loaded", {value: {revision: rec.revision, status: rec.status}, enumerable: false, writable: true, configurable: true}); return rec; }
async function loadRecord(id) {
  let rec;
  try { rec = await readJson(recordPath(id)); } catch (e) { fail("document_not_found", id); }
  return remember(checkRecord(rec, id));
}
// Storage has no conditional write: the record is read again just before the write, and the write is abandoned when
// another actor changed it (revision or status). The window is small, not null.
async function saveRecord(rec) {
  let fresh;
  try { fresh = await readJson(recordPath(rec.doc_id)); } catch (e) { fail("concurrent_update", "le dossier a disparu ou est illisible : " + rec.doc_id); }
  const was = rec._loaded;
  if (!isObject(fresh) || !was || fresh.revision !== was.revision || fresh.status !== was.status || fresh.status === "cancelled" && was.status !== "cancelled") fail("concurrent_update", "le dossier " + rec.doc_id + " a changé pendant l'opération ; rien n'a été écrit");
  await writeJson(recordPath(rec.doc_id), rec, true);
  remember(rec);
}
async function loadProfile() {
  let stored = null;
  try { stored = await readJson(ROOT + "/profile.json"); } catch (e) { stored = null; }
  if (!isObject(stored)) fail("profile_missing", "enregistrez la charte par document-studio-profile-save");
  return projectProfile(normalizeProfile(stored));
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

RENDER = r'''
function safeName(name, fallback) {
  const base = typeof name === "string" ? name.split("/").pop() : "";
  return /^[A-Za-z0-9._-]{1,100}$/.test(base) && !base.startsWith(".") ? base : fallback;
}

async function renderDocument(rec, data, profile, mode, number, status, revision) {
  const tpl = TEMPLATES[rec.template_key];
  if (!tpl) fail("template_unknown", rec.template_key);
  const tdata = templateData(rec.template_key, data);
  validateSchema(tpl.input_schema, tdata, "gabarit " + rec.template_key);
  const doc = {number: number || "BROUILLON", title: rec.title, date: today(), version: String(revision), status, locale: rec.locale};
  const raw = await callTool("artifact_render_v1", {template: {manifest: tpl.manifest, files: tpl.files}, data: tdata, context: {company: profile.company, brand: profile.brand, doc, i18n: I18N}, output: "pdf", mode});
  const res = unwrap(raw);
  if (isObject(res) && res.error) fail("render_failed", res.error + (res.message ? " : " + res.message : ""));
  if (!isObject(res) || res.status !== "ok" || !isObject(res.file)) fail("render_failed", "réponse inattendue du moteur de rendu");
  return res;
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
  for (const p of Array.isArray(res.previews) ? res.previews : []) {
    const page = Number.isInteger(p.page) ? p.page : previews.length + 1;
    const stored = await storeFile(dir + "/" + safeName(p.filename, "page-" + page + ".png"), p);
    previews.push({page, path: stored.path, sha256: stored.sha256});
  }
  return previews;
}
'''

NUMBERING = r'''
// Number reservation: lists the year folder, takes max + 1, writes the token without overwrite, reads it back and
// checks the owner. Not atomic: the check narrows the window, it does not close it.
async function reserveNumber(rec) {
  const year = new Date().getUTCFullYear();
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
    try { token = await readJson(path); } catch (e) { last = String(e && e.message); continue; }
    if (isObject(token) && token.doc_id === rec.doc_id) return TEMPLATES[rec.template_key].prefix + "-" + year + "-" + seq;
    last = "numéro " + seq + " pris par un autre document";
  }
  fail("number_conflict", "5 essais sans numéro libre (" + last + ")");
}
'''


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


def lib(*, templates=None, io=False, profile=False, render=False, numbering=False):
    parts = [IMPORT if io else '']
    if templates is not None:
        parts.append('const TEMPLATES = ' + js_embed(load_templates(templates == 'full')) + ';\n')
    if render:
        parts.append('const I18N = ' + js_embed(I18N) + ';\n')
    parts.append(CORE)
    if profile:
        parts.append(PROFILE)
    if io:
        parts.append(IO)
    if render:
        parts.append(RENDER)
    if numbering:
        parts.append(NUMBERING)
    return ''.join(parts)


def text(description, **extra):
    return {'type': 'string', 'description': description, **extra}


def schema(required, **props):
    return {'type': 'object', 'required': required, 'additionalProperties': False, 'properties': props}


DOC_ID = text('Document identifier: lowercase letters, digits and hyphens', pattern='^[a-z0-9][a-z0-9-]{0,47}$')
CONFIRM = {'type': ['boolean', 'string'], 'description': 'Manual confirmation: oui (or true) to proceed'}
LOCALE = text('Document language; fr only in V0', enum=['fr'])
TEMPLATE_KEY = text('Template key', enum=['quote', 'meeting-minutes'])
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
const key = prep.template_key || out.template_key;
if (typeof key !== "string" || !TEMPLATES[key]) fail("template_unknown", String(key));
const list = (v) => (Array.isArray(v) ? v.filter((x) => typeof x === "string" && x.trim()).map((x) => x.trim().slice(0, 300)).slice(0, 20) : []);
const title = typeof out.title === "string" && out.title.trim() ? out.title.trim().slice(0, 120) : TEMPLATES[key].title;
return {template_key: key, title, locale: prep.locale, missing: list(out.missing), questions: list(out.questions)};
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
const id = given ? docIdOf(input.doc_id) : slugify(title || (key === "quote" ? "devis " + (isObject(data.customer) ? data.customer.name : "") : (isObject(data.meeting) ? data.meeting.title : key))) + "-" + shortSuffix();
data = normalizeData(key, data, id);
if (!title) title = key === "quote" ? "Devis " + data.customer.name : data.meeting.title;
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
  data = {...rec.data, ...input.data_patch};
}
data = normalizeData(rec.template_key, data, id);
const profile = await loadProfile();
const revision = rec.revision + 1;
const res = await renderDocument(rec, data, profile, "preview", null, "draft", revision);
const dir = ROOT + "/docs/" + id + "/r" + revision;
const file = await storeFile(dir + "/" + safeName(res.file.filename, "document.pdf"), res.file);
const previews = await storePreviews(dir, res);
const at = nowIso();
if (rec.status === "approved") rec.history.push({at, action: "reopened", note: "nouveau rendu : l'approbation est à renouveler"});
rec.history.push({at, action: "rendered", note: "r" + revision + ", " + (Number.isInteger(res.pages) ? res.pages : previews.length) + " page(s)"});
rec.status = "draft";
rec.data = data;
rec.revision = revision;
rec.renders.push({revision, mode: "preview", file, previews, provenance: res.provenance === undefined ? null : res.provenance});
await saveRecord(rec);
return summarize(rec);
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
if (!rec.number) {
  rec.number = await reserveNumber(rec);
  rec.revision += 1;
  rec.history.push({at: nowIso(), action: "number_reserved", note: rec.number});
  await saveRecord(rec);
}
const data = normalizeData(rec.template_key, rec.data, id);
const revision = rec.revision + 1;
const res = await renderDocument(rec, data, profile, "final", rec.number, "issued", revision);
const dir = ROOT + "/docs/" + id;
const file = await storeFile(dir + "/issued/" + rec.number + ".pdf", res.file);
const previews = await storePreviews(dir + "/r" + revision, res);
const at = nowIso();
rec.status = "issued";
rec.revision = revision;
rec.renders.push({revision, mode: "final", file, previews, provenance: res.provenance === undefined ? null : res.provenance});
rec.issued = {number: rec.number, file: {path: file.path, sha256: file.sha256}, at};
rec.history.push({at, action: "issued", note: rec.number});
await saveRecord(rec);
return summarize(rec);
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
const last = rec.renders.length ? rec.renders[rec.renders.length - 1] : null;
const source = rec.issued ? rec.issued.file : (last ? last.file : null);
if (!source) fail("no_render", "aucun rendu à exporter");
const encoded = await readText(source.path, {encoding: "base64"});
const bytes = b64ToBytes(encoded.replace(/\s+/g, ""));
const sha = await sha256Hex(bytes);
if (sha !== source.sha256) fail("export_integrity_failed", "l'empreinte du fichier lu ne correspond pas au rendu");
await callTool("write_file", {path: dest, content: encoded.replace(/\s+/g, ""), encoding: "base64", overwrite: false});
return {doc_id: id, destination_path: dest, source_path: source.path, sha256: sha, bytes: bytes.length, draft: !rec.issued, warning: rec.issued ? "" : "document non émis : copie du dernier rendu, marquée brouillon"};
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
if (ids.length > 200) fail("too_many_documents", "plus de 200 documents : filtrez ou archivez");
const items = [];
for (const id of ids.sort()) {
  let rec;
  try { rec = await loadRecord(id); } catch (e) { continue; }
  if (input.status && rec.status !== input.status) continue;
  if (input.template_key && rec.template_key !== input.template_key) continue;
  const s = summarize(rec);
  items.push({doc_id: s.doc_id, title: s.title, template_key: s.template_key, status: s.status, number: s.number, revision: s.revision, sha256: s.issued ? s.issued.file.sha256 : (s.last_render ? s.last_render.sha256 : null)});
}
return {count: items.length, items};
'''

REVIEW_CODE = r'''
const input = {{ json . }};
const id = docIdOf(input.doc_id);
const rec = await loadRecord(id);
const last = rec.renders.length ? rec.renders[rec.renders.length - 1] : null;
const s = summarize(rec);
return {doc_id: id, title: rec.title, template_key: rec.template_key, status: rec.status, number: rec.number === null ? "" : rec.number, revision: rec.revision, pages: last ? last.previews.length : 0, previews: last ? last.previews : [], renders: rec.renders.map((r) => ({revision: r.revision, mode: r.mode, sha256: r.file.sha256, path: r.file.path})), history: rec.history, issued: rec.issued, record: rec};
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
                 field('brief', 'Brief', 'text', True), field('template_key', 'Gabarit (facultatif)', 'select', False, options=[
                     {'value': 'quote', 'label': 'Devis'}, {'value': 'meeting-minutes', 'label': 'Compte rendu de réunion'}])],
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
                 field('template_key', 'Gabarit', 'select', True, options=[
                     {'value': 'quote', 'label': 'Devis'}, {'value': 'meeting-minutes', 'label': 'Compte rendu de réunion'}]),
                 field('title', 'Titre (facultatif)', 'string', False), field('doc_id', 'Identifiant (facultatif)', 'string', False)],
                 ['prepare', 'draft-llm', 'create'])])

    workflow('document-studio-render', 'Render a document preview',
             'Renders the current data with the company profile through the artifact tool (mode preview), stores the PDF '
             'and its page previews in Storage and appends a revision. An issued or cancelled document is locked.',
             schema(['doc_id'], doc_id=DOC_ID, data_patch={'type': 'object', 'description': 'Shallow merge into the draft data, then revalidated'}),
             [node('render', code(lib(templates='full', io=True, profile=True, render=True), RENDER_CODE), 'result', tools=RENDER_TOOLS)],
             out_summary,
             forms=[form('render', 'Nouveau rendu', [field('doc_id', 'Identifiant du document', 'string', True)], ['render'])])

    workflow('document-studio-finalize', 'Approve a document',
             'Moves a rendered draft to approved. Requires a render of the current revision and a manual confirmation.',
             schema(['doc_id', 'confirmation_manuelle'], doc_id=DOC_ID, confirmation_manuelle=CONFIRM),
             [node('finalize', code(lib(io=True), FINALIZE_CODE), 'result', tools=STORAGE_TOOLS)],
             out_summary,
             forms=[form('approve', 'Approuver un document', [field('doc_id', 'Identifiant du document', 'string', True), CONFIRM_FIELD], ['finalize'])])

    workflow('document-studio-publish', 'Issue a document',
             'Reserves the next number of the template for the year, renders the final PDF (mode final) and stores it as the '
             'issued file. Requires an approved document and a manual confirmation. The reservation is not atomic.',
             schema(['doc_id', 'confirmation_manuelle'], doc_id=DOC_ID, confirmation_manuelle=CONFIRM),
             [node('publish', code(lib(templates='full', io=True, profile=True, render=True, numbering=True), PUBLISH_CODE), 'result', tools=RENDER_TOOLS)],
             out_summary,
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
             'Sending by mail or SFTP is out of scope.',
             schema(['doc_id', 'destination_path'], doc_id=DOC_ID, destination_path=text('Absolute Storage path of the copy, outside /document-studio/')),
             [node('export', code(lib(io=True), EXPORT_CODE), 'result', tools=STORAGE_TOOLS)],
             {'doc_id': '{{ result.doc_id }}', 'destination_path': '{{ result.destination_path }}', 'source_path': '{{ result.source_path }}',
              'sha256': '{{ result.sha256 }}', 'bytes': '{{ result.bytes }}', 'draft': '{{ result.draft }}', 'warning': '{{ result.warning }}'},
             forms=[form('export', 'Exporter un document', [field('doc_id', 'Identifiant du document', 'string', True),
                                                            field('destination_path', 'Chemin de destination', 'string', True)], ['export'])])

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
             {'count': '{{ result.count }}', 'items': '{{ result.items }}'})

    workflow('document-studio-review-read', 'Read a document for review',
             'Returns the record of a document with the previews of its last render, for the review MiniApp.',
             schema(['doc_id'], doc_id=DOC_ID),
             [node('read', code(lib(io=True), REVIEW_CODE), 'result', tools=STORAGE_TOOLS)],
             {k: '{{ result.%s }}' % k for k in ('doc_id', 'title', 'template_key', 'status', 'number', 'revision', 'pages', 'previews', 'renders', 'history', 'issued', 'record')},
             forms=[form('review', 'Relire un document', [field('doc_id', 'Identifiant du document', 'string', True)], ['read'])])

    workflow('document-studio-template-read', 'Read the templates',
             'Lists the available templates, or returns the manifest and the data schemas of one of them.',
             schema([], template_key=TEMPLATE_KEY),
             [node('read', code(lib(templates='meta'), TEMPLATE_READ_CODE), 'result')],
             {'templates': '{{ result.templates }}', 'template': '{{ result.template }}'})

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
                          'review': {'status': '', 'revision': 0, 'number': '', 'pages': 0, 'title': '', 'renders': []},
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
                        ref('document-studio-export', 'Export a document'), ref('document-studio-profile-save', 'Save the company profile')],
            'queries': [ref('document-studio-list', 'List documents'), ref('document-studio-review-read', 'Read a document for review'),
                        ref('document-studio-template-read', 'Read the templates')],
            'apps': [{'key': 'document-studio-review', 'name': 'Document studio', 'miniapp_id': 'document-studio-review',
                      'miniapp_version': '1'}]},
        'requires': {},
    }
    dump(MODULE / 'module.yaml', data)


if __name__ == '__main__':
    build()
