"""Offline checks for Company Memory 0.3.2.

Three layers, none of them calls a One, Memory or Brain:

1. Static rules on the shipped JSON: versions, Agent Spec V2 contract, no runtime
   data inside `code`, no NATS import text in `code`, SQL shapes sent to Memory.
2. Each `code_execution` runs under node with its `context` bound as `const`
   locals, as the sandbox does (code_step_harness.mjs).
3. A small engine runs the shipped Workflows against in-memory fakes for the
   native file tools, Memory and Brain. It replays capture -> proposal -> review
   -> query -> index -> search, including replacement and fail-closed cases.
   memory-search has no child Workflow: one Brain call, one Memory query, one listing.

Node and jsonschema are optional: the tests that need them are skipped with a
reason when they are missing.
"""
import importlib.util
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # solutions/company-memory
REPO = Path(__file__).resolve().parents[3]  # modules
MODULE = REPO / "company-memory"
WORKFLOWS = MODULE / "agents/main/workflows"
MINIAPPS = MODULE / "agents/main/miniapps"
HARNESS = Path(__file__).with_name("code_step_harness.mjs")
VALIDATOR = REPO / "contracts/agent-authoring/v2/generated/python/validator.gen.py"
NODE = shutil.which("node")

HAS_JSONSCHEMA = importlib.util.find_spec("jsonschema") is not None

# Same rule as chatserver internal/business/core/sandbox_host_channel.go (natsClientImport).
NATS_IMPORT = re.compile(
    r"(?i)(?:npm:\s*@?nats(?:[@/\"'`\s;)]|$)|jsr:\s*@nats-io|@nats-io/|deno\.land/x/nats"
    r"|esm\.sh/\*?nats|skypack\.dev/nats|unpkg\.com/nats|cdn\.jsdelivr\.net/npm/nats)"
)
IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
RESERVED = {
    "arguments", "await", "break", "case", "catch", "class", "const", "continue", "debugger",
    "default", "delete", "do", "else", "enum", "eval", "export", "extends", "false", "finally",
    "for", "function", "if", "implements", "import", "in", "instanceof", "interface", "let",
    "new", "null", "package", "private", "protected", "public", "return", "static", "super",
    "switch", "this", "throw", "true", "try", "typeof", "var", "void", "while", "with", "yield",
    "context",
}
# Expressions accepted in `context` (chatserver: ResolveTemplateValuePreservingTypes).
SINGLE_PATH = re.compile(r"^\{\{\s*\.?([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s*\}\}$")
DEFAULT_EMPTY = re.compile(r'^\{\{\s*default\s+""\s+\.([A-Za-z_][A-Za-z0-9_]*)\s*\}\}$')
INLINE = re.compile(r"\{\{\s*(json\s+)?\.?([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s*\}\}")
SLUG_RE = r"^[a-z0-9][a-z0-9_-]{0,63}$"
TENANT = "company-memory"
EXCERPT_MAX = 300
WINDOW_MAX = 400 + 8  # 400-character window plus two markers
IDENTIFIER_QUERY = re.compile(r"^[A-Z]+-\d+$")
# Single Memory query: candidates and successors, with validated slugs inlined.
SEARCH_SQL = re.compile(
    r"^SELECT external_id, name, status, attributes FROM v_entities"
    r" WHERE entity_type = 'company_memory_revision' AND status = 'validated'"
    r" AND \(external_id IN \((?P<ids>[^)]*)\)"
    r" OR json_extract_string\(attributes, '\$\.previous_revision'\) IN \((?P<prev>[^)]*)\)\)$"
)
SQL_ID_LIST = re.compile(r"^'[a-z0-9][a-z0-9_-]*'(?:, '[a-z0-9][a-z0-9_-]*')*$")  # never ''
# No candidates: empty query without a previous_revision clause.
EMPTY_SEARCH_SQL = ("SELECT external_id, name, status, attributes FROM v_entities"
                    " WHERE entity_type = 'company_memory_revision' AND external_id IN ('')")
FILLER = "Filler text unrelated to the query. "


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def workflows():
    return {p.stem: load_json(p) for p in sorted(WORKFLOWS.glob("*.json"))}


def code_steps(doc):
    return [a for a in doc["actions"] if a["type"] == "code_execution"]


def action(workflow_id, action_id):
    return next(a for a in WORKFLOWS_CACHE[workflow_id]["actions"] if a["id"] == action_id)


def run_node(code, context):
    payload = json.dumps({"code": code, "context": context}, ensure_ascii=False)
    proc = subprocess.run(
        [NODE, str(HARNESS)], input=payload, capture_output=True, text=True, encoding="utf-8"
    )
    if proc.returncode != 0 or not proc.stdout:
        raise AssertionError("harness failure: " + proc.stderr[-500:])
    return json.loads(proc.stdout)


class StepError(Exception):
    pass


def lookup(state, path):
    value = state
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            raise StepError(f"reference inconnue: {path}")
        value = value[part]
    return value


def copy_value(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def resolve_context(context, state):
    """Mirror of chatserver's context evaluation for the forms used by the module."""
    resolved = {}
    for key, expression in context.items():
        single = SINGLE_PATH.match(expression)
        if single:
            resolved[key] = copy_value(lookup(state, single.group(1)))
            continue
        default = DEFAULT_EMPTY.match(expression)
        if default:
            value = state.get(default.group(1))
            resolved[key] = "" if value in (None, "", False, 0) else copy_value(value)
            continue
        raise AssertionError(f"expression de contexte non prise en charge: {expression}")
    return resolved


def go_text(value):
    """Text rendering of a value by Go text/template ({{ x }} on a decoded JSON value)."""
    if isinstance(value, str):
        return value
    if value is None:
        return "<no value>"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + " ".join(go_text(v) for v in value) + "]"
    return "map[" + " ".join(f"{k}:{go_text(value[k])}" for k in sorted(value)) + "]"


def render(value, state, preserve_types=True):
    """Mirror of chatserver template rendering.

    Workflow outputs, `input` and `items` keep the JSON type of a single path
    (ResolveTemplateValuePreservingTypes). Tool parameters do not: mcp_executor renders
    them with ResolveTemplateMap, so an array referenced alone becomes Go text "[a b]".
    """
    if isinstance(value, dict):
        return {k: render(v, state, preserve_types) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, state, preserve_types) for v in value]
    if not isinstance(value, str) or "{{" not in value:
        return value
    single = SINGLE_PATH.match(value)
    if single:
        target = copy_value(lookup(state, single.group(1)))
        return target if preserve_types else go_text(target)

    def replace(match):
        target = lookup(state, match.group(2))
        if match.group(1):
            return json.dumps(target, ensure_ascii=False, indent=2)
        if not isinstance(target, str):
            if not preserve_types:
                return go_text(target)
            raise StepError("text rendering of a non-text value")
        return target

    return INLINE.sub(replace, value)


