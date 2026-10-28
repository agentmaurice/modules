# Launch Marketing Module

This directory provides a portable composer for a multi-resource Module owned
by one `veille` Agent. It composes the manual journey `campaign → content →
trial request → support → confirmed first result` into an initialized Agent
Spec V2.

`compose.py` requires `--consumer-dir` and `--agent-alias`, validates
`agents/<alias>/agent-spec.json`, then reads the fifteen packaged resources and
the test plan. A missing or unexpected resource or inconsistent ID fails before
any write. The composer does not generate Workflows, MiniApps or tests;
`build.py` produces deterministic bytes regardless of Python's hash seed.

The composer preserves unrelated resources, specifications, dependencies and
test cases. Preview without writing is the default; use `--write` after review.
It does not start MauriceCLI or One, deploy, or run a lifecycle procedure.

```sh
python3 tooling/marketing-launch/compose.py \
  --consumer-dir /path/to/company-in-a-box --agent-alias veille
python3 tooling/marketing-launch/compose.py \
  --consumer-dir /path/to/company-in-a-box --agent-alias veille --write
```

The nine Workflows are `cib-launch-campaign-save`, `cib-launch-content-link`,
`cib-launch-request`, `cib-launch-progress`, `cib-launch-read`,
`cib-launch-list`, `cib-launch-people`, `cib-launch-share` and
`cib-launch-summary`. The six MiniApps are the `campaign`, `content`,
`request`, `support`, `sharing` and `direction` consoles.

Storage uses the native `cib-launch-marketing` partition of the
`application_data_v1` broker; it creates no database. Records are private by
default and may be shared explicitly with native ACL operations and an expected
revision. `people` grants no permission. The Module is manual: no scheduler,
publication, sending, LLM, CRM or company memory is included.

The consumer profile must provide `cib_marketing`, `cib_service_client`,
`cib_dossiers` and `cib_direction`. The minimum owner remains `veille`; content
and support remain linked by reference to existing resources. A campaign can
reference several trial requests and one content item. A first result is an
internal attestation with evidence and a date; the Module invents no actual
result or external qualification.

The composer merges four technical cases into the consumer test plan with
stable IDs, preserving other cases. They verify refusal of machine identity for
launch operations. A known previous case is updated only when it matches the
exact historical case; unknown collisions or resource divergence stop composition.

## Operator journey from Home

Use the `cib_marketing`, `cib_service_client`, `cib_dossiers` and
`cib_direction` profiles as appropriate. Open the Application and these consoles:

| Console | Home title | Purpose |
| --- | --- | --- |
| `campaign` | **Marketing — campaign** | Create and review the campaign brief |
| `content` | **Marketing — link evidence and content** | Link Watch and Content records |
| `request` | **Marketing — trial request** | Record a trial request |
| `support` | **Support — trial progress** | Track support and attest a result |
| `sharing` | **Marketing — share or revoke access** | Manage a record ACL |
| `direction` | **Management — launch and first results** | View accessible records |

### 1. Create a campaign

In **Marketing — campaign**, choose **Real work** (`usage`) or **Synthetic
trials** (`qualification`). Supply a stable `campaign_id`; set
`expected_revision` to `0` for creation. Fill in the brief, audience, promise,
channel, owner, deadline and completion criterion, then confirm manually. A
campaign can link one content item and several trial requests. After editing
the brief, reread the record and use its returned revision for the next link.

### 2. Link sources and content

Prepare records in the existing **Watch** and **Content** roles. In
**Marketing — link evidence and content**, enter the campaign and exact
revision, then `veille_ref`, `veille_revision`, `contenu_ref`,
`contenu_revision` and `preuve_ref`. Use revisions returned by saving or
reading each source record and confirm manual review. This step publishes
nothing and does not copy the source records.

### 3. Record a trial request

In **Marketing — trial request**, select a ready campaign and its
`campaign_revision`. Supply a stable `trial_id`, `personne_ref` (an internal
reference, not a contact list), the need and objective, then confirm manually.
Identical data replayed with the same `trial_id` is deduplicated; a new ID is a
new request. Keep the exact ID for sharing and support.

### 4. Share the trial and provide support

In **Marketing — share or revoke access**, select the trial record, load
members, open the appropriate person's form and choose `write`. Use the exact
trial revision and confirm manually; reread the record and retain the new
revision. The share applies only to that record and does not grant service use
or sharing administration.

In **Support — trial progress**, select the trial and use the revision read
after sharing. Reference the existing Support record with `accompagnement_ref`
and `accompagnement_revision`. First set the trial **In progress** and save.
The Support record must contain the observed result, `preuve_ref`, next step,
no blocker and manual confirmation. Then choose `premier_resultat_confirme`,
enter `date_confirmation` as `YYYY-MM-DD` and set `confirmation_resultat` to
`oui`, then confirm. Confirmations reset to **No** after each save; the current
revision is prefilled. Evidence and date must come from internal observation;
never invent a result, sale or conversion.

### 5. Read the summary

**Management — launch and first results** summarizes only records accessible
to the current profile. Requests and first-result attestations remain distinct.
The console does not calculate conversion, attribution or time savings.

Records remain private by default. `people` only lists shareable members; an
explicit ACL share grants access. Watch, Content and Support references point
to their native records and revisions; memory is neither added nor linked
automatically. The Module sends and publishes nothing, calls no CRM and does
not automatically turn a request into a conversion.

Distributed tests are synthetic and offline. They prove no customer result and
do not replace qualification on your One. See [installation](../../docs/INSTALLATION.md),
[permissions](../../docs/SECURITY.md) and [tests](../../docs/TESTING.md).

## Install in an existing CIB profile

After composition and source commit, use the native Agent Spec rail:
`spec check`, then `spec deploy` and verification. Add the nine Workflows and
six MiniApps to the Application surface with their verified native versions.
`service-gates.json` defines required roles; preserve existing roles, members
and resources. Publishing the surface is separate from resource deployment and
is not done by the composer.

The profile requires `veille-save`, `contenu-save`, `accompagnement-save` and
their native namespaces. The Module does not configure people or grant rights
on deployment. Reuse the resources for another company with that consumer's
own profile links, existing members and data.
