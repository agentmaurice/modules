import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MODULE_DIRS = {"veille": "watch", "contenu": "content", "accompagnement": "support"}
ROLES = ("veille", "contenu", "accompagnement")


def _fixture(role):
    key = "acl-share-node-" + role
    return {
        "dossier_id": key,
        "id": key,
        "entreprise": "Fixture runtime",
        "source_ref": "source-node",
        "source_date": "2026-10-10",
        "date_revue": "2026-10-11",
        "faits": "synthetic facts",
        "preuve_ref": "preuve-node",
        "role_demande": "veille",
        "contradiction": "non",
        "confirmation_manuelle": "oui",
        "sujet": "synthetic subject",
        "brouillon": "test draft",
        "objectif": "test objective",
        "resultat_observe": "test result",
        "blocage": "",
        "prochaine_etape": "next step",
    }


def _context(role, workflow, action):
    data = _fixture(role)
    data["role_demande"] = role
    data["responsable_role"] = role
    data["service"] = "interne"
    data["jeu"] = "usage"
    data["case_id"] = data["id"]
    data["critere_fin"] = "criterion"
    data["priorite"] = "normale"
    data["statut"] = "en_cours"
    data["prochaine_action"] = "relire"
    data["memoire_ref"] = "memoire-node"
    data["revue_manuelle"] = "non"
    data["veille_ref"] = ""
    data["veille_version"] = ""
    data["contenu_ref"] = ""
    data["contenu_version"] = ""
    data["accompagnement_ref"] = ""
    data["accompagnement_version"] = ""
    if action in {"list"}:
        return {}
    if action == "people":
        return {"dossier_id": data["id"], "subject_user_id": "subject-b"}
    if action == "read":
        return {"target": {"id": data["id"]}}
    if action == "share":
        return {
            "selection_dossier_id": data["id"],
            "share_dossier_id": data["id"], "share_expected_revision": "4",
            "share_subject_user_id": "subject-b", "share_permission": "read",
            "share_confirmation_manuelle": "oui",
        }
    if action == "evaluate":
        return {"action": "save_internal_draft", "confirmation_manuelle": True}
    if action == "require-eligible":
        return {"guard": {"data": {"decision": "eligible"}}}
    if action in {"write-dossier", "save"}:
        return {"expected_revision": 4, "dossier": data, "record": data}
    if action == "prepare":
        if role == "contenu":
            return data
        return {"dossier": data, "routing": {"data": {}}, "research": {"data": {"verdict": "sufficient"}}}
    if action == "attach-review":
        return {"record": data, "review": {"data": {"decision": "accepted"}}}
    if action == "review-dossier":
        return {"dossier_id": data["id"], "preuve": "preuve-node", "confirmation_manuelle": True}
    if action == "check":
        return data
    if action == "route":
        return {"role_demande": role, "confirmation_manuelle": True}
    return data


def _cases():
    rows = []
    for role in ROLES:
        root = ROOT / MODULE_DIRS[role] / "agents" / "main" / "workflows"
        for path in sorted(root.glob("*.json")):
            workflow = json.loads(path.read_text(encoding="utf-8"))
            for action in workflow.get("actions", []):
                if action.get("type") != "code_execution":
                    continue
                rows.append({
                    "name": role + "/" + path.name + "/" + action["id"],
                    "code": action["code"],
                    "context": _context(role, path.stem, action["id"]),
                })
    return rows


NODE_RUNNER = r'''
const cases = JSON.parse(process.env.RUNTIME_CASES);
const permissions = {can_read: true, can_write: true, can_manage: true};
const dataFor = (key) => ({id: key, entreprise: "Fixture runtime", source_ref: "source-node",
  source_date: "2026-10-10", date_revue: "2026-10-11", faits: "synthetic facts",
  preuve_ref: "preuve-node", role_demande: "veille", sujet: "synthetic subject",
  brouillon: "test draft", objectif: "test objective", resultat_observe: "test result",
  blocage: "", prochaine_etape: "next step"});
async function callTool(_name, args) {
  const key = args.record_key || "acl-share-node";
  const record = {namespace: args.namespace, key, revision: 4, data: dataFor(key),
    owner_user_id: "owner-a", permissions, shares: []};
  if (args.operation === "list") return {items: [{record_key: key, revision: 4, data: record.data,
    owner_user_id: "owner-a", permissions, shares: []}], total: 1};
  if (args.operation === "people") return {people: [{user_id: "subject-b", display_name: "Member B"}]};
  return {record};
}
function replaceTemplates(code, context) {
  return code.replace(/\{\{\s*json\s+([^}]+?)\s*\}\}/g, (_all, expression) => {
    const path = expression.trim().replace(/^\./, '').split('.').filter(Boolean);
    let value = context;
    for (const part of path) value = value == null ? undefined : value[part];
    return JSON.stringify(value === undefined ? null : value);
  }).replace(/^import[^;]+;\s*/m, '');
}
(async () => {
  for (const item of cases) {
    const source = replaceTemplates(item.code, item.context);
    try {
      const execute = new Function('callTool', 'return (async () => {' + source + '\n})()');
      await execute(callTool);
    } catch (error) {
      console.error(item.name + ': ' + (error && error.stack || error));
      process.exitCode = 1;
      return;
    }
  }
  console.log('executed ' + cases.length + ' code_execution actions');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''


class RuntimeCodeTests(unittest.TestCase):
    def test_all_role_code_execution_actions_parse_and_execute_in_node(self):
        cases = _cases()
        self.assertGreaterEqual(len(cases), 20)
        completed = subprocess.run(
            ["node", "--check", "-"],
            input=NODE_RUNNER,
            text=True,
            capture_output=True,
            cwd=ROOT,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        completed = subprocess.run(
            ["node", "--input-type=commonjs", "-"],
            input=NODE_RUNNER,
            text=True,
            capture_output=True,
            cwd=ROOT,
            env={**__import__("os").environ, "RUNTIME_CASES": json.dumps(cases)},
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn(f"executed {len(cases)} code_execution actions", completed.stdout)


if __name__ == "__main__":
    unittest.main()
