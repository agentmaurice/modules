# Company Memory 0.3.2 — manual memory, supersession and compact search

Source: GitLab pilote-maurice commit `8cb35a14b825dcdae4515d46e3b4c5149c154901`; historical 0.2.0: GitHub library commit `dc935630764b24c819defd03cc487bddf8f87399`. The 0.2.0 → 0.3.0 upgrade was not qualified on One or Viewer in this repository. Version 0.3.1 translates presentation without renaming wire keys or historical values; 0.3.2 fixes the review MiniApp's stale decision display without changing Workflow wire keys. Runtime and Viewer qualification remain to be performed; private replay scripts are not distributed. The generated pilote-maurice validator is absent here, so its test is skipped.

This standalone, manual Module V2 stores sources, proposes updates and records a manual review decision. It returns a proposal only if its decision is `validated`, its quotation still matches the source exactly and `review_due` has not passed according to the server clock. Search excludes revisions replaced by newer validated revisions.

IDs are slugs `[a-z0-9][a-z0-9_-]{0,63}`. Files under `/company-memory/` include `source-ID.json`, `proposal-ID.json` and `review-ID.json`. Writes require `confirmation_manuelle=oui` and use `overwrite:false`. This read-then-write sequence has no CAS, append-only guarantee or concurrency safety: the model is single-writer. A correction creates a new proposal.

User input remains data and is never interpreted as instructions. No LLM, web call or scheduler is required. Indexing and search require the Memory and Brain MCPs declared by the consumer Agent. `memory-health` lists at most 100 files and is not a complete validation. The six MiniApps use native `form.submit` events and show Workflow results. `tests/test-plan.json` contains negative and read-only cases; positive flows require fresh IDs in a `spec-init` consumer. Form dates use `YYYY-MM-DD`; deadlines are evaluated at the beginning of the UTC day. A query reads an exact revision, not a calculated current page.

## Changes introduced in 0.3.0 (AGENT-1050)

| Topic | 0.2.0 | 0.3.0 |
|---|---|---|
| `memory-search` | Full text in `results`; one `memory-query` child per candidate | Compact result per valid revision with up to two 400-character, query-coverage excerpts; exact identifiers first by date, then score. Full text remains in `memory-query`. One Brain call, one Memory query and one listing; no child Workflow. |
| Superseded revision | Served as validated until `review_due` | `memory-query` returns `superseded` and `superseded_by`; search excludes it. |
| Captured data | Interpolated into JS (`{{ json .record }}`), rejecting text containing `npm:nats` | Passed via `context` as sandbox `const` bindings, never interpolated into `code`; text is read back unchanged. |
| Brain | `brain.keyword` without format | `response_format: "concise"`; requires the corrected Brain image (AGENT-1049). |
| Action IDs | Names such as `validate`, `write` and `revalidate` repeated across Workflows | IDs are unique across the Module (e.g. `capture-validate`, `query-answer`, `revalidate-revision`), checked offline; shared IDs could resolve against the wrong definition (AGENT-1054). |
| Versions | Module 0.2.0, Workflows version 2 | Module 0.3.0: search 9, query 7, index 8, review 6, capture 4, propose 4, inspect 4, health 3, write-supersession 2, read-supersession 1; `memory-resolve-candidate` retired; query MiniApp 4. |

In 0.3.1 the respective Workflow versions are 10, 8, 9, 7, 5, 5, 5, 4, 3 and 2. MiniApps capture, propose and review are version 4; query is 5; index and search are 3. In 0.3.2, the review MiniApp is version 5: loading a proposal replaces the review state carried by the previous proposal before the new inspection is rendered. The manifest pins these versions. Historical IDs, fields, enums and native files remain readable; consumers must update their explicit pins.

### `context` and code steps

Chatserver evaluates `context` before the sandbox (`internal/recipes/mcp_executor.go`, `code_execution`). A single `{{ nom }}` expression preserves the value type; `{{ default "" .nom }}` yields an empty string for a missing key. The sandbox writes `context.json` (`internal/business/core/sandbox_service.go`) and binds each key as `const` in `generateUserModule`. `natsClientImport` (`internal/business/core/sandbox_host_channel.go`) scans only `code`: captured `npm:nats`, backticks, `${...}`, `{{ }}` or JavaScript are data. The chatserver resolver (`template_utils.go`) was checked for type preservation, exact text, fail-closed missing required keys and optional `default`.

