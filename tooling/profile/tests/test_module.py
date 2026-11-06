"""Offline checks of the profile Module: contract pin, projection, validation, role gate, composition.

Everything runs on synthetic fixtures. The Workflow code is executed under Node with a mocked broker; no One,
no model and no network are involved, and the real broker is not wired yet, so none of this proves runtime behaviour.
"""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parents[2]
MODULE = ROOT / "profile"
TOOLING = ROOT / "tooling/profile"
sys.path.insert(0, str(TESTS))
from jsonschema_subset import Registry, validate  # noqa: E402


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


build = module_from(TOOLING / "build.py", "profile_build")
compose = module_from(TOOLING / "compose.py", "profile_compose")
service_roles = module_from(ROOT / "tooling/enterprise-admin/service_roles.py", "admin_service_roles")

NAMESPACES = load(TOOLING / "contract/namespaces.schema.json")
TOKENS = load(TOOLING / "contract/tokens.schema.json")
REGISTRY = Registry(NAMESPACES, TOKENS)
BODY = load(TESTS / "fixtures/profile-body.json")
MINIMAL = load(TESTS / "fixtures/profile-body-minimal.json")
READ = load(MODULE / "agents/main/workflows/cib-profile-read.json")
SAVE = load(MODULE / "agents/main/workflows/cib-admin-profile-save.json")
CONSOLE = load(MODULE / "agents/main/miniapps/cib-profile-console.json")

HARNESS = r'''
const [, , codePath, inputJson, scenarioJson] = process.argv;
const fs = require("fs");
const scenario = JSON.parse(scenarioJson);
const calls = [];
async function callTool(name, args) {
  calls.push({name, args});
  if (scenario.throw) { const e = typeof scenario.throw === "string" ? new Error(scenario.throw) : Object.assign(new Error(scenario.throw.message), scenario.throw); throw e; }
  if (scenario.mode === "echo-save") {
    return {data: {record: {namespace: args.namespace, key: args.record_key, revision: args.expected_revision + 1, owner_user_id: "user-1", permissions: {can_read: true, can_write: true, can_manage: true}, shares: [], data: scenario.stored || args.data}}};
  }
  return scenario.response;
}
let code = fs.readFileSync(codePath, "utf8").replace("import { callTool } from './tools/nats_bridge.ts';", "").replace("const input = {{ json . }};", "const input = JSON.parse(process.argv[3]);");
const main = new Function("callTool", "process", "return (async () => {" + code + "})();");
main(callTool, process).then((result) => { console.log(JSON.stringify({calls, result})); }).catch((error) => { console.log(JSON.stringify({calls, error: String(error.message)})); });
'''


