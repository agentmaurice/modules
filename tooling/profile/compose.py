#!/usr/bin/env python3
"""Dry-run composer for the profile Module resources; refuses divergence from a consumer Agent's files."""
from __future__ import annotations
import argparse, hashlib, json, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULE = ROOT.parents[1] / "profile"
RESOURCE_COUNT = 3
GATES = ROOT / "service-gates.json"
DRAFT_DIR = "surface-drafts"
DRAFT_NAME = "cib-profile.surface-draft.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose(consumer: Path, owner_alias: str = "admin"):
    """Plan the copy of the Module resources under the consumer Agent; an existing different file is a conflict."""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", owner_alias):
        raise ValueError("invalid owner alias")
    spec = json.loads((consumer / "agents" / owner_alias / "agent-spec.json").read_text(encoding="utf-8"))
    if spec.get("schema_version") != 2 or spec.get("agent_alias") != owner_alias or not re.fullmatch(r"[0-9a-v]{20}", spec.get("agent_id", "")):
        raise ValueError("consumer Agent identity mismatch")
    source = MODULE / "agents" / "main"
    resources = sorted(source.rglob("*.json"))
    if len(resources) != RESOURCE_COUNT:
        raise ValueError(f"expected exactly {RESOURCE_COUNT} Module resources, found {len(resources)}")
    planned = [(p, consumer / "agents" / owner_alias / p.relative_to(source)) for p in resources]
    for src, dst in planned:
        if dst.exists() and digest(dst) != digest(src):
            raise ValueError(f"refusing divergent resource: {dst} (expected sha256: {digest(src)})")
    return planned


def surface_draft(consumer: Path, owner_alias: str = "admin") -> dict:
    """Surface entries for the Module, with `required_role` carried explicitly (never left to a naming convention).

    The role lives in the published Application surface, which the platform checks at admission and the broker
    revalidates; the Workflow code cannot see the caller's roles. Only the Workflows listed in service-gates.json
    get a role; the others (read) carry none. Review the draft, merge it into the surface, then publish it.
    """
    spec = json.loads((consumer / "agents" / owner_alias / "agent-spec.json").read_text(encoding="utf-8"))
    gates = json.loads(GATES.read_text(encoding="utf-8"))["workflows"]
    manifest = json.loads((MODULE / "module.yaml").read_text(encoding="utf-8"))
    refs = manifest["provides"]["actions"] + manifest["provides"]["queries"]
    workflows = []
    for ref in refs:
        entry = {"agent_id": spec["agent_id"], "workflow_id": ref["workflow_id"], "version": ref["workflow_version"]}
        if ref["workflow_id"] in gates:
            entry["required_role"] = gates[ref["workflow_id"]]
        workflows.append(entry)
    if set(gates) - {w["workflow_id"] for w in workflows}:
        raise ValueError("service-gates.json names a Workflow the Module does not provide")
    miniapps = [{"agent_id": spec["agent_id"], "miniapp_id": a["miniapp_id"], "version": a["miniapp_version"]} for a in manifest["provides"]["apps"]]
    return {"public_surface": {"workflows": workflows, "miniapps": miniapps}}


def apply(consumer: Path, owner_alias: str = "admin"):
    """Copy the resources and write the surface draft; a differing existing file is a conflict, nothing is overwritten."""
    planned = compose(consumer, owner_alias)
    draft = json.dumps(surface_draft(consumer, owner_alias), indent=2) + "\n"
    target = consumer / DRAFT_DIR / DRAFT_NAME
    if target.exists() and target.read_text(encoding="utf-8") != draft:
        raise ValueError(f"refusing divergent surface draft: {target}")
    for src, dst in planned:
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(draft, encoding="utf-8")
    return planned, target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--consumer-dir", required=True, type=Path)
    p.add_argument("--owner-alias", default="admin")
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    consumer = a.consumer_dir.resolve()
    planned = compose(consumer, a.owner_alias)
    for src, dst in planned:
        print(("WRITE " if a.write else "PLAN ") + f"{src} -> {dst} [{'new' if not dst.exists() else 'identical'}]")
    print(("WRITE " if a.write else "PLAN ") + f"surface draft -> {consumer / DRAFT_DIR / DRAFT_NAME} (required_role on save)")
    if a.write:
        apply(consumer, a.owner_alias)
    print("No runtime mutation; no account creation, sharing, signing, deploy or publish. Merge the surface draft into the Application surface and publish it yourself.")


if __name__ == "__main__":
    main()
