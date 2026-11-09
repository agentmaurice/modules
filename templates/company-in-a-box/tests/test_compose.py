import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
COMPOSE_PATH = ROOT / "templates/company-in-a-box/compose.py"
spec = importlib.util.spec_from_file_location("cib_template_compose", COMPOSE_PATH)
compose = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compose)


class TemplateComposeTests(unittest.TestCase):
    def make_source_and_consumer(self, tmp):
        source = tmp / "source"
        for dirname in compose.MODULE_DIRS.values():
            shutil.copytree(ROOT / dirname, source / dirname)
        shutil.copytree(ROOT / "templates/company-in-a-box/tests", source / "templates/company-in-a-box/tests")
        consumer = tmp / "consumer"
        for role in compose.ROLES:
            spec_dir = consumer / "agents" / role
            spec_dir.mkdir(parents=True)
            (spec_dir / "agent-spec.json").write_text(json.dumps({
                "$schema": "agentmaurice.agent_spec/v2",
                "schema_version": 2,
                "agent_alias": role,
                "agent_id": f"agent-{role}",
            }), encoding="utf-8")
        return source, consumer

    def run_main(self, source, consumer, *extra):
        argv = ["compose.py", "--consumer-dir", str(consumer), "--source-root", str(source), *extra]
        old_argv = sys.argv
        sys.argv = argv
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return compose.main()
        finally:
            sys.argv = old_argv

    def test_upgrade_accepts_known_old_console_and_preserves_extra_files(self):
        with tempfile.TemporaryDirectory(prefix="cib-template-compose-") as directory:
            tmp = Path(directory)
            source, consumer = self.make_source_and_consumer(tmp)
            old = b'{"version":"5","fixture":"known-0.2.2"}\n'
            destination = consumer / "agents" / "veille" / "miniapps" / "veille-console.json"
            destination.parent.mkdir(parents=True)
            destination.write_bytes(old)
            extra = consumer / "agents" / "veille" / "workflows" / "operator-extra.json"
            extra.parent.mkdir(parents=True)
            extra.write_text("keep me", encoding="utf-8")
            old_path = tmp / "old-console.json"
            old_path.write_bytes(old)
            key = "modules/veille/agents/main/miniapps/veille-console.json"
            original = compose.KNOWN_UPGRADE_HASHES.get(key)
            compose.KNOWN_UPGRADE_HASHES[key] = {compose.digest(old_path)}
            try:
                self.assertEqual(self.run_main(source, consumer, "--write"), 0)
            finally:
                if original is None:
                    compose.KNOWN_UPGRADE_HASHES.pop(key, None)
                else:
                    compose.KNOWN_UPGRADE_HASHES[key] = original
            self.assertEqual(destination.read_bytes(), (source / "watch/agents/main/miniapps/veille-console.json").read_bytes())
            self.assertEqual(extra.read_text(encoding="utf-8"), "keep me")

    def test_unknown_destination_divergence_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix="cib-template-compose-") as directory:
            tmp = Path(directory)
            source, consumer = self.make_source_and_consumer(tmp)
            destination = consumer / "agents" / "veille" / "miniapps" / "veille-console.json"
            destination.parent.mkdir(parents=True)
            destination.write_text('{"operator":"divergent"}\n', encoding="utf-8")
            self.assertEqual(self.run_main(source, consumer), 2)

    def test_consumer_6421_share_surface_hashes_are_known(self):
        expected = {
            "modules/veille/agents/main/miniapps/veille-console.json": "e5babbb162c68e4dcedcb58545c0481e9daf34215279f2c8d54e06e9d8e0a7e9",
            "modules/veille/agents/main/workflows/veille-share.json": "921bb2494cfad30a459d6d484b8a664b387dbdeda73f469968113efc13fe0313",
            "modules/contenu/agents/main/miniapps/contenu-console.json": "f4da879d1069ba6b0b6b868d2537ca0bde9a2175334a319e354148050240b7eb",
            "modules/contenu/agents/main/workflows/contenu-share.json": "952eb14e1872fbd13f18ed6e4bbcc3b31e3bddd8cf9e3eb2709fe56e7e17aabb",
            "modules/accompagnement/agents/main/miniapps/accompagnement-console.json": "eaa3f29a7095282bed81df18b27cd2473fcee0088d303923ef594529c378acf9",
            "modules/accompagnement/agents/main/workflows/accompagnement-share.json": "5ab53efa2eb985c9f66da862cdb291ba0ea96e032491dc332003845b6e27a313",
        }
        for path, digest in expected.items():
            self.assertIn(digest, compose.KNOWN_UPGRADE_HASHES[path])

    def test_consumer_6ae9aed_b855_console_hashes_are_known(self):
        expected = {
            "modules/veille/agents/main/miniapps/veille-console.json": "4abf12444b81bf8341f60098d8cf8a68d9477bb469524aaa53511ed724fcf4f4",
            "modules/contenu/agents/main/miniapps/contenu-console.json": "a00ca950fbad27600cf94bf72b691044edb22a8b6b138bcb10bace81c7a8ebad",
            "modules/accompagnement/agents/main/miniapps/accompagnement-console.json": "e248412443c9013e996c32fb8b7ced326a8eef729a9644419e5ec8ba75920c2a",
        }
        for path, digest in expected.items():
            self.assertIn(digest, compose.KNOWN_UPGRADE_HASHES[path])

    def test_v024_composes_three_dedicated_sharing_consoles(self):
        self.assertEqual(compose.MODULE_VERSION, "0.2.4")
        for role in compose.ROLES:
            module = json.loads((ROOT / compose.MODULE_DIRS[role] / "module.yaml").read_text(encoding="utf-8"))
            self.assertEqual(module["version"], "0.2.4")
            apps = {app["miniapp_id"]: app for app in module["provides"]["apps"]}
            self.assertEqual(apps[f"{role}-sharing-console"]["miniapp_version"], "1")
            mini = json.loads((ROOT / compose.MODULE_DIRS[role] / "agents/main/miniapps" / f"{role}-sharing-console.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [event["event_id"] for event in mini["events"] if event["trigger"] == "form.submit"],
                ["share"],
            )
            self.assertEqual(
                next(event for event in mini["events"] if event["event_id"] == "share")["workflow"]["workflow_id"],
                f"{role}-share",
            )
        with tempfile.TemporaryDirectory(prefix="cib-template-compose-") as directory:
            tmp = Path(directory)
            source, consumer = self.make_source_and_consumer(tmp)
            self.assertEqual(self.run_main(source, consumer), 0)

    def add_documents(self, source, consumer, with_agent=True):
        shutil.copytree(ROOT / "document-studio", source / "document-studio")
        if with_agent:
            spec_dir = consumer / "agents" / "documents"
            spec_dir.mkdir(parents=True)
            (spec_dir / "agent-spec.json").write_text(json.dumps({
                "$schema": "agentmaurice.agent_spec/v2", "schema_version": 2,
                "agent_alias": "documents", "agent_id": "agent-documents",
            }), encoding="utf-8")

    def test_document_studio_is_an_optional_service_off_by_default(self):
        with tempfile.TemporaryDirectory(prefix="cib-template-compose-") as directory:
            source, consumer = self.make_source_and_consumer(Path(directory))
            self.add_documents(source, consumer)
            self.assertEqual(self.run_main(source, consumer, "--write"), 0)
            self.assertFalse((consumer / "agents/documents/workflows").exists())
            self.assertFalse((consumer / "surface-drafts").exists())

    def test_optional_service_needs_its_agent_and_the_pinned_version(self):
        with tempfile.TemporaryDirectory(prefix="cib-template-compose-") as directory:
            source, consumer = self.make_source_and_consumer(Path(directory))
            self.add_documents(source, consumer, with_agent=False)
            self.assertEqual(self.run_main(source, consumer, "--with-service", "documents", "--write"), 2)
            self.assertFalse((consumer / "agents/documents").exists())

    def test_documents_service_copies_the_module_and_gates_every_workflow_by_role(self):
        with tempfile.TemporaryDirectory(prefix="cib-template-compose-") as directory:
            source, consumer = self.make_source_and_consumer(Path(directory))
            self.add_documents(source, consumer)
            self.assertEqual(self.run_main(source, consumer, "--with-service", "documents"), 0)
            self.assertFalse((consumer / "surface-drafts").exists(), "dry-run writes nothing")
            self.assertEqual(self.run_main(source, consumer, "--with-service", "documents", "--write"), 0)
            for name in ("document-share", "document-read", "document-studio-publish"):
                self.assertTrue((consumer / "agents/documents/workflows" / f"{name}.json").is_file(), name)
            self.assertTrue((consumer / "agents/documents/tests/test-plan.json").is_file())
            draft = json.loads((consumer / "surface-drafts/cib-documents.surface-draft.json").read_text(encoding="utf-8"))
            roles = {w["workflow_id"]: w.get("required_role") for w in draft["public_surface"]["workflows"]}
            self.assertEqual(len(roles), 13)
            self.assertEqual(roles["document-studio-profile-save"], "cib_admin")
            self.assertIsNone(roles["document-read"], "ACL of the record protects the read, as for contenu-read")
            self.assertNotIn("required_role", next(w for w in draft["public_surface"]["workflows"] if w["workflow_id"] == "document-read"))
            self.assertEqual({r for k, r in roles.items() if k not in ("document-studio-profile-save", "document-read")}, {"cib_documents"})
            self.assertEqual({w["agent_id"] for w in draft["public_surface"]["workflows"]}, {"agent-documents"})
            self.assertEqual([a["miniapp_id"] for a in draft["public_surface"]["miniapps"]], ["document-studio-review"])
            self.assertEqual(self.run_main(source, consumer, "--with-service", "documents", "--write"), 0, "rerun is idempotent")
            (consumer / "surface-drafts/cib-documents.surface-draft.json").write_text("{}", encoding="utf-8")
            self.assertEqual(self.run_main(source, consumer, "--with-service", "documents", "--write"), 2, "divergent draft is refused")

    def test_documents_test_plan_targets_existing_workflows(self):
        plan = json.loads((ROOT / "templates/company-in-a-box/tests/documents.json").read_text(encoding="utf-8"))
        self.assertEqual((plan["$schema"], plan["schema_version"]), ("agentmaurice.test_plan/v2", 2))
        names = {p.stem for p in (ROOT / "document-studio/agents/main/workflows").glob("*.json")}
        self.assertLessEqual({c["workflow"]["workflow_id"] for c in plan["cases"]}, names)


if __name__ == "__main__":
    unittest.main()
