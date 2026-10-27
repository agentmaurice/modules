# Install in another company

## Prepare the consumer

Clone the private repository with an authorized account:

```sh
git clone https://github.com/agentmaurice/modules.git
cd modules
git rev-parse HEAD
```

Record this commit in the installation folder and use the same revision for
all composition. To replay qualification, use a clean clone, check
`git status --porcelain`, and run `git checkout <QUALIFIED_COMMIT>` before
composition. Preserve any existing local work in its checkout.

You need an operational One, its Agent Spec V2-compatible MauriceCLI and a
separate consumer project. This repository contains neither the One binary nor
authentication configuration. Use connection and initialization commands from
your instance with its real identifiers; do not invent IDs or copy them from
another environment.

The complete profile uses four initialized Agents: `veille`, `contenu`,
`accompagnement` and `memory`. A standalone Module can be composed only into
the Agent it needs. The consumer needs `agentmaurice.project.json`, its
environments and Agent Specs V2. CLI configuration remains outside this repo.

## Check compatibility

- Workflows V2, MiniApps/forms and `code_execution` are available.
- Roles, cases, Marketing and record administration require the human broker
  `recipe--application_data_v1`, per-record ACLs and native revision CAS.
- Administration requires `recipe--company_admin_v1`, native directory and roles.
- Memory requires persistent storage, a dedicated Agent and sidecars per company,
  and the Memory/Brain tools declared in the manifest and available at deployment.
- Memory integration requires native inter-Agent capabilities and
  `allowed_agent_ids`, with human identity retained by the runtime.

These are capabilities to verify, not a promise of compatibility with every
older One. Native `spec check` and deployment verification remain required.

## Initialize the first administrator

Use the organization's **native control plane** with an authorized author
connection (`orga-admin` for these routes). The Administration Module does not
create accounts, invite people or initialize its own first administrator.
`orga-admin` is a platform role; `cib_admin` is a Module business grant.
Granting the latter does not confer the former. Form confirmation never
replaces native authorization.

1. Verify instance, organization and connection identity with
   `maurice --config /path/config.yaml whoami --json`. Use configuration for
   the new One, not another company's global context. Do not expose the bearer
   in the terminal, Git or a URL.
2. With this authenticated client, read `GET /api/v1/user/me` and
   `GET /api/v1/organization/<ORGANIZATION_ID>/directory`. The first returns
   `user.id`; the second returns `people` and `grants`.
3. If the active person linked to that identity already has `cib_admin`, write
   nothing and proceed to verification. If the directory is nonempty without
   that link, stop automatic bootstrap and have an authorized administrator
   review its people and grants. Never replace an existing directory with the
   example below.
4. **Only on an empty directory**, an authorized author may apply
   `PUT /api/v1/organization/<ORGANIZATION_ID>/directory` with the following
   document after replacing placeholders with verified values:

```json
{
  "people": [{
    "person_id": "<CHOSEN_LOCAL_PERSON_ID>",
    "display_name": "Local administration",
    "platform_user_id": "<VERIFIED_USER_ID>",
    "status": "active"
  }],
  "grants": [{
    "person_id": "<CHOSEN_LOCAL_PERSON_ID>",
    "role_key": "cib_admin"
  }]
}
```

On a local One the author principal may be `local-operator`; use it only if
`/user/me` confirms it. Never substitute a human identity to execute or approve
for that person. This PUT replaces the entire directory without CAS: reserve
an administration window without concurrent authors, reread immediately before
writing and stop if it is no longer empty. Keep a private snapshot and verify
the response before continuing.

After surface publication, execute `cib-admin-overview` as the authorized
administrator through the Administration console or this native entrypoint:

```text
POST /api/v1/organization/<ORGANIZATION_ID>/applications/<APPLICATION_ID>/workflows/cib-admin-overview/executions
{"input": {}, "timeout_seconds": 30}
```

Require HTTP 200 and `state=completed`; verify the linked active identity and
`cib_admin` role in `data.people` and `data.grants`. A second execution of the
procedure must only read, not rewrite the directory. An unprivileged key or
HTTP 401/403 is not successful bootstrap.

For humans, use the native AM organization access flow, then Administration to
link existing identities to people and the Application with
`directory_upsert_person`, `directory_link_user`, `application_people_add` and
`directory_grant_role`. Verify Home access with intended real accounts. Do not
grant global administrator to test accounts to bypass a refusal. Service roles
remain distinct from each record's ACL.

## Preview composition, then write after review

Run from this repository root. Replace `/path/to/consumer` with the company
project. Each command is a read-only preview; review it, then add `--write` to
compose files.