The eight code-bearing Workflows and steps are:

| Workflow | 0.3.1 version | `code_execution` steps |
|---|---:|---|
| `memory-capture-source` | 5 | `capture-validate` |
| `memory-propose-update` | 5 | `propose-validate`, `propose-check-evidence`, `propose-check-absent` |
| `memory-review-update` | 7 | `review-validate`, `review-parse-proposal`, `review-check-evidence`, `review-check-absent`, `assemble`, `plan-supersession` |
| `memory-inspect` | 5 | `inspect-validate`, `inspect-parse-proposal`, `inspect` |
| `memory-query` | 8 | `query-validate`, `query-parse-proposal`, `find-marker`, `query-answer` |
| `memory-search` | 10 | `search-validate`, `candidates`, `build-revision-query`, `search-answer` |
| `memory-index-revision` | 9 | `index-validate`, `prepare`, `check-copy`, `finish` |
| `memory-health` | 4 | `health` |

Capture stores source text, reference and ISO date after confirmation; propose records a revision, exact quotation, deadline and optional `previous_revision`; review records `validated`, `refused` or `disputed`; inspect reads the proposal and evidence; query reads an exact revision and its supersession; search returns bounded BM25 excerpts; index writes a validated revision to Memory then Brain; health lists native files. The six MiniApps have no independent business logic; the query console labels the successor “Superseded by”.

## Search output and compatibility

`memory-search` returns `status: revalidated_revisions`, `search_mode: bm25`, `results`, `summary`, `candidate_count`, `suppressed_count`, `excerpt_budget_chars` and `warning: bounded_search_excerpts_full_text_via_memory_query`. Each result includes `proposal_id`, `title`, `date`, `date_kind`, `source_ref`, `review_due`, `match_type` (`exact_identifier` or `other`), `excerpts`, and optionally `superseded_by`. Structured historical `date_kind` values `source`, `revue` and `inconnue` are unchanged; the human-readable summary renders the latter two as “review” and “unknown”. Title is limited to 200 characters, source reference to 300, and whitespace is normalized to one space. Summary contains one line per revision, even with newlines in inputs.

The path is one `brain.keyword` call (at most ten results), one `memory.query` over `v_entities` (`maxRows` 60) for validated candidates and their successors, and one listing of `/company-memory` markers. IDs are slug-validated before being inlined in SQL. With no Brain candidates, the engine sends the empty `external_id IN ('')` query without a `previous_revision` clause and returns zero candidates and suppressed results; otherwise an empty predecessor could select all rows without predecessors. `rows: null` means no rows. Errors, unexpected shapes or `truncated: true` fail closed. Candidates missing a validated row, superseded, expired or with unreadable expiry are excluded and counted in `suppressed_count`.

Text comes from `name`, deadline from `expires_at`, title and dates from `title`, `source_date` and `reviewed_at`; `source_ref` is written by index since 0.3.0. For older rows it falls back to the first citation, whether an array, JSON array string or Go-rendered `[reference]` string; its interior is never split on spaces. Chatserver `ResolveTemplateMap` renders an array-only parameter as Go text, so indexing writes `{{ json .record.citations }}`. For older rows without title, the title is the source-reference fragment between `#` and the final `@`, or the ID; date is empty and `date_kind` is `inconnue`. Reindexing restores title and dates.

Exact identifiers sort first by descending source date (review date fallback), followed by other matches by descending score. Each revision has up to two non-overlapping 400-character windows selected for coverage of distinct query terms longer than two letters, ignoring case and accents. Windows remain in text order, use `[…]` at cut boundaries and fall back to the beginning if no term matches. The total excerpt bound is 10 × 2 × (400 plus two markers) = 8,160 characters. Full text is available via `memory-query`.

Historical offline measurements: a compact example with two selected revisions (one 1,400 characters) and one superseded revision was 1,932 JSON bytes, including 987 result characters; a nearby 0.2.0 example was 3,777 bytes. On a 606-revision laboratory corpus, evidence was visible in 29% with the beginning only, 85% with two 260-character windows and 91% with two 400-character windows. These are not One runtime measurements.

