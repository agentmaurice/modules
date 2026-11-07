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
- Social media come from Storage images only. No `human_action/v1`.
