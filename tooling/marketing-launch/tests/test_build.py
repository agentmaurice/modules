#!/usr/bin/env python3
"""Offline determinism test for the Marketing Module generator."""

from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("build.py", "domain.js", "runtime.js")


def copy_sources(destination: Path) -> None:
    destination.mkdir(parents=True)
    for name in SOURCES:
        shutil.copy2(ROOT / name, destination / name)


def all_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


class BuildDeterminismTest(unittest.TestCase):
    def test_sharing_members_labels_preserve_wire_and_selection(self) -> None:
        resource = ROOT.parents[1] / "marketing-launch/agents/main/miniapps/cib-launch-sharing-console.json"
        miniapp = json.loads(resource.read_text())
        self.assertEqual(miniapp["version"], "2")
        table = next(item for item in miniapp["ui"]["configuration"]["layout"] if item.get("columns") == ["user_id", "display_name"])
        self.assertEqual(table["column_labels"], {"user_id": "Identifier", "display_name": "Member"})
        self.assertEqual(table["rows"], {"state": "people.people"})
        self.assertEqual(table["on_row_click"], "choose")
        choose = next(event for event in miniapp["events"] if event["event_id"] == "choose")
        self.assertEqual(choose["trigger"], "table.row_click")
        self.assertEqual(choose["workflow"]["workflow_id"], "cib-launch-people")
        self.assertEqual(choose["workflow"]["input"]["subject_user_id"], "{{ event.payload.item.user_id }}")

    def test_build_is_byte_deterministic_across_hash_seeds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "seed-1/tooling/marketing-launch"
            second = root / "seed-99/tooling/marketing-launch"
            copy_sources(first)
            copy_sources(second)

            for destination, seed in ((first, "1"), (second, "99")):
                environment = os.environ.copy()
                environment["PYTHONHASHSEED"] = seed
                result = subprocess.run(
                    [sys.executable, "build.py"],
                    cwd=destination,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

            first_files = all_files(first.parents[1])
            second_files = all_files(second.parents[1])
            self.assertEqual(set(first_files), set(second_files))
            for relative in sorted(first_files):
                self.assertEqual(first_files[relative], second_files[relative], relative)

            resources = [
                relative for relative in first_files
                if relative.startswith("marketing-launch/agents/main/") and relative.endswith(".json")
            ]
            self.assertEqual(len(resources), 15)
            self.assertIn("marketing-launch/module.yaml", first_files)
            self.assertIn("templates/company-in-a-box/tests/marketing-launch-plan.json", first_files)
            self.assertIn("tooling/marketing-launch/service-gates.json", first_files)


if __name__ == "__main__":
    unittest.main()
