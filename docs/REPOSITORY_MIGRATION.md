# Repository migration to agentmaurice/modules

The existing private `agentmaurice/company-in-a-box` repository is reused as
`agentmaurice/modules`. The migration preserves its Git history, repository
identity, historical resource IDs and versions. Repository visibility and
runtime deployments are separate from this layout change.

## Package roots and tools

Application Module directories are directly below the repository root; each
contains `module.yaml` and its existing V2 resource tree. Development builders,
composers and tests live under `tooling/`. The consumer template lives under
`templates/company-in-a-box/` and pins versions in its generated
[Module list](../templates/company-in-a-box/modules.json).

| Historical path | Current path |
|---|---|
| `solutions/company-in-a-box/modules/veille` | `watch` |
| `solutions/company-in-a-box/modules/veille/test_acl_contract.py` | `tooling/roles/test_acl_contract.py` |
| `solutions/company-in-a-box/modules/contenu` | `content` |
| `solutions/company-in-a-box/modules/accompagnement` | `support` |
| `solutions/company-in-a-box/memory-integration/modules/veille` | `watch-memory` |
| `solutions/company-in-a-box/memory-integration/modules/contenu` | `content-memory` |
| `solutions/company-in-a-box/memory-integration/modules/accompagnement` | `support-memory` |
| `solutions/company-in-a-box/common-dossier/module` | `work-cases` |
| `solutions/company-in-a-box/daily-routine/module` | `daily-routine` |
| `solutions/company-in-a-box/enterprise-admin/module` | `enterprise-admin` |
| `solutions/company-in-a-box/marketing-launch/module` | `marketing-launch` |
| `solutions/company-memory/module` | `company-memory` |
| `solutions/company-in-a-box/template` | `templates/company-in-a-box` |
| `solutions/company-in-a-box/tests/<role>.json` | `templates/company-in-a-box/tests/<role>.json` |
| `solutions/company-in-a-box/common-dossier` tools | `tooling/work-cases` |
| `solutions/company-in-a-box/daily-routine` tools | `tooling/daily-routine` |
| `solutions/company-in-a-box/enterprise-admin` tools | `tooling/enterprise-admin` |
| `solutions/company-in-a-box/marketing-launch` tools | `tooling/marketing-launch` |
| `solutions/company-in-a-box/memory-integration` tools | `tooling/memory-integration` |
| `solutions/company-memory` tools | `tooling/company-memory` |
| `solutions/company-in-a-box/marketing-launch/module/test-plan.json` | `templates/company-in-a-box/tests/marketing-launch-plan.json` |
| `solutions/company-in-a-box/README.md` | `docs/COMPANY_IN_A_BOX.md` |

The marketing test plan remains a consumer test plan; it is outside the
application Module package. Historical upgrade fingerprints remain logical
keys used by their composers, even when physical source paths move. French
role aliases and wire keys such as `veille`, `contenu` and `accompagnement`
remain compatible; English directory names do not rename these contracts.

## Source reconciliation

The original library snapshot is commit
`dc935630764b24c819defd03cc487bddf8f87399`. The ten Modules other than Company
Memory retain their manifest and Workflow/MiniApp bytes. Their generated
builders are checked on temporary copies against the committed artifacts.

Company Memory carries the separately versioned 0.3.0 source from commit
`8cb35a14b825dcdae4515d46e3b4c5149c154901` of the internal canonical pilot.
Its package resources are preserved exactly from that source. The previous
0.2.0 remains in the library's original Git history and is never overwritten
at its historical commit. Version 0.3.0 adds supersession Workflows and retires
`memory-resolve-candidate`; its composer reports a retained retired Workflow
instead of silently deleting consumer files. Read its
[compatibility notes](../tooling/company-memory/README.md) before an upgrade.

[The generated inventory](../inventory/modules.json) records keys, versions,
resource hashes, source commits, generators, actions, dependencies and known
consumers. [Inventory notes](../inventory/README.md) document duplicate source
locations, excluded fixtures/caches and local/private replay evidence.
Private replay scripts, deployment identities and business data are not
copied into this library. An offline test is not a new Viewer or runtime proof.

## Existing clones and pinned revisions

For a clone of this repository, inspect local work before updating its remote:

```sh
git status --short
git remote -v
git remote set-url origin https://github.com/agentmaurice/modules.git
git fetch origin
```

Use a separate consumer project and retain its own locks, configuration and
data. Pin a commit when reproducing an installation. Historical paths are
resolved at their historical commit; the current layout uses the paths above.
The source alias `agentmaurice/company-in-a-box` identifies the same renamed
repository, not a different publisher.

## Checks and remaining delivery

```sh
python3 scripts/inventory.py --check
python3 scripts/check.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/test.py
git diff --check
```

The generated index has no fixed eleven-Module ceiling: every top-level
`*/module.yaml` is discovered and must have a documented source. Test fixtures,
caches, archives and private replay outputs are outside the product inventory.

This migration supplies repository organization and source reconciliation.
Module Catalog subpath import, deterministic archive transport, independent
release publication, full English content migration and qualified Go/WASM
activation follow their own contracts and acceptance steps. Existing consumer
projects keep their current runtime until their explicit governed migration.