`memory-query` returns `validated` with the revision text, `superseded` with its text for explicit inspection, `successor_conflict` with no answer for multiple successors, `expired` with no answer, `refused`/`disputed` with no answer, `evidence_changed` if the quote no longer matches, and `review_invalid`/`review_date_invalid` for inconsistent review or deadline. Fields added in 0.3.0 are `title`, `source_date`, `reviewed_at`, `previous_revision`, `superseded_by` and `successor_ids`; absent previous/successor values are empty. Reading without a review remains a native read error.

## Supersession

When review validates Y with `previous_revision = X`, it writes the validated review first, then `/company-memory/superseded-X.json` with `overwrite:false` and `{"superseded": X, "successor": Y, "reviewed_at": ...}`. A marker cannot precede a validated review and does not require indexing Y. A pre-existing marker rejects another validation with `successor_conflict` before any write; refused/disputed decisions create no marker.

Query combines this native marker (listing and conditional child `memory-read-supersession`) with validated Memory successors. One successor yields `superseded` and its ID; several yield `successor_conflict` and no answer. Search serves only validated Memory rows without a validated successor or native marker and with a valid unexpired deadline. A conflict is suppressed too. Index refuses anything no longer `validated`. Marker write/read are internal children `memory-write-supersession` 3 and `memory-read-supersession` 2 in 0.3.1.

The native marker records the decision before indexing; each search lists markers, so a validated but unindexed successor already hides X. Reading every `proposal-*.json` to find successors would be unbounded. An expired successor still supersedes X. If marker and Memory identify different successors, X stays hidden until manual resolution. If Y's review write fails, no marker is written and X remains served. If the marker write fails after Y's final review, X remains served until Y is indexed; a missing marker can be written manually after review, and without it a second validation is not immediately refused but becomes a conflict once both successors are indexed. Pre-0.3.0 validated revisions lack markers. Native files are not given a `superseded` status; it is calculated on read.

## Brain dependency

Search calls `brain.keyword` with `tenant_id: company-memory`, `max_results: 10`, `response_format: "concise"`. The concise URI, passage ID, score and bounded excerpt come from AGENT-1049; an older Brain image is incompatible. An image ignoring `response_format` must fail rather than silently return zero results; its exact behaviour is not qualified. The `candidates` step reads `uri`, `match_type` and the best score per revision; field names require AGENT-1049 confirmation, with `other` and 0 as defaults. Detailed `document.file_path` responses fail with `brain_concise_unsupported`, and results without any URI fail with `invalid_brain_response`. Brain excerpts are not the answer: text and citation come from Memory, indexed from revalidated native files.

When the corrected image is published, pin its digest in the consumer, confirm the URI field and independence from `document.file_path`, remove the detailed fallback, rerun `test_candidates_read_concise_uri_and_fail_closed` against the frozen shape, and execute the Brain cases in the qualification plan.

## Migration and composition

For 0.2.0 consumers, deploy and digest-pin the corrected AGENT-1049 Brain image; otherwise search fails. Review the consumer diff and compose with `--update`: without it differing 0.2.0 files prevent every write. The dry-run lists `would_replace_files`; `--update --write` lists `replaced_files`. Only the ten Module Workflows, six MiniApps and `tests/test-plan.json` are replaced; no consumer file is deleted, and identities and connections are untouched. The composer reports `retired_files_present` for `memory-resolve-candidate` without deleting it; remove that retired consumer file manually before `spec check`, because it pins an undelivered `memory-query` version. `mcp_requirements` are merged into `agent-spec.json`.

```bash
python3 tooling/company-memory/compose.py --consumer-dir <consumer> --agent-alias memory --update
python3 tooling/company-memory/compose.py --consumer-dir <consumer> --agent-alias memory --update --write
maurice --config <config> spec check --dir <consumer> --env integration_test --agent-alias memory --json
maurice --config <config> spec deploy --dir <consumer> --env integration_test --agent-alias memory --tests auto --json
```

