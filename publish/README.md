# Publish

Reusable Module that sends a file or a text out of Storage, in three ways: a
web server (file upload), an e-mail message, social channels (a post). Every
publication is journaled in Storage and can be checked and, for files and
posts, removed.

The Module sends nothing itself. Each diffusion goes through an MCP tool
called by its bare name (a registry sidecar publishes its tools without a
server prefix):

| Channel | Tool | Notes |
|---|---|---|
| web | `ssh_upload_v1`, `ssh_remove_v1` | the target must declare a publication root (otherwise `publish_not_enabled`) |
| email | `google_mail_send` | the tool of the connected Gmail integration |
| social | `social_post_create_v1`, `social_post_get_v1`, `social_post_delete_v1` | Postiz behind the `social` MCP |

Code steps are JavaScript (`code_execution`). No binary is versioned here. The
messages and prompts are French.

## Rules

- Every diffusion and every removal requires `confirmation_manuelle` = `oui`.
  Without it the Workflow refuses (`manual_confirmation_required`) before any
  read or write. `human_action/v1` is not wired in V0: the manual confirmation
  is the Module convention, the same as `document-studio`.
- The destination is an explicit argument of the caller (ssh target and
  remote path, recipients, social channel ids). It is never deduced by the
  model. `publish-plan` only suggests the channel, an e-mail subject or a post
  text, and writes nothing.
- The journal `/publish/log/<publication_id>.json` (`publish.record/v1`) is
  created at `requested` before the external call, then moves to `published`
  or `failed` with the remote identifiers. A removal records its intent first
  (the status stays `published`), then moves to `removed`.
- State machine of a `publication_id` (`requested`, `published`, `failed`,
  `outcome_unknown`, `removed`):
  - `published`: the same request answers `already_published`, no external call.
  - `removed` is terminal: the same request answers `already_removed`. To
    publish again, use a new `publication_id`, or, for a derived id, pass
    `attempt` (2 to 99): the id becomes `<channel>-<12 hex>-a<attempt>`.
  - `failed` is the only state that allows a new attempt on the same id (the
    tool answered with an error code).
  - `requested` and `outcome_unknown` are never retried by themselves
    (`publication_outcome_unknown`). Check the destination, then use a new id
    or pass `resend_after_unknown: oui` (with the manual confirmation; noted in
    the history as `resend_after_unknown`).
- An error raised during the external call without a stable tool error code
  (timeout, cut connection) does not prove that nothing was sent: the journal
  moves to `outcome_unknown`, never `failed`. Same for an e-mail answer
  without a 2xx `status_code` and a Gmail message `id` in `body` (the body
  may be JSON text). V0 does not lift the doubt itself (no `ssh_list_v1` or
  `social_post_get_v1` check).
- `overwrite`, `resend_after_unknown` and `attempt` are resume options, not part
  of the request: they do not enter the fingerprint that derives the id nor the
  same-request check (`overwrite` is recorded in `options`). After a failed
  integrity check, replay the same request with `overwrite: oui`.
- Order of a replay, on the three channels: format checks, then the answer
  `already_published` / `already_removed`, and only then the checks that depend
  on the date (a scheduled post whose date has passed is still answered
  `already_published`).
- Every journal write (`requested`, `published`, `failed`, `outcome_unknown`,
  `removed`) is read back. A write that is not visible answers
  `journal_unverified`, saying what is known of the external call (for example
  the file is published but the journal could not be confirmed): never `ok`.
- Web destinations have an index `/publish/dest/web/<sha256 of target and
  path>.json` (`publish.dest/v1`) naming the publication that owns the
  destination, updated and read back at each `published`. `publish-remove`
  refuses with `destination_superseded` when the publication no longer owns it
  (`destination_index_missing` when there is no index). The server gives no
  remote SHA-256, so the index is the check. Social posts are removed by their
  own `post_id`, which a newer post never replaces.
- The destination is reserved (`state: pending_owner`, read back) BEFORE
  `ssh_upload_v1`, then confirmed (`owner`). A previous owner loses it as soon
  as the next publication tries to write, even if that attempt ends `failed` or
  `outcome_unknown`; its removal then answers `destination_superseded`. If the
  reservation cannot be confirmed, nothing is uploaded.
- A definitive refusal of the upload, which wrote nothing (`file_exists`,
  `publish_not_enabled`, `invalid_arguments`, `file_too_large`,
  `atomic_replace_unavailable`), cancels the reservation: the index goes back
  to the previous owner and is read back. An `outcome_unknown` keeps it.
- A successful MCP result is opened before use: `structuredContent` first, else
  the JSON in the first text part of `content` (all tools, and `write_file` /
  `list_files`; for `read_file` only a clear envelope, never a file content).
- Ownership is confirmed (`owner`) only if the index is still this attempt's
  `pending_owner`. If another publication reserved or confirmed it meanwhile,
  nothing is written: the journal is `published` with `superseded_by` and the
  removal answers `destination_superseded` (an unclear index gives
  `outcome_unknown`).
- The previous owner of a destination is restored after a definitive refusal
  only if the index is still this attempt's reservation; otherwise nothing is
  written.
- A tool result carrying an `error` field (string or object, in the usual
  envelopes) is an error whatever `status` or `state` says; a failing
  `publish-status` read leaves the journal unchanged.
- Only a code documented as a refusal before any write allows `failed`: for
  ssh the five definitive refusal codes, for social the validation codes
  (`invalid_arguments`, `invalid_request`, `validation_failed`, `not_configured`,
  `rate_limited`, `channel_not_found`, `content_too_long`, `invalid_schedule`,
  `invalid_media`, `media_too_large`), for e-mail the known pre-send codes and
  4xx answers. Any other error (no code, `status: "error"`, free text such as
  an upstream timeout) is `outcome_unknown`, and replaying the same request
  answers `publication_outcome_unknown` without a new call.
