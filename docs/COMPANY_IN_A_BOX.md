# Company in a Box services

The base Modules are [Watch](../watch/module.yaml),
[Content](../content/module.yaml) and [Support](../support/module.yaml). The
[template composer](../templates/company-in-a-box/compose.py) copies them into
three initialized Agents in the consumer project, in preview mode by default.

[Standalone memory](../tooling/company-memory/README.md), its
[integration](../tooling/memory-integration/README.md), the
[daily routine](../tooling/daily-routine/README.md),
[work cases and Direction](../tooling/work-cases/README.md),
[administration](../tooling/enterprise-admin/README.md) and
[launch Marketing](../tooling/marketing-launch/README.md) can be composed to
meet the company's needs.

See [installation](INSTALLATION.md), [permissions](SECURITY.md) and
[tests](TESTING.md). Data, accounts and permissions belong to the destination
instance, never to a source company. The initial mode is manual, without
external effects.
