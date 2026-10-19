import json
import hashlib
import importlib.util
import unittest
import subprocess
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build", ROOT / "build.py")
build = importlib.util.module_from_spec(spec); spec.loader.exec_module(build)
compose_spec = importlib.util.spec_from_file_location("compose", ROOT / "compose.py")
compose = importlib.util.module_from_spec(compose_spec); compose_spec.loader.exec_module(compose)

class ModuleTest(unittest.TestCase):
  def test_generated_contract_and_bounded_tools(self):
    build.build()
    manifest = json.loads((ROOT / "module/module.yaml").read_text())
    self.assertEqual(manifest["version"], "0.2.2")
    self.assertEqual({x["workflow_id"] for x in manifest["provides"]["actions"] + manifest["provides"]["queries"]}, {"cib-admin-manage", "cib-admin-overview", "cib-admin-approval-check", "cib-admin-import-record", "cib-admin-record-read", "cib-admin-record-people", "cib-admin-record-share"})
    manage = json.loads((ROOT / "module/agents/main/workflows/cib-admin-manage.json").read_text())
    code = manage["actions"][0]["code"]
    self.assertIn('callTool("recipe--company_admin_v1"', code)
    self.assertEqual(manage["actions"][0]["context"], {"allowed_tools": ["recipe--company_admin_v1"]})
    for forbidden in ("organization_id", "application_id", "caller_id", "create_account", "invite_email", "sign"):
      self.assertNotIn(forbidden, code)

  def test_form_has_manual_confirmation_and_required_management_fields(self):
    manage = json.loads((ROOT / "module/agents/main/workflows/cib-admin-manage.json").read_text())
    names = {f["name"] for f in manage["forms"][0]["fields"]}
    self.assertTrue({"operation", "person_id", "display_name", "target_platform_user_id", "role_key", "mandate_id", "reason", "confirmation_manuelle"} <= names)
    self.assertEqual(manage["actions"][0]["type"], "code_execution")
    self.assertFalse(next(field for field in manage["forms"][0]["fields"] if field["name"] == "display_name")["required"])

  def test_overview_has_only_three_read_calls(self):
    overview = json.loads((ROOT / "module/agents/main/workflows/cib-admin-overview.json").read_text())
    action = overview["actions"][0]
    self.assertEqual(action["type"], "code_execution")
    self.assertEqual(action["context"], {"allowed_tools": ["recipe--company_admin_v1"]})
    self.assertEqual(action["code"].count('callTool("recipe--company_admin_v1"'), 3)
    self.assertNotIn('allowed_tools:', action["code"])

  def test_js_validation_sends_only_operation_fields_and_derived_context(self):
    manage = json.loads((ROOT / "module/agents/main/workflows/cib-admin-manage.json").read_text())
    code = manage["actions"][0]["code"].replace("import { callTool } from './tools/nats_bridge.ts';", "").replace("const input = {{ json . }};", "const input = payload;")
    script = f'''const payload = JSON.parse(process.argv[2]);
let received;
async function callTool(name, args) {{ received = {{name, args}}; return received; }}
async function main() {{ {code} }}
main().then(() => {{
  if (received.name !== "recipe--company_admin_v1") process.exit(2);
  const args = received.args;
  if (args.target_platform_user_id !== "user-1" || args.confirmation_manuelle !== true) process.exit(3);
  if (Object.prototype.hasOwnProperty.call(args, "person_id") || Object.prototype.hasOwnProperty.call(args, "organization_id")) process.exit(4);
}}).catch(() => process.exit(5));'''
    def run(payload):
      with tempfile.NamedTemporaryFile("w", suffix=".mjs") as handle:
        handle.write(script); handle.flush()
        return subprocess.run(["node", handle.name, json.dumps(payload)], capture_output=True, text=True)
    first = run({"operation":"application_people_add", "target_platform_user_id":"user-1", "person_id":"ignored", "organization_id":"forged", "confirmation_manuelle":"true"})
    self.assertEqual(first.returncode, 0, first.stderr)
    self.assertNotEqual(run({"operation":"application_people_add", "target_platform_user_id":"user-1", "confirmation_manuelle":"false"}).returncode, 0)
    self.assertNotEqual(run({"operation":"not_allowed", "confirmation_manuelle":"true"}).returncode, 0)
    self.assertNotEqual(run({"operation":"approval_mandate_revoke", "confirmation_manuelle":"true"}).returncode, 0)

  def test_compose_rejects_traversal_and_divergent_destination(self):
    with tempfile.TemporaryDirectory() as directory:
      consumer = Path(directory)
      spec_path = consumer / "agents" / "veille" / "agent-spec.json"
      spec_path.parent.mkdir(parents=True)
      spec_path.write_text(json.dumps({"schema_version": 2, "agent_alias": "veille", "agent_id": "abcdefghijklmnopqrst"}))
      with self.assertRaises(ValueError): compose.compose(consumer, "../outside")
      target = consumer / "agents" / "veille" / "workflows" / "cib-admin-manage.json"
      target.parent.mkdir(parents=True); target.write_text("{}")
      with self.assertRaises(ValueError): compose.compose(consumer, "veille")

  def test_compose_accepts_identical_destination_without_internal_git(self):
    with tempfile.TemporaryDirectory() as directory:
      consumer = Path(directory)
      spec_path = consumer / "agents" / "veille" / "agent-spec.json"
      spec_path.parent.mkdir(parents=True)
      spec_path.write_text(json.dumps({"schema_version": 2, "agent_alias": "veille", "agent_id": "abcdefghijklmnopqrst"}))
      old = (ROOT / "module/agents/main/workflows/cib-admin-manage.json").read_bytes()
      target = consumer / "agents" / "veille" / "workflows" / "cib-admin-manage.json"
      target.parent.mkdir(parents=True); target.write_bytes(old)
      planned = compose.compose(consumer, "veille")
      self.assertEqual(len(planned), 10)
      self.assertEqual(compose.digest(target), compose.digest(next(src for src, dst in planned if dst == target)))

  def test_compose_accepts_only_published_021_fingerprint_when_source_changed(self):
    with tempfile.TemporaryDirectory() as directory:
      root_copy = Path(directory) / "module-source"
      shutil.copytree(ROOT / "module", root_copy / "module")
      changed = root_copy / "module/agents/main/miniapps/cib-admin-records-console.json"
      previous = (ROOT / "tests/fixtures/admin-records-0.2.1.json").read_bytes()
      self.assertEqual(hashlib.sha256(previous).hexdigest(), compose.LEGACY_021_HASHES["module/agents/main/miniapps/cib-admin-records-console.json"])
      candidate = json.loads(previous)
      candidate["description"] = "Synthetic candidate for upgrade contract test"
      changed.write_text(json.dumps(candidate) + "\n")
      consumer = Path(directory) / "consumer"
      spec_path = consumer / "agents" / "veille" / "agent-spec.json"
      spec_path.parent.mkdir(parents=True)
      spec_path.write_text(json.dumps({"schema_version": 2, "agent_alias": "veille", "agent_id": "abcdefghijklmnopqrst"}))
      target = consumer / "agents" / "veille" / "miniapps" / changed.name
      target.parent.mkdir(parents=True)
      target.write_bytes(previous)
      original_root = compose.ROOT
      compose.ROOT = root_copy
      try:
        planned = compose.compose(consumer, "veille")
      finally:
        compose.ROOT = original_root
      self.assertEqual(len(planned), 10)
      self.assertEqual(compose.digest(target), compose.LEGACY_021_HASHES["module/agents/main/miniapps/cib-admin-records-console.json"])

  def test_confirmation_defaults_to_non(self):
    miniapp = json.loads((ROOT / "module/agents/main/miniapps/cib-admin-console.json").read_text())
    self.assertEqual(miniapp["initial_state"]["confirmation_manuelle"], "false")

  def test_historical_acl_contract_is_unitary_and_bodyless(self):
    read = json.loads((ROOT / "module/agents/main/workflows/cib-admin-record-read.json").read_text())
    people = json.loads((ROOT / "module/agents/main/workflows/cib-admin-record-people.json").read_text())
    share = json.loads((ROOT / "module/agents/main/workflows/cib-admin-record-share.json").read_text())
    for item in (read, people, share):
      code = item["actions"][0]["code"]
      self.assertIn('callTool("recipe--application_data_v1"', code)
      self.assertEqual(item["actions"][0]["context"], {"allowed_tools": ["recipe--application_data_v1"]})
      self.assertIn("cib-cases", code)
      self.assertIn("cib-accompagnement", code)
      self.assertNotIn("owner_user_id", {field["name"] for field in item.get("forms", [{"fields": []}])[0]["fields"]})
      self.assertNotIn("legacy_path", item["output"])
    self.assertIn('operation:"share"', share["actions"][0]["code"])
    self.assertIn("admin_recovery:true", share["actions"][0]["code"])
    self.assertIn("expected_revision", share["actions"][0]["code"])
    self.assertEqual(share["output"]["body_included"], False)
    self.assertEqual(share["output"]["confirmation_manuelle"], False)
    self.assertEqual(read["forms"][0]["id"], "read")
    self.assertEqual(share["forms"][0]["id"], "share")
    self.assertNotIn("forms", people)
    manifest = json.loads((ROOT / "module/module.yaml").read_text())
    self.assertEqual(set(manifest["provides"]["apps"][1].keys()), {"key", "miniapp_id", "miniapp_version"})
    self.assertEqual(manifest["provides"]["apps"][2], {"key": "record-share-console", "miniapp_id": "cib-admin-record-share-console", "miniapp_version": "1"})

  def test_records_console_resets_confirmation_and_has_no_bulk_event(self):
    miniapp = json.loads((ROOT / "module/agents/main/miniapps/cib-admin-records-console.json").read_text())
    self.assertEqual(miniapp["initial_state"]["confirmation_manuelle"], "non")
    self.assertEqual({event["event_id"] for event in miniapp["events"]}, {"read", "people", "select-person", "share"})
    self.assertNotIn("bulk", json.dumps(miniapp).lower())
    events = {event["event_id"]: event for event in miniapp["events"]}
    self.assertEqual(events["read"]["trigger"], "form.submit")
    self.assertEqual(events["read"]["workflow"]["workflow_id"], "cib-admin-record-read")
    self.assertEqual(events["people"]["trigger"], "action.click")
    self.assertEqual(events["share"]["trigger"], "form.submit")
    self.assertEqual(events["people"]["workflow"]["input"]["record_key"], "{{ state.read.record_key }}")
    self.assertEqual(events["share"]["workflow"]["input"]["expected_revision"], "{{ state.read.revision }}")
    self.assertEqual(events["share"]["workflow"]["input"]["subject_user_id"], "{{ state.people.selected_target.user_id }}")
    ui = json.dumps(miniapp["ui"], ensure_ascii=False)
    self.assertNotIn("Partager / retirer l’accès", ui)
    self.assertIn("console dédiée cib-admin-record-share-console", ui)

  def test_dedicated_share_console_has_one_form_submit_and_root_inputs(self):
    miniapp = json.loads((ROOT / "module/agents/main/miniapps/cib-admin-record-share-console.json").read_text())
    self.assertEqual(miniapp["miniapp_id"], "cib-admin-record-share-console")
    self.assertEqual(miniapp["version"], "1")
    self.assertNotIn("forms", miniapp)
    self.assertEqual(len(miniapp["events"]), 1)
    event = miniapp["events"][0]
    self.assertEqual(event["event_id"], "share")
    self.assertEqual(event["trigger"], "form.submit")
    # A layout click cannot open a form.submit interaction in the current Viewer.
    # The available Workflow interaction is the executable entry point.
    layout = miniapp["ui"]["configuration"]["layout"]
    click_events = {e["event_id"] for e in miniapp["events"] if e["trigger"] == "action.click"}
    self.assertTrue(all(item.get("on_click") in click_events for item in layout if item.get("type") == "button"))
    self.assertIn("interactions disponibles", json.dumps(layout, ensure_ascii=False))
    self.assertEqual(event["workflow"], {"workflow_id": "cib-admin-record-share", "input": {
      "namespace": "{{ state.namespace }}", "record_key": "{{ state.record_key }}", "expected_revision": "{{ state.expected_revision }}",
      "subject_user_id": "{{ state.subject_user_id }}", "permission": "{{ state.permission }}", "confirmation_manuelle": "{{ state.confirmation_manuelle }}",
    }})
    self.assertEqual(set(miniapp["state_schema"]["properties"]), {"namespace", "record_key", "expected_revision", "subject_user_id", "permission", "confirmation_manuelle", "result"})
    guide = json.dumps(miniapp["ui"])
    self.assertIn("Copiez depuis la console", guide)
    self.assertIn("aucun secret", guide)
    self.assertNotIn("bulk", guide.lower())

  def test_generated_js_enforces_native_call_contract_and_transitions(self):
    paths = {name: ROOT / "module/agents/main/workflows" / f"cib-admin-record-{name}.json" for name in ("read", "people", "share")}

    def run(item, payload, native_result):
      code = json.loads(paths[item].read_text())["actions"][0]["code"]
      code = code.replace("import { callTool } from './tools/nats_bridge.ts';", "").replace("const input = {{ json . }};", "const input = request;")
      script = f'''const request = {json.dumps(payload)};
const nativeResult = {json.dumps(native_result)};
const calls = [];
async function callTool(name, args) {{ calls.push({{name, args}}); return nativeResult; }}
async function main() {{ {code} }}
main().then((value) => console.log(JSON.stringify({{value, calls}}))).catch((error) => {{ console.error(error.message); process.exit(1); }});'''
      with tempfile.NamedTemporaryFile("w", suffix=".mjs", encoding="utf-8") as handle:
        handle.write(script); handle.flush()
        completed = subprocess.run(["node", handle.name], capture_output=True, text=True)
      self.assertEqual(completed.returncode, 0, completed.stderr)
      return json.loads(completed.stdout)

    metadata = {"namespace":"cib-veille", "key":"veille-1", "revision":4, "owner_user_id":"user-a", "permissions":{"can_read":True,"can_write":False,"can_manage":False}, "shares":[{"user_id":"user-b","permission":"read"}]}
    read_result = run("read", {"namespace":"cib-veille", "record_key":"veille-1"}, {"record":metadata})
    self.assertEqual(read_result["calls"], [{"name":"recipe--application_data_v1", "args":{"operation":"read", "namespace":"cib-veille", "record_key":"veille-1"}}])
    self.assertEqual(read_result["value"]["rows"][0]["record_key"], "veille-1")
    self.assertFalse(read_result["value"]["body_included"])
    self.assertNotIn("record", read_result["value"])
    read_prefill = read_result["value"]["effects"][0]["payload"]["prefill"]
    self.assertEqual(read_prefill["expected_revision"], "4")
    self.assertEqual(read_prefill["subject_user_id"], "")
    self.assertEqual(read_prefill["confirmation_manuelle"], "non")

    people_result = run("people", {"namespace":"cib-veille", "record_key":"veille-1", "subject_user_id":"user-b"}, {"people":[{"user_id":"user-a","display_name":"A"},{"user_id":"user-b","display_name":"B"}]})
    self.assertEqual(people_result["calls"], [{"name":"recipe--application_data_v1", "args":{"operation":"people", "namespace":"cib-veille", "record_key":"veille-1"}}])
    self.assertEqual(people_result["value"]["selected_target"], {"user_id":"user-b", "display_name":"B"})

    share_result = run("share", {"namespace":"cib-veille", "record_key":"veille-1", "expected_revision":"4", "subject_user_id":"user-b", "permission":"read", "confirmation_manuelle":"oui"}, {"record":{**metadata, "revision":5}})
    self.assertEqual(share_result["calls"][0]["args"]["admin_recovery"], True)
    self.assertEqual(share_result["calls"][0]["args"]["expected_revision"], 4)
    self.assertFalse(share_result["value"]["confirmation_manuelle"])
    self.assertEqual(share_result["value"]["effects"][0]["payload"]["prefill"]["confirmation_manuelle"], "non")

  def test_approval_check_is_one_static_read_requiring_human_approval(self):
    item=json.loads((ROOT / "module/agents/main/workflows/cib-admin-approval-check.json").read_text())
    self.assertEqual(len(item["actions"]),1)
    action=item["actions"][0]
    self.assertTrue(action["require_approval"])
    self.assertEqual(action["tool"],"list_files")
    self.assertEqual(action["params"],{"path":"/company-in-a-box/veille"})

  def test_approval_check_declares_contract_for_file_list(self):
    item=json.loads((ROOT / "module/agents/main/workflows/cib-admin-approval-check.json").read_text())
    self.assertEqual(item["output"], {"files":"{{ files }}"})
    schema=item["output_schema"]
    self.assertEqual(schema["required"], ["files"])
    self.assertFalse(schema["additionalProperties"])
    files=schema["properties"]["files"]
    self.assertEqual(files["type"], "array")
    self.assertEqual(set(files["items"]["required"]), {"path","size","last_modified"})
