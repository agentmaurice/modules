# Document studio

Reusable Module that turns a brief into a business document (quote, meeting
minutes): draft, PDF render from a template and the company profile, review,
approval and issue with a number. Everything lives in Storage; nothing is sent
outside.

The Module contains no rendering engine. Rendering goes through the MCP tool
`artifact_render_v1` (mode `preview` for drafts, `final` for the issue). Code
steps are JavaScript (`code_execution`): no WASM in V0. No binary is versioned
here (no PDF, no PNG). The document content (prompts, templates, error
messages) is French; `fr` is the only locale in V0.

## Workflows

| Workflow | Role |
|---|---|
| `document-studio-plan` | picks the template from a brief, proposes a title, lists the missing data and the questions to ask. Writes nothing |
| `document-studio-draft` | fills the template data (model call, then strict validation) and creates the document record with status `draft`. For a quote, amounts and totals are computed here, in integer cents, from the lines: the model only provides quantities and prices |
| `document-studio-render` | renders the current state (PDF and PNG previews) and adds a revision. `data_patch` merges (shallow) corrections into the data, which is revalidated. An issued or cancelled document no longer renders (`document_locked`) |
| `document-studio-finalize` | `draft` to `approved`. Requires a render of the current revision and `confirmation_manuelle` |
| `document-studio-publish` | requires `approved` and `confirmation_manuelle`. Reserves the next number, renders in `final` mode, stores the issued PDF, moves to `issued` |
| `document-studio-cancel` | moves to `cancelled` with a reason. An issued number is never reused |
| `document-studio-export` | refuses a cancelled document (`document_cancelled`); otherwise copies the issued PDF (or the latest render, flagged as a draft) to a Storage path outside `/document-studio/`, with its SHA-256. Mail and SFTP are out of V0 |
| `document-studio-new-version` | adds a DOCX version of an existing document from a Storage file (`source_path`, `author`): fingerprints it, compares it with the previous version through the MCP tool `office_compare_v1`, stores the redline (tracked changes) and appends the version to the versions manifest. Refuses a stale `base_version` or `base_manifest_sha256` (`base_version_conflict`) and a cancelled document. Same request again: nothing is written (`replayed`) |
| `document-studio-mark-authoritative` | makes one version the authoritative one (`confirmation_manuelle` required, refused before any read otherwise); the previously authoritative version becomes `superseded`. No version file is modified |
| `document-studio-profile-save` | validates and stores the company profile and brand (`/document-studio/profile.json`), with manual confirmation |
| `document-studio-list` | lists the documents (identifier, title, status, number, revision, latest hash) |
| `document-studio-review-read` | full record of a document and previews of its latest render, for the MiniApp |
| `document-studio-template-read` | lists the templates, or the manifest and data schemas of one template |

The `document-studio-review` MiniApp has no input component of its own (the
MiniApp vocabulary has none): the document identifier (`doc_id`) is typed in
the form "Relire un document" of `document-studio-review-read`, which loads
the document. The MiniApp then shows status, revision, number, pages and the
table of renders (revision, mode, hash, path), refreshes it, and triggers a
new render. Approval and issue go through the
Workflow forms, with the manual confirmation.

## Lifecycle

`draft` (successive renders) → `approved` → `issued`. `cancelled` is reachable
from every other status. A new render of an `approved` document brings it back
to `draft`: the approval must be given again. The manual confirmation is the
form field `confirmation_manuelle` (`oui` or `non`); without `oui`, the
Workflow refuses (`manual_confirmation_required`) before any read or write.
The Module never approves on a person's behalf.

## Storage

