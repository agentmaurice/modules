#!/usr/bin/env python3
"""Compose the portable Company-in-a-Box resources into a spec-init project.

This is a file packager only. It never calls MauriceCLI, starts a runtime, or
applies/deploys an Agent Spec. Dry-run is the default; pass --write to copy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROLES = ("veille", "contenu", "accompagnement")
MODULE_DIRS = {"veille": "watch", "contenu": "content", "accompagnement": "support"}
MODULE_VERSION = "0.2.4"

# Optional services are off unless asked with --with-service. Each one is an
# extra Agent (alias = service name) that must already be spec-init'ed in the
# consumer. `role` is the business role of the service owner ("responsable") and
# is carried explicitly, per Workflow, in the surface draft written next to the
# copied files; `gates` overrides it for the Workflows an administrator owns.
# Role grants and per-record ACL stay cumulative, as for the three roles.
OPTIONAL_SERVICES = {
    "documents": {
        "module_dir": "document-studio",
        "version": "0.4.0",
        "role": "cib_documents",
        # document-read carries no required_role, like contenu-read: any member of the Application may call it
        # and the ACL of each shared record decides what it returns. None = no role.
        "gates": {"document-studio-profile-save": "cib_admin", "document-read": None},
    },
}
SURFACE_DRAFT_DIR = "surface-drafts"

# A consumer composed at 0.2.3 may already contain the old console.  Only
# these exact source bytes are a supported in-place upgrade; any other
# destination divergence remains an operator conflict.
KNOWN_UPGRADE_HASHES = {
    "modules/veille/agents/main/miniapps/veille-console.json": {
        "53310cac6124d3f8d6440fe5b6cb4f7792515d13e7142d22fa290e8f8a39b4dc",
        "e5babbb162c68e4dcedcb58545c0481e9daf34215279f2c8d54e06e9d8e0a7e9",
        # Consumer 6ae9aed / source b855763c exact bytes.
        "4abf12444b81bf8341f60098d8cf8a68d9477bb469524aaa53511ed724fcf4f4",
    },
    "modules/veille/agents/main/workflows/veille-share.json": {
        "921bb2494cfad30a459d6d484b8a664b387dbdeda73f469968113efc13fe0313",
    },
    "modules/veille/agents/main/workflows/veille-read.json": {
        "996d135e35941453348376962ab1748cd62d69a77847fb877adfbb844d2d3f5b",  # local 0.2.3 before syntax repair
        "6460d0eecd7ff492f58f331d6c461c63c301390d079904d119c68e8eb57783d4",
    },
    "modules/contenu/agents/main/miniapps/contenu-console.json": {
        "d7d7ac7b4f85345132daaf0f9aa5617d3647d81b52324dec8f99965e043c50b6",
        "f4da879d1069ba6b0b6b868d2537ca0bde9a2175334a319e354148050240b7eb",
        # Consumer 6ae9aed / source b855763c exact bytes.
        "a00ca950fbad27600cf94bf72b691044edb22a8b6b138bcb10bace81c7a8ebad",
    },
    "modules/contenu/agents/main/workflows/contenu-share.json": {
        "952eb14e1872fbd13f18ed6e4bbcc3b31e3bddd8cf9e3eb2709fe56e7e17aabb",
    },
    "modules/contenu/agents/main/workflows/contenu-read.json": {
        "7268db7f64e9c3a2f45da02d5d2772b48deded9294d3a583fa0ef4d17c2029d9",  # local 0.2.3 before syntax repair
        "4795f6da90d35c99964c1c1d78662e7b1f56dd0d1bd47870eaa411a287c2b230",
    },
    "modules/accompagnement/agents/main/miniapps/accompagnement-console.json": {
        "77350dde5386ece3e02f7057db3701351f8b1006d96755e4e6b8caedfa642e51",
        "eaa3f29a7095282bed81df18b27cd2473fcee0088d303923ef594529c378acf9",
        # Consumer 6ae9aed / source b855763c exact bytes.
        "e248412443c9013e996c32fb8b7ced326a8eef729a9644419e5ec8ba75920c2a",
    },
    "modules/accompagnement/agents/main/workflows/accompagnement-share.json": {
        "5ab53efa2eb985c9f66da862cdb291ba0ea96e032491dc332003845b6e27a313",
    },
    "modules/accompagnement/agents/main/workflows/accompagnement-read.json": {
        "c3340f1772bd736b88403f552578f871eb6b099414727247d90c991de3040413",  # local 0.2.3 before syntax repair
        "881e7d421ef315dba65bdf2138517d2d82d933e255a29fcebc8d92fb4b6e31df",
    },
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def files_under(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*") if path.is_file())


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def validate_module(module_root: Path, role: str, errors: list[str], version: str = MODULE_VERSION) -> None:
    manifest_path = module_root / "module.yaml"
    try:
        manifest = load_json(manifest_path)
    except ValueError as exc:
        errors.append(str(exc))
        return
    if manifest.get("$schema") != "agentmaurice.module/v2" or manifest.get("schema_version") != 2:
        errors.append(f"module manifest is not pure V2: {manifest_path}")
    for forbidden in ("deployment", "deployments", "agent_spec", "recipes", "tests"):
        if forbidden in manifest:
            errors.append(f"forbidden legacy field {forbidden}: {manifest_path}")
    for forbidden_path in ("deployments", "agent-spec.json", "agents/main/tests", "agents/main/recipes"):
        if (module_root / forbidden_path).exists():
            errors.append(f"forbidden legacy path {module_root / forbidden_path}")
    if not isinstance(manifest.get("key"), str) or not manifest["key"]:
        errors.append(f"module key missing: {manifest_path}")
    if manifest.get("version") != version:
        errors.append(f"unexpected bundle version in {manifest_path}: {manifest.get('version')!r}")
    workflows = module_root / "agents" / "main" / "workflows"
    miniapps = module_root / "agents" / "main" / "miniapps"
    workflow_ids = {load_json(path).get("workflow_id") for path in files_under(workflows)} if workflows.exists() else set()
    miniapp_ids = {load_json(path).get("miniapp_id") for path in files_under(miniapps)} if miniapps.exists() else set()
    provides = manifest.get("provides", {})
    for kind in ("actions", "queries"):
        for capability in provides.get(kind, []):
            target = capability.get("workflow_id")
            if target not in workflow_ids:
                errors.append(f"{role}: manifest target not packaged: {target}")
    for capability in provides.get("apps", []):
        target = capability.get("miniapp_id")
        if target not in miniapp_ids:
            errors.append(f"{role}: manifest app target not packaged: {target}")


def validate_agent_spec(path: Path, role: str, errors: list[str]) -> None:
    try:
        spec = load_json(path)
    except ValueError as exc:
        errors.append(str(exc))
        return
    if spec.get("$schema") != "agentmaurice.agent_spec/v2" or spec.get("schema_version") != 2:
        errors.append(f"consumer spec is not Agent Spec V2: {path}")
    if spec.get("agent_alias") != role:
        errors.append(f"consumer spec alias must be {role!r}: {path}")
    if not isinstance(spec.get("agent_id"), str) or not spec["agent_id"].strip():
        errors.append(f"consumer spec agent_id is empty: {path}")


def surface_draft(source_root: Path, service: str, agent_spec: Path) -> str:
    """Surface entries of an optional service, with `required_role` on every Workflow but the ACL-protected read (never left to a naming convention)."""
    config = OPTIONAL_SERVICES[service]
    manifest = load_json(source_root / config["module_dir"] / "module.yaml")
    agent_id = load_json(agent_spec)["agent_id"]
    provides = manifest["provides"]
    workflows = []
    for ref in provides["actions"] + provides["queries"]:
        entry = {"agent_id": agent_id, "workflow_id": ref["workflow_id"], "version": ref["workflow_version"]}
        role = config["gates"].get(ref["workflow_id"], config["role"])
        if role is not None:
            entry["required_role"] = role
        workflows.append(entry)
    miniapps = [{"agent_id": agent_id, "miniapp_id": a["miniapp_id"], "version": a["miniapp_version"]} for a in provides["apps"]]
    return json.dumps({"public_surface": {"workflows": workflows, "miniapps": miniapps}}, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--consumer-dir",
        required=True,
        type=Path,
        help="Projet consommateur déjà spec-init avec agents/<role>/agent-spec.json",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Racine du dépôt contenant les Modules et templates/",
    )
    parser.add_argument(
        "--with-service",
        action="append",
        default=[],
        choices=sorted(OPTIONAL_SERVICES),
        help="Ajouter un service optionnel (Agent déjà spec-init sous le même alias) ; aucun par défaut",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Copier les octets après toutes les validations préalables",
    )
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    consumer = args.consumer_dir.resolve()

    errors: list[str] = []
    planned: list[tuple[Path, Path]] = []
    drafts: list[tuple[Path, str]] = []
    targets = [(role, MODULE_DIRS[role], MODULE_VERSION) for role in ROLES]
    for service in dict.fromkeys(args.with_service):
        config = OPTIONAL_SERVICES[service]
        targets.append((service, config["module_dir"], config["version"]))
    for role, module_dir, version in targets:
        module_root = source_root / module_dir
        manifest = module_root / "module.yaml"
        workflows = module_root / "agents" / "main" / "workflows"
        miniapps = module_root / "agents" / "main" / "miniapps"
        test_plan = source_root / "templates/company-in-a-box/tests" / f"{role}.json"
        agent_spec = consumer / "agents" / role / "agent-spec.json"

        validate_module(module_root, role, errors, version)
        if agent_spec.exists():
            validate_agent_spec(agent_spec, role, errors)
        for required in (manifest, workflows, miniapps, test_plan, agent_spec):
            if not required.exists():
                errors.append(f"missing: {required}")
        if workflows.exists():
            planned.extend((path, consumer / "agents" / role / "workflows" / path.name) for path in files_under(workflows))
        if miniapps.exists():
            planned.extend((path, consumer / "agents" / role / "miniapps" / path.name) for path in files_under(miniapps))
        if test_plan.exists():
            try:
                plan = load_json(test_plan)
                if plan.get("$schema") != "agentmaurice.test_plan/v2" or plan.get("schema_version") != 2:
                    errors.append(f"test plan is not V2: {test_plan}")
            except ValueError as exc:
                errors.append(str(exc))
            planned.append((test_plan, consumer / "agents" / role / "tests" / "test-plan.json"))
        if role in OPTIONAL_SERVICES and not errors:
            draft_path = consumer / SURFACE_DRAFT_DIR / f"cib-{role}.surface-draft.json"
            draft = surface_draft(source_root, role, agent_spec)
            if draft_path.exists() and draft_path.read_text(encoding="utf-8") != draft:
                errors.append(f"destination conflict (refusing overwrite): {draft_path}")
            drafts.append((draft_path, draft))

    upgradeable: set[tuple[Path, Path]] = set()
    for source, destination in planned:
        if not destination.exists() or digest(destination) == digest(source):
            continue
        relative = source.relative_to(source_root).as_posix()
        for role, dirname in MODULE_DIRS.items():
            if relative.startswith(dirname + "/"):
                relative = "modules/" + role + "/" + relative[len(dirname) + 1:]
                break
        if digest(destination) in KNOWN_UPGRADE_HASHES.get(relative, set()):
            upgradeable.add((source, destination))
            continue
        errors.append(f"destination conflict (refusing overwrite): {destination}")

    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 2

    print(f"consumer: {consumer}")
    print(f"mode: {'write' if args.write else 'dry-run'}")
    print("runtime: no CLI, no deploy, no apply")
    for source, destination in planned:
        source_hash = digest(source)
        destination_state = "absent"
        if destination.exists():
            destination_state = "identical" if digest(destination) == source_hash else "different"
        if (source, destination) in upgradeable:
            destination_state = "upgrade-from-known-0.2.3"
        print(f"{source.relative_to(source_root)} -> {destination} [{destination_state}] sha256={source_hash}")
        if args.write:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if digest(destination) != source_hash:
                print(f"ERROR copy verification failed: {destination}", file=sys.stderr)
                return 3

    for draft_path, draft in drafts:
        print(f"surface draft -> {draft_path} (required_role on every Workflow except document-read, protected by the record ACL; merge it into the Application surface and publish it yourself)")
        if args.write:
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_path.write_text(draft, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
