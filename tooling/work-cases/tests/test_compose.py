import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("common_case_compose", ROOT / "compose.py")
COMPOSE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPOSE)


class ComposeTest(unittest.TestCase):
    def consumer(self):
        tmp = tempfile.TemporaryDirectory(prefix="cib-case-compose-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for alias in ("veille", "contenu", "accompagnement"):
            agent = root / "agents" / alias
            agent.mkdir(parents=True)
            (agent / "agent-spec.json").write_text(json.dumps({
                "schema_version": 2, "agent_alias": alias,
                "agent_id": "12345678901234567890", "dependencies": []}))
        return root

    def test_dry_run_preserves_specs_and_other_agents(self):
        root = self.consumer()
        before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
        planned = COMPOSE.compose(root)
        self.assertEqual(9, len(planned))
        self.assertTrue(all(p.is_relative_to(root / "agents/veille") for p in planned))
        self.assertEqual(before, {p: p.read_bytes() for p in root.rglob("*") if p.is_file()})
        for p, content in planned.items():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        self.assertEqual(planned, COMPOSE.compose(root))
        for p, content in before.items():
            self.assertEqual(content, p.read_bytes())

    def test_divergent_resource_refuses_before_partial_write(self):
        root = self.consumer()
        target = root / "agents/veille/workflows/cib-case-read.json"
        target.parent.mkdir()
        target.write_text("sentinel")
        with self.assertRaisesRegex(ValueError, "divergent"):
            COMPOSE.compose(root)
        self.assertEqual("sentinel", target.read_text())
        self.assertFalse((target.parent / "cib-case-save.json").exists())

    def test_exact_previous_bytes_are_accepted(self):
        root = self.consumer()
        target = root / "agents/veille/workflows/cib-case-read.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"known-0.1.2-placeholder")
        digest = COMPOSE.PREVIOUS_SHA256[Path("workflows/cib-case-read.json")]
        class Digest:
            def hexdigest(self):
                return digest
        with patch.object(COMPOSE.hashlib, "sha256", return_value=Digest()):
            planned = COMPOSE.compose(root)
        self.assertEqual(9, len(planned))

    def test_write_mode_updates_an_existing_planned_resource(self):
        root = self.consumer()
        target = root / "agents/veille/workflows/cib-case-read.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"old")
        planned = {target: b"new"}
        argv = ["compose.py", "--consumer-dir", str(root), "--write"]
        with patch.object(COMPOSE, "compose", return_value=planned), patch.object(sys, "argv", argv):
            COMPOSE.main()
        self.assertEqual(b"new", target.read_bytes())

    def test_upgrade_exact_022_resource_and_reject_modified_copy(self):
        root = self.consumer()
        target = root / "agents/veille/workflows/cib-case-read.json"
        target.parent.mkdir(parents=True)
        fixture = ROOT / "tests/fixtures/cib-case-read-0.2.2.json"
        target.write_bytes(fixture.read_bytes())
        planned = COMPOSE.compose(root)
        self.assertEqual(json.loads(planned[target])["version"], "3")
        target.write_bytes(fixture.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "divergent"):
            COMPOSE.compose(root)

    def test_owner_path_and_identity_are_validated(self):
        root = self.consumer()
        with self.assertRaisesRegex(ValueError, "invalid owner"):
            COMPOSE.compose(root, "../contenu")
        spec = root / "agents/veille/agent-spec.json"
        value = json.loads(spec.read_text())
        value["agent_alias"] = "different"
        spec.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "identity"):
            COMPOSE.compose(root)


if __name__ == "__main__":
    unittest.main()
