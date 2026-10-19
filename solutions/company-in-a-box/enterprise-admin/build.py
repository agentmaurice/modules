#!/usr/bin/env python3
"""Generate the bounded, portable Company-in-a-Box enterprise admin Module."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "module" / "agents" / "main"
TOOLS = {
    "directory_snapshot", "application_people_list", "approval_mandates_list",
    "directory_upsert_person", "directory_link_user", "directory_grant_role",
    "directory_revoke_role", "application_people_add", "application_people_remove",
    "approval_mandate_revoke",
}


def dump(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def field(name: str, title: str, kind: str = "string", options=None, required: bool = True) -> dict:
    result = {"name": name, "title": title, "type": kind, "required": required}
    if options:
        result["options"] = [{"value": value, "label": label} for value, label in options]
    return result


READS = [
    ("directory_snapshot", "Annuaire — personnes et rôles"),
    ("application_people_list", "Application — personnes autorisées"),
    ("approval_mandates_list", "Mandats — liste"),
]
MUTATIONS = [
    ("directory_upsert_person", "Annuaire — créer ou actualiser une personne"),
    ("directory_link_user", "Annuaire — lier une identité existante"),
    ("directory_grant_role", "Annuaire — accorder un rôle métier"),
    ("directory_revoke_role", "Annuaire — retirer un rôle métier"),
    ("application_people_add", "Application — ajouter une personne"),
    ("application_people_remove", "Application — retirer une personne"),
    ("approval_mandate_revoke", "Mandat — révoquer"),
]

HISTORICAL_NAMESPACES = [
    ("cib-cases", "Dossiers"),
    ("cib-veille", "Veille"),
    ("cib-contenu", "Contenu"),
    ("cib-accompagnement", "Accompagnement"),
]


def record_input_code() -> str:
    return '''const input = {{ json . }};
const namespaces = new Set(["cib-cases", "cib-veille", "cib-contenu", "cib-accompagnement"]);
if (!input || !namespaces.has(input.namespace)) throw new Error("historical_namespace_invalid");
if (typeof input.record_key !== "string" || !/^[a-z0-9][a-z0-9:_./-]{0,127}$/.test(input.record_key) || input.record_key.includes("..")) throw new Error("historical_record_key_invalid");'''


def record_read_workflow() -> dict:
    code = '''import { callTool } from './tools/nats_bridge.ts';
''' + record_input_code() + '''
const response = await callTool("recipe--application_data_v1", {operation:"read", namespace:input.namespace, record_key:input.record_key});
const payload = response && response.data ? response.data : response;
const item = payload && payload.record;
if (!item || item.namespace !== input.namespace || item.key !== input.record_key) throw new Error("broker_record_identity_invalid");
if (!Number.isSafeInteger(item.revision) || item.revision < 0) throw new Error("broker_revision_invalid");
const permissions = item.permissions;
if (!permissions || typeof permissions.can_read !== "boolean" || typeof permissions.can_write !== "boolean" || typeof permissions.can_manage !== "boolean") throw new Error("broker_permissions_invalid");
const shares = Array.isArray(item.shares) ? item.shares.map((share) => ({user_id: share.user_id || share.subject_user_id || "", permission: share.permission || ""})) : [];
return {namespace:item.namespace, record_key:item.key, revision:item.revision, owner_user_id:typeof item.owner_user_id === "string" ? item.owner_user_id : "", permissions, shares, share_count:shares.length, rows:[{namespace:item.namespace, record_key:item.key, revision:item.revision, owner_user_id:typeof item.owner_user_id === "string" ? item.owner_user_id : "", permissions, share_count:shares.length, body_included:false}], body_included:false, message:"Métadonnées ACL lues ; le corps métier n’est pas renvoyé.", effects:[{type:"open_form", payload:{form_id:"read", submit_event:"read", prefill:{namespace:item.namespace, record_key:item.key, expected_revision:String(item.revision), subject_user_id:"", permission:"read", confirmation_manuelle:"non"}}}], external_effect:false};'''
    item = workflow("cib-admin-record-read", "Administration — métadonnées d’une fiche historique", [{"id":"read", "type":"code_execution", "context":{"allowed_tools":["recipe--application_data_v1"]}, "code":code, "output_key":"result"}], {"namespace":"{{ result.namespace }}", "record_key":"{{ result.record_key }}", "revision":"{{ result.revision }}", "owner_user_id":"{{ result.owner_user_id }}", "permissions":"{{ result.permissions }}", "shares":"{{ result.shares }}", "share_count":"{{ result.share_count }}", "rows":"{{ result.rows }}", "body_included":False, "effects":"{{ result.effects }}", "message":"{{ result.message }}", "external_effect":False}, [{"name":"namespace","title":"Type de fiche","type":"select","required":True,"options":[{"value":value,"label":label} for value,label in HISTORICAL_NAMESPACES]}, {"name":"record_key","title":"Clé de fiche","type":"string","required":True}])
    item["forms"][0]["id"] = "read"
    item["version"] = "1"
    return item


def record_people_workflow() -> dict:
    code = '''import { callTool } from './tools/nats_bridge.ts';
''' + record_input_code() + '''
const response = await callTool("recipe--application_data_v1", {operation:"people", namespace:input.namespace, record_key:input.record_key});
const payload = response && response.data ? response.data : response;
if (!payload || !Array.isArray(payload.people)) throw new Error("broker_people_invalid");
const people = payload.people.map((person) => { if (!person || typeof person.user_id !== "string" || typeof person.display_name !== "string") throw new Error("broker_person_invalid"); return {user_id:person.user_id, display_name:person.display_name}; });
    return {namespace:input.namespace, record_key:input.record_key, people, selected_target:typeof input.subject_user_id === "string" ? people.find((person) => person.user_id === input.subject_user_id.trim()) || null : null, message:"Membres existants de l’Application ; aucun droit n’est modifié.", external_effect:false};'''
    item = workflow("cib-admin-record-people", "Administration — membres partageables", [{"id":"people", "type":"code_execution", "context":{"allowed_tools":["recipe--application_data_v1"]}, "code":code, "output_key":"result"}], {"namespace":"{{ result.namespace }}", "record_key":"{{ result.record_key }}", "people":"{{ result.people }}", "selected_target":"{{ result.selected_target }}", "message":"{{ result.message }}", "external_effect":False})
    item["version"] = "1"
    return item


def record_share_workflow() -> dict:
    code = '''import { callTool } from './tools/nats_bridge.ts';
''' + record_input_code() + '''
if (typeof input.subject_user_id !== "string" || !input.subject_user_id.trim() || input.subject_user_id.length > 256 || /[\\/\\s]/.test(input.subject_user_id)) throw new Error("subject_user_id_invalid");
if (!["read", "write", "none"].includes(input.permission)) throw new Error("permission_invalid");
let expected_revision = input.expected_revision;
if (typeof expected_revision === "string" && /^[0-9]+$/.test(expected_revision)) expected_revision = Number(expected_revision);
if (!Number.isSafeInteger(expected_revision) || expected_revision < 0) throw new Error("expected_revision_invalid");
if (input.confirmation_manuelle !== true && input.confirmation_manuelle !== "oui") throw new Error("manual_confirmation_required");
const response = await callTool("recipe--application_data_v1", {operation:"share", namespace:input.namespace, record_key:input.record_key, expected_revision, subject_user_id:input.subject_user_id.trim(), permission:input.permission, admin_recovery:true});
const payload = response && response.data ? response.data : response;
const item = payload && payload.record;
if (!item || item.namespace !== input.namespace || item.key !== input.record_key) throw new Error("broker_record_identity_invalid");
if (!Number.isSafeInteger(item.revision) || item.revision < 0) throw new Error("broker_revision_invalid");
const permissions = item.permissions;
if (!permissions || typeof permissions.can_read !== "boolean" || typeof permissions.can_write !== "boolean" || typeof permissions.can_manage !== "boolean") throw new Error("broker_permissions_invalid");
const shares = Array.isArray(item.shares) ? item.shares.map((share) => ({user_id: share.user_id || share.subject_user_id || "", permission: share.permission || ""})) : [];
    return {namespace:item.namespace, record_key:item.key, revision:item.revision, owner_user_id:typeof item.owner_user_id === "string" ? item.owner_user_id : "", permissions, shares, share_count:shares.length, body_included:false, message:"Partage ACL mis à jour par le broker natif ; le corps métier n’est pas renvoyé.", effects:[{type:"open_form", payload:{form_id:"share", submit_event:"share", prefill:{namespace:item.namespace, record_key:item.key, expected_revision:String(item.revision), subject_user_id:input.subject_user_id.trim(), permission:input.permission, confirmation_manuelle:"non"}}}], confirmation_manuelle:false, external_effect:false};'''
    forms = [{"name":"namespace","title":"Type de fiche","type":"select","required":True,"options":[{"value":value,"label":label} for value,label in HISTORICAL_NAMESPACES]}, {"name":"record_key","title":"Clé de fiche","type":"string","required":True}, {"name":"expected_revision","title":"Révision attendue","type":"string","required":True}, {"name":"subject_user_id","title":"Membre existant","type":"string","required":True}, {"name":"permission","title":"Permission","type":"select","required":True,"options":[{"value":"read","label":"Lecture"},{"value":"write","label":"Écriture"},{"value":"none","label":"Retirer"}]}, {"name":"confirmation_manuelle","title":"Confirmation manuelle","type":"select","required":True,"options":[{"value":"oui","label":"Oui"},{"value":"non","label":"Non"}]}]
    item = workflow("cib-admin-record-share", "Administration — partager une fiche historique", [{"id":"share", "type":"code_execution", "context":{"allowed_tools":["recipe--application_data_v1"]}, "code":code, "output_key":"result"}], {"namespace":"{{ result.namespace }}", "record_key":"{{ result.record_key }}", "revision":"{{ result.revision }}", "owner_user_id":"{{ result.owner_user_id }}", "permissions":"{{ result.permissions }}", "shares":"{{ result.shares }}", "share_count":"{{ result.share_count }}", "body_included":False, "effects":"{{ result.effects }}", "confirmation_manuelle":False, "message":"{{ result.message }}", "external_effect":False}, forms)
    item["forms"][0]["id"] = "share"
    item["version"] = "1"
    return item


def records_console() -> dict:
    return {"$schema":"agentmaurice.miniapp/v2", "schema_version":2, "kind":"miniapp", "miniapp_id":"cib-admin-records-console", "version":"1", "title":"Administration — fiches historiques", "description":"Contrôle unitaire des métadonnées et partages ACL des fiches historiques. Les fiches restent privées par défaut.", "ui":{"renderer":"component", "component":"company-in-a-box", "configuration":{"layout":[{"type":"text","value":"Saisissez une fiche à la fois. L’administrateur reste dépositaire ; aucun transfert ni partage en masse n’est disponible."},{"type":"button","label":"Lire les métadonnées ACL","on_click":"read"},{"type":"button","label":"Charger les membres existants","on_click":"people"},{"type":"section","title":"Métadonnées ACL","children":[{"type":"text","value":{"state":"read.message"}},{"type":"table","columns":["namespace","record_key","revision","owner_user_id","body_included"],"rows":{"state":"read.rows"}}]},{"type":"section","title":"Membres existants — cliquer pour sélectionner","children":[{"type":"table","columns":["user_id","display_name"],"rows":{"state":"people.people"},"on_row_click":"select-person"}]},{"type":"section","title":"Partage unitaire","children":[{"type":"text","value":{"state":"people.selected_target.display_name"}},{"type":"text","value":"Pour partager ou retirer un accès, ouvrez la console dédiée cib-admin-record-share-console depuis la navigation et recopiez namespace, clé, révision et membre connus."},{"type":"text","value":{"state":"share.message"}}]}] }}, "state_schema":{"type":"object","properties":{"read":{"type":"object"},"people":{"type":"object"},"share":{"type":"object"},"namespace":{"type":"string"},"record_key":{"type":"string"},"expected_revision":{"type":"string"},"subject_user_id":{"type":"string"},"permission":{"type":"string"},"confirmation_manuelle":{"type":"string"}}}, "initial_state":{"read":{"message":"Aucune fiche lue.","rows":[]},"people":{"message":"Aucun membre chargé.","people":[],"selected_target":None},"share":{"message":"Aucune action.","rows":[]},"namespace":"cib-cases","record_key":"","expected_revision":"","subject_user_id":"","permission":"read","confirmation_manuelle":"non"}, "events":[{"event_id":"read","trigger":"form.submit","workflow":{"workflow_id":"cib-admin-record-read","input":{"namespace":"{{ state.namespace }}","record_key":"{{ state.record_key }}"}},"result_to_state":"read"},{"event_id":"people","trigger":"action.click","workflow":{"workflow_id":"cib-admin-record-people","input":{"namespace":"{{ state.read.namespace }}","record_key":"{{ state.read.record_key }}"}},"result_to_state":"people"},{"event_id":"select-person","trigger":"table.row_click","workflow":{"workflow_id":"cib-admin-record-people","input":{"namespace":"{{ state.read.namespace }}","record_key":"{{ state.read.record_key }}","subject_user_id":"{{ event.payload.item.user_id }}"}},"result_to_state":"people"},{"event_id":"share","trigger":"form.submit","workflow":{"workflow_id":"cib-admin-record-share","input":{"namespace":"{{ state.read.namespace }}","record_key":"{{ state.read.record_key }}","expected_revision":"{{ state.read.revision }}","subject_user_id":"{{ state.people.selected_target.user_id }}","permission":"{{ state.permission }}","confirmation_manuelle":"{{ state.confirmation_manuelle }}"}},"result_to_state":"share"}]}


def record_share_console() -> dict:
    return {
        "$schema": "agentmaurice.miniapp/v2", "schema_version": 2, "kind": "miniapp",
        "miniapp_id": "cib-admin-record-share-console", "version": "1",
        "title": "Administration — partager une fiche historique",
        "description": "Partage ACL unitaire à partir des métadonnées déjà lues ; aucune lecture du corps métier, aucun transfert ni partage en masse.",
        "ui": {"renderer": "component", "component": "company-in-a-box", "configuration": {"layout": [
            {"type": "text", "value": "Copiez depuis la console des fiches historiques les quatre informations connues : namespace, clé de fiche, révision et identifiant du membre. N’inscrivez aucun secret. Une seule fiche et un seul membre sont traités à la fois ; l’administrateur reste dépositaire."},
            {"type": "text", "value": "Ouvrez le formulaire « Administration — partager une fiche historique » dans les interactions disponibles, puis confirmez le partage ou le retrait."},
            {"type": "text", "value": {"state": "result.message"}},
        ]}},
        "state_schema": {"type": "object", "properties": {
            "namespace": {"type": "string"}, "record_key": {"type": "string"},
            "expected_revision": {"type": "string"}, "subject_user_id": {"type": "string"},
            "permission": {"type": "string"}, "confirmation_manuelle": {"type": "string"},
            "result": {"type": "object"},
        }},
        "initial_state": {"namespace": "cib-cases", "record_key": "", "expected_revision": "", "subject_user_id": "", "permission": "read", "confirmation_manuelle": "non", "result": {"message": "Aucune action."}},
        "events": [{"event_id": "share", "trigger": "form.submit", "workflow": {"workflow_id": "cib-admin-record-share", "input": {
            "namespace": "{{ state.namespace }}", "record_key": "{{ state.record_key }}", "expected_revision": "{{ state.expected_revision }}",
            "subject_user_id": "{{ state.subject_user_id }}", "permission": "{{ state.permission }}", "confirmation_manuelle": "{{ state.confirmation_manuelle }}",
        }}, "result_to_state": "result"}],
    }


def invoke_code() -> str:
    return '''import { callTool } from './tools/nats_bridge.ts';
const input = {{ json . }};
const read = ["directory_snapshot", "application_people_list", "approval_mandates_list"];
const write = ["directory_upsert_person", "directory_link_user", "directory_grant_role", "directory_revoke_role", "application_people_add", "application_people_remove", "approval_mandate_revoke"];
const op = typeof input.operation === "string" ? input.operation.trim() : "";
if (!read.includes(op) && !write.includes(op)) throw new Error("admin_operation_invalid");
const confirmed = input.confirmation_manuelle === true || input.confirmation_manuelle === "true";
if (write.includes(op) && !confirmed) throw new Error("manual_confirmation_required");
const args = {};
const fields = {person_id:"person_id", display_name:"display_name", target_platform_user_id:"target_platform_user_id", role_key:"role_key", mandate_id:"mandate_id", reason:"reason"};
const permitted = {
  directory_upsert_person:["person_id","display_name"], directory_link_user:["person_id","target_platform_user_id"],
  directory_grant_role:["person_id","role_key"], directory_revoke_role:["person_id","role_key"],
  application_people_add:["target_platform_user_id"], application_people_remove:["target_platform_user_id"],
  approval_mandate_revoke:["mandate_id","reason"], directory_snapshot:[], application_people_list:[], approval_mandates_list:[]
}[op];
for (const source of permitted) if (typeof input[source] === "string" && input[source].trim() !== "") args[fields[source]] = input[source].trim();
if (["directory_upsert_person", "directory_link_user", "directory_grant_role", "directory_revoke_role"].includes(op) && !args.person_id) throw new Error("person_id_required");
if (op === "directory_upsert_person" && !args.display_name) throw new Error("display_name_required");
if (["directory_link_user", "application_people_add", "application_people_remove"].includes(op) && !args.target_platform_user_id) throw new Error("target_platform_user_id_required");
if (["directory_grant_role", "directory_revoke_role"].includes(op) && !args.role_key) throw new Error("role_key_required");
if (op === "approval_mandate_revoke" && (!args.mandate_id || !args.reason)) throw new Error("mandate_revoke_fields_required");
if (write.includes(op)) args.confirmation_manuelle = true;
const native_result = await callTool("recipe--company_admin_v1", {operation: op, ...args});
return {operation:op, native_result, message:"Opération enregistrée. Actualisez l’état pour consulter le résultat.", external_effect:false};'''


def workflow(workflow_id: str, title: str, actions: list, output: dict, forms=None) -> dict:
    value = {"$schema": "agentmaurice.workflow/v2", "schema_version": 2, "kind": "workflow", "workflow_id": workflow_id, "version": "2", "title": title, "actions": actions, "output": output}
    if forms:
        value["forms"] = [{"id": "submit", "title": title, "fields": forms, "actions_on_submit": [action["id"] for action in actions]}]
    return value


def build() -> None:
    overview_code = '''import { callTool } from './tools/nats_bridge.ts';
const directory = await callTool("recipe--company_admin_v1", {operation:"directory_snapshot"});
const application_people = await callTool("recipe--company_admin_v1", {operation:"application_people_list"});
const approval_mandates = await callTool("recipe--company_admin_v1", {operation:"approval_mandates_list"});
return {people: directory.people || [], grants: directory.grants || [], application_people: application_people.people || [], approval_mandates: (approval_mandates.items || []).map(item => ({mandate_id: item.mandate?.mandate_id || item.mandate_id || "", status: item.status || ""})), mandate_count: approval_mandates.count || 0, message:"État administratif lu ; aucune mutation."};'''
    overview = workflow("cib-admin-overview", "Administration — état", [{"id": "read", "type": "code_execution", "context": {"allowed_tools": ["recipe--company_admin_v1"]}, "code": overview_code, "output_key": "result"}], {"people": "{{ result.people }}", "grants": "{{ result.grants }}", "application_people": "{{ result.application_people }}", "approval_mandates": "{{ result.approval_mandates }}", "mandate_count": "{{ result.mandate_count }}", "message": "{{ result.message }}", "external_effect": False})
    forms = [
        field("operation", "Opération", "select", READS + MUTATIONS),
        field("person_id", "Identifiant de personne", required=False),
        field("display_name", "Nom affiché", required=False),
        field("target_platform_user_id", "Identité utilisateur existante", required=False),
        field("role_key", "Rôle métier", "select", [("cib_admin", "Administration"), ("cib_marketing", "Marketing"), ("cib_service_client", "Service client"), ("cib_direction", "Direction"), ("cib_dossiers", "Dossiers communs")], required=False),
        field("mandate_id", "Identifiant du mandat", required=False),
        field("reason", "Motif", "text", required=False),
        field("confirmation_manuelle", "Confirmation manuelle", "select", [("false", "Non"), ("true", "Oui")]),
    ]
    manage = workflow("cib-admin-manage", "Administration — opération manuelle", [{"id": "invoke", "type": "code_execution", "context": {"allowed_tools": ["recipe--company_admin_v1"]}, "code": invoke_code(), "output_key": "result"}], {"result": "{{ result }}", "message": "Opération enregistrée. Actualisez l’état pour consulter le résultat.", "external_effect": False}, forms)
    dump(DEST / "workflows/cib-admin-overview.json", overview)
    dump(DEST / "workflows/cib-admin-manage.json", manage)
    miniapp = {
        "$schema": "agentmaurice.miniapp/v2", "schema_version": 2, "kind": "miniapp", "miniapp_id": "cib-admin-console", "version": "2", "title": "Administration Company-in-a-Box", "description": "Lecture et opérations administratives manuelles, sans création de compte ni invitation email.",
        "ui": {"renderer": "component", "component": "company-in-a-box", "configuration": {"layout": [
            {"type": "text", "value": "Gérez les personnes, leurs accès aux services et les mandats. Une fiche dans l’annuaire ne crée pas de compte utilisateur."},
            {"type": "button", "label": "Actualiser l’état", "on_click": "refresh"},
            {"type": "section", "title": "Personnes", "children": [{"type": "table", "columns": ["person_id", "display_name", "platform_user_id"], "column_labels": {"person_id": "Référence", "display_name": "Nom", "platform_user_id": "Identité liée"}, "rows": {"state": "overview.people"}}]},
            {"type": "section", "title": "Rôles métier", "children": [{"type": "table", "columns": ["person_id", "role_key"], "column_labels": {"person_id": "Personne", "role_key": "Rôle"}, "rows": {"state": "overview.grants"}}]},
            {"type": "section", "title": "Membres Application", "children": [{"type": "table", "columns": ["user_id"], "column_labels": {"user_id": "Identité"}, "rows": {"state": "overview.application_people"}}]},
            {"type": "section", "title": "Mandats", "children": [{"type": "metric", "label": "Mandats actuels", "value": {"state": "overview.mandate_count"}}, {"type": "table", "columns": ["mandate_id", "status"], "column_labels": {"mandate_id": "Mandat", "status": "État"}, "rows": {"state": "overview.approval_mandates"}}]},
            {"type": "text", "value": {"state": "overview.message"}},
            {"type": "text", "value": {"state": "result.message"}},
        ]}},
        "state_schema": {"type": "object", "properties": {"overview": {"type": "object"}, "result": {"type": "object"}}},
        "initial_state": {"overview": {"people": [], "grants": [], "application_people": [], "approval_mandates": [], "mandate_count": 0}, "result": {"message": "Aucun état consulté."}},
        "events": [{"event_id": "refresh", "trigger": "action.click", "workflow": {"workflow_id": "cib-admin-overview", "input": {}}, "result_to_state": "overview"}, {"event_id": "submit", "trigger": "form.submit", "workflow": {"workflow_id": "cib-admin-manage", "input": {"operation": "{{ state.operation }}", "person_id": "{{ state.person_id }}", "display_name": "{{ state.display_name }}", "target_platform_user_id": "{{ state.target_platform_user_id }}", "role_key": "{{ state.role_key }}", "mandate_id": "{{ state.mandate_id }}", "reason": "{{ state.reason }}", "confirmation_manuelle": "{{ state.confirmation_manuelle }}"}}, "result_to_state": "result"}],
    }
    miniapp["state_schema"]["properties"].update({f["name"]: {"type": "string"} for f in forms})
    miniapp["initial_state"].update({f["name"]: "false" if f["name"] == "confirmation_manuelle" else "" for f in forms})
    dump(DEST / "miniapps/cib-admin-console.json", miniapp)
    approval_check = workflow("cib-admin-approval-check", "Accord CIB — lecture locale de qualification", [{"id":"read_only", "type":"tool_call", "tool":"list_files", "require_approval":True, "params":{"path":"/company-in-a-box/veille"}, "output_key":"files"}], {"files":"{{ files }}"})
    approval_check["version"] = "1"
    approval_check["description"] = "Qualification manuelle : lister des fichiers locaux uniquement après la décision humaine sur le plan immuable. Aucun envoi ni écriture métier."
    approval_check["output_schema"] = {'type': 'object', 'additionalProperties': False, 'required': ['files'], 'properties': {'files': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False, 'required': ['path', 'size', 'last_modified'], 'properties': {'path': {'type': 'string'}, 'size': {'type': 'integer', 'minimum': 0}, 'last_modified': {'type': 'string'}}}}}}
    dump(DEST / "workflows/cib-admin-approval-check.json", approval_check)
    import_record = {'$schema': 'agentmaurice.workflow/v2',
     'schema_version': 2,
     'kind': 'workflow',
     'workflow_id': 'cib-admin-import-record',
     'version': '1',
     'title': 'Administration — reprendre une fiche historique',
     'description': 'Reprise manuelle à chemin fixe. Le propriétaire initial est l’administrateur authentifié qui reprend '
                    'le dossier ; aucun accès implicite des autres personnes.',
     'forms': [{'id': 'import',
                'title': 'Reprise administrative explicite',
                'fields': [{'name': 'namespace',
                            'type': 'select',
                            'title': 'Type de fiche',
                            'required': True,
                            'options': [{'value': 'cib-cases', 'label': 'cases'},
                                        {'value': 'cib-veille', 'label': 'veille'},
                                        {'value': 'cib-contenu', 'label': 'contenu'},
                                        {'value': 'cib-accompagnement', 'label': 'accompagnement'}]},
                           {'name': 'record_key',
                            'type': 'string',
                            'title': 'Identifiant (jeu/identifiant pour les dossiers communs)',
                            'required': True},
                           {'name': 'confirmation_manuelle',
                            'type': 'select',
                            'title': 'Reprendre cette fiche, en conserver le fichier original et en devenir le dépositaire',
                            'required': True,
                            'options': [{'value': 'non', 'label': 'Non'}, {'value': 'oui', 'label': 'Oui'}]}],
                'actions_on_submit': ['import']}],
     'actions': [{'id': 'import',
                  'type': 'code_execution',
                  'context': {'allowed_tools': ['recipe--application_data_v1']},
                  'code': "import { callTool } from './tools/nats_bridge.ts';\n"
                          'const input={{ json . }};\n'
                          'if(input.confirmation_manuelle!==true&&input.confirmation_manuelle!=="oui") throw '
                          'Error("manual_confirmation_required");\n'
                          'const result=await '
                          'callTool("recipe--application_data_v1",{operation:"import_legacy",namespace:input.namespace,record_key:input.record_key,confirmation_manuelle:true});\n'
                          'return '
                          '{revision:result.record?.revision,permissions:result.record?.permissions,legacy_file_preserved:result.legacy_file_preserved,external_effect:false};',
                  'output_key': 'result'}],
     'output': {'result': '{{ result }}', 'external_effect': False}}
    dump(DEST / "workflows/cib-admin-import-record.json", import_record)
    dump(ROOT / "module/module.yaml", {"$schema": "agentmaurice.module/v2", "schema_version": 2, "key": "cib-enterprise-admin", "name": "Company-in-a-Box — administration entreprise", "version": "0.2.1", "provides": {"actions": [{"key": "manage", "workflow_id": "cib-admin-manage", "workflow_version": "2"}, {"key":"import-record","workflow_id":"cib-admin-import-record","workflow_version":"1"}], "queries": [{"key": "overview", "workflow_id": "cib-admin-overview", "workflow_version": "2"}, {"key":"approval-check", "workflow_id":"cib-admin-approval-check", "workflow_version":"1"}], "apps": [{"key": "admin-console", "miniapp_id": "cib-admin-console", "miniapp_version": "2"}]}, "requires": {}})

    dump(DEST / "workflows/cib-admin-record-read.json", record_read_workflow())
    dump(DEST / "workflows/cib-admin-record-people.json", record_people_workflow())
    dump(DEST / "workflows/cib-admin-record-share.json", record_share_workflow())
    dump(DEST / "miniapps/cib-admin-records-console.json", records_console())

    manifest = json.loads((ROOT / "module/module.yaml").read_text(encoding="utf-8"))
    manifest["version"] = "0.2.2"
    manifest["provides"]["actions"].append({"key":"record-share", "workflow_id":"cib-admin-record-share", "workflow_version":"1"})
    manifest["provides"]["queries"].extend([
        {"key":"record-read", "workflow_id":"cib-admin-record-read", "workflow_version":"1"},
        {"key":"record-people", "workflow_id":"cib-admin-record-people", "workflow_version":"1"},
    ])
    manifest["provides"]["apps"].append({"key":"records-console", "miniapp_id":"cib-admin-records-console", "miniapp_version":"1"})
    manifest["provides"]["apps"].append({"key":"record-share-console", "miniapp_id":"cib-admin-record-share-console", "miniapp_version":"1"})
    dump(ROOT / "module/module.yaml", manifest)
    dump(DEST / "miniapps/cib-admin-record-share-console.json", record_share_console())


if __name__ == "__main__":
    build()
