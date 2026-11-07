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
| `document-studio-export` | copies the issued PDF (or the latest render, flagged as a draft) to a Storage path outside `/document-studio/`, with its SHA-256. Mail and SFTP are out of V0 |
| `document-studio-profile-save` | validates and stores the company profile and brand (`/document-studio/profile.json`), with manual confirmation |
| `document-studio-list` | lists the documents (identifier, title, status, number, revision, latest hash) |
| `document-studio-review-read` | full record of a document and previews of its latest render, for the MiniApp |
| `document-studio-template-read` | lists the templates, or the manifest and data schemas of one template |

The `document-studio-review` MiniApp loads a document by its identifier, shows
status, revision, number, pages and the table of renders (revision, mode,
hash, path), and triggers a new render. Approval and issue go through the
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
- `/document-studio/docs/<doc_id>/r<revision>/`: PDF and previews of one render.
- `/document-studio/docs/<doc_id>/issued/<number>.pdf`: the issued PDF.
- `/document-studio/numbers/<template>/<year>/<4-digit seq>.json`: number token.

`doc_id`: `^[a-z0-9][a-z0-9-]{0,47}$`, chosen by the caller or derived from the
title with a short suffix. Number: `<PREFIX>-<year>-<seq>` (`DEV` for the
quote, `CR` for the minutes).

Without a company profile, `render` and `publish` fail with `profile_missing`:
store the brand with `document-studio-profile-save`.

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

- The brand is read from Storage only. The `profile` Module keeps the profile in an application record whose broker is not wired in the One yet: calling the `cib-profile-read` Workflow would make every render fail until then.
- The logo is a reference (`storage://…`); this Module does not resolve it to a file before rendering.
- Number reservation is not atomic: it lists, writes without overwrite, reads back and checks the owner, at most 5 attempts (`number_conflict`). A number reserved then lost (failed render) stays reserved: it is taken again on the next attempt, never reused by another document. Atomic sequences are a platform follow-up.
- No sending (mail, SFTP), no DOCX, one locale (`fr`).
- `document-studio-export` reads the PDF in base64 through `read_file`; if the runtime does not allow it, the export fails on the hash (`export_integrity_failed`).
- No Viewer `document` card for a preview in the chat yet.
