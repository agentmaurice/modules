import json
import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DIRS = {"veille": "watch", "contenu": "content", "accompagnement": "support"}
MODULES = {
    "veille": "cib-veille",
    "contenu": "cib-contenu",
    "accompagnement": "cib-accompagnement",
}
MINIAPP_VERSIONS = {"veille": "7", "contenu": "7", "accompagnement": "8"}


def load(role, name):
    path = ROOT / DIRS[role] / "agents" / "main" / "workflows" / f"{role}-{name}.json"
    return path, json.loads(path.read_text())


def broker_action(spec, operation):
    matches = [a for a in spec["actions"] if a.get("type") == "code_execution"
               and operation in a.get("code", "")]
    assert len(matches) == 1, (spec["workflow_id"], operation)
    action = matches[0]
    assert action.get("context", {}).get("allowed_tools") == [
        "recipe--application_data_v1"
    ]
    return action


def test_all_roles_use_acl_broker_for_crud():
    for role, namespace in MODULES.items():
        for operation in ("save", "read", "list"):
            path, spec = load(role, operation)
            assert namespace in broker_action(spec, operation)["code"], path
            assert "write_file" not in json.dumps(spec)
            assert "read_file" not in json.dumps(spec)
            assert "list_files" not in json.dumps(spec)
        _, save = load(role, "save")
        save_code = broker_action(save, "save")["code"]
        assert 'operation:"save"' in save_code
        assert "expected_revision" in save_code
        _, read = load(role, "read")
        assert 'operation:"read"' in broker_action(read, "read")["code"]
        _, listing = load(role, "list")
        assert 'operation:"list"' in broker_action(listing, "list")["code"]
        manifest = json.loads((ROOT / DIRS[role] / "module.yaml").read_text())
        assert manifest["version"] == "0.2.5"


def test_share_and_people_use_closed_acl_contract():
    for role, namespace in MODULES.items():
        _, people = load(role, "people")
        people_code = broker_action(people, "people")["code"]
        assert f'operation:"people"' in people_code
        assert f'namespace:"{namespace}"' in people_code
        assert "dossier_id:input.dossier_id" in people_code
        assert "namespace" not in json.dumps(people["output"])
        assert "admin_recovery" not in json.dumps(people)

        _, share = load(role, "share")
        share_code = broker_action(share, "share")["code"]
        assert f'operation:"share"' in share_code
        assert f'namespace:"{namespace}"' in share_code
        assert '"read","write","none"' in share_code
        assert "expected_revision" in share_code
        assert "subject_user_id" in share_code
        assert "input.dossier_id" not in share_code
        assert "input.expected_revision" not in share_code
        assert "input.subject_user_id" not in share_code
        assert "input.permission" not in share_code
        assert "input.confirmation_manuelle" not in share_code
        assert "input.share_dossier_id" in share_code
        assert "input.share_expected_revision" in share_code
        assert "input.share_subject_user_id" in share_code
        assert "input.share_permission" in share_code
        assert "input.share_confirmation_manuelle" in share_code
        assert "selection_dossier_id" in share_code
        assert "selection_dossier_mismatch" in share_code
        assert "admin_recovery" not in json.dumps(share)
        form = share["forms"][0]
        assert form["id"] == f"{role}-share"
        permission = next(field for field in form["fields"] if field["name"] == "share_permission")
        assert [option["value"] for option in permission["options"]] == ["read", "write", "none"]
        confirmation = next(field for field in form["fields"] if field["name"] == "share_confirmation_manuelle")
        assert confirmation["default"] == "non"
        assert all(field["name"].startswith("share_") for field in form["fields"])
        assert share["output"]["confirmation_manuelle"] is False
        assert "effects" in share["output"]
        assert "admin_recovery" not in share_code


