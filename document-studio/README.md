# Document studio

Reusable Module that turns a brief into a business document (quote, meeting
minutes, chart dashboard) or an e-mail message (support reply, launch newsletter): draft, render from a
template and the company profile (PDF for a document; html, txt and eml for a message), review,
approval and issue with a number. Everything lives in Storage; nothing is sent
outside, a message included.

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
| `document-studio-render` | renders the current state (PDF and PNG previews; for a message, the three files html, txt and eml, no preview) and adds a revision. `data_patch` merges (shallow) corrections into the data, which is revalidated. An issued or cancelled document no longer renders (`document_locked`) |
| `document-studio-finalize` | `draft` to `approved`. Requires a render of the current revision and `confirmation_manuelle` |
| `document-studio-publish` | requires `approved` and `confirmation_manuelle`. Reserves the next number, renders in `final` mode, stores the issued PDF (a message: its html, txt and eml files), moves to `issued`. Nothing is sent |
| `document-studio-cancel` | moves to `cancelled` with a reason. An issued number is never reused |
| `document-studio-export` | refuses a cancelled document (`document_cancelled`); otherwise copies the issued PDF (or the latest render, flagged as a draft) to a Storage path outside `/document-studio/`, with its SHA-256. A message exports its `eml` (default), `html` or `txt` through the optional `format`; `format` on a PDF document is `format_not_applicable`. Mail and SFTP are out of V0 |
| `document-studio-new-version` | adds a DOCX version of an existing document from a Storage file (`source_path`, `author`): fingerprints it, compares it with the previous version through the MCP tool `office_compare_v1`, stores the redline (tracked changes) and appends the version to the versions manifest. Refuses a stale `base_version` or `base_manifest_sha256` (`base_version_conflict`) and a cancelled document. Same request again: nothing is written (`replayed`) |
| `document-studio-mark-authoritative` | makes one version the authoritative one (`confirmation_manuelle` required, refused before any read otherwise); the previously authoritative version becomes `superseded`. No version file is modified |
| `document-studio-profile-save` | validates and stores the company profile and brand (`/document-studio/profile.json`), with manual confirmation |
| `document-studio-list` | lists the documents (identifier, title, status, number, revision, latest hash) |
| `document-studio-review-read` | full record of a document and previews of its latest render, for the MiniApp. For a message: `text` (the plain text, read back and checked against its SHA-256) and `files` (path, SHA-256 and size of html, txt and eml), never the HTML |
| `document-studio-template-read` | lists the templates, or the manifest and data schemas of one template |
| `document-share` | publishes the reference of an **issued** document as a record of the native application data broker (`recipe--application_data_v1`, namespace `cib-documents`, key `doc_id`), then grants or removes `read` for one member. Requires `confirmation_manuelle`. The PDF stays in Storage |
| `document-read` | reads one shared reference through the broker (with the caller's permissions), or lists the references the caller may read when `doc_id` is empty or absent (`"doc_id": ""` is valid, so the form can be submitted blank) |

The `document-studio-review` MiniApp has no input component of its own (the
MiniApp vocabulary has none): the document identifier (`doc_id`) is typed in
the form "Relire un document" of `document-studio-review-read`, which loads
the document. The MiniApp then shows status, revision, number, pages, the title,
the plain text of a message (empty for a PDF document) and the
table of renders (revision, mode, hash, path), refreshes it, and triggers a
new render. It displays no HTML. Approval and issue go through the
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
- Message: `r<revision>-<sha12>/document.html`, `document.txt` and `document.eml` for a render (the 12 characters are those of the SHA-256 of the three outputs' fingerprints, so two attempts that differ in any one output never share a folder), and `issued/<number>-<sha12>.html`, `.txt` and `.eml` for the issue. See "Messages (e-mail)".
- `/document-studio/numbers/<template>/<year>/<4-digit seq>.json`: number token.
- `/document-studio/docs/<doc_id>/versions/manifest.json`: the versions manifest (`document-studio.versions/v1`): `versions` is the list of `{version, sha256, bytes, storage_ref, redline_ref, redline_sha256, changes: {insertions, deletions, changed_paragraphs}, author, created_at, status: draft|authoritative|superseded, supersedes, base_version, request_sha256}` (plus `superseded_by`, `authoritative_at`, `approved_by` when set), and `history` is its journal. At most one version is authoritative.
- `/document-studio/docs/<doc_id>/versions/v<N>-<sha12>.docx` and `v<N>-redline-<sha12>.docx`: one immutable file per version and its redline against version N-1 (the first version has none). The file name carries the content, so a retry rewrites the same bytes.

`doc_id`: `^[a-z0-9][a-z0-9-]{0,47}$`, chosen by the caller or derived from the
title with a short suffix. Number: `<PREFIX>-<year>-<seq>` (`DEV` for the
quote, `CR` for the minutes, `TB` for the dashboard, `REP` for the support reply, `NL` for the newsletter).

The company profile is read from the `cib-profile` record of the `profile` Module through
`recipe--application_data_v1` (`operation: read`, `namespace: cib-profile`, `record_key: company-profile`, the call of
`cib-profile-read`); `render` and `publish` report the source in `profile_source`. Fallback: `/document-studio/profile.json`
in Storage. Without either, they fail with `profile_missing`. The fingerprints of the brand checked at issue
(`profile_changed`) are computed on the projected profile, whatever its source.

## DOCX versions

Versions live in Storage, next to the record, which they never write: an issued or signed document keeps its record and
its PDF, and a new version is only added. `new-version` accepts a DOCX (ZIP package, 20 MiB at most) and numbers it N+1. A DOCX is checked twice before anything is written: a fast structural filter (readable ZIP holding `[Content_Types].xml` and `word/document.xml`), then the document engine. The first version goes through `office_inspect_v1` (it has nothing to compare with), the next ones through `office_compare_v1`; `mark-authoritative` inspects the version again before it makes it authoritative. An engine error or an unreadable document is `docx_invalid`.
`mark-authoritative` is the only action that changes a status, with the manual confirmation, and never on a person's behalf
(`approved_by` is recorded as stated, not attested). A superseded version is never restored: add a new version instead, and an
older draft cannot take over from a newer authoritative one.

The request fingerprint of `new-version` is the canonical hash of `{action, doc_id, sha256 of the file, author}`, stored in the
manifest entry (`request_sha256`). The same request as any entry of the manifest is a replay: it returns that entry and writes nothing, even after later versions were added. To bring old content back, send it under another author.
The same bytes under another author are refused (`version_unchanged`).

## Templates

`examples/templates/quote`, `examples/templates/meeting-minutes`,
`examples/templates/dashboard`, `examples/templates/support-reply` and
`examples/templates/launch-newsletter` are copies of the reference templates of the
`agentmaurice.template/v1` contract, with the shared fragments they import.
`tooling/document-studio/contract/PIN.json` records the origin commit of the
contract and the hash of every file. One file differs from the original:
`quote/main.typ`, which adds the notice « Ce document est un devis, ce n'est
pas une facture ». The contract check runs with
that contract's `template_check.py` (`check <folder>`); the CI of this
repository is offline and does not depend on it.

The templates are embedded as text in the rendering Workflows, without
`fragments/`, `brand.typ` and `values.json`: the renderer writes those itself
from its pinned contract and refuses them from the caller
(`reserved_file_name`). Their braces are written as escape sequences, because
the Workflow engine would read a double brace in the code as a template action.

### Messages (e-mail)

`support-reply` (prefix `REP`, transactional) and `launch-newsletter` (prefix `NL`, `message.category: marketing`, with the
unsubscribe footer and an absolute https link for the button, the image and the unsubscribe URL) declare the `message` profile
of the contract (engine `mjml`, outputs `html`, `txt`, `eml`). The profile is read from the manifest, never from the template key:
any template that declares `profile: message` is rendered this way. Their fragments (`fragments/message/header.mjml`,
`footer-unsubscribe.mjml`) are pinned like the other fragments and never sent to the engine. The data carries an optional `subject`,
which becomes the `Subject` header of the eml; the document title is the subject, else the headline, else the template title.

The render calls `artifact_render_v1` three times (`html`, `txt`, `eml`, in `preview` then `final` mode), stores each file in the
attempt folder, reads it back and checks its SHA-256 and size, with the same rigour as a PDF. Nothing is stored when one of the
three renders fails, nor when an inline output has a wrong type, size or fingerprint (all three are checked
before the first write). An output given by buffer reference is checked when it is read back: if it is wrong, the
render fails and the document record is left unchanged, but the files already written stay in their own attempt folder
(never reused, never overwritten). An incomplete render fails with a stable code: `render_output_missing` (output absent or empty),
`render_integrity_failed` (fingerprint or size differ), `render_failed` (engine error), `render_invalid` (wrong output or MIME type).
A message has no page preview: `previews` is empty and `pages` is 0.

Record shape (`document-studio.record/v1`, additive): a render entry keeps `file` (the html, as for a PDF document) and, for a
message only, `files`: `{html, txt, eml}` each with `path`, `sha256`, `bytes` and `mime`, with `previews: []`. `provenance` is that of the html (the three outputs share the template,
data and context digests). The issue keeps `issued.file` (the html) and `issued.files` (`path` and `sha256` per output). Issuing numbers
and freezes the files; it sends nothing, the module has no sending tool.

Not applicable to a message, refused with `not_applicable_to_message` before any write: `document-studio-new-version` and
`document-studio-mark-authoritative` (DOCX versions) and `document-share` (the shared reference designates a PDF, so `document-read`
`include_pdf` never concerns a message). `document-studio-export` with a PDF-only `format` is `format_not_applicable`, and `format` on a PDF document too.

Dependency: the message templates need the MCP `artifact` engine **v0.2.7 or later** (MJML). The Viewer does not preview HTML yet: that is a separate ticket, the MiniApp shows the text only.

### Dashboard template (charts)

The `dashboard` template (number prefix `TB`) draws six charts, one page each,
from `chart/v1` data (`fragments/charts.typ` of the contract, pure vector
Typst, deterministic): `bar` (grouped bars), `line`, `pie`, `gantt`
(phases and tasks over weeks), `org` (organisation chart) and `process`
(process flow with start, step, decision and end). The draft holds one chart
object per property (`bar`, `line`, `pie`, `gantt`, `org`, `process`) plus a
`title` and the `titles` of the six pages; the model only provides the data,
the engine draws it and nothing is computed by the Workflow (the draft schema
is the template input schema). The bounds of `chart/v1` apply (for example 24
categories, 5 series, 10 pie parts, 25 Gantt tasks, 30 organisation nodes); a
violation fails the render.

Dependency: this template needs the MCP `artifact` engine **v0.2.5 or later**,
which embeds `charts.typ`. The Workflow never sends `fragments/`: the engine
writes them from its pinned contract, so a One whose artifact is older than
v0.2.5 fails the render of this template (the quote and the minutes are not
affected). The Module manifest has no field for a minimum MCP version
(`requires.mcp` only lists a name and tools), so the constraint is stated
here only.

Quote data: the draft holds numbers (`quantity`, `unit_price_ht`, `vat_rate`),
never formatted amounts nor totals. At render time the Workflow produces the
strings the template expects (`1 250,00 €`) and the HT, per-rate VAT and TTC
totals.

Quote numbers are validated: quantity strictly positive, at most 3 decimals and
at most 1,000,000; unit price excl. VAT zero or positive with at most 2
decimals; VAT rate among 0, 2.1, 5.5, 10 and 20 (`data_invalid` otherwise). The
quantity is displayed with its real decimals and the line total is
quantity x price rounded to the cent.

Every stored file (PDF, previews, message files) is read back after the write: its SHA-256
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
- Concurrent `mark-authoritative`: two calls on the same document at the same time are not safe. Both may pass the second read and the later write wins, which can leave the wrong version authoritative or bring a superseded one back while both calls report success. Serialise them (one writer per document). Moving the manifest to `application_data_v1`, which has compare-and-swap, lifts this limit (lot 4).
- Versions: Storage has no compare-and-swap. A manifest is read, the version file and redline are written, then the manifest is read again and written only if its text is unchanged (`concurrent_update` otherwise; a first manifest is written without overwrite). The window between the second read and the write is small, not null: allow one writer at a time per document. Files written before an abandoned manifest write stay orphaned in `versions/`. Pass `base_version` and `base_manifest_sha256` (returned as `manifest_sha256`) to make a stale caller fail.
- Versions are DOCX only (XLSX and PDF are out of this lot), the comparison and its 20 MiB input limit are those of `office_compare_v1`, and there is no review MiniApp for versions yet.
- The logo is a reference (`storage://…`); this Module does not resolve it to a file before rendering.
- Number reservation is not atomic: it lists, writes without overwrite, reads back and checks the owner, at most 5 attempts (`number_conflict`). A number reserved then lost (failed render) stays reserved: it is taken again on the next attempt, never reused by another document. Atomic sequences are a platform follow-up.
- No sending (mail, SFTP; a message is only rendered, numbered and exported as files), no HTML preview of a message in the Viewer, no DOCX rendering (DOCX files are only versioned), one locale (`fr`).
- `document-studio-export` reads the PDF in base64 through `read_file`; if the runtime does not allow it, the export fails on the hash (`export_integrity_failed`).
- No Viewer `document` card for a preview in the chat yet.
- Concurrent updates: Storage has no conditional write. Before each record write, `render`, `finalize`, `publish` and `cancel` read the record again and abandon with `concurrent_update` if its revision or status changed (for example a cancel during a render). Files already rendered stay orphaned in `r<revision>-<sha12>/`. The window is small but not null until Storage offers conditional writes.
- A failing `list_files` (outage, permission) fails with `storage_unavailable`; only a missing folder counts as empty. Number reservation therefore never restarts at 0001 after a Storage error.
