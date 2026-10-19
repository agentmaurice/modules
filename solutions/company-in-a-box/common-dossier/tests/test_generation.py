import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("common_case_build", ROOT / "build.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class GenerationTest(unittest.TestCase):
    def test_generator_contract_is_native_acl(self):
        module = BUILD.MODULE / "module.yaml"
        self.assertEqual("0.2.2", json.loads(module.read_text())["version"])
        workflows = sorted((BUILD.MODULE / "agents/main/workflows").glob("*.json"))
        miniapps = sorted((BUILD.MODULE / "agents/main/miniapps").glob("*.json"))
        self.assertEqual(6, len(workflows))
        self.assertEqual(2, len(miniapps))
        for path in workflows:
            value = json.loads(path.read_text())
            text = path.read_text()
            self.assertEqual("workflow", value["kind"])
            self.assertNotRegex(text, r"read_file|write_file|list_files")
            broker_actions = [a for a in value["actions"] if a.get("context", {}).get("allowed_tools")]
            if path.name != "cib-direction-brief.json":
                self.assertTrue(broker_actions, path.name)
                self.assertTrue(all(BUILD.BROKER in a["context"]["allowed_tools"] for a in broker_actions))
        self.assertIn("cib-case-share", {json.loads(p.read_text())["workflow_id"] for p in workflows})
        self.assertIn("cib-case-people", {json.loads(p.read_text())["workflow_id"] for p in workflows})

    def test_selection_prefill_and_cas_state_are_declared(self):
        read = json.loads((BUILD.MODULE / "agents/main/workflows/cib-case-read.json").read_text())
        self.assertIn("effects", read["output"])
        self.assertIn("open_form", read["actions"][1]["code"])
        save = json.loads((BUILD.MODULE / "agents/main/workflows/cib-case-save.json").read_text())
        self.assertTrue(all("default" in field for field in save["forms"][0]["fields"]))
        manual = {field["name"]: field["default"] for field in save["forms"][0]["fields"] if field["name"] in {"revue_manuelle", "confirmation_manuelle"}}
        self.assertEqual({"revue_manuelle": "non", "confirmation_manuelle": "non"}, manual)
        self.assertIn('revue_manuelle:"non",confirmation_manuelle:"non"', read["actions"][1]["code"])
        console = json.loads((BUILD.MODULE / "agents/main/miniapps/cib-case-console.json").read_text())
        events = {event["event_id"]: event for event in console["events"]}
        self.assertEqual("{{ state.selected.revision }}", events["save"]["workflow"]["input"]["expected_revision"])
        self.assertEqual("selected", events["save"]["result_to_state"])
        self.assertEqual("selected", events["share"]["result_to_state"])
        self.assertEqual("{{ state.people.selected_target.user_id }}", events["share"]["workflow"]["input"]["subject_user_id"])
        brief = json.loads((BUILD.MODULE / "agents/main/workflows/cib-direction-brief.json").read_text())
        self.assertEqual("code_execution", brief["actions"][0]["type"])
        self.assertEqual([BUILD.BROKER], brief["actions"][0]["context"]["allowed_tools"])

    def test_acl_metadata_has_primitive_render_contract(self):
        for name in ("cib-case-read", "cib-case-save", "cib-case-share"):
            workflow = json.loads((BUILD.MODULE / "agents/main/workflows" / f"{name}.json").read_text())
            output = workflow["output"]
            self.assertIn("permissions_summary", output)
            self.assertIn("share_count", output)
        for path in (BUILD.MODULE / "agents/main/miniapps").glob("*.json"):
            value = json.loads(path.read_text())
            layout = json.dumps(value["ui"]["configuration"]["layout"])
            self.assertNotIn('"state": "selected.permissions"', layout)
            self.assertNotIn('"state": "selected.shares"', layout)
            selected = value["initial_state"]["selected"]
            self.assertIsInstance(selected["permissions_summary"], str)
            self.assertIsInstance(selected["share_count"], int)


if __name__ == "__main__":
    unittest.main()