- `/document-studio/profile.json`: the brand, with the `{schema_version: 1, company, brand}` shape of the template contract. A fictitious example is in `examples/profile.example.json`.
- `/document-studio/docs/<doc_id>/record.json`: the record (`document-studio.record/v1`): status, number, revision (+1 at every write), data, history, renders (path, SHA-256, previews, provenance), issue.
- `/document-studio/docs/<doc_id>/r<revision>-<sha12>/`: PDF and previews of one render attempt (12 first characters of the PDF SHA-256, so a losing attempt never overwrites another attempt's file).
- `/document-studio/docs/<doc_id>/issued/<number>-<sha12>.pdf`: the issued PDF.
- `/document-studio/numbers/<template>/<year>/<4-digit seq>.json`: number token.
- `/document-studio/docs/<doc_id>/versions/manifest.json`: the versions manifest (`document-studio.versions/v1`): `versions` is the list of `{version, sha256, bytes, storage_ref, redline_ref, redline_sha256, changes: {insertions, deletions, changed_paragraphs}, author, created_at, status: draft|authoritative|superseded, supersedes, base_version, request_sha256}` (plus `superseded_by`, `authoritative_at`, `approved_by` when set), and `history` is its journal. At most one version is authoritative.
- `/document-studio/docs/<doc_id>/versions/v<N>-<sha12>.docx` and `v<N>-redline-<sha12>.docx`: one immutable file per version and its redline against version N-1 (the first version has none). The file name carries the content, so a retry rewrites the same bytes.

`doc_id`: `^[a-z0-9][a-z0-9-]{0,47}$`, chosen by the caller or derived from the
title with a short suffix. Number: `<PREFIX>-<year>-<seq>` (`DEV` for the
quote, `CR` for the minutes).

Without a company profile, `render` and `publish` fail with `profile_missing`:
store the brand with `document-studio-profile-save`.

## DOCX versions

Versions live in Storage, next to the record, which they never write: an issued or signed document keeps its record and
its PDF, and a new version is only added. `new-version` accepts a DOCX (ZIP package, 20 MiB at most) and numbers it N+1.
`mark-authoritative` is the only action that changes a status, with the manual confirmation, and never on a person's behalf
(`approved_by` is recorded as stated, not attested). A superseded version is never restored: add a new version instead, and an
older draft cannot take over from a newer authoritative one.

The request fingerprint of `new-version` is the canonical hash of `{action, doc_id, sha256 of the file, author}`, stored in the
manifest entry (`request_sha256`). The same request as the latest entry is a replay: it returns that entry and writes nothing.
The same bytes under another author are refused (`version_unchanged`).

## Templates

`examples/templates/quote` and `examples/templates/meeting-minutes` are copies
of the reference templates of the `agentmaurice.template/v1` contract, with the
shared fragments they import. `tooling/document-studio/contract/PIN.json`
records the origin commit of the contract and the hash of every file. One file
differs from the original: `quote/main.typ`, which adds the notice « Ce
document est un devis, ce n'est pas une facture ». The contract check runs with
that contract's `template_check.py` (`check <folder>`); the CI of this
repository is offline and does not depend on it.

The templates are embedded as text in the rendering Workflows, without
`fragments/`, `brand.typ` and `values.json`: the renderer writes those itself
from its pinned contract and refuses them from the caller
(`reserved_file_name`). Their braces are written as escape sequences, because
the Workflow engine would read a double brace in the code as a template action.

Quote data: the draft holds numbers (`quantity`, `unit_price_ht`, `vat_rate`),
never formatted amounts nor totals. At render time the Workflow produces the
strings the template expects (`1 250,00 €`) and the HT, per-rate VAT and TTC
totals.

Quote numbers are validated: quantity strictly positive, at most 3 decimals and
at most 1,000,000; unit price excl. VAT zero or positive with at most 2
decimals; VAT rate among 0, 2.1, 5.5, 10 and 20 (`data_invalid` otherwise). The
quantity is displayed with its real decimals and the line total is
quantity x price rounded to the cent.

Every stored file (PDF and previews) is read back after the write: its SHA-256
and size must match what the renderer announced, else `render_integrity_failed`
and the record is not updated.

## Runtime notes

- The render tool is called by its bare name `artifact_render_v1`: a registry
  sidecar publishes its tools without a server prefix.
- The `llm_call` steps answer `text`: `json` requires a closed
  `llm_response_schema`, and the schema depends on the template. The next step
  parses the `{text}` output and validates it strictly.

## Regeneration and tests

```
python3 tooling/document-studio/build.py
python3 -m unittest discover -s tooling/document-studio/tests -p 'test_*.py'
```

The tests run every JavaScript step under Node, with a simulated Storage and
renderer, on synthetic data. They do not prove the behavior on a One.

## Known limits (V0)

- Versions: Storage has no compare-and-swap. A manifest is read, the version file and redline are written, then the manifest is read again and written only if its text is unchanged (`concurrent_update` otherwise; a first manifest is written without overwrite). The window between the second read and the write is small, not null: allow one writer at a time per document. Files written before an abandoned manifest write stay orphaned in `versions/`. Pass `base_version` and `base_manifest_sha256` (returned as `manifest_sha256`) to make a stale caller fail.
- Versions are DOCX only (XLSX and PDF are out of this lot), the comparison and its 20 MiB input limit are those of `office_compare_v1`, and there is no review MiniApp for versions yet.

- The brand is read from Storage only. The `profile` Module keeps the profile in an application record whose broker is not wired in the One yet: calling the `cib-profile-read` Workflow would make every render fail until then.
- The logo is a reference (`storage://…`); this Module does not resolve it to a file before rendering.
- Number reservation is not atomic: it lists, writes without overwrite, reads back and checks the owner, at most 5 attempts (`number_conflict`). A number reserved then lost (failed render) stays reserved: it is taken again on the next attempt, never reused by another document. Atomic sequences are a platform follow-up.
- No sending (mail, SFTP), no DOCX rendering (DOCX files are only versioned), one locale (`fr`).
- `document-studio-export` reads the PDF in base64 through `read_file`; if the runtime does not allow it, the export fails on the hash (`export_integrity_failed`).
- No Viewer `document` card for a preview in the chat yet.
- Concurrent updates: Storage has no conditional write. Before each record write, `render`, `finalize`, `publish` and `cancel` read the record again and abandon with `concurrent_update` if its revision or status changed (for example a cancel during a render). Files already rendered stay orphaned in `r<revision>-<sha12>/`. The window is small but not null until Storage offers conditional writes.
- A failing `list_files` (outage, permission) fails with `storage_unavailable`; only a missing folder counts as empty. Number reservation therefore never restarts at 0001 after a Storage error.
