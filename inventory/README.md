# Module inventory

Run `python3 scripts/inventory.py` to generate the documentary indexes. `--check` compares them without writing. Discovery covers every top-level `*/module.yaml`, without a numerical limit. The catalog records resource fingerprints, declared capabilities and manifest requirements. Composition dependencies are listed separately and are not claimed to be exhaustive. Neither language nor runtime qualification is inferred.

The historical library source is GitHub `agentmaurice/company-in-a-box` at `dc935630764b24c819defd03cc487bddf8f87399`. Company Memory 0.3.0 is sourced from GitLab `mcpchatui/pilote-maurice` at `8cb35a14b825dcdae4515d46e3b4c5149c154901`; its previous 0.2.0 is in the historical GitHub commit. Version 0.3.0 removes `memory-resolve-candidate`, adds supersession workflows and changes the search contract. The composer reports the retired file without deleting it; indexed data and callers require a specific migration. Offline tests do not prove deployment or Viewer rendering.

Private replay scripts and test differences from branch AGENT-858 are not automatically included. Its module resources were compared with the historical library; future inclusion requires a separate review. Fixtures, caches, archives, worktrees, generated artifacts and probes are excluded from discovery. Future M5 and M6 steps remain to be defined and qualified; this inventory does not attest their completion.

## Path mapping

Published module keys and runtime identifiers are unchanged. Paths below are repository-relative.

| Old path | New path |
|---|---|
| `solutions/company-in-a-box/modules/veille` | `watch` |
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
| `solutions/company-in-a-box/common-dossier` | `tooling/work-cases` |
| `solutions/company-in-a-box/daily-routine` | `tooling/daily-routine` |
| `solutions/company-in-a-box/enterprise-admin` | `tooling/enterprise-admin` |
| `solutions/company-in-a-box/marketing-launch` | `tooling/marketing-launch` |
| `solutions/company-in-a-box/memory-integration` | `tooling/memory-integration` |
| `solutions/company-memory` | `tooling/company-memory` |
| `solutions/company-in-a-box/README.md` | `docs/COMPANY_IN_A_BOX.md` |
| `solutions/company-in-a-box/marketing-launch/module/test-plan.json` | `templates/company-in-a-box/tests/marketing-launch-plan.json` |

The package paths above are exceptions to their parent tooling moves.