- With an explicit `publication_id`, `already_published`, `already_removed` and
  the refusal of a `requested` / `outcome_unknown` publication are decided on
  the journal alone, before any read of the Storage source (the cheap parts of
  the request and an optional `source_sha256` are still compared:
  `publication_conflict`). A derived id comes from the source fingerprint, so
  its replay needs the source: pass a `publication_id` for a source-free replay.
- `isError: true` always wins in a tool result, even next to a
  `structuredContent` or a text saying ok. The code is read from the content;
  without any code the outcome is `outcome_unknown`.
- E-mail: only a code known to happen before the sending (`not_connected`,
  `authorization_required`, `identity_unproven`) or a 4xx answer gives
  `failed`. A 5xx, any other error code or any answer without proof of
  non-sending gives `outcome_unknown`.
- Absence is recognised on a structured signal only: a code (`not_found`,
  `file_not_found`, `ENOENT`, `no_such_file`), an explicit HTTP 404, or the
  exact message of the storage tools (`failed to download file: ... status 404`
  or `object not found`). Free text such as "Storage credential not found" is
  `storage_unavailable`.
- Storage errors are found in the usual envelopes (`data`, `result`, JSON
  text in `content[0].text`) up to a depth of 3.
- A remote identifier (post, group, channel, message, thread) is never
  truncated: 1 to 1024 characters, else `remote_id_invalid` and the
  publication is not marked `published`.
- The journal write at `requested` is read back before any external call
  (`journal_unverified`, no call otherwise). A Storage result carrying `error`
  (string or object), `isError`, `status: "error"` or a JSON text with an
  error is an error.
- The `publication_id` is the caller's or derived. It is the
  `idempotency_key` of a social post. The same id with another request is
  refused (`publication_conflict`).
- Every Storage tool result is checked by one helper: an exception or a
  returned `{isError: true}` / `{error: ...}` is an error. Only "not found"
  reads as absent; anything else is `storage_unavailable`.

## Workflows

| Workflow | Role |
|---|---|
| `publish-plan` | reads a Storage file or a text, suggests the channel, a subject or a post text, with warnings. One `llm_call` (text), strict parsing. Writes nothing |
| `publish-web` | reads the source in base64, calls `ssh_upload_v1` with `content_base64`, checks the returned SHA-256 and size. `overwrite` is an explicit choice (default no) |
| `publish-email` | calls `google_mail_send` with `to`, `subject` and `body` (plain text; from `body` or from a `.md`/`.txt` file). Recipients: 1 to 10, validated, no line break in the subject |
| `publish-social` | calls `social_post_create_v1`: `channels` (1 to 10), text from `content` or a `.md`/`.txt` file, up to 4 images from Storage, `mode` `draft` (default), `schedule` (RFC 3339 `schedule_at` in the future) or `now` |
| `publish-remove` | requires a `published` journal: `ssh_remove_v1` (recorded target and path, revalidated) or `social_post_delete_v1`. An e-mail answers `not_removable` |
| `publish-status` | returns the journal; for a social post, reads the state again with `social_post_get_v1` and records it. No confirmation: nothing is published |
| `publish-list` | lists the journals (identifier, channel, status, target label, last update) |
| `publish-read` | full journal of a publication, with its history |

The `publish-tracker` MiniApp has no input component: the identifier is typed
in the form of `publish-read`. It then shows the channel, status, attempts and
history, rereads the remote state, and removal goes through the form of
`publish-remove`, with the manual confirmation.

## Storage

- `/publish/log/<publication_id>.json`: `publish.record/v1` with `channel`,
  `status` (`requested`, `published`, `failed`, `outcome_unknown`, `removed`), `revision` (+1 at
  every write), `attempts`, `request_sha256`, `source` (kind, path, SHA-256,
  bytes), `target`, `remote` (identifiers returned by the tool), `error` and
  `history`.

`publication_id`: `^[a-z0-9][a-z0-9-]{0,47}$`. For a social post, the status
`published` means the social service accepted the post; `remote.state` says
whether it is a draft, scheduled or published.

Guards shared with `document-studio`: the record is read again before each
write and the write is abandoned on `concurrent_update`; a Storage error is
never swallowed (`storage_unavailable`, only a missing record counts as
absent); the keys `__proto__`, `constructor` and `prototype` are refused in
every input and model answer; the `llm_call` answers `text` and the next step
parses `{text}` strictly.

## Regeneration and tests

```
python3 tooling/publish/build.py
python3 -m unittest discover -s tooling/publish/tests -p 'test_*.py'
```

The tests run every JavaScript step under Node, with a simulated Storage and
simulated tools, on synthetic data. They do not prove the behavior on a One.

## Known limits (V0)

- E-mail: plain text, no attachment, no HTML; `google_mail_send` has no
  idempotency key, hence the refusal to retry an unknown outcome. The Outlook
  tool is not supported.
- Files are limited to 10 MiB and travel in base64 through the Workflow.
- The log write after a successful diffusion can fail (`log_write_failed`):
  the error then carries the remote identifiers. The window between the check
  and the write is small, not null, until Storage offers conditional writes.
- A server that does not confirm the SHA-256 leaves the file in place and the
  journal `failed`: retry with `overwrite`, or clean the server by hand.
- The owner of a web destination is read again right before `ssh_remove_v1`,
  but a window remains between that read and the removal, and between the
  reservation and the upload, until Storage offers conditional writes (the same
  limit as the document numbering of `document-studio`).
- Social media come from Storage images only. No `human_action/v1`.