class Store:
    """In-memory fakes for native files, Memory and Brain, with strict SQL shapes."""

    def __init__(self):
        self.files = {}
        self.memory = {}
        self.brain = []
        self.calls = []
        self.attributes_as_string = False  # Memory may return JSON attributes as a string


    def call(self, tool, params):
        self.calls.append(tool)
        if tool == "write_file":
            path = params["path"]
            if path in self.files and not params.get("overwrite", True):
                raise StepError("fichier existant")
            content = params["content"]
            self.files[path] = content if isinstance(content, str) else json.dumps(content)
            return {"path": path}
        if tool == "read_file":
            if params["path"] not in self.files:
                raise StepError("fichier absent")
            return {"content": self.files[params["path"]], "path": params["path"]}
        if tool == "list_files":
            prefix = params["path"] + "/"
            return [{"path": p, "size": len(c)} for p, c in sorted(self.files.items()) if p.startswith(prefix)]
        if tool == "memory.entities.upsert":
            self._tenant(params)
            for item in params["items"]:
                self.memory[item["externalId"]] = {
                    "entity_type": params["entityType"],
                    "name": item["name"],
                    "status": item["status"],
                    "attributes": item["attributes"],
                }
            return {"upserted": len(params["items"])}
        if tool == "memory.query":
            self._tenant(params)
            rows = self._sql(params)
            truncated = len(rows) > params.get("maxRows", 500)
            rows = rows[: params.get("maxRows", 500)]
            # Real Memory answers rows=null when nothing matches (observed on sandbox agent-1050).
            return {"rows": rows if rows else None, "truncated": truncated, "queryStats": {"rowCount": len(rows)}}
        if tool == "brain.document.upsert":
            self._tenant(params)
            self.brain = [d for d in self.brain if d["uri"] != params["document_uri"]]
            self.brain.append({"uri": params["document_uri"], "content": params["content"]})
            return {"status": "completed"}
        if tool == "brain.keyword":
            self._tenant(params)
            if params.get("response_format") != "concise":
                raise StepError("brain.keyword sans response_format concise")
            query = params["query"]
            needle = query.lower()
            exact_query = IDENTIFIER_QUERY.match(query) is not None
            hits = []
            for i, d in enumerate(self.brain):
                count = d["content"].lower().count(needle)
                if count == 0:
                    continue
                exact = exact_query and re.search(
                    r"(?<![A-Za-z0-9-])" + re.escape(query) + r"(?![A-Za-z0-9-])", d["content"]) is not None
                hits.append({"uri": d["uri"], "chunk_id": str(i), "score": float(count),
                             "match_type": "exact_identifier" if exact else "bm25",
                             "excerpt": d["content"][:120]})
            hits.sort(key=lambda h: -h["score"])
            hits = hits[: params.get("max_results", 10)]
            return {"results": hits, "total_results": len(hits)}
        raise StepError("outil inconnu: " + tool)

    def _tenant(self, params):
        if params.get("tenant_id") != TENANT:
            raise StepError("tenant_id manquant")

    def _sql(self, params):
        sql = params["sql"]
        bound = list(params.get("params", {}).values())
        if sql == EMPTY_SEARCH_SQL:
            if params.get("maxRows") != 60 or params.get("timeoutMs") != 10000 or bound:
                raise StepError("search query limits")
            return [[ext, e["name"], e["status"], e["attributes"]] for ext, e in sorted(self.memory.items())
                    if e["entity_type"] == "company_memory_revision" and ext == ""]
        search = SEARCH_SQL.match(sql)
        if search:
            if search.group("ids") != search.group("prev") or not SQL_ID_LIST.match(search.group("ids")):
                raise StepError("liste d'identifiants SQL non conforme")
            if params.get("maxRows") != 60 or params.get("timeoutMs") != 10000 or bound:
                raise StepError("search query limits")
            ids = set(re.findall(r"'([^']*)'", search.group("ids")))
            rows = []
            for ext in sorted(self.memory):
                entry = self.memory[ext]
                if entry["entity_type"] != "company_memory_revision" or entry["status"] != "validated":
                    continue
                if ext in ids or entry["attributes"].get("previous_revision") in ids:
                    attrs = entry["attributes"]
                    rows.append([ext, entry["name"], entry["status"],
                                 json.dumps(attrs, ensure_ascii=False) if self.attributes_as_string else attrs])
            return rows
        if "json_extract_string(attributes, '$.previous_revision') = ?" in sql:
            return [
                [ext]
                for ext in sorted(self.memory)
                if self.memory[ext]["entity_type"] == "company_memory_revision"
                and self.memory[ext]["status"] == "validated"
                and self.memory[ext]["attributes"].get("previous_revision") == bound[0]
            ]
        if "SELECT external_id, name, json_extract_string(attributes, '$.previous_revision')" in sql:
            ext = bound[0]
            entry = self.memory.get(ext)
            if not entry or entry["entity_type"] != "company_memory_revision":
                return []
            return [[ext, entry["name"], entry["attributes"].get("previous_revision")]]
        raise StepError("SQL non reconnue par le fake Memory")


class Engine:
    def __init__(self, store):
        self.store = store

    def run(self, workflow_id, data):
        doc = WORKFLOWS_CACHE[workflow_id]
        actions = {a["id"]: a for a in doc["actions"]}
        if doc.get("forms"):
            order = doc["forms"][0]["actions_on_submit"]
        else:
            order = [a["id"] for a in doc["actions"]]
        state = dict(data)
        try:
            for action_id in order:
                self.step(actions[action_id], state)
            output = {k: render(v, state) for k, v in doc["output"].items()}
        except StepError as error:
            return {"state": "failed", "error": str(error)}
        return {"state": "completed", "data": output}

    def step(self, action, state):
        kind = action["type"]
        if kind == "code_execution":
            result = run_node(action["code"], resolve_context(action.get("context", {}), state))
            if not result["ok"]:
                raise StepError(result["error"])
            state[action["output_key"]] = result["result"]
        elif kind == "tool_call":
            params = render(action.get("params", {}), state, preserve_types=False)
            state[action["output_key"]] = self.store.call(action["tool"], params)
        elif kind == "workflow_call":
            child = self.run(action["workflow_id"], render(action.get("input", {}), state))
            if child["state"] != "completed":
                raise StepError(child["error"])
            state[action["output_key"]] = {"data": child["data"]}
        elif kind == "for_each":
            items = render(action["items"], state)
            if not items:
                state[action["output_key"]] = None
                return
            outputs = []
            for item in items:
                child = self.run(action["workflow_id"], {action["item_key"]: item})
                if child["state"] != "completed":
                    raise StepError(child["error"])
                outputs.append(child["data"])
            state[action["output_key"]] = outputs
        else:
            raise StepError("unsimulated action type: " + kind)


WORKFLOWS_CACHE = workflows()


