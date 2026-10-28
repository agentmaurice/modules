#!/usr/bin/env python3
"""Compose the common dossier in one existing Agent; dry-run, no runtime call."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Exact 0.1.2 resources are the only divergent bytes accepted during an
# upgrade.  Any other destination content remains an explicit conflict.
PREVIOUS_SHA256 = {
    Path("miniapps/cib-case-console.json"): "2cd7221004d04579e54a04fa3d6d30c6b26d7c644758946c004fd28f1060b80c",
    Path("workflows/cib-case-read.json"): "4dc53a9e6400eb1d7e78f2fef578588bc268f50a2021ff1fe4e272b6468910f0",
    Path("workflows/cib-case-list.json"): "867e46c4dd1f2894c551bd7fe788435b7c711447acdab2716d1df4dfbeb61369",
    Path("workflows/cib-direction-brief.json"): "a3124e27c07aa4f10a203c49edf5ce0946e697ec34a8c0ac8902034ce7b55708",
    Path("workflows/cib-case-save.json"): "cf34f7d72a93f9037f2dbd49baf0eff3fbb0775f95a7646b26fa6372e1c19245",
    Path("miniapps/cib-direction-console.json"): "fd1bb972e00c100f2354dcf8306b4e73797e18959eff0369bf982cffaee4939e",
}


ADDITIONAL_PREVIOUS_SHA256 = {'miniapps/cib-direction-console.json': '700d88b85967d52cd0d4d7115254b763e734787a7df3421006005a6ad4bc0b50', 'miniapps/cib-case-console.json': 'a52a8baafd40d5dac93985ff64705672da8fd6b0d183a9565d19292d1761bf22', 'workflows/cib-case-list.json': '228790de82fac9492620e412364670802185e624930e20823f92f0479b652668', 'workflows/cib-case-share.json': '5e7a535264d5525bc3c7634bd218ab1fd4eefc2b61b8560fee259ecfd8c5655a', 'workflows/cib-case-read.json': 'c8a22bd61d2752d458ba1507d5307dab20ce170cf1f1d1ca49ddd66cacb76bd8', 'workflows/cib-case-people.json': 'd5221d2a1d38f455b5d39902c44d84dcdd9d12cd44a590a8a284bfb5399a93ea', 'workflows/cib-direction-brief.json': '1f3c9b321fbc2f288b115390de9a65ec760276934388ee4d9f645fd4e2f6436e', 'workflows/cib-case-save.json': 'e57b95416234d24ee20dd3779e1952a0503c71743d3a65ec7038671f2ed9607c'}

ACL_PREFILL_PREVIOUS_SHA256 = {'workflows/cib-case-read.json': '94a165cf10b29d44463433b379def6b642a2c55e644333cb18885fe23376806c', 'workflows/cib-case-save.json': '7755efcb58f47286c5c6aebc05e4b6f0ca85eda48b012c642340cc7880718317'}

CANDIDATE_4A_SHA256 = {
    'miniapps/cib-case-console.json': 'a0f35d08d4d39c6eff424e774b2d924a64291bd20f7df29e13955dc26f5c72f0',
    'miniapps/cib-direction-console.json': '7cf3ee9ef1b1824537bbcda6eb7ecefff90c20c413ad41e7ece80c801322953b',
    'workflows/cib-case-list.json': '1bcf1168d5c35e0fdc0431618555191e84adc0c02d077357ff4ff5063b46339c',
    'workflows/cib-case-people.json': '879c20df05c945c6ac244e75689de187caa6d336a4b9013bfc33c69f1c7f228f',
    'workflows/cib-case-read.json': '84ba99136a265aca68262fed238111a082ececadc383831f6d8e52a524606379',
    'workflows/cib-case-save.json': '758bd304bb1dc58227e0079025777938397073f246659a3c021e2123bcd27b20',
    'workflows/cib-case-share.json': '88b9013f09fd7c195cc52bcb0a47ba12c1dbf77216c4312c0a6cb129c790349a',
    'workflows/cib-direction-brief.json': 'cd267299db603ebaf4ae2a204bd686bf213519fe03ade4d9f645fd4e2f6436e',
}

def compose(consumer, owner_alias="veille"):
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", owner_alias):
        raise ValueError("invalid owner alias")
    agent = consumer / "agents" / owner_alias
    spec = json.loads((agent / "agent-spec.json").read_text())
    if spec.get("schema_version") != 2 or spec.get("agent_alias") != owner_alias:
        raise ValueError("consumer Agent identity mismatch")
    if not re.fullmatch(r"[0-9a-v]{20}", spec.get("agent_id", "")):
        raise ValueError("a real existing Agent ID is required")
    source = ROOT.parents[1] / "work-cases" / "agents" / "main"
    planned = {agent / p.relative_to(source): p.read_bytes()
               for p in sorted(source.rglob("*.json"))}
    if len(planned) != 9:
        raise ValueError("expected six Workflows and three MiniApps")
    migration_hashes = json.loads((ROOT / "legacy-0.2.2-hashes.json").read_text())
    for dest, content in planned.items():
        if dest.exists() and dest.read_bytes() != content:
            relative = dest.relative_to(agent)
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            if PREVIOUS_SHA256.get(relative) != digest and ADDITIONAL_PREVIOUS_SHA256.get(str(relative)) != digest and ACL_PREFILL_PREVIOUS_SHA256.get(str(relative)) != digest and migration_hashes.get(str(relative)) != digest and CANDIDATE_4A_SHA256.get(str(relative)) != digest:
                raise ValueError("refusing divergent resource: " + str(dest))
    return planned


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consumer-dir", required=True, type=Path)
    parser.add_argument("--owner-alias", default="veille")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        planned = compose(args.consumer_dir.resolve(), args.owner_alias)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    for dest, content in planned.items():
        changed = not dest.exists() or dest.read_bytes() != content
        print(("WRITE " if args.write else "PLAN ") + str(dest)
              + (" [new]" if changed else " [identical]"))
        if args.write and changed:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
    print("No runtime mutation. Review and deploy the owner Agent Spec, then its local Application surface.")


if __name__ == "__main__":
    main()
