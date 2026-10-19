#!/usr/bin/env python3
"""Compose the real Marketing launch resources into an existing Agent Spec.

This packager is strict and offline. It never invents Workflows or MiniApps,
calls MauriceCLI, starts One, or deploys anything.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

WORKFLOW_IDS = (
    "cib-launch-campaign-save", "cib-launch-content-link", "cib-launch-request",
    "cib-launch-progress", "cib-launch-read", "cib-launch-list",
    "cib-launch-people", "cib-launch-share", "cib-launch-summary",
)
MINIAPP_IDS = (
    "cib-launch-campaign-console", "cib-launch-content-console",
    "cib-launch-request-console", "cib-launch-support-console",
    "cib-launch-sharing-console", "cib-launch-direction-console",
)
ALIAS_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
AGENT_ID_RE = re.compile(r"^[a-z0-9]{20}$")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def encoded(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def validate_spec(path: Path, alias: str, errors: list[str]) -> None:
    if not path.exists():
        errors.append(f"missing Agent Spec V2: {path}")
        return
    try:
        spec = load_json(path)
    except ValueError as exc:
        errors.append(str(exc))
        return
    if spec.get("$schema") != "agentmaurice.agent_spec/v2" or spec.get("schema_version") != 2:
        errors.append(f"consumer spec is not Agent Spec V2: {path}")
    if spec.get("agent_alias") != alias or not ALIAS_RE.fullmatch(alias):
        errors.append(f"invalid consumer agent_alias: {alias!r}")
    agent_id = spec.get("agent_id")
    if not isinstance(agent_id, str) or not AGENT_ID_RE.fullmatch(agent_id):
        errors.append(f"consumer agent_id must be 20 lowercase base32-like characters: {path}")


def resource_files(source_root: Path, errors: list[str]) -> list[tuple[Path, bytes, str]]:
    source = source_root / "module" / "agents" / "main"
    if not source.is_dir():
        errors.append(f"missing real resource source: {source}")
        return []
    found = {path.relative_to(source).as_posix(): path for path in source.rglob("*.json") if path.is_file()}
    expected = {f"workflows/{item}.json" for item in WORKFLOW_IDS} | {f"miniapps/{item}.json" for item in MINIAPP_IDS}
    for item in sorted(expected - found.keys()):
        errors.append(f"missing required resource: {source / item}")
    for item in sorted(set(found) - expected):
        errors.append(f"unexpected resource (strict 15-file module): {source / item}")
    result: list[tuple[Path, bytes, str]] = []
    for relative in sorted(expected):
        path = found.get(relative)
        if path is None:
            continue
        try:
            content = path.read_bytes()
            document = json.loads(content.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid resource {path}: {exc}")
            continue
        expected_id = Path(relative).stem
        actual_id = document.get("workflow_id" if relative.startswith("workflows/") else "miniapp_id")
        if actual_id != expected_id:
            errors.append(f"resource ID mismatch: {path} expected {expected_id!r}, got {actual_id!r}")
        result.append((path, content, relative))
    return result


def merged_plan(source_root: Path, destination: Path, errors: list[str]) -> tuple[bytes, bool] | None:
    source = source_root / "module" / "test-plan.json"
    if not source.is_file():
        errors.append(f"missing real test plan: {source}")
        return None
    try:
        incoming = load_json(source)
    except ValueError as exc:
        errors.append(str(exc))
        return None
    if incoming.get("$schema") != "agentmaurice.test_plan/v2" or incoming.get("schema_version") != 2 or not isinstance(incoming.get("cases"), list):
        errors.append(f"invalid test plan V2: {source}")
        return None
    if not destination.exists():
        return encoded(incoming), False
    try:
        existing = load_json(destination)
    except ValueError as exc:
        errors.append(str(exc))
        return None
    prior = existing.get("cases")
    if existing.get("$schema") != "agentmaurice.test_plan/v2" or existing.get("schema_version") != 2 or not isinstance(prior, list):
        errors.append(f"invalid existing test plan V2: {destination}")
        return None
    prior_by_id = {case.get("id"): case for case in prior if isinstance(case, dict)}
    incoming_ids = [case.get("id") for case in incoming["cases"] if isinstance(case, dict)]
    if len(incoming_ids) != len(set(incoming_ids)):
        errors.append(f"duplicate incoming test case ID: {source}")
        return None
    additions = []
    for case in incoming["cases"]:
        case_id = case.get("id") if isinstance(case, dict) else None
        if case_id in prior_by_id:
            if prior_by_id[case_id] != case:
                errors.append(f"test plan case divergence (refusing merge): {destination}#{case_id}")
        else:
            additions.append(case)
    merged = dict(existing)
    merged["cases"] = prior + additions
    return encoded(merged), True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer-dir", required=True, type=Path)
    parser.add_argument("--agent-alias", required=True)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    if not ALIAS_RE.fullmatch(args.agent_alias):
        errors.append(f"invalid --agent-alias: {args.agent_alias!r}")
    consumer = args.consumer_dir.resolve()
    source_root = args.source_root.resolve()
    agent = consumer / "agents" / args.agent_alias
    validate_spec(agent / "agent-spec.json", args.agent_alias, errors)
    resources = resource_files(source_root, errors)
    plan = merged_plan(source_root, agent / "tests" / "test-plan.json", errors)
    planned: list[tuple[bytes, Path, str]] = [(content, agent / relative, "resource") for _, content, relative in resources]
    if plan is not None:
        content, is_merge = plan
        planned.append((content, agent / "tests" / "test-plan.json", "test-plan-merge" if is_merge else "test-plan"))
    # All validation and conflict checks finish before any write.
    for content, destination, kind in planned:
        if destination.exists() and kind == "resource" and destination.read_bytes() != content:
            errors.append(f"destination conflict (refusing overwrite): {destination}")
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 2
    print(f"consumer: {consumer}")
    print(f"agent_alias: {args.agent_alias}")
    print(f"mode: {'write' if args.write else 'dry-run'}")
    print("runtime: no CLI, no deploy, no apply")
    for content, destination, kind in planned:
        state = "absent" if not destination.exists() else ("merge" if kind == "test-plan-merge" else "identical")
        print(f"{destination} [{state}] sha256={sha256(content)}")
        if args.write:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            if destination.read_bytes() != content:
                print(f"ERROR copy verification failed: {destination}", file=sys.stderr)
                return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