def test_miniapp_share_transitions_are_separate_from_save():
    for role in MODULES:
        mini = json.loads((ROOT / DIRS[role] / "agents/main/miniapps" / f"{role}-console.json").read_text())
        assert mini["version"] == MINIAPP_VERSIONS[role]
        assert {event["event_id"] for event in mini["events"]} >= {"save", "people", "select-person", "share"}
        share = next(event for event in mini["events"] if event["event_id"] == "share")
        assert share["workflow"]["workflow_id"] == f"{role}-share"
        share_input = share["workflow"]["input"]
        assert set(share_input) == {
            "share_dossier_id", "share_expected_revision", "share_subject_user_id",
            "share_permission", "share_confirmation_manuelle", "selection_dossier_id",
        }
        assert share_input["share_dossier_id"] == "{{ state.selected.record.id }}"
        assert share_input["share_expected_revision"] == "{{ state.selected.revision }}"
        assert share_input["share_subject_user_id"] == "{{ state.people.selected_target.user_id }}"
        assert share_input["share_permission"] == "{{ state.share_permission }}"
        assert share_input["share_confirmation_manuelle"] == "{{ state.share_confirmation_manuelle }}"
        assert share_input["selection_dossier_id"] == "{{ state.people.dossier_id }}"
        assert share["result_to_state"] == "selected"
        people = next(event for event in mini["events"] if event["event_id"] == "people")
        assert people["workflow"]["workflow_id"] == f"{role}-people"
        select_person = next(event for event in mini["events"] if event["event_id"] == "select-person")
        assert select_person["trigger"] == "table.row_click"
        assert "share_permission" in mini["state_schema"]["properties"]
        assert mini["initial_state"]["share_confirmation_manuelle"] == "non"
        assert mini["initial_state"]["people"]["dossier_id"] == ""
        assert "Refresh members" in json.dumps(mini)
        assert "admin_recovery" not in json.dumps(mini)


def test_dedicated_sharing_miniapps_compile_one_share_form_and_keep_acl_events():
    """The public sharing console must expose exactly one form.submit event.

    The V2 compiler materializes the form of the first form.submit event in a
    MiniApp. Keeping save and share in the same public console would therefore
    bind the wrong form. This contract is intentionally checked against the
    actual JSON resources and the matching Workflow form.
    """
    for role in MODULES:
        mini_path = ROOT / DIRS[role] / "agents/main/miniapps" / f"{role}-sharing-console.json"
        mini = json.loads(mini_path.read_text())
        assert mini["miniapp_id"] == f"{role}-sharing-console"
        form_events = [event for event in mini["events"] if event["trigger"] == "form.submit"]
        assert len(form_events) == 1
        assert form_events[0]["event_id"] == "share"
        assert form_events[0]["workflow"]["workflow_id"] == f"{role}-share"
        assert {event["event_id"] for event in mini["events"]} == {
            "refresh", "select", "people", "select-person", "share"
        }
        assert "dedicated sharing console from navigation" not in json.dumps(mini)
        share_path, share = load(role, "share")
        assert len(share["forms"]) == 1, share_path
        assert share["forms"][0]["id"] == f"{role}-share"
        assert share["forms"][0]["fields"]
        assert all(field["required"] for field in share["forms"][0]["fields"])
        assert "Sharing a record does not grant access to the service." in json.dumps(mini, ensure_ascii=False)


def test_native_selection_carries_revision_and_prefills_form():
    for role in MODULES:
        _, read = load(role, "read")
        output = json.dumps(read["output"])
        assert "effects" in output
        assert "open_form" in broker_action(read, "read")["code"]
        read_code = broker_action(read, "read")["code"]
        assert f'form_id:"{role}-share"' in read_code
        assert 'share_subject_user_id:""' in read_code
        assert 'share_confirmation_manuelle:"non"' in read_code
        mini = json.loads((ROOT / DIRS[role] / "agents/main/miniapps" / f"{role}-console.json").read_text())
        save = next(event for event in mini["events"] if event["event_id"] == "save")
        assert save["workflow"]["input"]["expected_revision"] == "{{ state.selected.revision }}"
        assert save["result_to_state"] == "selected"
        save_spec = load(role, "save")[1]
        assert "permissions_summary" in json.dumps(save_spec["output"])
        assert "share_count" in json.dumps(save_spec["output"])
        save_form_id = save_spec["forms"][0]["id"]
        assert f'form_id:"{save_form_id}"' in read_code
        assert "prefill:{dossier_id:d.id" in read_code
        save_fields = save_spec["forms"][0]["fields"]
        assert all("default" in field for field in save_fields)
        dossier_field = next(field for field in save_fields if field["name"] == "dossier_id")
        assert dossier_field["default"] == "{{ state.selected.record.id }}"
        assert save_fields[-1]["default"] == "non"
        select = next(event for event in mini["events"] if event["event_id"] == "select")
        assert select["trigger"] == "table.row_click"
        assert select["result_to_state"] == "selected"

        if role == "veille":
            save_code = next(action["code"] for action in save_spec["actions"]
                             if action["id"] == "validate")
            for field in ("source_date", "date_revue", "role_demande", "contradiction"):
                assert f"{field}:" in save_code
            assert 'contradiction===true?"oui":"non"' in read_code