def run_workflow(workflow, input_value, scenario):
    code = workflow["actions"][0]["code"]
    with tempfile.TemporaryDirectory() as tmp:
        code_path, harness = Path(tmp) / "code.js", Path(tmp) / "harness.js"
        code_path.write_text(code, encoding="utf-8")
        harness.write_text(HARNESS, encoding="utf-8")
        proc = subprocess.run(["node", str(harness), str(code_path), json.dumps(input_value), json.dumps(scenario)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return json.loads(proc.stdout)


def record(data, revision=3):
    return {"data": {"record": {"namespace": "cib-profile", "key": "company-profile", "revision": revision, "owner_user_id": "user-1", "permissions": {"can_read": True, "can_write": True, "can_manage": False}, "shares": [], "data": data}}}


def read(data, revision=3):
    return run_workflow(READ, {}, {"response": record(data, revision)})


def contract_errors(profile):
    errors = validate(NAMESPACES["$defs"]["company"], profile["company"], REGISTRY, NAMESPACES)
    return errors + validate(TOKENS, profile["brand"], REGISTRY)


def fields_input(body=BODY, **overrides):
    fields = run_workflow(READ, {}, {"response": record(body)})["result"]["fields"]
    return {**fields, "expected_revision": "3", "confirmation_manuelle": "true", **overrides}


class ContractPinTest(unittest.TestCase):
    def test_frozen_copy_matches_its_pin(self):
        pin = load(TOOLING / "contract/PIN.json")
        self.assertRegex(pin["source_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(sorted(pin["files"]), ["namespaces.schema.json", "tokens.schema.json"])
        for name, expected in pin["files"].items():
            self.assertEqual(hashlib.sha256((TOOLING / "contract" / name).read_bytes()).hexdigest(), expected, name)

    def test_frozen_copy_carries_the_bank_field(self):
        bank = NAMESPACES["$defs"]["bank"]
        self.assertEqual(sorted(bank["properties"]), ["account_holder", "bank_name", "bic", "iban"])
        self.assertEqual(NAMESPACES["$defs"]["company"]["properties"]["bank"], {"$ref": "#/$defs/bank"})
        self.assertNotIn("bank", NAMESPACES["$defs"]["company"].get("required", []))

    def test_subset_validator_rejects_contract_violations(self):
        bad = json.loads(json.dumps(BODY))
        for key, value in (("iban", "fr7600000000000000000000000"), ("iban", "FR76 0000"), ("iban", "FR7600000000"), ("bic", "exmp"), ("account_holder", 3), ("iban", "FR7600000000000000000000000\n"), ("bic", "EXMPFRPP\n")):
            bad["company"]["bank"][key] = value
            self.assertTrue(contract_errors({"company": bad["company"], "brand": bad["brand"]}), (key, value))
            bad["company"]["bank"] = dict(BODY["company"]["bank"])
        worse = json.loads(json.dumps(BODY))
        worse["brand"]["colors"]["primary"] = "blue"
        self.assertTrue(contract_errors(worse))
        del worse["company"]["legal_name"]
        self.assertTrue(contract_errors(worse))

    def test_fixtures_are_valid_context(self):
        for body in (BODY, MINIMAL):
            self.assertEqual(contract_errors({"company": body["company"], "brand": body["brand"]}), [])


class ManifestTest(unittest.TestCase):
    def test_manifest_contract(self):
        manifest = load(MODULE / "module.yaml")
        self.assertEqual((manifest["key"], manifest["version"], manifest["schema_version"]), ("cib-profile", "0.1.0", 2))
        self.assertEqual([x["key"] for x in manifest["provides"]["queries"]], ["read"])
        self.assertEqual([x["key"] for x in manifest["provides"]["actions"]], ["save"])
        self.assertEqual(len(manifest["provides"]["apps"]), 1)

    def test_generator_reproduces_the_published_files(self):
        published = {p: p.read_bytes() for p in MODULE.rglob("*") if p.is_file()}
        build.build()
        self.assertEqual(published, {p: p.read_bytes() for p in MODULE.rglob("*") if p.is_file()})

    def test_only_the_native_broker_and_no_identity_or_legal_format(self):
        for workflow in (READ, SAVE):
            action = workflow["actions"][0]
            self.assertEqual(action["context"], {"allowed_tools": ["recipe--application_data_v1"]})
            self.assertEqual(action["code"].count('callTool("recipe--application_data_v1"'), 1)
            for forbidden in ("organization_id", "application_id", "caller_id", "owner_user_id:input", "admin_recovery", "create_account"):
                self.assertNotIn(forbidden, action["code"])
        raw = " ".join(p.read_text(encoding="utf-8").lower() for p in MODULE.rglob("*.json"))
        for legal in ("factur-x", "facturx", "peppol", "ubl"):
            self.assertNotIn(legal, raw)

    def test_go_template_actions_are_only_the_input_binding(self):
        self.assertEqual(SAVE["actions"][0]["code"].count("{{"), 1)
        self.assertIn("const input = {{ json . }};", SAVE["actions"][0]["code"])
        self.assertNotIn("{{", READ["actions"][0]["code"])

    def test_save_is_cib_admin_only_and_read_is_not_gated(self):
        surface = {"workflows": [{"workflow_id": "cib-admin-profile-save", "agent_id": "a"}, {"workflow_id": "cib-profile-read", "agent_id": "a"}]}
        gated = service_roles.prepare(surface, {"agents": [{"agent_id": "a", "agent_alias": "admin"}]})["public_surface"]["workflows"]
        self.assertEqual({w["workflow_id"]: w.get("required_role") for w in gated}, {"cib-admin-profile-save": "cib_admin", "cib-profile-read": None})

    def test_console_events_target_existing_workflows_and_cover_every_field(self):
        form = {f["name"] for f in SAVE["forms"][0]["fields"]}
        events = {e["event_id"]: e for e in CONSOLE["events"]}
        self.assertEqual(events["read"]["workflow"]["workflow_id"], "cib-profile-read")
        self.assertEqual(events["save"]["workflow"]["workflow_id"], "cib-admin-profile-save")
        self.assertEqual(set(events["save"]["workflow"]["input"]), form)
        self.assertTrue(form <= set(CONSOLE["state_schema"]["properties"]) and form <= set(CONSOLE["initial_state"]))
        self.assertEqual(CONSOLE["initial_state"]["confirmation_manuelle"], "false")
        for name in ("legal_name", "bank_iban", "bank_bic", "color_primary", "color_background", "logo_ref", "logo_alt"):
            self.assertIn(name, form)
        self.assertNotIn("upload", json.dumps(CONSOLE).lower().replace("uploading a logo is not available", ""))


class ReadTest(unittest.TestCase):
    def test_projection_is_the_body_plus_the_derived_logo(self):
        out = read(BODY)
        self.assertNotIn("error", out)
        result = out["result"]
        profile = result["profile"]
        self.assertEqual(contract_errors(profile), [])
        self.assertEqual(profile["brand"], BODY["brand"])
        self.assertEqual({k: v for k, v in profile["company"].items() if k != "logo"}, BODY["company"])
        self.assertEqual(profile["company"]["logo"], {"ref": BODY["brand"]["logo"]["ref"]})
        self.assertEqual((result["found"], result["revision"], result["body"]), (True, 3, BODY))
        self.assertEqual(out["calls"], [{"name": "recipe--application_data_v1", "args": {"operation": "read", "namespace": "cib-profile", "record_key": "company-profile"}}])

    def test_minimal_profile_has_no_bank_and_still_validates(self):
        profile = read(MINIMAL)["result"]["profile"]
        self.assertNotIn("bank", profile["company"])
        self.assertEqual(contract_errors(profile), [])

    def test_logo_is_single_source(self):
        stored = json.loads(json.dumps(BODY))
        stored["company"]["logo"] = {"ref": "storage://other/logo.svg"}
        self.assertEqual(read(stored)["error"], "company_logo_derived_from_brand")

    def test_stored_body_is_revalidated(self):
        for mutate, error in (
            (lambda b: b["company"]["bank"].update(iban="FR76"), "iban_invalid"),
            (lambda b: b["company"]["bank"].update(iban="FR7600000000000000000000000\n"), "stored_body_not_canonical"),
            (lambda b: b["brand"]["colors"].update(primary="red"), "color_primary_invalid"),
            (lambda b: b["brand"]["logo"].update(ref="logo.svg"), "logo_ref_invalid"),
            (lambda b: b.update(schema_version=2), "body_schema_invalid"),
            (lambda b: b["company"].update(extra="x"), "company_unknown_field"),
        ):
            stored = json.loads(json.dumps(BODY))
            mutate(stored)
            self.assertEqual(read(stored)["error"], error)

    def test_broker_shape_errors(self):
        wrong = record(BODY)
        wrong["data"]["record"]["namespace"] = "cib-cases"
        self.assertEqual(run_workflow(READ, {}, {"response": wrong})["error"], "broker_record_identity_invalid")
        wrong = record(BODY)
        wrong["data"]["record"]["permissions"] = {}
        self.assertEqual(run_workflow(READ, {}, {"response": wrong})["error"], "broker_permissions_invalid")

    def test_only_the_explicit_not_found_code_means_no_profile_yet(self):
        for scenario in ({"throw": {"code": "NOT_FOUND", "message": "application data record not found"}}, {"response": {"error": {"code": "NOT_FOUND"}}}):
            result = run_workflow(READ, {}, scenario)["result"]
            self.assertEqual((result["found"], result["revision"], result["profile"]), (False, 0, None))
            self.assertEqual(result["effects"][0]["payload"]["prefill"]["expected_revision"], "0")

    def test_every_other_broker_outcome_is_an_explicit_error(self):
        cases = (
            ({"throw": {"code": "PERMISSION_DENIED", "message": "permission_denied"}}, "permission_denied"),
            ({"throw": {"message": "record_not_found"}}, "record_not_found"),
            ({"throw": {"message": "boom"}}, "boom"),
            ({"throw": {"code": "NOT_FOUND_OTHER", "message": "application not found"}}, "application not found"),
            ({"response": {"error": {"code": "PERMISSION_DENIED"}}}, "broker_error_permission_denied"),
            ({"response": {"error": {}}}, "broker_error_unknown"),
            ({"response": {}}, "broker_record_identity_invalid"),
            ({"response": {"data": {}}}, "broker_record_identity_invalid"),
            ({"response": {"data": {"record": None}}}, "broker_record_identity_invalid"),
            ({"response": None}, "broker_record_identity_invalid"),
            ({"response": "ok"}, "broker_record_identity_invalid"),
        )
        for scenario, error in cases:
            out = run_workflow(READ, {}, scenario)
            self.assertNotIn("result", out, scenario)
            self.assertEqual(out["error"], error, scenario)

    def test_save_never_reports_a_missing_record_as_success(self):
        for scenario, error in (({"throw": {"code": "NOT_FOUND", "message": "gone"}}, "gone"), ({"response": {}}, "broker_record_identity_invalid"),
                                ({"response": {"error": {"code": "PERMISSION_DENIED"}}}, "broker_error_permission_denied")):
            out = run_workflow(SAVE, fields_input(), scenario)
            self.assertEqual((out.get("error"), "result" in out), (error, False), scenario)

    def test_projection_is_the_body_up_to_the_logo_derivation(self):
        for body in (BODY, MINIMAL):
            profile = read(body)["result"]["profile"]
            expected_company = json.loads(json.dumps(body["company"]))
            expected_company["logo"] = {"ref": body["brand"]["logo"]["ref"]}
            self.assertEqual(profile, {"company": expected_company, "brand": body["brand"]})
        self.assertEqual(read(MINIMAL)["result"]["profile"]["company"], {"legal_name": "Atelier Minimal", "logo": {"ref": "storage://company-profile/logo.svg"}})

    def test_a_stored_body_is_projected_as_is_or_refused(self):
        for mutate in (lambda b: b["company"].update(trade_name=""), lambda b: b["company"].update(legal_name=" Atelier "), lambda b: b["company"]["bank"].update(iban="fr7600000000000000000000000"),
                       lambda b: b["brand"]["fonts"]["body"].update(family="Libertinus Serif "), lambda b: b["company"].update(address={})):
            stored = json.loads(json.dumps(BODY))
            mutate(stored)
            self.assertEqual(read(stored)["error"], "stored_body_not_canonical")

    def test_color_preview_has_contrast(self):
        preview = {row["token"]: row for row in read(BODY)["result"]["color_preview"]}
        self.assertEqual(list(preview), ["primary", "secondary", "accent", "text", "muted", "background"])
        self.assertEqual(preview["background"]["contrast_on_background"], 1)
        self.assertGreater(preview["text"]["contrast_on_background"], 15)


class SaveTest(unittest.TestCase):
    def save(self, **overrides):
        return run_workflow(SAVE, fields_input(**overrides), {"mode": "echo-save"})

    def test_round_trip_saves_the_exact_body_with_expected_revision(self):
        out = self.save()
        self.assertNotIn("error", out)
        (call,) = out["calls"]
        self.assertEqual(call["args"], {"operation": "save", "namespace": "cib-profile", "record_key": "company-profile", "data": BODY, "expected_revision": 3})
        self.assertEqual(out["result"]["revision"], 4)
        self.assertEqual(contract_errors(out["result"]["profile"]), [])

    def test_minimal_round_trip(self):
        out = run_workflow(SAVE, fields_input(MINIMAL), {"mode": "echo-save"})
        self.assertEqual(out["calls"][0]["args"]["data"], MINIMAL)

    def test_creation_with_revision_zero(self):
        self.assertEqual(self.save(expected_revision="0")["calls"][0]["args"]["expected_revision"], 0)

    def test_manual_confirmation_and_revision_are_required(self):
        for override, error in (({"confirmation_manuelle": "false"}, "manual_confirmation_required"), ({"confirmation_manuelle": "oui"}, "manual_confirmation_required"),
                                ({"confirmation_manuelle": ""}, "manual_confirmation_required"), ({"expected_revision": ""}, "expected_revision_required"),
                                ({"expected_revision": "-1"}, "expected_revision_invalid"), ({"expected_revision": "x"}, "expected_revision_invalid")):
            out = self.save(**override)
            self.assertEqual((out["error"], out["calls"]), (error, []), override)

    def test_iban_and_bic_are_normalised_then_checked(self):
        out = self.save(bank_iban="fr76 0000 0000 0000 0000 0000 000", bank_bic="exmp frpp")
        self.assertEqual(out["calls"][0]["args"]["data"]["company"]["bank"]["iban"], "FR7600000000000000000000000")
        self.assertEqual(out["calls"][0]["args"]["data"]["company"]["bank"]["bic"], "EXMPFRPP")
        for override, error in (({"bank_iban": "FR76"}, "iban_invalid"), ({"bank_iban": "FR76" + "0" * 31}, "iban_invalid"), ({"bank_iban": "1R7600000000000000000000000"}, "iban_invalid"),
                                ({"bank_bic": "EXMP-FR"}, "bic_invalid")):
            out = self.save(**override)
            self.assertEqual((out["error"], out["calls"]), (error, []), override)

    def test_bank_is_optional(self):
        out = self.save(bank_iban="", bank_bic="", bank_account_holder="", bank_name="")
        self.assertNotIn("bank", out["calls"][0]["args"]["data"]["company"])

    def test_field_validation_refuses_before_any_broker_call(self):
        for override, error in (({"legal_name": ""}, "legal_name_required"), ({"color_primary": "blue"}, "color_primary_invalid"), ({"color_background": ""}, "color_background_invalid"),
                                ({"logo_ref": "logo.svg"}, "logo_ref_invalid"), ({"logo_ref": "storage://a/../b.svg"}, "logo_ref_invalid"), ({"logo_ref": "https://example.invalid/logo.svg"}, "logo_ref_invalid"),
                                ({"logo_alt": ""}, "logo_alt_required"), ({"page_size": "A3"}, "page_size_invalid"), ({"margin_top": "-1"}, "margin_top_invalid"),
                                ({"margin_left": "abc"}, "margin_left_invalid"), ({"address_city": ""}, "address_city_required"), ({"font_body": ""}, "font_body_required")):
            out = self.save(**override)
            self.assertEqual((out["error"], out["calls"]), (error, []), override)

    def test_logo_is_set_only_through_brand(self):
        out = run_workflow(SAVE, {**fields_input(), "company_logo": "storage://x/y.svg"}, {"mode": "echo-save"})
        self.assertNotIn("logo", out["calls"][0]["args"]["data"]["company"])

    def test_forged_identity_fields_are_ignored(self):
        out = run_workflow(SAVE, {**fields_input(), "owner_user_id": "forged", "organization_id": "forged", "admin_recovery": True}, {"mode": "echo-save"})
        self.assertEqual(set(out["calls"][0]["args"]), {"operation", "namespace", "record_key", "data", "expected_revision"})

    def test_a_conflict_from_the_broker_is_not_swallowed(self):
        out = run_workflow(SAVE, fields_input(), {"throw": "revision_conflict"})
        self.assertEqual(out["error"], "revision_conflict")

    def test_stored_response_is_revalidated(self):
        stored = json.loads(json.dumps(BODY))
        stored["brand"]["colors"]["accent"] = "oops"
        out = run_workflow(SAVE, fields_input(), {"mode": "echo-save", "stored": stored})
        self.assertEqual(out["error"], "color_accent_invalid")


class ComposeTest(unittest.TestCase):
    def consumer(self, directory):
        consumer = Path(directory)
        spec = consumer / "agents/admin/agent-spec.json"
        spec.parent.mkdir(parents=True)
        spec.write_text(json.dumps({"schema_version": 2, "agent_alias": "admin", "agent_id": "abcdefghijklmnopqrst"}))
        return consumer

    def test_plan_for_a_clean_consumer(self):
        with tempfile.TemporaryDirectory() as directory:
            planned = compose.compose(self.consumer(directory), "admin")
            self.assertEqual(len(planned), 3)

    def test_rejects_traversal_alias_bad_identity_and_divergence(self):
        with tempfile.TemporaryDirectory() as directory:
            consumer = self.consumer(directory)
            with self.assertRaises(ValueError):
                compose.compose(consumer, "../outside")
            target = consumer / "agents/admin/workflows/cib-profile-read.json"
            target.parent.mkdir(parents=True)
            target.write_text("{}")
            with self.assertRaises(ValueError):
                compose.compose(consumer, "admin")
            target.write_bytes((MODULE / "agents/main/workflows/cib-profile-read.json").read_bytes())
            self.assertEqual(len(compose.compose(consumer, "admin")), 3)
        with tempfile.TemporaryDirectory() as directory:
            consumer = Path(directory)
            spec = consumer / "agents/admin/agent-spec.json"
            spec.parent.mkdir(parents=True)
            spec.write_text(json.dumps({"schema_version": 2, "agent_alias": "other", "agent_id": "abcdefghijklmnopqrst"}))
            with self.assertRaises(ValueError):
                compose.compose(consumer, "admin")

    def test_composed_surface_declares_cib_admin_on_save_and_not_on_read(self):
        with tempfile.TemporaryDirectory() as directory:
            consumer = self.consumer(directory)
            subprocess.run([sys.executable, str(TOOLING / "compose.py"), "--consumer-dir", str(consumer), "--owner-alias", "admin", "--write"], check=True, capture_output=True)
            draft = load(consumer / "surface-drafts/cib-profile.surface-draft.json")["public_surface"]
            workflows = {w["workflow_id"]: w for w in draft["workflows"]}
            self.assertEqual(workflows["cib-admin-profile-save"]["required_role"], "cib_admin")
            self.assertNotIn("required_role", workflows["cib-profile-read"])
            self.assertEqual({w["agent_id"] for w in draft["workflows"]}, {"abcdefghijklmnopqrst"})
            self.assertEqual([m["miniapp_id"] for m in draft["miniapps"]], ["cib-profile-console"])
            self.assertTrue((consumer / "agents/admin/workflows/cib-admin-profile-save.json").is_file())
            # idempotent, and a divergent draft is refused
            compose.apply(consumer, "admin")
            (consumer / "surface-drafts/cib-profile.surface-draft.json").write_text("{}\n")
            with self.assertRaises(ValueError):
                compose.apply(consumer, "admin")

    def test_plan_mode_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            consumer = self.consumer(directory)
            proc = subprocess.run([sys.executable, str(TOOLING / "compose.py"), "--consumer-dir", str(consumer)], check=True, capture_output=True, text=True)
            self.assertIn("required_role on save", proc.stdout)
            self.assertFalse((consumer / "surface-drafts").exists())

    def test_the_gate_file_names_only_provided_workflows_and_only_save(self):
        gates = load(TOOLING / "service-gates.json")["workflows"]
        self.assertEqual(gates, {"cib-admin-profile-save": "cib_admin"})

    def test_workflow_code_cannot_see_roles_and_ignores_a_forged_one(self):
        # The role is enforced by the platform on the published surface and revalidated by the broker; the code gets
        # no caller identity. A non-admin call is refused before the code runs, which a mocked broker cannot show;
        # here we only prove the code never trusts a role sent in its input.
        code = SAVE["actions"][0]["code"]
        self.assertNotIn("cib_admin", code)
        out = run_workflow(SAVE, {**fields_input(), "role": "cib_admin", "roles": ["cib_admin"], "required_role": "cib_admin"}, {"mode": "echo-save"})
        self.assertEqual(set(out["calls"][0]["args"]), {"operation", "namespace", "record_key", "data", "expected_revision"})
        refused = run_workflow(SAVE, fields_input(), {"throw": {"code": "PERMISSION_DENIED", "message": "required_role_missing"}})
        self.assertEqual((refused["error"], "result" in refused), ("required_role_missing", False))


if __name__ == "__main__":
    unittest.main()
