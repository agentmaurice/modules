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

# Exact 0.2.2 resources before the language upgrade.
LEGACY_022_HASHES = {
    "module/agents/main/miniapps/cib-admin-console.json": "f5af65b2c8561fb73db254846e6f72bb95e1fa03909ac13eed9d30d9d01aa56d",
    "module/agents/main/miniapps/cib-admin-record-share-console.json": "7d25915d7fe535dd6adfbe4b5b18d5102a0f154f6b2b55a608a997e61b82a955",
    "module/agents/main/miniapps/cib-admin-records-console.json": "4f3b29d179b0381ddba6c8650ddba1b7a0f6d7751b20114667b4a7613f037911",
    "module/agents/main/workflows/cib-admin-record-read.json": "36f2d732708207c631e645deaed4866aeeb7e4dc0314fedb2e6cdfb31c26f8db",
    "module/agents/main/workflows/cib-admin-manage.json": "4f4f81f41e76028e17b74186d81bc00d3652e3ad18d3cfe6a468f6fc94fc5290",
    "module/agents/main/workflows/cib-admin-approval-check.json": "c85571946ab004b2c2336b91753360e991dc88bb2e5a673ce4ca051e493af2a8",
    "module/agents/main/workflows/cib-admin-import-record.json": "be538b17a3ccab818a3f346db3481c10c99a00fd0ed51940476b76f79b0682ca",
    "module/agents/main/workflows/cib-admin-record-people.json": "7aeebd81653b2805a4ceb9adfd1d9e2c4e1a56949da74cf63a13b43392771e7b",
    "module/agents/main/workflows/cib-admin-overview.json": "e8e0d163dfd4a18ec047e53c54ac4a58c3830f8804a08383562c0fc65d8a50fe",
    "module/agents/main/workflows/cib-admin-record-share.json": "fd589b6b4ab8fc074d859286d6869f7b30dfec919c8d845ed5f4366ab46b3258",
    "module/module.yaml": "b70c51ca0d95f494a49b349a9997ce328f8cd0f73ae9b2db92af57839e49f543"
}

# Exact local 0.2.2 prequalification bytes, before removing an inert layout button.
PREQUAL_022_HASHES = {
    'module/agents/main/miniapps/cib-admin-record-share-console.json': 'c6e1625161d3a13b0c5510801ebc120e6b7b69a892cb29dd6d0bac3688340ed7',
}

# Exact candidate bytes at source revision 4a1447d, accepted for upgrade while
# retaining the published and prequalification histories above.
CANDIDATE_4A_HASHES = {
    "module/module.yaml": "7cff6f9345fc142250d5653d5115334747c103c4cf22df8763fc7f3dcfb2ac41",
    "module/agents/main/miniapps/cib-admin-console.json": "2b049ef01f7a24916df8235a4768e8ec7f27a01e9ab0b316d0f7c11158997ddc",
    "module/agents/main/miniapps/cib-admin-record-share-console.json": "297ad0bb06cdb42e80c57642c633db9e58825adabca54f3e5c70deecc5f1ec41",
    "module/agents/main/miniapps/cib-admin-records-console.json": "386cc3ffc59d6351779dacf574fda2167b900f8d92eb742ebe54c48c3e730aee",
    "module/agents/main/workflows/cib-admin-approval-check.json": "6101bda7644845a6da708aab6415a56793ad8f8314d0020df672849fa1ac7f86",
    "module/agents/main/workflows/cib-admin-import-record.json": "8b149ff31b9da0a1deeb1ca3f4343efe539212136478aebd8394fca679631c9d",
    "module/agents/main/workflows/cib-admin-manage.json": "8ba4e8e2558a118dcc3302d939f2a6b38378b1f4369be645399fee3d1ea0524",
    "module/agents/main/workflows/cib-admin-overview.json": "3dbe1a1964ab8e3c4229b94f1b0a3ce46bc30e3e9bc9e3fe7059b23dd3964cd0",
    "module/agents/main/workflows/cib-admin-record-people.json": "f46e021f94b39cbc63ed3d7d7a8ccfd4fecf50d5be89bf118c583fc70e7dd985",
    "module/agents/main/workflows/cib-admin-record-read.json": "8f1157fc57b318fa68115310f3dd821252a8b58537081fec1cca06fa52fddf96",
    "module/agents/main/workflows/cib-admin-record-share.json": "c285276a3f37c5a3723143d6f170bcf7efe66805428ca40ccabf58aa948c20e8",
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
        if actual not in {current, legacy, LEGACY_022_HASHES.get(relative), PREQUAL_022_HASHES.get(relative), CANDIDATE_4A_HASHES.get(relative)}:
            expected = ", ".join(value for value in (current, legacy, LEGACY_022_HASHES.get(relative), PREQUAL_022_HASHES.get(relative), CANDIDATE_4A_HASHES.get(relative)) if value)
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
