# Manual memory integration for the three roles

The `cib-veille-memory`, `cib-contenu-memory` and
`cib-accompagnement-memory` Modules add search, retrieval and contribution of
a selected excerpt. Content can prepare a draft from a validated, cited
revision. Review and indexing remain with the memory Agent.

```sh
python3 tooling/memory-integration/compose.py --consumer-dir /path/to/consumer
python3 tooling/memory-integration/compose.py --consumer-dir /path/to/consumer --write
```

Prerequisites: four initialized Agents, `veille`, `contenu`, `accompagnement`
and `memory`, with distinct identities; composed role and memory resources;
and native inter-Agent capabilities with `allowed_agent_ids` and the human
broker. The composer reads consumer identities, creates local bindings and
refuses divergent resources or permissions.

Deploy memory and then the three roles, review each plan and commit its lock
before proceeding. `surface.py` prepares a draft from a recent `app get` using
`--consumer-dir`, `--application-snapshot` and `--output`; review the draft
before publishing the native surface.

The owner selects and confirms the shared excerpt. Revoking the original case
does not remove knowledge intentionally shared earlier; removal follows the
memory review lifecycle. Complete private cases are never indexed automatically.
If capture succeeds but proposal fails, inspect state before replay: sources
refuse overwrites.

See [installation](../../docs/INSTALLATION.md) and
[permissions and isolation](../../docs/SECURITY.md).
