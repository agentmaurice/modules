# Manual watch

Explicitly import supplied sources and facts, assign them manually and check
fields and dates (30 days). There is no web access or model judgement. A
sufficient field does not prove a fact is true. Cases are stored privately by
the Agent, with a fixed directory, bounded identifier and explicit confirmation.

## Record sharing contract

The `veille`, `contenu` and `accompagnement` role MiniApps submit the sharing
form with the closed fields `share_dossier_id`, `share_expected_revision`,
`share_subject_user_id`, `share_permission` and `share_confirmation_manuelle`.
`selection_dossier_id` binds the member selection to the record just read.
Permission values are `read`, `write` and `none` (`none` removes access). The
five `share_*` fields remain required and confirmation returns to `non` after
success. A native call to the `*-share` Workflow must map its canonical
parameters to these form fields; the Workflow does not read the canonical keys
directly.
