"""Validate Company Memory local resource links without calling a One.

The public V2 for_each and MiniApp event contracts do not expose a version
field. Their versions are resolved by the backend compiler; this offline test
checks the source graph and must not be presented as compiler or runtime proof.
"""
import copy
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "company-memory" / "agents" / "main"


def load_resources():
    workflows = {}
    for path in (ROOT / "workflows").glob("*.json"):
        doc = json.loads(path.read_text())
        workflows[doc["workflow_id"]] = doc
    miniapps = [json.loads(path.read_text()) for path in (ROOT / "miniapps").glob("*.json")]
    return workflows, miniapps


def local_link_errors(workflows, miniapps):
    errors = []
    for parent_id, workflow in workflows.items():
        for action in workflow.get("actions", []):
            if action.get("type") not in {"workflow_call", "for_each"}:
                continue
            target = action.get("workflow_id")
            if target is None:  # A capability target belongs to another Agent.
                continue
            location = f"{parent_id}/{action.get('id')}"
            if action["type"] == "for_each" and "workflow_version" in action:
                errors.append(f"{location}: for_each forbids workflow_version")
            if target not in workflows:
                errors.append(f"{location}: missing {target}")
                continue
            version = action.get("workflow_version")
            if version is not None and version != workflows[target]["version"]:
                errors.append(f"{location}: {target}@{version} != {workflows[target]['version']}")
    for miniapp in miniapps:
        for event in miniapp.get("events", []):
            call = event.get("workflow", {})
            target = call.get("workflow_id")
            if target is None:
                continue
            location = f"{miniapp['miniapp_id']}/{event.get('event_id')}"
            if "workflow_version" in call:
                errors.append(f"{location}: MiniApp event forbids workflow_version")
            if target not in workflows:
                errors.append(f"{location}: missing {target}")
    return errors


class CompanyMemoryResourceLinksTest(unittest.TestCase):
    def test_shipped_local_graph_has_complete_consistent_links(self):
        workflows, miniapps = load_resources()
        self.assertEqual(len(workflows), 10)
        self.assertEqual(len(miniapps), 6)
        self.assertEqual(local_link_errors(workflows, miniapps), [])
        for parent, action_id, child, version in (
            ("memory-review-update", "write-supersession", "memory-write-supersession", "3"),
            ("memory-query", "read-marker", "memory-read-supersession", "2"),
        ):
            action = next(a for a in workflows[parent]["actions"] if a["id"] == action_id)
            self.assertEqual((action["type"], action["workflow_id"]), ("for_each", child))
            self.assertNotIn("workflow_version", action)
            self.assertEqual(workflows[child]["version"], version)

    def test_stale_pin_missing_target_and_unsupported_field_fail_closed(self):
        workflows, miniapps = load_resources()
        workflows = copy.deepcopy(workflows)
        miniapps = copy.deepcopy(miniapps)
        index = next(a for a in workflows["memory-index-revision"]["actions"] if a.get("workflow_id") == "memory-query")
        index["workflow_version"] = "7"
        marker = next(a for a in workflows["memory-query"]["actions"] if a.get("workflow_id") == "memory-read-supersession")
        marker["workflow_version"] = "2"
        miniapps[0]["events"][0]["workflow"]["workflow_id"] = "missing-workflow"
        errors = local_link_errors(workflows, miniapps)
        self.assertTrue(any("memory-query@7 != 8" in error for error in errors), errors)
        self.assertTrue(any("for_each forbids workflow_version" in error for error in errors), errors)
        self.assertTrue(any("missing missing-workflow" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
