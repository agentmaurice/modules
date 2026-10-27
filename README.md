# AgentMaurice Modules

Reusable application Modules for AgentMaurice, maintained in one repository.
Each Module has its own version and a root `module.yaml`; published Module
keys, Workflow IDs and MiniApp IDs keep their existing contracts. The repository
remains private and retains the history of `agentmaurice/company-in-a-box`.

## Modules

| Module directory | Stable Module key | Manifest |
|---|---|---|
| Company Memory | `company-memory` | [company-memory](company-memory/module.yaml) |
| Work cases and Direction | `cib-work-dossiers` | [work-cases](work-cases/module.yaml) |
| Daily routine | `cib-daily-routine` | [daily-routine](daily-routine/module.yaml) |
| Enterprise administration | `cib-enterprise-admin` | [enterprise-admin](enterprise-admin/module.yaml) |
| Marketing launch | `cib-marketing-launch` | [marketing-launch](marketing-launch/module.yaml) |
| Watch | `cib-veille` | [watch](watch/module.yaml) |
| Content | `cib-contenu` | [content](content/module.yaml) |
| Customer support | `cib-accompagnement` | [support](support/module.yaml) |
| Watch memory adapter | `cib-veille-memory` | [watch-memory](watch-memory/module.yaml) |
| Content memory adapter | `cib-contenu-memory` | [content-memory](content-memory/module.yaml) |
| Support memory adapter | `cib-accompagnement-memory` | [support-memory](support-memory/module.yaml) |

[modules.json](modules.json) is generated from the manifests. The detailed
[source and migration inventory](inventory/modules.json) records resources,
runtimes, dependencies, consumers and source reconciliation. The
[repository migration guide](docs/REPOSITORY_MIGRATION.md) maps historical
paths and explains version compatibility.

## Company in a Box

The [Company in a Box template](templates/company-in-a-box/modules.json)
pins these Modules without duplicating their resources. Its role composer is
[templates/company-in-a-box/compose.py](templates/company-in-a-box/compose.py).
Module-specific generators, composers and tests live under `tooling/`.
Consumer Agent Specs, deployment locks, accounts, connections and data remain
in a separate consumer project.

Follow the [installation guide](docs/INSTALLATION.md), then use the native
Agent Spec check/plan/apply/verify rail and verify the resulting UI. The current
library uses local composition; URL/catalog installation and archive transport
have separate implementation work. Existing UI text and business code remain
on their current language/runtime until their qualified migrations.

Company Memory now carries the separately versioned 0.3.0 source. Its
[reconciliation notes](tooling/company-memory/README.md) explain supersession,
the retired helper Workflow and the limits of upgrade/Viewer qualification.
The historical 0.2.0 package remains recoverable from its original Git commit.

## Offline checks

Python 3.12+ and Node.js 22+ are required. No extra package, credential or One
is needed for these checks:

```sh
python3 scripts/inventory.py --check
python3 scripts/check.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test.py
git diff --check
```

Tests run on temporary copies. Read the [testing guide](docs/TESTING.md),
[security boundaries](docs/SECURITY.md) and [upgrade guide](docs/UPGRADING.md).
Offline CI proves these checks; runtime and business acceptance are separate.

AgentMaurice proprietary software. See [NOTICE](NOTICE).