```sh
# Three roles
python3 templates/company-in-a-box/compose.py --consumer-dir /path/to/consumer
# Standalone memory
python3 tooling/company-memory/compose.py --consumer-dir /path/to/consumer --agent-alias memory
# Role-to-memory links, after composing all four Agents
python3 tooling/memory-integration/compose.py --consumer-dir /path/to/consumer
# Daily routine, after memory links
python3 tooling/daily-routine/compose.py --consumer-dir /path/to/consumer
# Optional services on the existing Watch Agent
python3 tooling/work-cases/compose.py --consumer-dir /path/to/consumer --owner-alias veille
python3 tooling/enterprise-admin/compose.py --consumer-dir /path/to/consumer --owner-alias veille
python3 tooling/marketing-launch/compose.py --consumer-dir /path/to/consumer --agent-alias veille
```

Memory integration also checks that each explicitly pinned local Workflow is
available at the required native version before writing any files. In
particular, the Content Agent must already provide `review_completion` version
`2`; composing over an older role does not upgrade it automatically. Remote
capability targets retain their separate contract versions.

Daily routine requires the memory integration composer first: every role must have a
parseable `company-memory-query` bridge Workflow at native version `2`. This
is independent of the memory capability contract version `1`.

Unknown divergence is refused: preserve local changes and resolve the conflict
before writing. No composer deploys for you. Review each Module guide, including
memory limits.

## Wait for Memory and Brain without changing their data

Install existing connectors in the **new One's** Registry and provision
sidecars with company-specific persistent volumes through applicable native
plans. Record image tags and digests in the private installation folder; do not
reuse a customer's database or volume. The manual Aurore run on 19 October 2026
used Memory 1.0.17 and Brain 1.1.8; these observations do not guarantee
compatibility with all AM versions.

Discover the catalog with the consumer's real identifiers:

```sh
maurice --config /path/config.yaml tools list --organization <ORGANIZATION_ID> --deployment <MEMORY_AGENT_ID> --json
```

Verify the Module manifest tools: `memory.entities.upsert`, `memory.query`,
`brain.document.upsert` and `brain.keyword`. The CLI catalog provides business
names in `display_name` and call names in `name`; also verify `mcp_server_id`
and `availability=available`. Do not copy a tool-name suffix from another One.
Follow CLI pagination if the inventory is truncated.

If the Registry is provisioned by the first `spec deploy`, this check can only
be performed after provisioning. An empty pre-deployment catalog is not proof
that memory is operational.

If the catalog also exposes `memory.health` and `brain.health`, use their
**returned call names** for these optional diagnostics:

```sh
maurice --config /path/config.yaml tools call <MEMORY_HEALTH_CALL_NAME> --organization <ORGANIZATION_ID> --deployment <MEMORY_AGENT_ID> --timeout 15 --json
maurice --config /path/config.yaml tools call <BRAIN_HEALTH_CALL_NAME> --organization <ORGANIZATION_ID> --deployment <MEMORY_AGENT_ID> --timeout 15 --json
```

For each exposed health tool, require a native response without error,
`status=ok` and `result.status=ok`. Absence of a health tool not declared in
the manifest is not itself a blocker: record it and test the actual memory
journey. The Module's `memory-health` inventories files; it does not replace
`memory.health`. A health version string can be old: verify the deployed image
digest.

**Bounded wait:** for at most five minutes, reread the catalog and repeat only
these reads if tools are absent or `not ready`, or catalog preparation or MCP
transport times out during startup. Wait ten seconds between attempts; bound
each client HTTP request to fifteen seconds and do not start one beyond the
remaining overall time. `tools call --timeout` bounds requested execution but
the CLI may wait longer for preparation/HTTP. The 300-second overall and
15-second per-request limits therefore require a suitably bounded HTTP client
or external CLI supervisor. Keep each attempt's time, result and cause in
private evidence. Equivalent routes are
`GET /api/v1/organization/<ORGANIZATION_ID>/deployment/<MEMORY_AGENT_ID>/tools?format=verbose`
and `POST /api/v1/organization/<ORGANIZATION_ID>/deployment/<MEMORY_AGENT_ID>/tools/call`;
for the latter send `{"tool_name":"<CALL_NAME>","arguments":{},"timeout_sec":15}`.
Send the bearer only to the verified instance through the authenticated client;
do not display it or store it in evidence. Stop on timeout, inconsistent
identity or instance, HTTP 401/403, approval refusal or business error; do not
treat those errors as MCP readiness waits. Never automatically replay a write,
indexing or deployment.

One `/ready`, an MQTT heartbeat and health checks are insufficient because the
catalog may still be syncing. After deployment and publication, qualify the
complete memory journey below as well.

