# Mémoire d’entreprise — company-memory 0.2.0

Module autonome de capture, proposition, revue manuelle, consultation citée,
indexation Memory et recherche Brain. Les fichiers natifs sont la source de
vérité ; Memory/Brain portent des copies reconstructibles.

```sh
python3 solutions/company-memory/compose.py --consumer-dir /chemin/consommateur --agent-alias memory
python3 solutions/company-memory/compose.py --consumer-dir /chemin/consommateur --agent-alias memory --write
```

Préconditions : Agent `memory` initialisé, outils Memory `memory.entities.upsert`
et `memory.query`, outils Brain `brain.document.upsert` et `brain.keyword`.
Le composeur déclare `mcp_requirements` ; les MCP et leurs volumes doivent être
provisionnés par le plan natif du consommateur. Épingler les images autorisées
par digest dans ce consommateur, jamais des secrets dans le package.

Le parcours est capture → proposition avec citation exacte → inspection → revue
explicite → consultation. Seules les propositions validées, dont la citation
correspond à la source et dont l’échéance n’est pas dépassée, sont restituées.
L’indexation est une opération manuelle séparée ; la recherche revalide chaque
révision native au lieu de faire confiance à un extrait d’index.

**Isolation : un Agent mémoire et des sidecars/volumes dédiés par entreprise.**
Le tenant fixe `company-memory` ne sépare pas deux entreprises sur un même
sidecar. La mémoire est commune aux personnes admises ; ce n’est pas un coffre
privé par personne. Les dossiers privés ne doivent pas être versés en bloc.

Les écritures refusent l’écrasement ; une correction crée une nouvelle
proposition. Le protocole est single-writer, sans transaction CAS concurrente
ni dépublication automatique d’une ancienne révision. Memory et Brain ne sont
pas mis à jour dans une transaction commune : inspecter un échec partiel avant
rejeu. La recherche est bornée à dix candidats et n’est pas un inventaire.
Les dates de revue sont évaluées au début du jour UTC.

Voir [installation](../../docs/INSTALLATION.md),
[droits et isolation](../../docs/SECURITY.md) et
[tests hors ligne](../../docs/TESTING.md). Le dépôt n’inclut aucun rejeu privé
ni données d’une mémoire existante.
