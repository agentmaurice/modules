#!/usr/bin/env python3
"""Dry-run composer for the existing Agent; refuses divergence."""
from __future__ import annotations
import argparse, hashlib, json, re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULE = ROOT.parents[1] / "enterprise-admin"

# Bytes from the published 0.2.1 package. They are accepted only as an
# upgrade source; every other pre-existing destination is a manual conflict.
LEGACY_021_HASHES = {
    "module/module.yaml": "302c0df657eb26d9c5c961d1de1be5995ed953f7333a7ff3563df88254ed93cf",
    "module/agents/main/workflows/cib-admin-approval-check.json": "c85571946ab004b2c2336b91753360e991dc88bb2e5a673ce4ca051e493af2a8",
    "module/agents/main/workflows/cib-admin-import-record.json": "be538b17a3ccab818a3f346db3481c10c99a00fd0ed51940476b76f79b0682ca",
    "module/agents/main/workflows/cib-admin-manage.json": "4f4f81f41e76028e17b74186d81bc00d3652e3ad18d3cfe6a468f6fc94fc5290",
    "module/agents/main/workflows/cib-admin-overview.json": "e8e0d163dfd4a18ec047e53c54ac4a58c3830f8804a08383562c0fc65d8a50fe",
    "module/agents/main/miniapps/cib-admin-console.json": "f5af65b2c8561fb73db254846e6f72bb95e1fa03909ac13eed9d30d9d01aa56d",
    "module/agents/main/miniapps/cib-admin-records-console.json": "43a508c2f903d9453096a0ca0a1e8088be02da94f017f484ff13b1c9d0a96e7e",
    "module/agents/main/workflows/cib-admin-record-people.json": "7aeebd81653b2805a4ceb9adfd1d9e2c4e1a56949da74cf63a13b43392771e7b",
    "module/agents/main/workflows/cib-admin-record-read.json": "36f2d732708207c631e645deaed4866aeeb7e4dc0314fedb2e6cdfb31c26f8db",
    "module/agents/main/workflows/cib-admin-record-share.json": "fd589b6b4ab8fc074d859286d6869f7b30dfec919c8d845ed5f4366ab46b3258",
}

# Exact local 0.2.2 prequalification bytes, before removing an inert layout button.
PREQUAL_022_HASHES = {
    'module/agents/main/miniapps/cib-admin-record-share-console.json': 'c6e1625161d3a13b0c5510801ebc120e6b7b69a892cb29dd6d0bac3688340ed7',
}

def digest(path):
    h = hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()

def compose(consumer: Path, owner_alias: str = "veille"):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", owner_alias):
        raise ValueError("invalid owner alias")
    spec_path = consumer / "agents" / owner_alias / "agent-spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != 2 or spec.get("agent_alias") != owner_alias or not re.fullmatch(r"[0-9a-v]{20}", spec.get("agent_id", "")):
        raise ValueError("consumer Agent identity mismatch")
    source = MODULE / "agents" / "main"
    resources = sorted(source.rglob("*.json"))
    if len(resources) != 10:
        raise ValueError(f"expected exactly ten Module resources, found {len(resources)}")
    planned = [(p, consumer / "agents" / owner_alias / p.relative_to(source)) for p in resources]
    for src, dst in planned:
        if not dst.exists():
            continue
        actual = digest(dst)
        current = digest(src)
        relative = "module/" + src.relative_to(MODULE).as_posix()
        legacy = LEGACY_021_HASHES.get(relative)
        if actual not in {current, legacy, PREQUAL_022_HASHES.get(relative)}:
            expected = ", ".join(value for value in (current, legacy) if value)
            raise ValueError(f"refusing divergent resource: {dst} (expected sha256: {expected})")
    return planned

def main():
    p = argparse.ArgumentParser(); p.add_argument("--consumer-dir", required=True, type=Path); p.add_argument("--owner-alias", default="veille"); p.add_argument("--write", action="store_true"); a = p.parse_args()
    planned = compose(a.consumer_dir.resolve(), a.owner_alias)
    for src, dst in planned:
        status = "new" if not dst.exists() else ("identical" if digest(src) == digest(dst) else "upgrade from known Module fingerprint")
        print(("WRITE " if a.write else "PLAN ") + f"{src} -> {dst} [{status}]")
        if a.write and (not dst.exists() or digest(src) != digest(dst)):
            dst.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(src, dst)
    print("No runtime mutation; no account creation, email invitation, signing, deploy or publish.")

if __name__ == "__main__": main()