## Check and deploy through the native contract

After composition, review and commit consumer files. For each affected Agent,
using your instance configuration:

```sh
maurice --config /path/config.yaml spec check --dir /path/to/consumer --env local --agent-alias memory --json
# Review, git diff and commit in the consumer before deployment.
maurice --config /path/config.yaml spec deploy --dir /path/to/consumer --env local --agent-alias memory --tests auto --json
```

Deploy memory, then `veille`, `contenu` and `accompagnement` by changing
`--agent-alias`. Verify the result and commit the lock after each Agent. If
verification fails because MCP tools are not ready, preserve the plan and
diagnostics, check native rollback and actual remaining state, then complete
the bounded wait. If rollback is confirmed without drift, the operator may
explicitly decide to rerun deployment from the same committed sources and
review the new plan **outside the readiness loop**; obtain a new approval if
required. Do not reuse an approval tied to an old plan or reset volumes; stop
on incomplete rollback or unknown state.

If AM requests approval, the authorized person decides in AM; no command or
service key substitutes for that decision.

## Publish the surface and access

Deploying resources and making them accessible are separate steps. Retrieve the
recent Application surface with your CLI's `maurice app` commands. Add only new
resources at the native versions returned by deployment, preserving existing
resources and entrypoints. Do not confuse declared and runtime versions.

`templates/company-in-a-box/surface.example.json` is a documentary example
with placeholders, **not a ready-to-apply file**. `memory-integration/surface.py`
and `enterprise-admin/service_roles.py` prepare drafts as described in their
`--help`; Marketing provides `service-gates.json` for its nine Workflows.

The reviewed file must retain `public_surface` and existing entrypoints:

```sh
maurice --config /path/config.yaml app surface set <APPLICATION_ID> --organization <ORGANIZATION_ID> --file /path/reviewed-surface.json --json
maurice --config /path/config.yaml app surface publish <APPLICATION_ID> --organization <ORGANIZATION_ID> --bump minor --json
```

Link existing people to appropriate services. Marketing uses `cib_marketing`,
Support `cib_service_client`, Cases `cib_dossiers`, Management `cib_direction`
and administration `cib_admin`. A role does not implicitly grant access to a
private record: explicitly share that record.

From Home, open the Application with intended accounts and test a synthetic
journey, refusals, individual sharing and revocation. A refused machine-key call
does not qualify human journeys. Cloning causes no real sending, publication,
payment or campaign.

## Validate memory after installation or restart

From Home, with each service's account:

1. Create a synthetic company-specific record, explicitly propose a shareable
   excerpt to memory, then manually review and index it with the authorized
   role. Retain the exact revision ID. If this set already exists, reuse it for
   reads; do not reindex on every attempt.
2. For Watch, Content and Support, run their memory queries and searches through
   the right Agent's MiniApps. Require a cited, unexpired `validated` revision
   and then the expected revision in search results. An empty search does not
   prove retrieval of the set.
3. For an authorized authenticated HTTP client on the published surface,
   equivalent reads use:

```text
POST /api/v1/organization/<ORGANIZATION_ID>/applications/<APPLICATION_ID>/workflows/<WORKFLOW_ID>/executions
{"input": {"proposal_id": "<VALIDATED_SYNTHETIC_REVISION>"}, "timeout_seconds": 15}
```

For the three roles, replace `<WORKFLOW_ID>` with `veille-memory-query`,
`contenu-memory-query` or `accompagnement-memory-query`. Require HTTP 200,
`state=completed`, `data.status=validated` and nonempty `data.citations`. For
`veille-memory-search`, `contenu-memory-search` or
`accompagnement-memory-search`, send `input: {"query": "<SET_KEYWORD>"}` and
verify the expected revision in `data.results`. Repeat only these reads for
`mcp servers not ready`, within the same five-minute catalog/health bound. A
business error or permission refusal stops the test. Never broaden a role to
obtain a green result.

For a qualification restart, capture data and ACLs first, restart **only this
One** using its native commands and explicit `--data-dir`, then repeat these
reads and Home access. Verify revocations persist, data is retained and volumes
remain separate from other companies. Starting One does not prove the two MCPs
have reconnected.

`daily-context`, `daily-time-save` and `daily-report` IDs exist on three Agents:
qualify them through their Agent-contextualized MiniApps, without a global
lookup by Workflow ID alone or an invented API filter.

The manual Aurore test checked initial bootstrap, reuse without directory
rewrite, and all three role memory reads after waiting. The consumer folder
holds private evidence; this repo provides no real identity, session, company
data or screenshot. This procedure does not qualify automatic URL/Module
Catalog installation, a new real human approval or external business effects.
