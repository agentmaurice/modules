#!/usr/bin/env python3
"""Generate the cib-profile Module: the company profile (company and brand) kept in an Application record.

The Module reads and saves one record, namespace `cib-profile`, key `company-profile`, through the native
`recipe--application_data_v1` broker, and projects it as the `{company, brand}` pair of the template/v1 contract.
Nothing here is executed by the generator; the Workflows run in the One once the broker is wired (AGENT-1305).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULE_DIR = ROOT.parents[1] / "profile"
DEST = MODULE_DIR / "agents" / "main"

NAMESPACE = "cib-profile"
RECORD_KEY = "company-profile"
BROKER = "recipe--application_data_v1"

# Flat form fields, in display order: (name, title, kind, required). Selects are added separately.
COMPANY_FIELDS = [
    ("legal_name", "Legal name", "string", True),
    ("trade_name", "Trade name", "string", False),
    ("legal_form", "Legal form", "string", False),
    ("share_capital", "Share capital", "string", False),
    ("siren", "SIREN", "string", False),
    ("siret", "SIRET", "string", False),
    ("vat_number", "VAT number", "string", False),
    ("rcs", "Trade register (RCS)", "string", False),
    ("address_line1", "Address, line 1", "string", False),
    ("address_line2", "Address, line 2", "string", False),
    ("address_postal_code", "Postal code", "string", False),
    ("address_city", "City", "string", False),
    ("address_country", "Country", "string", False),
    ("email", "E-mail", "string", False),
    ("phone", "Phone", "string", False),
    ("website", "Website", "string", False),
    ("legal_mentions", "Legal mentions", "text", False),
    ("bank_account_holder", "Bank account holder", "string", False),
    ("bank_iban", "IBAN", "string", False),
    ("bank_bic", "BIC", "string", False),
    ("bank_name", "Bank name", "string", False),
]
BRAND_FIELDS = [
    ("color_primary", "Primary colour (#RRGGBB)", "string", True),
    ("color_secondary", "Secondary colour (#RRGGBB)", "string", True),
    ("color_accent", "Accent colour (#RRGGBB)", "string", True),
    ("color_text", "Text colour (#RRGGBB)", "string", True),
    ("color_muted", "Muted colour (#RRGGBB)", "string", True),
    ("color_background", "Background colour (#RRGGBB)", "string", True),
    ("font_heading", "Heading font family", "string", True),
    ("font_body", "Body font family", "string", True),
    ("font_mono", "Monospace font family", "string", True),
    ("logo_ref", "Logo reference (storage://...)", "string", True),
    ("logo_alt", "Logo alternative text", "string", True),
    ("margin_top", "Top margin (mm)", "string", True),
    ("margin_right", "Right margin (mm)", "string", True),
    ("margin_bottom", "Bottom margin (mm)", "string", True),
    ("margin_left", "Left margin (mm)", "string", True),
]
ALL_FIELD_NAMES = [f[0] for f in COMPANY_FIELDS] + [f[0] for f in BRAND_FIELDS] + ["page_size"]

# Shared JavaScript (Deno sandbox). It never contains a double-brace sequence: the Workflow engine would read it
# as a template action. Validation is strict and canonical; a stored body is re-validated on every read.
LIB = r'''
const NAMESPACE = "cib-profile";
const RECORD_KEY = "company-profile";
const COLOR = /^#[0-9a-fA-F]{6}$/;
const IBAN = /^[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}$/;
const BIC = /^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$/;
const COLOR_TOKENS = ["primary", "secondary", "accent", "text", "muted", "background"];
const FONT_ROLES = ["heading", "body", "mono"];
const MARGIN_SIDES = ["top", "right", "bottom", "left"];
const ADDRESS_PARTS = ["line1", "line2", "postal_code", "city", "country"];
const COMPANY_TEXT = {trade_name: 200, legal_form: 100, share_capital: 100, siren: 32, siret: 32, vat_number: 32, rcs: 200, email: 254, phone: 64, website: 300, legal_mentions: 4000};
const BANK_TEXT = {account_holder: 200, bank_name: 200};
const COMPANY_KEYS = ["legal_name", ...Object.keys(COMPANY_TEXT), "address", "bank"];
const BRAND_KEYS = ["colors", "fonts", "logo", "page"];

function fail(code) { throw new Error(code); }
function isObject(value) { return value !== null && typeof value === "object" && !Array.isArray(value); }
function onlyKeys(value, allowed, name) { for (const key of Object.keys(value)) if (!allowed.includes(key)) fail(name + "_unknown_field"); }
function text(value, name, max, required) {
  if (value === undefined || value === null || value === "") { if (required) fail(name + "_required"); return ""; }
  if (typeof value !== "string" || value.length > max) fail(name + "_invalid");
  const trimmed = value.trim();
  if (required && !trimmed) fail(name + "_required");
  return trimmed;
}
function margin(value, name) {
  const raw = typeof value === "number" ? String(value) : value;
  if (typeof raw !== "string" || !/^[0-9]{1,3}(\.[0-9]{1,2})?$/.test(raw.trim())) fail(name + "_invalid");
  const number = Number(raw.trim());
  if (number > 100) fail(name + "_invalid");
  return number;
}
function logoRef(value) {
  if (typeof value !== "string" || !/^storage:\/\/[^\s]{1,500}$/.test(value) || value.includes("..") || value.toLowerCase().includes("secret://")) fail("logo_ref_invalid");
  return value;
}

// Canonical body, the stored shape: { schema_version, company, brand }. company.logo is never stored: it is derived from brand.logo.ref on read.
function normalizeBody(body) {
  if (!isObject(body) || body.schema_version !== 1) fail("body_schema_invalid");
  onlyKeys(body, ["schema_version", "company", "brand"], "body");
  const c = body.company, b = body.brand;
  if (!isObject(c) || !isObject(b)) fail("body_schema_invalid");
  if (c.logo !== undefined) fail("company_logo_derived_from_brand");
  onlyKeys(c, COMPANY_KEYS, "company");
  const company = {legal_name: text(c.legal_name, "legal_name", 200, true)};
  for (const [key, max] of Object.entries(COMPANY_TEXT)) { const value = text(c[key], key, max, false); if (value) company[key] = value; }
  if (c.address !== undefined) {
    if (!isObject(c.address)) fail("address_invalid");
    onlyKeys(c.address, ADDRESS_PARTS, "address");
    const address = {};
    for (const part of ADDRESS_PARTS) { const value = text(c.address[part], "address_" + part, 200, false); if (value) address[part] = value; }
    if (Object.keys(address).length) {
      for (const part of ["line1", "postal_code", "city", "country"]) if (!address[part]) fail("address_" + part + "_required");
      company.address = address;
    }
  }
  if (c.bank !== undefined) {
    if (!isObject(c.bank)) fail("bank_invalid");
    onlyKeys(c.bank, ["account_holder", "iban", "bic", "bank_name"], "bank");
    const bank = {};
    for (const [key, max] of Object.entries(BANK_TEXT)) { const value = text(c.bank[key], "bank_" + key, max, false); if (value) bank[key] = value; }
    if (c.bank.iban !== undefined && c.bank.iban !== "") {
      if (typeof c.bank.iban !== "string") fail("iban_invalid");
      const iban = c.bank.iban.replace(/\s+/g, "").toUpperCase();
      if (iban.length < 15 || iban.length > 34 || !IBAN.test(iban)) fail("iban_invalid");
      bank.iban = iban;
    }
    if (c.bank.bic !== undefined && c.bank.bic !== "") {
      if (typeof c.bank.bic !== "string") fail("bic_invalid");
      const bic = c.bank.bic.replace(/\s+/g, "").toUpperCase();
      if (!BIC.test(bic)) fail("bic_invalid");
      bank.bic = bic;
    }
    if (Object.keys(bank).length) company.bank = bank;
  }
  onlyKeys(b, BRAND_KEYS, "brand");
  if (!isObject(b.colors) || !isObject(b.fonts) || !isObject(b.logo) || !isObject(b.page) || !isObject(b.page.margins_mm)) fail("brand_invalid");
  onlyKeys(b.colors, COLOR_TOKENS, "colors");
  onlyKeys(b.fonts, FONT_ROLES, "fonts");
  onlyKeys(b.logo, ["ref", "alt"], "logo");
  onlyKeys(b.page, ["size", "margins_mm"], "page");
  onlyKeys(b.page.margins_mm, MARGIN_SIDES, "margins_mm");
  const colors = {};
  for (const token of COLOR_TOKENS) { if (typeof b.colors[token] !== "string" || !COLOR.test(b.colors[token])) fail("color_" + token + "_invalid"); colors[token] = b.colors[token]; }
  const fonts = {};
  for (const role of FONT_ROLES) { if (!isObject(b.fonts[role])) fail("font_" + role + "_invalid"); onlyKeys(b.fonts[role], ["family"], "font_" + role); fonts[role] = {family: text(b.fonts[role].family, "font_" + role, 100, true)}; }
  if (b.page.size !== "A4" && b.page.size !== "Letter") fail("page_size_invalid");
  const margins_mm = {};
  for (const side of MARGIN_SIDES) margins_mm[side] = margin(b.page.margins_mm[side], "margin_" + side);
  const brand = {colors, fonts, logo: {ref: logoRef(b.logo.ref), alt: text(b.logo.alt, "logo_alt", 200, true)}, page: {size: b.page.size, margins_mm}};
  return {schema_version: 1, company, brand};
}

// Flat form input -> structured body.
function bodyFromFields(input) {
  if (!isObject(input)) fail("input_invalid");
  const field = (name) => (input[name] === undefined || input[name] === null ? "" : input[name]);
  const company = {legal_name: field("legal_name")};
  for (const key of Object.keys(COMPANY_TEXT)) if (field(key) !== "") company[key] = field(key);
  const address = {};
  for (const part of ADDRESS_PARTS) if (field("address_" + part) !== "") address[part] = field("address_" + part);
  if (Object.keys(address).length) company.address = address;
  const bank = {};
  if (field("bank_account_holder") !== "") bank.account_holder = field("bank_account_holder");
  if (field("bank_iban") !== "") bank.iban = field("bank_iban");
  if (field("bank_bic") !== "") bank.bic = field("bank_bic");
  if (field("bank_name") !== "") bank.bank_name = field("bank_name");
  if (Object.keys(bank).length) company.bank = bank;
  const colors = {};
  for (const token of COLOR_TOKENS) colors[token] = field("color_" + token);
  const fonts = {};
  for (const role of FONT_ROLES) fonts[role] = {family: field("font_" + role)};
  const margins_mm = {};
  for (const side of MARGIN_SIDES) margins_mm[side] = field("margin_" + side);
  return {schema_version: 1, company, brand: {colors, fonts, logo: {ref: field("logo_ref"), alt: field("logo_alt")}, page: {size: field("page_size"), margins_mm}}};
}

// Stored body -> flat strings, to prefill the form.
function toFields(body) {
  const c = body.company, b = body.brand, a = c.address || {}, k = c.bank || {};
  const fields = {legal_name: c.legal_name, address_line1: a.line1 || "", address_line2: a.line2 || "", address_postal_code: a.postal_code || "", address_city: a.city || "", address_country: a.country || "", bank_account_holder: k.account_holder || "", bank_iban: k.iban || "", bank_bic: k.bic || "", bank_name: k.bank_name || ""};
  for (const key of Object.keys(COMPANY_TEXT)) fields[key] = c[key] || "";
  for (const token of COLOR_TOKENS) fields["color_" + token] = b.colors[token];
  for (const role of FONT_ROLES) fields["font_" + role] = b.fonts[role].family;
  fields.logo_ref = b.logo.ref; fields.logo_alt = b.logo.alt; fields.page_size = b.page.size;
  for (const side of MARGIN_SIDES) fields["margin_" + side] = String(b.page.margins_mm[side]);
  return fields;
}

// The template/v1 context pair. The body maps onto company and brand as is; only company.logo is derived, from the single brand.logo source.
function project(body) {
  return {company: {...body.company, logo: {ref: body.brand.logo.ref}}, brand: body.brand};
}

function luminance(hex) {
  const channel = (offset) => { const v = parseInt(hex.slice(offset, offset + 2), 16) / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
}
function contrast(a, b) { const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x); return Math.round(((hi + 0.05) / (lo + 0.05)) * 100) / 100; }
function colorPreview(brand) {
  return COLOR_TOKENS.map((token) => ({token, hex: brand.colors[token], contrast_on_background: contrast(brand.colors[token], brand.colors.background)}));
}

function brokerRecord(response, revisionRequired) {
  const payload = response && response.data ? response.data : response;
  const item = payload && payload.record;
  if (!item || item.namespace !== NAMESPACE || item.key !== RECORD_KEY) fail("broker_record_identity_invalid");
  if (!Number.isSafeInteger(item.revision) || item.revision < 0) fail("broker_revision_invalid");
  const p = item.permissions;
  if (!p || typeof p.can_read !== "boolean" || typeof p.can_write !== "boolean" || typeof p.can_manage !== "boolean") fail("broker_permissions_invalid");
  return item;
}
'''

READ_CODE = "import { callTool } from './tools/nats_bridge.ts';\n" + LIB + r'''
let response;
try {
  response = await callTool("recipe--application_data_v1", {operation: "read", namespace: NAMESPACE, record_key: RECORD_KEY});
} catch (error) {
  if (/not[_ -]?found/i.test(String((error && error.message) || error))) response = null; else throw error;
}
const payload = response && response.data ? response.data : response;
if (!payload || payload.record === null || payload.record === undefined) {
  return {found: false, namespace: NAMESPACE, record_key: RECORD_KEY, revision: 0, owner_user_id: "", permissions: {can_read: false, can_write: false, can_manage: false}, body: null, profile: null, color_preview: [], fields: {}, message: "No company profile saved yet. Save one with expected revision 0.", effects: [{type: "open_form", payload: {form_id: "save", submit_event: "save", prefill: {expected_revision: "0", page_size: "A4", confirmation_manuelle: "false"}}}], external_effect: false};
}
const item = brokerRecord(response);
const body = normalizeBody(item.data);
const fields = toFields(body);
return {found: true, namespace: NAMESPACE, record_key: RECORD_KEY, revision: item.revision, owner_user_id: typeof item.owner_user_id === "string" ? item.owner_user_id : "", permissions: item.permissions, body, profile: project(body), color_preview: colorPreview(body.brand), fields, message: "Company profile read. The projection is ready for template/v1.", effects: [{type: "open_form", payload: {form_id: "save", submit_event: "save", prefill: {...fields, expected_revision: String(item.revision), confirmation_manuelle: "false"}}}], external_effect: false};'''

SAVE_CODE = "import { callTool } from './tools/nats_bridge.ts';\nconst input = {{ json . }};\n" + LIB + r'''
const confirmed = input.confirmation_manuelle === true || input.confirmation_manuelle === "true";
if (!confirmed) fail("manual_confirmation_required");
let expected_revision = input.expected_revision;
if (expected_revision === undefined || expected_revision === null || expected_revision === "") fail("expected_revision_required");
if (typeof expected_revision === "string" && /^[0-9]+$/.test(expected_revision)) expected_revision = Number(expected_revision);
if (!Number.isSafeInteger(expected_revision) || expected_revision < 0) fail("expected_revision_invalid");
const body = normalizeBody(bodyFromFields(input));
const response = await callTool("recipe--application_data_v1", {operation: "save", namespace: NAMESPACE, record_key: RECORD_KEY, data: body, expected_revision});
const item = brokerRecord(response);
const stored = normalizeBody(item.data);
return {namespace: NAMESPACE, record_key: RECORD_KEY, revision: item.revision, owner_user_id: typeof item.owner_user_id === "string" ? item.owner_user_id : "", permissions: item.permissions, shares: Array.isArray(item.shares) ? item.shares.length : 0, profile: project(stored), color_preview: colorPreview(stored.brand), message: "Company profile saved in the internal ACL store; no external effect. Other people read it only after an explicit per-person share.", external_effect: false};'''


def dump(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def field(name: str, title: str, kind: str, required: bool, options=None, default=None) -> dict:
    result = {"name": name, "title": title, "type": kind, "required": required}
    if options:
        result["options"] = [{"value": value, "label": label} for value, label in options]
    if default is not None:
        result["default"] = default
    return result


def read_workflow() -> dict:
    return {
        "$schema": "agentmaurice.workflow/v2", "schema_version": 2, "kind": "workflow",
        "workflow_id": "cib-profile-read", "version": "1",
        "title": "Company profile — read",
        "description": "Reads the company profile record (namespace cib-profile, key company-profile) through the native broker and returns the body with the { company, brand } projection for template/v1. It needs read access on the record; it never reads another person's data.",
        "actions": [{"id": "read", "type": "code_execution", "context": {"allowed_tools": [BROKER]}, "code": READ_CODE, "output_key": "result"}],
        "output": {key: "{{ result.%s }}" % key for key in ("found", "namespace", "record_key", "revision", "owner_user_id", "permissions", "body", "profile", "color_preview", "fields", "effects", "message")} | {"external_effect": False},
    }


def save_workflow() -> dict:
    fields = [field(n, t, k, r) for n, t, k, r in COMPANY_FIELDS]
    for n, t, k, r in BRAND_FIELDS:
        if n == "margin_top":
            fields.append(field("page_size", "Page size", "select", True, [("A4", "A4"), ("Letter", "Letter")], "A4"))
        fields.append(field(n, t, k, r))
    for f in fields:
        if f["name"] in ALL_FIELD_NAMES and "default" not in f:
            f["default"] = "{{ state.profile.fields.%s }}" % f["name"]
    fields.append(field("expected_revision", "Expected revision (0 to create)", "string", True, default="{{ state.profile.revision }}"))
    fields.append(field("confirmation_manuelle", "Manual confirmation", "select", True, [("false", "No"), ("true", "Yes")], "false"))
    return {
        "$schema": "agentmaurice.workflow/v2", "schema_version": 2, "kind": "workflow",
        "workflow_id": "cib-admin-profile-save", "version": "1",
        "title": "Company profile — save",
        "description": "Saves the company profile with an expected revision. Restricted to the cib_admin role (the cib-admin- prefix is what tooling/enterprise-admin/service_roles.py maps to it) and to a manual confirmation. The logo is a storage:// reference; there is no upload. Bank details are optional and checked by shape only.",
        "forms": [{"id": "save", "title": "Company profile — save", "fields": fields, "actions_on_submit": ["save"]}],
        "actions": [{"id": "save", "type": "code_execution", "context": {"allowed_tools": [BROKER]}, "code": SAVE_CODE, "output_key": "result"}],
        "output": {key: "{{ result.%s }}" % key for key in ("namespace", "record_key", "revision", "owner_user_id", "permissions", "shares", "profile", "color_preview", "message")} | {"external_effect": False},
    }


def console() -> dict:
    state_fields = ALL_FIELD_NAMES + ["expected_revision", "confirmation_manuelle"]
    initial = {name: "" for name in state_fields}
    initial.update({"page_size": "A4", "expected_revision": "0", "confirmation_manuelle": "false"})
    initial["profile"] = {"found": False, "revision": 0, "color_preview": [], "fields": {}, "message": "No profile loaded."}
    initial["result"] = {"message": "No action."}
    save_input = {name: "{{ state.%s }}" % name for name in state_fields}
    return {
        "$schema": "agentmaurice.miniapp/v2", "schema_version": 2, "kind": "miniapp",
        "miniapp_id": "cib-profile-console", "version": "1",
        "title": "Company profile",
        "description": "Edit the company profile (identity, address, optional bank details, colours, fonts, logo reference and page margins) used by generated documents. One record, saved by a cib_admin with a manual confirmation.",
        "ui": {"renderer": "component", "component": "company-in-a-box", "configuration": {"layout": [
            {"type": "callout", "title": "Company profile", "tone": "info", "value": "One shared profile for your documents. Load it, check the colour preview, then open the form \"Company profile - save\" in the available interactions. The logo is a storage:// reference to a file already in Storage; uploading a logo is not available here."},
            {"type": "button", "label": "Load the company profile", "on_click": "read"},
            {"type": "section", "title": "Current record", "children": [
                {"type": "stat", "label": "Revision", "value": {"state": "profile.revision"}},
                {"type": "stat", "label": "Legal name", "value": {"state": "profile.fields.legal_name"}},
                {"type": "stat", "label": "Logo reference", "value": {"state": "profile.fields.logo_ref"}},
                {"type": "text", "value": {"state": "profile.message"}}]},
            {"type": "section", "title": "Colour preview", "children": [
                {"type": "table", "columns": ["token", "hex", "contrast_on_background"], "column_labels": {"token": "Token", "hex": "Colour", "contrast_on_background": "Contrast on background"}, "rows": {"state": "profile.color_preview"}}]},
            {"type": "section", "title": "Last save", "children": [
                {"type": "text", "value": {"state": "result.message"}},
                {"type": "table", "columns": ["token", "hex", "contrast_on_background"], "column_labels": {"token": "Token", "hex": "Colour", "contrast_on_background": "Contrast on background"}, "rows": {"state": "result.color_preview"}}]},
        ]}},
        "state_schema": {"type": "object", "properties": {**{name: {"type": "string"} for name in state_fields}, "profile": {"type": "object"}, "result": {"type": "object"}}},
        "initial_state": initial,
        "events": [
            {"event_id": "read", "trigger": "action.click", "workflow": {"workflow_id": "cib-profile-read", "input": {}}, "result_to_state": "profile"},
            {"event_id": "save", "trigger": "form.submit", "workflow": {"workflow_id": "cib-admin-profile-save", "input": save_input}, "result_to_state": "result"},
        ],
    }


def manifest() -> dict:
    return {"$schema": "agentmaurice.module/v2", "schema_version": 2, "key": "cib-profile",
            "name": "Company-in-a-Box — company profile", "version": "0.1.0",
            "provides": {
                "actions": [{"key": "save", "workflow_id": "cib-admin-profile-save", "workflow_version": "1"}],
                "queries": [{"key": "read", "workflow_id": "cib-profile-read", "workflow_version": "1"}],
                "apps": [{"key": "profile-console", "miniapp_id": "cib-profile-console", "miniapp_version": "1"}]},
            "requires": {}}


def build() -> None:
    dump(DEST / "workflows/cib-profile-read.json", read_workflow())
    dump(DEST / "workflows/cib-admin-profile-save.json", save_workflow())
    dump(DEST / "miniapps/cib-profile-console.json", console())
    dump(MODULE_DIR / "module.yaml", manifest())


if __name__ == "__main__":
    build()