@unittest.skipUnless(NODE, "node absent: code_execution steps unavailable")
class CodeStepTest(unittest.TestCase):
    """Behaviour of single code steps, data only ever reaching them through context."""

    HOSTILE = (
        "Consigne : npm:nats et `backticks`, ${process.env.X}, {{ json .record }} {{ y }},\n"
        'const a = "\\u2028\\n"; </script> “guillemets” — fin.'
    )

    def test_capture_validate_round_trips_hostile_text(self):
        step = code_steps(WORKFLOWS_CACHE["memory-capture-source"])[0]
        context = {
            "source_id": "src-hostile", "source_ref": "fixture:hostile", "content": self.HOSTILE,
            "source_date": "2026-10-10", "confirmation_manuelle": "oui",
        }
        result = run_node(step["code"], resolve_context({k: "{{ %s }}" % k for k in context}, context))
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["content"], self.HOSTILE)
        self.assertEqual(result["result"]["ref"], "fixture:hostile")

    def test_capture_refuses_missing_confirmation(self):
        step = code_steps(WORKFLOWS_CACHE["memory-capture-source"])[0]
        context = {"source_id": "s", "source_ref": "r", "content": "c", "source_date": "2026-10-10",
                   "confirmation_manuelle": "non"}
        result = run_node(step["code"], context)
        self.assertFalse(result["ok"])
        self.assertIn("manual_confirmation_required", result["error"])

    def test_propose_maps_absent_previous_revision_to_null(self):
        step = code_steps(WORKFLOWS_CACHE["memory-propose-update"])[0]
        base = {"proposal_id": "p-one", "source_id": "s-one", "title": "T", "content": "C",
                "evidence_quote": "C", "review_due": "2099-01-01", "confirmation_manuelle": "oui"}
        result = run_node(step["code"], dict(base, previous_revision=""))
        self.assertTrue(result["ok"], result)
        self.assertIsNone(result["result"]["previous_revision"])
        result = run_node(step["code"], dict(base, previous_revision="p-zero"))
        self.assertEqual(result["result"]["previous_revision"], "p-zero")
        result = run_node(step["code"], dict(base, previous_revision="../etc"))
        self.assertFalse(result["ok"])

    def test_candidates_read_concise_uri_and_fail_closed(self):
        step = action("memory-search", "candidates")
        hits = {"results": [
            {"uri": "company-memory://revisions/rev-a", "chunk_id": "1", "score": 2.0, "excerpt": "x"},
            {"uri": "company-memory://revisions/rev-a", "chunk_id": "2", "score": 1.0, "excerpt": "y"},
            {"uri": "https://example.invalid/other", "chunk_id": "3", "score": 0.5, "excerpt": "z"},
        ], "total_results": 3}
        result = run_node(step["code"], {"search": hits})
        self.assertEqual(result["result"], [{"proposal_id": "rev-a", "match_type": "other", "score": 2.0}])
        broken = {"results": [{"chunk_id": "1", "score": 1.0}], "total_results": 1}
        result = run_node(step["code"], {"search": broken})
        self.assertFalse(result["ok"])
        self.assertIn("invalid_brain_response", result["error"])
        detailed = {"results": [{"document": {"file_path": "company-memory://revisions/rev-a"}, "chunk_id": "1"}],
                    "total_results": 1}
        result = run_node(step["code"], {"search": detailed})
        self.assertFalse(result["ok"])
        self.assertIn("brain_concise_unsupported", result["error"])  # detailed form: no silent fallback
        empty = run_node(step["code"], {"search": {"results": None, "total_results": 0}})
        self.assertEqual(empty["result"], [])

    def test_candidates_keep_exact_identifier_and_best_score_per_revision(self):
        step = action("memory-search", "candidates")
        hits = {"results": [
            {"uri": "company-memory://revisions/rev-a", "chunk_id": "1", "score": 1.0, "match_type": "other"},
            {"uri": "company-memory://revisions/rev-a", "chunk_id": "2", "score": 3.0, "match_type": "exact_identifier"},
            {"uri": "company-memory://revisions/rev-b", "chunk_id": "3", "score": 2.0, "match_type": "other"},
        ], "total_results": 3}
        result = run_node(step["code"], {"search": hits})
        self.assertEqual(result["result"], [
            {"proposal_id": "rev-a", "match_type": "exact_identifier", "score": 3.0},
            {"proposal_id": "rev-b", "match_type": "other", "score": 2.0},
        ])

    @staticmethod
    def revision(proposal_id, answer, **extra):
        base = {"status": "validated", "proposal_id": proposal_id, "title": "Title " + proposal_id,
                "answer": answer, "citations": ["fixture:" + proposal_id], "expires_at": "2099-01-01",
                "source_date": "2026-10-10", "match_type": "other", "score": 1.0}
        base.update(extra)
        return base

    ATTRIBUTE_KEYS = ("citations", "source_ref", "expires_at", "title", "source_date", "reviewed_at",
                      "previous_revision")

    def search_context(self, revisions, query, attributes_as_string=False):
        """Memory rows and file listing equivalent to revision dicts: validated -> one Memory row,
        superseded -> Memory row plus native marker, any other status -> no Memory row."""
        rows, files = [], [{"path": "/company-memory/proposal-x.json"}]
        for r in revisions:
            if r["status"] not in ("validated", "superseded"):
                continue
            attrs = {k: r[k] for k in self.ATTRIBUTE_KEYS if k in r}
            rows.append([r["proposal_id"], r["answer"], "validated",
                         json.dumps(attrs, ensure_ascii=False) if attributes_as_string else attrs])
            if r["status"] == "superseded":
                files.append({"path": "/company-memory/superseded-%s.json" % r["proposal_id"]})
        candidates = [{"proposal_id": r["proposal_id"], "match_type": r.get("match_type", "other"),
                       "score": r.get("score", 0)} for r in revisions]
        return {"candidates": candidates, "memory_rows": {"rows": rows or None, "truncated": False},
                "files": files, "query": query}

    def run_answer(self, context):
        return run_node(action("memory-search", "search-answer")["code"], context)

    def search_value(self, revisions, query, attributes_as_string=False):
        result = self.run_answer(self.search_context(revisions, query, attributes_as_string))
        self.assertTrue(result["ok"], result)
        return result["result"]

    def test_build_query_inlines_checked_slugs_only(self):
        code = action("memory-search", "build-revision-query")["code"]
        result = run_node(code, {"candidates": [{"proposal_id": "rev-a"}, {"proposal_id": "rev_b-2"}]})
        self.assertTrue(result["ok"], result)
        expected = ("SELECT external_id, name, status, attributes FROM v_entities"
                    " WHERE entity_type = 'company_memory_revision' AND status = 'validated'"
                    " AND (external_id IN ('rev-a', 'rev_b-2')"
                    " OR json_extract_string(attributes, '$.previous_revision') IN ('rev-a', 'rev_b-2'))")
        self.assertEqual(result["result"], {"ids": ["rev-a", "rev_b-2"], "sql": expected})
        for empty in ([], None):
            sql = run_node(code, {"candidates": empty})["result"]["sql"]
            self.assertEqual(sql, EMPTY_SEARCH_SQL)
            # Every revision without a predecessor has previous_revision "": this clause would return all.
            self.assertNotIn("previous_revision", sql)
        self.assertNotIn("''", result["result"]["sql"])  # the IN list never contains an empty string
        self.assertIn('if (ids.some(id => id.length === 0)) throw new Error("empty_candidate_id");', code)
        for bad in ("rev'); DROP TABLE x; --", "Rev-A", "-rev", "a" * 65, "", None, 7):
            refused = run_node(code, {"candidates": [{"proposal_id": "rev-a"}, {"proposal_id": bad}]})
            self.assertFalse(refused["ok"], bad)
            self.assertIn("invalid_candidate_id", refused["error"])
        too_many = run_node(code, {"candidates": [{"proposal_id": "rev-%d" % i} for i in range(11)]})
        self.assertIn("too_many_candidates", too_many["error"])
        self.assertIn("invalid_candidates", run_node(code, {"candidates": {"x": 1}})["error"])

    def test_answer_reads_rows_null_as_empty_and_fails_on_tool_errors(self):
        context = self.search_context([self.revision("rev-a", "Text."), self.revision("rev-b", "Other.")], "text")
        context["memory_rows"] = {"rows": None}
        empty = self.run_answer(context)
        self.assertTrue(empty["ok"], empty)
        self.assertEqual(empty["result"]["results"], [])
        self.assertEqual((empty["result"]["candidate_count"], empty["result"]["suppressed_count"]), (2, 2))
        for broken, error in (({"error": "boom"}, "memory_lookup_unavailable"),
                              ({"columns": []}, "memory_lookup_unavailable"),
                              (None, "memory_lookup_unavailable"),
                              ({"rows": [["rev-a", "x", "validated", {}]], "truncated": True}, "memory_rows_truncated"),
                              ({"rows": [["../x", "x", "validated", {}]]}, "memory_row_invalid"),
                              ({"rows": [["rev-a", "x", "validated", "{non json"]]}, "memory_attributes_invalid"),
                              ({"rows": [["rev-a", "x", "validated", "[1]"]]}, "memory_attributes_invalid")):
            failed = self.run_answer(dict(context, memory_rows=broken))
            self.assertFalse(failed["ok"], broken)
            self.assertIn(error, failed["error"])
        unlisted = self.run_answer(dict(self.search_context([self.revision("rev-a", "x")], "x"), files=None))
        self.assertIn("storage_listing_unavailable", unlisted["error"])
        no_candidate = self.run_answer({"candidates": [], "memory_rows": {"rows": None}, "files": [], "query": "x"})
        self.assertEqual(no_candidate["result"]["summary"], "No validated revisions found.")

    def test_answer_without_candidate_is_empty_whatever_memory_returned(self):
        reference = self.search_value([self.revision("rev-a", "Text.")], "text")["excerpt_budget_chars"]
        many = {"rows": [["rev-%d" % i, "x", "validated", {"previous_revision": ""}] for i in range(60)],
                "truncated": True}
        for candidates in ([], None):
            for memory_rows in ({"rows": None}, many):
                result = self.run_answer({"candidates": candidates, "memory_rows": memory_rows, "files": [],
                                          "query": "absent"})
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["result"], {"results": [], "summary": "No validated revisions found.",
                                                    "candidate_count": 0, "suppressed_count": 0,
                                                    "excerpt_budget_chars": reference})

    def test_answer_accepts_attributes_as_object_or_json_string(self):
        revisions = [self.revision("rev-a", "Limit of six projects.", reviewed_at="2026-10-11T08:00:00.000Z"),
                     self.revision("rev-b", "Plafond ancien.", status="superseded")]
        as_object = self.search_value(revisions, "limit")
        as_string = self.search_value(revisions, "limit", attributes_as_string=True)
        self.assertEqual(as_object, as_string)
        self.assertEqual([r["proposal_id"] for r in as_object["results"]], ["rev-a"])
        row = as_object["results"][0]
        self.assertEqual((row["title"], row["date"], row["date_kind"], row["source_ref"], row["review_due"]),
                         ("Title rev-a", "2026-10-10", "source", "fixture:rev-a", "2099-01-01"))
        double = self.search_context(revisions[:1], "limit")
        double["memory_rows"]["rows"][0][3] = json.dumps(json.dumps(double["memory_rows"]["rows"][0][3]))
        self.assertEqual(self.run_answer(double)["result"]["results"], as_object["results"])
        positional = self.search_context(revisions[:1], "limit")
        positional["memory_rows"]["rows"] = [dict(zip(("external_id", "name", "status", "attributes"), r))
                                             for r in positional["memory_rows"]["rows"]]
        self.assertEqual(self.run_answer(positional)["result"]["results"], as_object["results"])

    def test_answer_hides_revisions_replaced_by_memory_row_or_native_marker(self):
        context = self.search_context([self.revision("rev-a", "Rule A."), self.revision("rev-b", "Rule B."),
                                       self.revision("rev-c", "Rule C."), self.revision("rev-self", "Rule S.",
                                                                                       previous_revision="rev-self")],
                                      "rule")
        # rev-a is replaced by a validated Memory row; rev-b by a native marker.
        context["memory_rows"]["rows"].append(["rev-a2", "Rule A revised.", "validated",
                                               {"previous_revision": "rev-a", "expires_at": "2099-01-01"}])
        context["files"].append({"path": "/company-memory/superseded-rev-b.json"})
        value = self.run_answer(context)["result"]
        self.assertEqual([r["proposal_id"] for r in value["results"]], ["rev-c", "rev-self"])
        self.assertEqual((value["candidate_count"], value["suppressed_count"]), (4, 2))
        self.assertNotIn("Rule A", value["summary"])
        self.assertNotIn("Rule B", value["summary"])
        for row in value["results"]:
            self.assertNotIn("superseded_by", row)

    def test_answer_excludes_candidates_absent_from_memory_or_expired(self):
        value = self.search_value([self.revision("rev-ok", "Present."),
                                   self.revision("rev-missing", "Absente de Memory.", status="not_indexed"),
                                   self.revision("rev-old", "Expired.", expires_at="2020-01-01"),
                                   self.revision("rev-bad-date", "Unreadable date.", expires_at="soon")], "present")
        self.assertEqual([r["proposal_id"] for r in value["results"]], ["rev-ok"])
        self.assertEqual((value["candidate_count"], value["suppressed_count"]), (4, 3))

    def test_answer_reads_citations_as_array_json_string_or_go_string(self):
        ref = "pilote-maurice:wiki/operations/one-sandbox.md#Authentification des agents@8963891e"
        forms = {
            "array": [ref, "autre:ref"],
            "json": json.dumps([ref, "autre:ref"], indent=2),
            "go": "[" + ref + "]",  # Go rendering of a single citation array; the reference contains spaces
            "go-padded": "  [" + ref + "]  ",
        }
        for name, citations in forms.items():
            row = self.search_value([self.revision("rev-" + name, "Text.", citations=citations, title="")],
                                    "text")["results"][0]
            self.assertEqual(row["source_ref"], ref, name)
            self.assertEqual(row["title"], "Authentification des agents", name)
        for citations, expected in (("[]", ""), ("", ""), ("fixture:sans-crochets", "fixture:sans-crochets"),
                                    ('[ref "citée" #x@y]', 'ref "citée" #x@y'), (None, ""), (7, ""),
                                    ([], ""), ([3, "fixture:b"], "fixture:b")):
            row = self.search_value([self.revision("rev-edge", "Text.", citations=citations)], "text")["results"][0]
            self.assertEqual(row["source_ref"], expected, citations)

    def test_answer_prefers_the_source_ref_attribute(self):
        row = self.search_value([self.revision("rev-s", "Text.", source_ref="wiki/a.md#Section A@1f2e@abc",
                                               citations="[wiki/b.md#Section B@9]", title="")],
                                "text")["results"][0]
        self.assertEqual(row["source_ref"], "wiki/a.md#Section A@1f2e@abc")
        self.assertEqual(row["title"], "Section A@1f2e")  # fragment up to the last @
        blank = self.search_value([self.revision("rev-b", "Text.", source_ref="  ", citations=["fixture:c"])],
                                  "text")["results"][0]
        self.assertEqual(blank["source_ref"], "fixture:c")
        titled = self.search_value([self.revision("rev-t", "Text.", source_ref="wiki/a.md#Section@1")],
                                   "text")["results"][0]
        self.assertEqual(titled["title"], "Title rev-t")  # the title attribute takes precedence over the derived title

    def test_answer_derives_title_and_unknown_date_for_rows_indexed_before_the_new_attributes(self):
        legacy = lambda pid, citation: {"status": "validated", "proposal_id": pid, "answer": "Legacy text.",
                                        "citations": [citation], "expires_at": "2099-01-01", "match_type": "other",
                                        "score": 1.0}
        value = self.search_value([legacy("rev-wiki", "wiki/regles.md#plafond-chantiers@3f2a9c1"),
                                   legacy("rev-frag", "wiki/regles.md#section"),
                                   legacy("rev-plain", "fixture:source-sans-fragment"),
                                   legacy("rev-empty", "wiki/regles.md#@3f2a")], "legacy")
        titles = {r["proposal_id"]: r["title"] for r in value["results"]}
        self.assertEqual(titles, {"rev-wiki": "plafond-chantiers", "rev-frag": "section",
                                  "rev-plain": "rev-plain", "rev-empty": "rev-empty"})
        for row in value["results"]:
            self.assertEqual((row["date"], row["date_kind"]), ("", "inconnue"))
            self.assertIn("unknown ", value["summary"])

    def test_compact_rows_carry_identifier_date_title_source_and_bounded_excerpts(self):
        value = self.search_value([
            self.revision("rev-long", ("A detailed procedure. " * 80).strip(), source_date="2026-10-10"),
            self.revision("rev-old", "ancien", status="superseded"),
            self.revision("rev-short", "Short.\nTwo lines.", source_date="",
                          reviewed_at="2026-10-12T08:00:00.000Z"),
        ], "procedure")
        self.assertEqual(value["candidate_count"], 3)
        self.assertEqual(value["suppressed_count"], 1)
        self.assertEqual([r["proposal_id"] for r in value["results"]], ["rev-long", "rev-short"])
        for row in value["results"]:
            self.assertEqual(set(row), {"proposal_id", "title", "date", "date_kind", "source_ref",
                                        "review_due", "match_type", "excerpts"})
            self.assertLessEqual(len(row["excerpts"]), 2)
            for excerpt in row["excerpts"]:
                self.assertLessEqual(len(excerpt), WINDOW_MAX)
        self.assertEqual(value["results"][0]["date_kind"], "source")
        self.assertEqual(value["results"][1]["date_kind"], "revue")
        self.assertEqual(value["results"][1]["date"], "2026-10-12T08:00:00.000Z")
        self.assertEqual(len(value["summary"].splitlines()), 2)
        self.assertNotIn("\n", value["summary"].splitlines()[1].split(" | ")[-1])

    def test_row_fields_are_flattened_and_bounded_so_each_revision_stays_on_one_line(self):
        value = self.search_value([self.revision("rev-nl", "Short text.", title="Title\nNext",
                                                 citations=["fixture:a\nfixture:b"])], "text")
        row = value["results"][0]
        self.assertEqual(row["title"], "Title Next")
        self.assertEqual(row["source_ref"], "fixture:a fixture:b")
        self.assertEqual(len(value["summary"].splitlines()), 1)
        self.assertNotIn("\n", value["summary"])
        long_row = self.search_value([self.revision("rev-long", "Short text.", title="T" * 250,
                                                    citations=["S" * 350])], "text")["results"][0]
        self.assertEqual(len(long_row["title"]), 200)
        self.assertEqual(len(long_row["source_ref"]), 300)

    @unittest.skip("Private replay scripts are not distributed in this library")
    def test_replay_scripts_read_only_the_compact_row_fields(self):
        row = self.search_value([self.revision("rev-r", "Replay response.")], "response")["results"][0]
        for script in (ROOT / "tests/search-replay.py", ROOT / "tests/mcp-replay.py"):
            text = script.read_text(encoding="utf-8")
            self.assertNotIn("'excerpt'", text, script.name)
            self.assertNotIn('"excerpt"', text, script.name)
            for field in ("proposal_id", "excerpts", "source_ref", "match_type"):
                self.assertIn(field, text, (script.name, field))
                self.assertIn(field, row, field)

    def test_excerpt_keeps_the_term_located_in_the_middle_of_a_long_text(self):
        text = (FILLER * 40)[:1500] + " La dérogation écrite du fondateur est requise. " + (FILLER * 40)[:1500]
        excerpts = self.search_value([self.revision("rev-mid", text)], "Derogation")["results"][0]["excerpts"]
        self.assertTrue(any("dérogation" in e for e in excerpts), excerpts)
        self.assertNotIn("dérogation", text[:EXCERPT_MAX])  # a beginning-only excerpt would miss the term
        self.assertTrue(excerpts[0].startswith("[…] "))
        for excerpt in excerpts:
            self.assertLessEqual(len(excerpt), WINDOW_MAX)

    def test_two_windows_cover_two_distant_terms_in_text_order(self):
        text = "alpha " + "x" * 95 + " " + "y" * 2400 + " beta gamma " + "z" * 500
        excerpts = self.search_value([self.revision("rev-two", text)], "Alpha, BETA !")["results"][0]["excerpts"]
        self.assertEqual(len(excerpts), 2, excerpts)
        self.assertIn("alpha", excerpts[0])
        self.assertIn("beta", excerpts[1])
        self.assertFalse(excerpts[0].startswith("[…] "))

    def test_excerpt_falls_back_to_the_start_when_no_term_matches(self):
        text = "Unremarkable text. " * 40
        excerpts = self.search_value([self.revision("rev-none", text)], "zèbre")["results"][0]["excerpts"]
        flat = " ".join(text.split())
        self.assertEqual(excerpts, [flat[:400] + " […]"])

    def test_exact_identifier_first_by_date_then_other_by_score(self):
        # A recent correction precedes the section it corrects.
        value = self.search_value([
            self.revision("rev-other-high", "AGENT-530 mentioned here.", match_type="other", score=9.0),
            self.revision("rev-exact-old", "Initial AGENT-530 entry.", match_type="exact_identifier",
                          source_date="2026-10-01"),
            self.revision("rev-other-low", "AGENT-530 encore.", match_type="other", score=1.0),
            self.revision("rev-exact-correction", "Correction AGENT-530: the limit is six.",
                          match_type="exact_identifier", source_date="2026-10-21"),
            self.revision("rev-exact-review", "AGENT-530 revue.", match_type="exact_identifier",
                          source_date="", reviewed_at="2026-10-15T08:00:00.000Z"),
        ], "AGENT-530")
        self.assertEqual([r["proposal_id"] for r in value["results"]],
                         ["rev-exact-correction", "rev-exact-review", "rev-exact-old",
                          "rev-other-high", "rev-other-low"])

    def test_response_size_is_bounded_for_ten_long_results(self):
        body = FILLER * 60
        revisions = [self.revision("rev-%02d" % i, body + " termeclé " + body + " termeclé2 " + body)
                     for i in range(10)]
        value = self.search_value(revisions, "termecle termecle2")
        self.assertEqual(len(value["results"]), 10)
        total = sum(len(e) for row in value["results"] for e in row["excerpts"])
        self.assertLessEqual(total, 10 * 2 * WINDOW_MAX)
        self.assertTrue(all(len(row["excerpts"]) == 2 for row in value["results"]))

    def test_query_answer_reports_successor_states(self):
        step = code_steps(WORKFLOWS_CACHE["memory-query"])[-1]

        def context(successor_rows, review_decision="validated", evidence="Corps", source_content="Corps",
                    markers=None):
            proposal = {"proposal_id": "rev-x", "source_id": "src-x", "title": "T", "content": "Corps",
                        "evidence_quote": "Corps", "review_due": "2099-01-01", "status": "proposed"}
            source = {"source_id": "src-x", "ref": "fixture:x", "content": source_content, "date": "2026-10-10"}
            review = {"proposal_id": "rev-x", "source_id": "src-x", "evidence_quote": evidence,
                      "decision": review_decision, "reviewed_at": "2026-10-11T08:00:00.000Z"}
            return {"proposal": proposal,
                    "source_file": {"content": json.dumps(source)},
                    "review_file": {"content": json.dumps(review)},
                    "successors": {"rows": successor_rows},
                    "markers": markers}

        ok = run_node(step["code"], context([]))
        self.assertEqual(ok["result"]["status"], "validated")
        self.assertEqual(ok["result"]["citations"], ["fixture:x"])
        sup = run_node(step["code"], context([["rev-y"]]))
        self.assertEqual(sup["result"]["status"], "superseded")
        self.assertEqual(sup["result"]["superseded_by"], "rev-y")
        self.assertEqual(sup["result"]["answer"], "Corps")
        conflict = run_node(step["code"], context([["rev-y"], ["rev-z"]]))
        self.assertEqual(conflict["result"]["status"], "successor_conflict")
        self.assertEqual(conflict["result"]["answer"], "")
        self_only = run_node(step["code"], context([["rev-x"]]))
        self.assertEqual(self_only["result"]["status"], "validated")
        marker = lambda successor, superseded="rev-x": [{"text": json.dumps(
            {"superseded": superseded, "successor": successor, "reviewed_at": "2026-10-21T08:00:00.000Z"})}]
        by_marker = run_node(step["code"], context([], markers=marker("rev-m")))
        self.assertEqual(by_marker["result"]["status"], "superseded")
        self.assertEqual(by_marker["result"]["superseded_by"], "rev-m")
        both = run_node(step["code"], context([["rev-y"]], markers=marker("rev-m")))
        self.assertEqual(both["result"]["status"], "successor_conflict")
        forged = run_node(step["code"], context([], markers=marker("rev-m", superseded="rev-autre")))
        self.assertFalse(forged["ok"])
        self.assertIn("supersession_marker_invalid", forged["error"])
        refused = run_node(step["code"], context([], review_decision="refused"))
        self.assertEqual(refused["result"]["status"], "refused")
        changed = run_node(step["code"], context([], source_content="autre"))
        self.assertEqual(changed["result"]["status"], "evidence_changed")
        missing = run_node(step["code"], {k: v for k, v in context([]).items() if k != "successors"})
        self.assertFalse(missing["ok"])
        unavailable = run_node(step["code"], dict(context([]), successors={"columns": []}))
        self.assertFalse(unavailable["ok"])
        self.assertIn("successor_lookup_unavailable", unavailable["error"])
        # rows=null with rowCount 0 is an empty result, as Memory returns it when nothing matches.
        empty_null = run_node(step["code"], dict(context([]), successors={"rows": None, "queryStats": {"rowCount": 0}}))
        self.assertEqual(empty_null["result"]["status"], "validated")
        no_stats = run_node(step["code"], dict(context([]), successors={"rows": None}))
        self.assertEqual(no_stats["result"]["status"], "validated")  # child call: queryStats absent
        bad_missing = run_node(step["code"], dict(context([]), successors={"columns": []}))
        self.assertFalse(bad_missing["ok"])


