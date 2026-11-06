#!/usr/bin/env python3
"""Dry-run composer for the profile Module resources; refuses divergence from a consumer Agent's files."""
from __future__ import annotations
import argparse, hashlib, json, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULE = ROOT.parents[1] / "profile"
RESOURCE_COUNT = 3


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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--consumer-dir", required=True, type=Path)
    p.add_argument("--owner-alias", default="admin")
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    for src, dst in compose(a.consumer_dir.resolve(), a.owner_alias):
        status = "new" if not dst.exists() else "identical"
        print(("WRITE " if a.write else "PLAN ") + f"{src} -> {dst} [{status}]")
        if a.write and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    print("No runtime mutation; no account creation, sharing, signing, deploy or publish.")


if __name__ == "__main__":
    main()
