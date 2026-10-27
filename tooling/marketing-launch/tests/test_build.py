#!/usr/bin/env python3
"""Offline determinism test for the Marketing Module generator."""

from __future__ import annotations

import os
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