@unittest.skipUnless(NODE, "node absent: simulated Workflow engine unavailable")
class ChainTest(unittest.TestCase):
    """Runs the shipped Workflows end to end against in-memory fakes."""

    def setUp(self):
        self.store = Store()
        self.engine = Engine(self.store)
        self.hostile = (
            "Règle synthétique : npm:nats, `backticks`, ${x} et {{ json .record }}.\n"
            "Ligne « deux » avec un antislash \\ et un JSON {\"a\": [1]}."
        )

    def run_wf(self, workflow_id, data, expected="completed"):
        result = self.engine.run(workflow_id, data)
        self.assertEqual(result["state"], expected, (workflow_id, result))
        return result.get("data", {})

    def capture(self, source_id, content):
        return self.run_wf("memory-capture-source", {
            "source_id": source_id, "source_ref": "fixture:" + source_id, "content": content,
            "source_date": "2026-10-10", "confirmation_manuelle": "oui"})

    def propose(self, proposal_id, source_id, content, quote, previous="", due="2099-01-01"):
        return self.run_wf("memory-propose-update", {
            "proposal_id": proposal_id, "source_id": source_id, "title": "Title " + proposal_id,
            "content": content, "evidence_quote": quote, "review_due": due,
            "previous_revision": previous, "confirmation_manuelle": "oui"})

    def review(self, proposal_id, decision="validated", expected="completed"):
        return self.run_wf("memory-review-update", {
            "proposal_id": proposal_id, "decision": decision, "review_note": "synthetic review",
            "confirmation_manuelle": "oui"}, expected)

    def query(self, proposal_id, expected="completed"):
        return self.run_wf("memory-query", {"proposal_id": proposal_id}, expected)

    def index(self, proposal_id, expected="completed"):
        return self.run_wf("memory-index-revision", {"proposal_id": proposal_id, "confirmation_manuelle": "oui"},
                           expected)

    def search(self, query):
        return self.run_wf("memory-search", {"query": query})

    def test_hostile_text_survives_capture_proposal_query_index(self):
        self.capture("src-h", self.hostile)
        source = json.loads(self.store.files["/company-memory/source-src-h.json"])
        self.assertEqual(source["content"], self.hostile)
        quote = self.hostile.splitlines()[0]
        self.propose("rev-h", "src-h", self.hostile, quote)
        self.review("rev-h")
        answer = self.query("rev-h")
        self.assertEqual(answer["answer"], self.hostile)
        self.assertEqual(answer["status"], "validated")
        self.index("rev-h")
        self.assertEqual(self.store.brain[-1]["content"], self.hostile)
        self.assertEqual(self.store.memory["rev-h"]["name"], self.hostile)

    def test_replacement_hides_predecessor_from_search_and_marks_it(self):
        self.capture("src-r", "The limit is three projects.")
        quote = "The limit is three projects."
        self.propose("rev-old", "src-r", "The limit is three projects. Previous rule.", quote)
        self.review("rev-old")
        self.index("rev-old")
        self.capture("src-r2", "The limit is six projects since 2026-10-21.")
        self.propose("rev-new", "src-r2", "The limit is six projects.",
                     "The limit is six projects", previous="rev-old")
        self.review("rev-new")
        self.index("rev-new")
        self.assertEqual(self.store.memory["rev-new"]["attributes"]["previous_revision"], "rev-old")
        self.assertEqual(self.store.memory["rev-old"]["attributes"]["previous_revision"], "")

        old = self.query("rev-old")
        self.assertEqual(old["status"], "superseded")
        self.assertEqual(old["superseded_by"], "rev-new")
        self.assertEqual(old["answer"], "The limit is three projects. Previous rule.")

        found = self.search("limit")
        ids = [row["proposal_id"] for row in found["results"]]
        self.assertEqual(ids, ["rev-new"])
        self.assertEqual(found["suppressed_count"], 1)
        self.assertNotIn("Previous rule", json.dumps(found, ensure_ascii=False))

        self.index("rev-old", expected="failed")
        self.assertEqual(self.query("rev-new")["status"], "validated")

    def test_second_replacement_is_refused_and_the_first_one_stays(self):
        self.capture("src-c", "Synthetic conflict policy.")
        quote = "Synthetic conflict policy."
        self.propose("rev-base", "src-c", "Synthetic conflict policy.", quote)
        self.review("rev-base")
        self.index("rev-base")
        self.propose("rev-fork-a", "src-c", "Synthetic conflict policy.", quote, previous="rev-base")
        self.review("rev-fork-a")
        self.index("rev-fork-a")
        marker = json.loads(self.store.files["/company-memory/superseded-rev-base.json"])
        self.assertEqual((marker["superseded"], marker["successor"]), ("rev-base", "rev-fork-a"))
        self.propose("rev-fork-b", "src-c", "Synthetic conflict policy.", quote, previous="rev-base")
        refused = self.engine.run("memory-review-update", {
            "proposal_id": "rev-fork-b", "decision": "validated", "review_note": "synthetic review",
            "confirmation_manuelle": "oui"})
        self.assertEqual(refused["state"], "failed")
        self.assertEqual(refused["error"], "successor_conflict")  # explicit refusal before any write
        self.assertNotIn("rev-fork-b", self.store.memory)
        self.assertNotIn("/company-memory/review-rev-fork-b.json", self.store.files)
        replaced = self.query("rev-base")
        self.assertEqual(replaced["status"], "superseded")
        self.assertEqual(replaced["superseded_by"], "rev-fork-a")
        found = self.search("conflict")
        self.assertEqual([r["proposal_id"] for r in found["results"]], ["rev-fork-a"])
        self.assertEqual(found["suppressed_count"], 1)
        # A Memory-only successor in addition to the native marker remains a conflict.
        self.store.memory["rev-fork-b"] = {"entity_type": "company_memory_revision", "name": "x",
                                           "status": "validated", "attributes": {"previous_revision": "rev-base"}}
        conflict = self.query("rev-base")
        self.assertEqual(conflict["status"], "successor_conflict")
        self.assertEqual(conflict["answer"], "")
        self.assertEqual(conflict["successor_ids"], ["rev-fork-a", "rev-fork-b"])
        del self.store.memory["rev-fork-b"]

    def test_validated_successor_not_indexed_still_hides_its_predecessor(self):
        self.capture("src-u", "Synthetic unindexed limit.")
        quote = "Synthetic unindexed limit."
        self.propose("rev-x", "src-u", quote, quote)
        self.review("rev-x")
        self.index("rev-x")
        self.assertEqual(self.search("limit")["results"][0]["proposal_id"], "rev-x")
        self.capture("src-v", "Synthetic revised unindexed limit.")
        revised = "Synthetic revised unindexed limit."
        self.propose("rev-y", "src-v", revised, revised, previous="rev-x")
        self.review("rev-y")  # validated, never indexed: only the native marker links it to X
        self.assertNotIn("rev-y", self.store.memory)
        self.assertEqual(self.query("rev-x")["status"], "superseded")
        self.assertEqual(self.query("rev-x")["superseded_by"], "rev-y")
        found = self.search("limit")
        self.assertEqual(found["results"], [])
        self.assertEqual(found["suppressed_count"], 1)
        self.index("rev-x", expected="failed")

    def fail_writes_to(self, path):
        original = self.store.call

        def failing(tool, params):
            if tool == "write_file" and params["path"] == path:
                raise StepError("simulated write failure")
            return original(tool, params)

        self.store.call = failing
        return original

    def replaced_pair(self, prefix):
        self.capture("src-" + prefix, "Synthetic limit " + prefix + ".")
        quote = "Synthetic limit " + prefix + "."
        self.propose(prefix + "-x", "src-" + prefix, quote, quote)
        self.review(prefix + "-x")
        self.index(prefix + "-x")
        self.propose(prefix + "-y", "src-" + prefix, quote, quote, previous=prefix + "-x")
        return prefix + "-x", prefix + "-y"

    def test_failed_review_write_leaves_no_marker_and_the_predecessor_served(self):
        # Adversarial review: a marker without a validated review hid X for an unvalidated replacement.
        x, y = self.replaced_pair("rw")
        original = self.fail_writes_to("/company-memory/review-%s.json" % y)
        self.review(y, expected="failed")
        self.store.call = original
        self.assertNotIn("/company-memory/superseded-%s.json" % x, self.store.files)
        self.assertNotIn("/company-memory/review-%s.json" % y, self.store.files)
        self.assertEqual(self.query(x)["status"], "validated")
        self.assertEqual([r["proposal_id"] for r in self.search("limit")["results"]], [x])
        self.review(y)  # review can be retried: nothing final was written
        self.assertEqual(self.query(x)["superseded_by"], y)

    def test_failed_marker_write_keeps_the_validated_review_and_replaces_at_indexing(self):
        x, y = self.replaced_pair("mk")
        original = self.fail_writes_to("/company-memory/superseded-%s.json" % x)
        self.review(y, expected="failed")
        self.store.call = original
        review = json.loads(self.store.files["/company-memory/review-%s.json" % y])
        self.assertEqual(review["decision"], "validated")
        self.assertNotIn("/company-memory/superseded-%s.json" % x, self.store.files)
        self.assertEqual(self.query(y)["status"], "validated")
        self.assertEqual(self.query(x)["status"], "validated")  # conservative side: X remains served until Y is indexed
        self.assertEqual([r["proposal_id"] for r in self.search("limit")["results"]], [x])
        self.index(y)
        self.assertEqual(self.query(x)["superseded_by"], y)
        found = self.search("limit")
        self.assertEqual([r["proposal_id"] for r in found["results"]], [y])
        self.assertEqual(found["suppressed_count"], 1)

    def test_marker_is_written_only_by_a_validated_review_and_refused_siblings_do_not_block(self):
        self.capture("src-p", "Synthetic marker rule.")
        quote = "Synthetic marker rule."
        self.propose("rev-p", "src-p", quote, quote)
        self.review("rev-p")
        self.index("rev-p")
        self.propose("rev-q", "src-p", quote, quote, previous="rev-p")
        self.review("rev-q", decision="refused")
        self.assertNotIn("/company-memory/superseded-rev-p.json", self.store.files)
        self.propose("rev-r", "src-p", quote, quote, previous="rev-p")
        self.review("rev-r")
        marker = json.loads(self.store.files["/company-memory/superseded-rev-p.json"])
        self.assertEqual(marker["successor"], "rev-r")
        self.assertTrue(marker["reviewed_at"])
        self.assertEqual(self.query("rev-p")["status"], "superseded")

        self.capture("src-e", "Synthetic expired data.")
        self.propose("rev-exp", "src-e", "Synthetic expired data.", "Synthetic expired data.", due="2020-01-01")
        self.review("rev-exp")
        self.assertEqual(self.query("rev-exp")["status"], "expired")
        self.index("rev-exp", expected="failed")
        self.assertEqual(self.search("expired")["results"], [])

    def test_refused_review_is_never_indexed_nor_served(self):
        self.capture("src-f", "Synthetic refused statement.")
        self.propose("rev-ref", "src-f", "Synthetic refused statement.", "Synthetic refused statement.")
        self.review("rev-ref", decision="refused")
        self.assertEqual(self.query("rev-ref")["status"], "refused")
        self.index("rev-ref", expected="failed")
        self.assertEqual(self.search("refused")["results"], [])
        self.assertEqual(self.search("refused")["candidate_count"], 0)

    def test_negative_cases_fail_closed(self):
        self.run_wf("memory-capture-source", {
            "source_id": "src-n", "source_ref": "r", "content": "c", "source_date": "2026-10-10",
            "confirmation_manuelle": "non"}, expected="failed")
        self.run_wf("memory-query", {"proposal_id": "../secret"}, expected="failed")
        self.run_wf("memory-search", {"query": "   "}, expected="failed")
        self.run_wf("memory-review-update", {"proposal_id": "rev-none", "decision": "approved",
                                             "confirmation_manuelle": "oui"}, expected="failed")

    def test_search_calls_brain_once_memory_once_and_lists_once_without_child_workflow(self):
        self.capture("src-k", "Synthetic counting rule.")
        quote = "Synthetic counting rule."
        for i in range(3):
            self.propose("rev-k%d" % i, "src-k", quote, quote)
            self.review("rev-k%d" % i)
            self.index("rev-k%d" % i)
        self.store.calls = []
        found = self.search("counting")
        self.assertEqual(len(found["results"]), 3)
        self.assertEqual(self.store.calls, ["brain.keyword", "memory.query", "list_files"])

    def test_index_stores_title_and_dates_and_search_reads_them(self):
        self.capture("src-t", "Synthetic title and dates.")
        quote = "Synthetic title and dates."
        self.propose("rev-t", "src-t", quote, quote)
        self.review("rev-t")
        self.index("rev-t")
        attrs = self.store.memory["rev-t"]["attributes"]
        self.assertEqual((attrs["title"], attrs["source_date"], attrs["source_ref"]),
                         ("Title rev-t", "2026-10-10", "fixture:src-t"))
        self.assertTrue(attrs["reviewed_at"])
        self.assertEqual(json.loads(attrs["citations"]), ["fixture:src-t"])  # JSON string, not [fixture:src-t]
        for as_string in (False, True):
            self.store.attributes_as_string = as_string
            row = self.search("synthetic")["results"][0]
            self.assertEqual((row["proposal_id"], row["title"], row["date"], row["date_kind"], row["source_ref"]),
                             ("rev-t", "Title rev-t", "2026-10-10", "source", "fixture:src-t"))
            self.assertEqual(row["excerpts"], [quote])

    def test_tool_parameters_render_a_lone_array_as_go_text(self):
        # Fake engine fidelity: this rendering produced [ref] in Memory before JSON rendering.
        state = {"record": {"citations": ["a b", "c"], "n": 60.0}}
        self.assertEqual(render({"x": "{{ record.citations }}"}, state, preserve_types=False), {"x": "[a b c]"})
        self.assertEqual(render({"x": "{{ record.citations }}"}, state), {"x": ["a b", "c"]})
        self.assertEqual(json.loads(render({"x": "{{ json .record.citations }}"}, state, preserve_types=False)["x"]),
                         ["a b", "c"])
        self.assertEqual(render({"x": "{{ record.n }}"}, state, preserve_types=False), {"x": "60"})

    def test_rows_indexed_with_go_rendered_citations_still_give_source_ref_and_title(self):
        ref = "pilote-maurice:wiki/operations/am-lifecycle-loop.md#Introduction et portée@8963891e"
        self.capture("src-g", "Revision rendered as Go text.")
        quote = "Revision rendered as Go text."
        self.propose("rev-g", "src-g", quote, quote)
        self.review("rev-g")
        self.index("rev-g")
        attrs = self.store.memory["rev-g"]["attributes"]
        for key in ("source_ref", "title"):
            del attrs[key]
        attrs["citations"] = "[" + ref + "]"  # shape observed on Agent C (index v7)
        for as_string in (False, True):
            self.store.attributes_as_string = as_string
            row = self.search("rendered")["results"][0]
            self.assertEqual((row["source_ref"], row["title"], row["date_kind"]),
                             (ref, "Introduction et portée", "source"))

    def test_revision_indexed_before_the_new_attributes_gets_a_derived_title(self):
        self.capture("src-l", "Synthetic legacy revision.")
        quote = "Synthetic legacy revision."
        self.propose("rev-l", "src-l", quote, quote)
        self.review("rev-l")
        self.index("rev-l")
        for key in ("title", "source_date", "reviewed_at"):
            del self.store.memory["rev-l"]["attributes"][key]
        row = self.search("legacy")["results"][0]
        self.assertEqual((row["title"], row["date"], row["date_kind"]), ("rev-l", "", "inconnue"))

    def test_search_without_brain_candidate_answers_empty_even_with_many_revisions(self):
        # Campaign: 607 revisions without predecessors (previous_revision = ""), no Brain candidates; the old
        # IN ('') query returned all, Memory truncated at 60 rows and search failed (memory_rows_truncated).
        for i in range(61):
            self.store.memory["rev-bulk-%02d" % i] = {
                "entity_type": "company_memory_revision", "name": "Text %d." % i, "status": "validated",
                "attributes": {"previous_revision": "", "expires_at": "2099-01-01", "citations": "[fixture:x]"}}
        self.store.calls = []
        found = self.search("notfound")
        self.assertEqual((found["results"], found["candidate_count"], found["suppressed_count"]), ([], 0, 0))
        self.assertEqual(found["summary"], "No validated revisions found.")
        self.assertEqual(self.store.calls, ["brain.keyword", "memory.query", "list_files"])

    def test_brain_hit_without_memory_row_is_suppressed_not_failed(self):
        self.store.brain.append({"uri": "company-memory://revisions/rev-ghost", "content": "synthetic ghost"})
        found = self.search("ghost")
        self.assertEqual(found["results"], [])
        self.assertEqual((found["candidate_count"], found["suppressed_count"]), (1, 1))

    def test_search_fails_closed_on_brain_response_without_uri(self):
        original = self.store.call

        def broken(tool, params):
            if tool == "brain.keyword":
                return {"results": [{"chunk_id": "1", "score": 1.0}], "total_results": 1}
            return original(tool, params)

        self.store.call = broken
        self.run_wf("memory-search", {"query": "x"}, expected="failed")

    def test_detailed_brain_image_fails_memory_search_explicitly(self):
        original = self.store.call

        def detailed(tool, params):
            if tool == "brain.keyword":
                return {"results": [{"document": {"file_path": "company-memory://revisions/rev-a"}, "chunk_id": "1",
                                     "score": 1.0}], "total_results": 1}
            return original(tool, params)

        self.store.call = detailed
        result = self.engine.run("memory-search", {"query": "x"})
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["error"], "brain_concise_unsupported")

    def test_search_requires_concise_format(self):
        original = self.store.call

        def detailed(tool, params):
            if tool == "brain.keyword":
                params = dict(params)
                params.pop("response_format", None)
            return original(tool, params)

        self.store.call = detailed
        self.run_wf("memory-search", {"query": "x"}, expected="failed")