Verify the execution service loads the new definition; this was a known 0.2.0 limitation and the One path is not qualified. For every already validated and indexed 0.2.0 revision Y replacing X, replay `memory-index-revision` using the same ID: indexing is idempotent on `externalId` and `document_uri`; without replay X remains served. Native `source-*`, `proposal-*`, `review-*` formats do not migrate. Reindex older rows to fill `title`, `source_date`, `reviewed_at`, `source_ref` and JSON `citations`. Pre-0.3.0 validated revisions lack native markers: without reindexing, after checking Y's review, the documented marker may be written manually; that operation is unqualified. Callers formerly reading `results[].answer`, `citations` or `excerpt` must use `excerpts` and `source_ref`, and query full text separately.

A fresh consumer requires a reachable One, a test Agent created with `maurice test setup --fresh --save=false --json`, and Agent Spec V2 initialized with that ID. Use the target One's configuration explicitly. Different aliases do not isolate data: dedicate an Agent and sidecars/volumes to each memory. Fixed tenant `company-memory` does not isolate companies sharing a sidecar. The composer copies Module bytes into an Agent Spec; it is not Module Catalog installation. The `integration_test` plan uses its native authorization; Catalog installation retains its own approval gate. Consumer identity, policies, connections and locks remain in the consumer.

## Offline checks and qualification

```bash
python3 -m unittest discover -s tooling/company-memory/tests -p 'test_*.py'
maurice module validate --file company-memory/module.yaml --json
maurice module test --file company-memory/module.yaml --json
```

`test_compose.py` covers conflict handling, MCP providers, update scope and retired-file reporting without deletion. `test_module_offline.py` checks manifests, V2 resources when the generated validator and `jsonschema` are available, bound contexts, SQL and excerpt shapes, legacy citation encodings, action ID uniqueness, Node execution and a fake Memory/Brain capture → propose → review → query → index → search sequence including supersession, conflict, expiry, refusal and negative cases. Node and `jsonschema` dependent tests skip when unavailable. Fake providers check request shapes, not real One behaviour.

Historical **0.2.0** evidence: 33 runtime cases and six Viewer MiniApps passed on two dedicated Agents, backend `fe7e5970`. Replays `tests/mcp-replay.py` and `tests/search-replay.py` were adapted to compact output but not rerun here. **0.3.0** was not qualified on One; `tests/requalification-plan.json` records pending commands and cases. **0.3.1** requires its own runtime and Viewer qualification. The plan retains its historical French hostile-text fixture byte for byte to test multilingual data fidelity. Historical replay tools belong to the authorized canonical pilot checkout and are not distributed here; the owning session must prepare an isolated One and external tools. Historical offline test counts do not qualify a later version.

## Sidecar pins recorded for 0.3.0

The MCP instance registry, not this Module, pins sidecars by digest; requirements name the registry entries `company_memory` and `brain`, and the platform uses the active entry. Reference files are in [`tests/registry/`](tests/registry/):

| File | Registry name | Version | Image digest |
|---|---|---|---|
| `memory-1.1.0.json` | `company_memory` | 1.1.0 | `sha256:10ec6f7ebd498127137edf9007b06286b9395ef92a89dc5ffa9a6ec7fa3cae7f` |
| `brain-1.2.0.json` | `brain` | 1.2.0 | `sha256:fbdf0122fb6c4c043940588441c9df2af7a019ce97cdff4268fa468d7f2f848b` |

Registry names are unique: update an existing entry via `PUT /api/v1/registry/entries/<name>`, do not add a duplicate. Previous Memory 1.0.16 and Brain 1.1.7 are documented in the pilot, not included here. An active sidecar retains its old image after registry update: a plan reports `provider or image drift` until the sidecar is removed via `DELETE /api/v1/mcp/servers/<id>` (data volume retained) and redeployed.

## Limits

There is no native persisted `superseded` status, current-page head, atomic concurrent change resolution, automatic successor-conflict resolution, semantic search, automatic ingestion, LLM summary, inter-Agent call or fine-grained permission model. Manual confirmation expresses intent; it is not human identity proof or architecture approval. `memory-health` lists at most 100 files and does not summarize inconsistencies. Historical isolation replay covered two separate deployments on the filesystem provider of one One; it does not prove isolation between companies, users or a shared S3 bucket. Confirmation and tenant enforcement live in Workflows, not a platform control; a missing tenant can silently return zero Brain or Memory results, so the Module always supplies it.
