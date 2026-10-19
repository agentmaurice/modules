import json
import tempfile
import unittest
from pathlib import Path

from importlib.util import module_from_spec, spec_from_file_location


ROOT = Path(__file__).resolve().parents[1]
SPEC = spec_from_file_location("daily_compose", ROOT / "compose.py")
COMPOSE = module_from_spec(SPEC)
SPEC.loader.exec_module(COMPOSE)


ROLES = ("veille", "contenu", "accompagnement")


class ComposeTest(unittest.TestCase):
    def consumer(self):
        tmp = tempfile.TemporaryDirectory(prefix="daily-compose-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for role in ROLES:
            agent = root / "agents" / role
            (agent / "workflows").mkdir(parents=True)
            (agent / "miniapps").mkdir()
            (agent / "agent-spec.json").write_text(json.dumps({"agent_alias": role, "schema_version": 2}))
            (agent / "workflows" / f"{role}-read.json").write_text("{}")
            (agent / "workflows" / "company-memory-query.json").write_text("{}")
        return root

    def materialize(self, planned):
        for path, content in planned.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def test_three_roles_are_identical_and_second_compose_is_idempotent(self):
        consumer = self.consumer()
        first = COMPOSE.compose(consumer)
        self.assertEqual(len(first), 3 * len(list((ROOT / "module" / "agents" / "main").rglob("*.json"))) + 3)
        self.materialize(first)
        second = COMPOSE.compose(consumer)
        self.assertEqual(first, second)
        for role in ROLES:
            bridge = json.loads((consumer / "agents" / role / "workflows" / "daily-role-read.json").read_text())
            self.assertEqual(bridge["workflow_id"], "daily-role-read")
            self.assertEqual(bridge["actions"][0]["type"], "code_execution")
            self.assertIn("recipe--application_data_v1", bridge["actions"][0]["code"])
            self.assertIn(f'namespace:"cib-{role}"',bridge["actions"][0]["code"])
            context=json.loads((consumer/"agents"/role/"workflows/daily-context.json").read_text())
            self.assertEqual(context["actions"][0]["type"], "code_execution")
            self.assertIn(f'namespace:"cib-{role}"',context["actions"][0]["code"])

        resources = [path.relative_to(ROOT / "module" / "agents" / "main") for path in (ROOT / "module" / "agents" / "main").rglob("*.json")]
        for resource in resources:
            copies = [(consumer / "agents" / role / resource).read_text().replace("cib-"+role,"cib-role") for role in ROLES]
            self.assertTrue(all(copy == copies[0] for copy in copies))

    def test_missing_dependency_refuses_before_any_write(self):
        consumer = self.consumer()
        missing = consumer / "agents" / "contenu" / "workflows" / "company-memory-query.json"
        missing.unlink()
        with self.assertRaisesRegex(ValueError, "missing existing workflow company-memory-query"):
            COMPOSE.compose(consumer)
        self.assertFalse((consumer / "agents" / "veille" / "workflows" / "daily-role-read.json").exists())

    def test_divergent_resource_refuses_without_overwrite(self):
        consumer = self.consumer()
        target = consumer / "agents" / "veille" / "workflows" / "daily-role-read.json"
        target.write_text("sentinel")
        with self.assertRaisesRegex(ValueError, "refusing divergent resource"):
            COMPOSE.compose(consumer)
        self.assertEqual(target.read_text(), "sentinel")

    def test_module_contains_only_bounded_local_primitives(self):
        forbidden = ("llm", "http", "cron", "schedule", "grant", "mcp")
        for path in (ROOT / "module").rglob("*.json"):
            text = path.read_text().lower()
            for word in forbidden:
                self.assertNotIn(word, text, f"{word} found in {path}")
            payload = json.loads(text)
            self.assertEqual(payload.get("external_effect"), False) if "external_effect" in payload else None


if __name__ == "__main__":
    unittest.main()