def test_language_upgrade_retains_previous_fingerprints_and_bumps_versions():
    fixture = json.loads((ROOT / "tooling/roles/legacy-resource-hashes.json").read_text())
    assert fixture["source_commit"] == "be204e3"
    entries = fixture["resources"]
    expected_paths = {str(path.relative_to(ROOT)) for directory in DIRS.values() for path in (ROOT / directory / "agents/main").rglob("*.json")}
    expected_paths |= {f"{directory}/module.yaml" for directory in DIRS.values()}
    assert set(entries) == expected_paths
    for path, previous in entries.items():
        current_bytes = (ROOT / path).read_bytes()
        current = json.loads(current_bytes)
        assert len(previous["sha256"]) == 64
        assert hashlib.sha256(current_bytes).hexdigest() != previous["sha256"]
        if path.endswith("module.yaml"):
            assert previous["version"] == "0.2.4" and current["version"] == "0.2.5"
        else:
            assert int(current["version"]) == int(previous["version"]) + 1



def test_resource_versions_and_options_remain_consistent():
    for role, directory in DIRS.items():
        base = ROOT / directory
        resources = [json.loads(path.read_text()) for path in (base / "agents/main").rglob("*.json")]
        versions = {item.get("workflow_id", item.get("miniapp_id")): item["version"] for item in resources}
        manifest = json.loads((base / "module.yaml").read_text())
        def check(value):
            if isinstance(value, dict):
                for kind in ("workflow", "miniapp"):
                    identity = value.get(kind + "_id")
                    version = value.get(kind + "_version")
                    if identity in versions and version is not None:
                        assert version == versions[identity], (identity, version, versions[identity])
                for child in value.values():
                    check(child)
            elif isinstance(value, list):
                for child in value:
                    check(child)
        check(manifest)
        for item in resources:
            check(item)
        _, share = load(role, "share")
        options = next(field["options"] for field in share["forms"][0]["fields"] if field["name"] == "share_confirmation_manuelle")
        assert [(item["value"], item["label"]) for item in options] == [("non", "No"), ("oui", "Yes")]


def test_read_display_labels_preserve_wire_data():
    for role, namespace in MODULES.items():
        _, spec = load(role, "read")
        code = broker_action(spec, "read")["code"]
        original = {"id": "case", "etat": "pret_a_revoir", "decision": {"routing": {"worker": "veille"}, "research": {"verdict": "sufficient"}, "decision": "human_review"}}
        item = {"namespace": namespace, "key": "case", "revision": 1, "data": original, "permissions": {"can_read": True, "can_write": False, "can_manage": False}, "shares": []}
        code = code.replace("import { callTool } from './tools/nats_bridge.ts';", "const callTool=async()=>({record:" + json.dumps(item) + "});")
        code = code.replace("{{ json .target }}", '{"id":"case"}')
        runner = "(async()=>{" + code + "})().then(x=>console.log(JSON.stringify(x))).catch(e=>{console.error(e);process.exit(1)})"
        result = json.loads(subprocess.run(["node", "-e", runner], text=True, check=True, capture_output=True).stdout)
        assert result["record"] == original
        assert result["display"] == {"status": "Ready for review", "worker": "Watch", "verdict": "Sufficient", "review": "Human review"}
        assert result["permissions_summary"] == "Read: yes · Write: no · Share: no"
        for name in (f"{role}-console.json", f"{role}-sharing-console.json"):
            mini = json.loads((ROOT / DIRS[role] / "agents/main/miniapps" / name).read_text())
            assert "selected.display.status" in json.dumps(mini)


if __name__ == "__main__":
    test_all_roles_use_acl_broker_for_crud()
    test_share_and_people_use_closed_acl_contract()
    test_miniapp_share_transitions_are_separate_from_save()
    test_dedicated_sharing_miniapps_compile_one_share_form_and_keep_acl_events()
    test_native_selection_carries_revision_and_prefills_form()
    test_read_display_labels_preserve_wire_data()
    test_language_upgrade_retains_previous_fingerprints_and_bumps_versions()
    test_resource_versions_and_options_remain_consistent()
