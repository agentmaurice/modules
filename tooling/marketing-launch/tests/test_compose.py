#!/usr/bin/env python3
"""Offline contract tests for the Marketing composeur.

These tests never invoke MauriceCLI, a One, deploy, apply, or a network
endpoint.  They exercise creation, idempotent planning, conflict refusal, and
preservation of an unrelated consumer file.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.py"


def load_compose():
    spec = importlib.util.spec_from_file_location("marketing_compose", COMPOSE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load compose.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_consumer(root: Path) -> Path:
    agent = root / "agents" / "veille"
    agent.mkdir(parents=True)
    (agent / "agent-spec.json").write_text(
        json.dumps({
            "$schema": "agentmaurice.agent_spec/v2",
            "schema_version": 2,
            "agent_alias": "veille",
            "agent_id": "abcdefghijklmnopqrst",
        }) + "\n",
        encoding="utf-8",
    )
    return root


def run_compose(consumer: Path, *extra: str, source_root: Path = ROOT.parents[1] / "marketing-launch") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(COMPOSE), "--consumer-dir", str(consumer),
         "--agent-alias", "veille", "--source-root", str(source_root), *extra],
        text=True,
        capture_output=True,
        check=False,
    )


class ComposeContractTest(unittest.TestCase):
    def make_source(self, root: Path) -> Path:
        compose = load_compose()
        main = root / "agents" / "main"
        (main / "workflows").mkdir(parents=True)
        (main / "miniapps").mkdir(parents=True)
        for resource_id in compose.WORKFLOW_IDS:
            (main / "workflows" / f"{resource_id}.json").write_text(
                json.dumps({"kind": "workflow", "workflow_id": resource_id}) + "\n",
                encoding="utf-8",
            )
        for resource_id in compose.MINIAPP_IDS:
            (main / "miniapps" / f"{resource_id}.json").write_text(
                json.dumps({"kind": "miniapp", "miniapp_id": resource_id}) + "\n",
                encoding="utf-8",
            )
        module = root.parent / "templates/company-in-a-box/tests"
        module.mkdir(parents=True, exist_ok=True)
        (module / "marketing-launch-plan.json").write_text(json.dumps({
            "$schema": "agentmaurice.test_plan/v2",
            "schema_version": 2,
            "test_plan_id": "cib-launch-marketing",
            "cases": [{
                "id": "offline-contract",
                "description": "offline contract",
                "workflow": {"workflow_id": compose.WORKFLOW_IDS[0]},
                "assertions": [{"type": "status", "expected": "failed"}],
            }],
        }) + "\n", encoding="utf-8")
        return root

    def test_clean_write_creates_owned_resources_and_preserves_unrelated_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            consumer = make_consumer(root / "consumer")
            source = self.make_source(root / "source")
            unrelated = consumer / "agents" / "veille" / "KEEP.txt"
            unrelated.write_text("preserve me\n", encoding="utf-8")

            result = run_compose(consumer, "--write", source_root=source)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("runtime: no CLI, no deploy, no apply", result.stdout)
            self.assertTrue((consumer / "agents/veille/workflows/cib-launch-campaign-save.json").is_file())
            self.assertTrue((consumer / "agents/veille/miniapps/cib-launch-campaign-console.json").is_file())
            self.assertTrue((consumer / "agents/veille/tests/test-plan.json").is_file())
            self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve me\n")

    def test_dry_run_is_identical_for_existing_owned_resource_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            consumer = make_consumer(root / "consumer")
            source = self.make_source(root / "source")
            target = consumer / "agents" / "veille" / "workflows" / "cib-launch-campaign-save.json"
            target.parent.mkdir(parents=True)
            target.write_bytes((source / "agents/main/workflows/cib-launch-campaign-save.json").read_bytes())
            sentinel = consumer / "agents" / "veille" / "untouched.txt"
            sentinel.write_text("keep\n", encoding="utf-8")

            result = run_compose(consumer, source_root=source)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("mode: dry-run", result.stdout)
            self.assertIn("[identical]", result.stdout)
            self.assertFalse((consumer / "agents/veille/tests/test-plan.json").exists())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_divergent_owned_resource_is_refused_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            consumer = make_consumer(root / "consumer")
            source = self.make_source(root / "source")
            target = consumer / "agents" / "veille" / "workflows" / "cib-launch-campaign-save.json"
            target.parent.mkdir(parents=True)
            target.write_text('{"local":"change"}\n', encoding="utf-8")
            before = target.read_bytes()
            sentinel = consumer / "agents" / "veille" / "untouched.txt"
            sentinel.write_text("keep\n", encoding="utf-8")

            result = run_compose(consumer, source_root=source)

            self.assertEqual(result.returncode, 2)
            self.assertIn("destination conflict", result.stderr)
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")
            self.assertFalse((consumer / "agents/veille/tests/test-plan.json").exists())

    def test_missing_source_fails_without_activity(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            consumer = make_consumer(root / "consumer")
            missing = root / "missing-source"
            result = run_compose(consumer, source_root=missing)
            self.assertEqual(result.returncode, 2)
            self.assertIn("source", result.stderr.lower())
            self.assertEqual(list((consumer / "agents" / "veille").rglob("*")), [
                consumer / "agents" / "veille" / "agent-spec.json",
            ])

    def test_exact_previous_resource_and_plan_upgrade_without_touching_other_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            consumer = make_consumer(Path(temp) / "consumer")
            agent = consumer / "agents/veille"
            target = agent / "workflows/cib-launch-read.json"
            target.parent.mkdir(parents=True)
            fixture = ROOT / "tests/fixtures/cib-launch-read-0.1.0.json"
            target.write_bytes(fixture.read_bytes())
            plan = json.loads((ROOT / "legacy-0.1.0-test-plan.json").read_text())
            plan['cases'].append({'id':'consumer-case','description':'preserve'})
            test_plan = agent / 'tests/test-plan.json'
            test_plan.parent.mkdir(parents=True)
            test_plan.write_text(json.dumps(plan))
            result = run_compose(consumer, '--write')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(target.read_text())['version'], '2')
            self.assertIn({'id':'consumer-case','description':'preserve'}, json.loads(test_plan.read_text())['cases'])
            target.write_bytes(fixture.read_bytes() + b' ')
            result = run_compose(consumer)
            self.assertEqual(result.returncode, 2)
            self.assertIn('destination conflict', result.stderr)

    def test_duplicate_existing_test_ids_refuse_upgrade(self):
        with tempfile.TemporaryDirectory() as temp:
            consumer = make_consumer(Path(temp) / 'consumer')
            plan = json.loads((ROOT / 'legacy-0.1.0-test-plan.json').read_text())
            plan['cases'].append(dict(plan['cases'][0]))
            target = consumer / 'agents/veille/tests/test-plan.json'
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps(plan))
            result = run_compose(consumer, '--write')
            self.assertEqual(result.returncode, 2)
            self.assertIn('duplicate existing test case ID', result.stderr)
            self.assertFalse((consumer / 'agents/veille/workflows/cib-launch-read.json').exists())


if __name__ == "__main__":
    unittest.main()
