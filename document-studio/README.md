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
| `document-studio-profile-save` | validates and stores the company profile and brand (`/document-studio/profile.json`), with manual confirmation |
| `document-studio-list` | lists the documents (identifier, title, status, number, revision, latest hash) |
| `document-studio-review-read` | full record of a document and previews of its latest render, for the MiniApp |
| `document-studio-template-read` | lists the templates, or the manifest and data schemas of one template |
| `document-share` | publishes the reference of an **issued** document as a record of the native application data broker (`recipe--application_data_v1`, namespace `cib-documents`, key `doc_id`), then grants or removes `read` for one member. Requires `confirmation_manuelle`. The PDF stays in Storage |
| `document-read` | reads one shared reference through the broker (with the caller's permissions), or lists the references the caller may read when `doc_id` is empty or absent (`"doc_id": ""` is valid, so the form can be submitted blank) |

The `document-studio-review` MiniApp has no input component of its own (the
MiniApp vocabulary has none): the document identifier (`doc_id`) is typed in
the form "Relire un document" of `document-studio-review-read`, which loads
the document. The MiniApp then shows status, revision, number, pages and the
table of renders (revision, mode, hash, path), refreshes it, and triggers a
new render. Approval and issue go through the
Workflow forms, with the manual confirmation.

## Sharing with the company

Sharing follows the `cib-contenu` pattern: the broker holds one record per document and enforces a per-member ACL; a
record is private to its owner until `document-share` grants `read` (`write` is refused on purpose: a member must not
be able to rewrite the reference). `expected_revision` is `0` for the first publication, then the revision returned by
the previous call (compare-and-set). The shared record (`document-studio.shared/v1`) holds `doc_id`, `title`,
`template_key`, `number`, `version` (the revision of the Storage record at issue), `path` (Storage path of the issued
PDF), `sha256` and `issued_at`. Removing access (`none`) does not need the Storage record, so it still works after a
cancellation; a cancelled document stays referenced until its owner removes the members. The PDF itself is read through the ACL of the
record, not through the Storage rights of the member: `document-read` with `doc_id` and `include_pdf: oui` (optional,
default `non`; a form field, `non` by default) reads the PDF at `data.path` from the Agent's Storage with `read_file`
(base64) only after the broker read succeeded, recomputes its SHA-256 and refuses `pdf_integrity_failed` when it differs
from the shared `sha256`, `pdf_too_large` above 5 MiB, and `invalid_path` when the path is not an issued document of
`/document-studio/docs/<doc_id>/issued/`. It returns `pdf_base64`, `pdf_sha256` and `pdf_bytes`. `include_pdf` without a
`doc_id` is refused.

## Optional service in the Company-in-a-Box template

`templates/company-in-a-box/compose.py --with-service documents` adds this Module as an optional fourth Agent
(`documents`, spec-init'ed in the consumer like the three roles; off by default). Besides the resources and the test
plan it writes `surface-drafts/cib-documents.surface-draft.json`, with `required_role` on every Workflow: `cib_documents`
for the owner of the service, `cib_admin` for `document-studio-profile-save`. Role grants and the ACL of each record are
cumulative; the Module never grants a role or a share. `document-read` has no `required_role` in the surface draft, like `contenu-read`: any member of the Application may call it and the ACL of each record decides what is returned. `document-share` republished without a member reports the real shares returned by the broker. The Administration select of `cib-admin-manage` does not list
`cib_documents` yet.

## Lifecycle

`draft` (successive renders) → `approved` → `issued`. `cancelled` is reachable
from every other status. A new render of an `approved` document brings it back
to `draft`: the approval must be given again. The manual confirmation is the
form field `confirmation_manuelle` (`oui` or `non`); without `oui`, the
Workflow refuses (`manual_confirmation_required`) before any read or write.
The Module never approves on a person's behalf.

## Storage

- `/document-studio/profile.json`: the fallback brand (used when `cib-profile` is unavailable), with the `{schema_version: 1, company, brand}` shape of the template contract. A fictitious example is in `examples/profile.example.json`.
- `/document-studio/docs/<doc_id>/record.json`: the record (`document-studio.record/v1`): status, number, revision (+1 at every write), data, history, renders (path, SHA-256, previews, provenance), issue.
- `/document-studio/docs/<doc_id>/r<revision>-<sha12>/`: PDF and previews of one render attempt (12 first characters of the PDF SHA-256, so a losing attempt never overwrites another attempt's file).
- `/document-studio/docs/<doc_id>/issued/<number>-<sha12>.pdf`: the issued PDF.
- `/document-studio/numbers/<template>/<year>/<4-digit seq>.json`: number token.

`doc_id`: `^[a-z0-9][a-z0-9-]{0,47}$`, chosen by the caller or derived from the
title with a short suffix. Number: `<PREFIX>-<year>-<seq>` (`DEV` for the
quote, `CR` for the minutes).

The company profile is read from the `cib-profile` record of the `profile` Module through
`recipe--application_data_v1` (`operation: read`, `namespace: cib-profile`, `record_key: company-profile`, the call of
`cib-profile-read`); `render` and `publish` report the source in `profile_source`. Fallback: `/document-studio/profile.json`
in Storage. Without either, they fail with `profile_missing`. The fingerprints of the brand checked at issue
(`profile_changed`) are computed on the projected profile, whatever its source.

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

- The brand is read from the `cib-profile` record (key `company-profile`) through the broker, by `render` and `publish`. If that record is absent, refused to the caller or unreadable, the Storage copy `/document-studio/profile.json` is used and the output says so (`profile_source`: `cib-profile` or `storage`). A broker refusal is therefore not distinguished from an absent record. `document-studio-profile-save` still writes only the Storage copy: save the profile in `cib-profile` (profile Module) to make it the source.
- The logo is a reference (`storage://…`); this Module does not resolve it to a file before rendering.
- Number reservation is not atomic: it lists, writes without overwrite, reads back and checks the owner, at most 5 attempts (`number_conflict`). A number reserved then lost (failed render) stays reserved: it is taken again on the next attempt, never reused by another document. Atomic sequences are a platform follow-up.
- No sending (mail, SFTP), no DOCX, one locale (`fr`).
- `document-studio-export` reads the PDF in base64 through `read_file`; if the runtime does not allow it, the export fails on the hash (`export_integrity_failed`).
- No Viewer `document` card for a preview in the chat yet.
- Concurrent updates: Storage has no conditional write. Before each record write, `render`, `finalize`, `publish` and `cancel` read the record again and abandon with `concurrent_update` if its revision or status changed (for example a cancel during a render). Files already rendered stay orphaned in `r<revision>-<sha12>/`. The window is small but not null until Storage offers conditional writes.
- A failing `list_files` (outage, permission) fails with `storage_unavailable`; only a missing folder counts as empty. Number reservation therefore never restarts at 0001 after a Storage error.