class ContractTest(unittest.TestCase):
    def test_module_manifest_matches_shipped_versions(self):
        manifest = load_json(MODULE / "module.yaml")
        self.assertEqual(manifest["version"], "0.3.2")
        for group in ("actions", "queries"):
            for entry in manifest["provides"][group]:
                doc = WORKFLOWS_CACHE[entry["workflow_id"]]
                self.assertEqual(entry["workflow_version"], doc["version"], entry)
        for entry in manifest["provides"]["apps"]:
            app = load_json(MINIAPPS / (entry["miniapp_id"] + ".json"))
            self.assertEqual(entry["miniapp_version"], app["version"], entry)
        self.assertEqual(WORKFLOWS_CACHE["memory-search"]["version"], "10")

    def test_confirmation_options_keep_wire_values_and_english_labels(self):
        for name in ("memory-capture-source", "memory-propose-update", "memory-review-update", "memory-index-revision"):
            fields = WORKFLOWS_CACHE[name]["forms"][0]["fields"]
            confirmation = next(f for f in fields if f["name"] == "confirmation_manuelle")
            self.assertEqual({o["value"]: o["label"] for o in confirmation["options"]}, {"oui": "Yes", "non": "No"})

    def test_search_summary_uses_english_labels_without_changing_wire_values(self):
        code = action("memory-search", "search-answer")["code"]
        self.assertIn('date_kind: "revue"', code)
        self.assertIn('date_kind: "inconnue"', code)
        self.assertIn('revue: "review", inconnue: "unknown"', code)

    def test_review_buttons_submit_english_generated_notes(self):
        app = load_json(MINIAPPS / "memory-review.json")
        notes = [event["workflow"]["input"]["review_note"] for event in app["events"]
                 if "review_note" in event["workflow"].get("input", {})]
        self.assertEqual(notes, ["Review from the MiniApp"] * 3)

    def test_review_load_replaces_previous_decision_state(self):
        app = load_json(MINIAPPS / "memory-review.json")
        inspect = next(event for event in app["events"] if event["event_id"] == "inspect")
        self.assertEqual(inspect["result_to_state"], "proposal_id")
        self.assertEqual(
            {event["result_to_state"] for event in app["events"] if event["event_id"] != "inspect"},
            {"proposal_id"},
        )
        for event in app["events"]:
            if event["event_id"] != "inspect":
                self.assertEqual(
                    event["workflow"]["input"]["proposal_id"],
                    "{{ state.proposal_id.proposal_id }}",
                )

        def deep_merge(base, patch):
            merged = dict(base)
            for key, value in patch.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = deep_merge(merged[key], value)
                else:
                    merged[key] = value
            return merged

        state = {"proposal_id": ""}
        state = deep_merge(state, {"proposal_id": {"proposal_id": "old", "review": {"decision": "disputed"}}})
        state = deep_merge(state, {"proposal_id": "new"})
        self.assertEqual(state["proposal_id"], "new")
        self.assertNotIsInstance(state["proposal_id"], dict)

    def test_revalidation_calls_pin_the_new_query_version(self):
        calls = [(name, a) for name, doc in WORKFLOWS_CACHE.items() for a in doc["actions"]
                 if a["type"] == "workflow_call"]
        self.assertEqual([(name, a["id"]) for name, a in calls], [("memory-index-revision", "revalidate-revision")])
        for _, call in calls:
            self.assertEqual(call["workflow_id"], "memory-query")
            self.assertEqual(call["workflow_version"], WORKFLOWS_CACHE["memory-query"]["version"])

    def test_action_ids_are_unique_across_the_module(self):
        # A shared ID across Workflows may resolve in the wrong definition (AGENT-1054).
        seen = {}
        for name, doc in WORKFLOWS_CACHE.items():
            ids = [a["id"] for a in doc["actions"]]
            self.assertEqual(len(ids), len(set(ids)), name)
            for action_id in ids:
                self.assertNotIn(action_id, seen, f"{action_id}: {seen.get(action_id)} et {name}")
                seen[action_id] = name
            for form in doc.get("forms", []):
                self.assertEqual(form["actions_on_submit"], ids, name)

    def test_search_uses_one_memory_query_and_no_child_workflow(self):
        doc = WORKFLOWS_CACHE["memory-search"]
        self.assertEqual([(a["id"], a["type"]) for a in doc["actions"]], [
            ("search-validate", "code_execution"), ("search", "tool_call"), ("candidates", "code_execution"),
            ("build-revision-query", "code_execution"), ("read-revisions", "tool_call"),
            ("list-markers", "tool_call"), ("search-answer", "code_execution")])
        read = action("memory-search", "read-revisions")
        self.assertEqual(read["tool"], "memory.query")
        self.assertEqual(read["params"], {"tenant_id": TENANT, "sql": "{{ revision_query.sql }}",
                                          "maxRows": 60, "timeoutMs": 10000})
        self.assertEqual(action("memory-search", "list-markers")["params"], {"path": "/company-memory"})
        self.assertNotIn("memory-resolve-candidate", WORKFLOWS_CACHE)
        for path in MODULE.rglob("*"):
            if path.is_file():
                self.assertNotIn("memory-resolve-candidate", path.read_text(encoding="utf-8"), path.name)

    def test_review_file_is_written_before_the_supersession_marker(self):
        doc = WORKFLOWS_CACHE["memory-review-update"]
        ids = [a["id"] for a in doc["actions"]]
        self.assertEqual(ids[-2:], ["review-write", "write-supersession"])
        self.assertEqual(doc["forms"][0]["actions_on_submit"][-2:], ["review-write", "write-supersession"])
        self.assertLess(ids.index("review-check-absent"), ids.index("review-write"))  # conflict rejected before any write

    def test_index_revision_stores_title_dates_source_ref_and_json_citations(self):
        attrs = action("memory-index-revision", "store-memory")["params"]["items"][0]["attributes"]
        for key in ("title", "source_date", "reviewed_at", "source_ref"):
            self.assertEqual(attrs[key], "{{ record.%s }}" % key)
        # An array-only tool parameter renders as [a b] (ResolveTemplateMap): use explicit JSON.
        self.assertEqual(attrs["citations"], "{{ json .record.citations }}")

    def test_code_steps_hold_no_runtime_data_and_no_nats_text(self):
        for name, doc in WORKFLOWS_CACHE.items():
            for step in code_steps(doc):
                self.assertNotIn("{{", step["code"], f"{name}/{step['id']}")
                self.assertNotIn("}}", step["code"], f"{name}/{step['id']}")
                self.assertIsNone(NATS_IMPORT.search(step["code"]), f"{name}/{step['id']}")

    def test_context_keys_are_bindable_and_expressions_supported(self):
        for name, doc in WORKFLOWS_CACHE.items():
            for step in code_steps(doc):
                for key, expression in step.get("context", {}).items():
                    self.assertTrue(IDENTIFIER.match(key) and key not in RESERVED, f"{name}/{key}")
                    self.assertTrue(
                        SINGLE_PATH.match(expression) or DEFAULT_EMPTY.match(expression),
                        f"{name}/{step['id']}/{key}: {expression}",
                    )

    def test_workflows_carry_context_and_expected_versions(self):
        self.assertEqual(len(WORKFLOWS_CACHE), 10)
        for name, doc in WORKFLOWS_CACHE.items():
            for step in code_steps(doc):
                self.assertIn("context", step, f"{name}/{step['id']}")
            expected = {"memory-capture-source": "5", "memory-propose-update": "5", "memory-inspect": "5",
                        "memory-search": "10", "memory-query": "8", "memory-review-update": "7",
                        "memory-index-revision": "9", "memory-read-supersession": "2",
                        "memory-write-supersession": "3", "memory-health": "4"}[name]
            self.assertEqual(doc["version"], expected, name)

    def test_brain_request_asks_for_concise_format_once(self):
        calls = [a for a in WORKFLOWS_CACHE["memory-search"]["actions"] if a.get("tool") == "brain.keyword"]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["params"]["response_format"], "concise")

    def test_read_successors_sql_and_its_binding(self):
        action = next(a for a in WORKFLOWS_CACHE["memory-query"]["actions"] if a["id"] == "read-successors")
        self.assertEqual(action["tool"], "memory.query")
        self.assertEqual(action["params"]["tenant_id"], TENANT)
        self.assertIn("json_extract_string(attributes, '$.previous_revision') = ?", action["params"]["sql"])
        self.assertIn("status = 'validated'", action["params"]["sql"])
        self.assertEqual(action["params"]["params"], {"revision": "{{ query.proposal_id }}"})
        self.assertIn("read-successors", WORKFLOWS_CACHE["memory-query"]["forms"][0]["actions_on_submit"])

    def test_query_console_shows_replacement(self):
        app = load_json(MINIAPPS / "memory-query-console.json")
        values = [item.get("value") for item in app["ui"]["configuration"]["layout"]]
        self.assertIn({"state": "result.superseded_by"}, values)
        self.assertEqual(app["version"], "5")

    @unittest.skipUnless(HAS_JSONSCHEMA and VALIDATOR.exists(), "jsonschema or Agent Spec V2 validator unavailable")
    def test_shipped_json_is_valid_agent_spec_v2(self):
        spec = importlib.util.spec_from_file_location("agent_spec_validator", VALIDATOR)
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        for path in sorted(WORKFLOWS.glob("*.json")):
            validator.validate_document("agentmaurice.workflow/v2", path.read_bytes())
        for path in sorted(MINIAPPS.glob("*.json")):
            validator.validate_document("agentmaurice.miniapp/v2", path.read_bytes())
        validator.validate_document("agentmaurice.test_plan/v2", (ROOT / "tests/test-plan.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
