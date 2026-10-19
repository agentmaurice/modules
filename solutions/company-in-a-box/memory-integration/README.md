# Raccordement manuel des trois rôles à la mémoire

Les Modules `cib-veille-memory`, `cib-contenu-memory` et
`cib-accompagnement-memory` 0.2.0 ajoutent recherche, consultation et proposition
d’un extrait sélectionné. Contenu peut préparer un brouillon depuis une
révision validée et citée. La revue et l’indexation restent sur l’Agent mémoire.

```sh
python3 solutions/company-in-a-box/memory-integration/compose.py --consumer-dir /chemin/consommateur
python3 solutions/company-in-a-box/memory-integration/compose.py --consumer-dir /chemin/consommateur --write
```

Préconditions : les quatre Agents `veille`, `contenu`, `accompagnement`, `memory`
initialisés avec des identifiants distincts ; ressources métier et mémoire
composées ; capacités inter-Agent avec `allowed_agent_ids` et broker humain
natifs disponibles. Le composeur lit les identités du consommateur, crée les
liaisons locales et refuse toute ressource ou permission divergente.

Déployer mémoire puis les trois rôles, vérifier chaque plan et committer son
lock avant le suivant. `surface.py` prépare un brouillon depuis un `app get`
récent, avec `--consumer-dir`, `--application-snapshot` et `--output` ; relire ce
brouillon avant publication de la surface native.

Le propriétaire choisit et confirme l’extrait partagé. Une révocation du
dossier d’origine ne retire pas une connaissance déjà partagée intentionnellement ;
son retrait relève du cycle de revue de la mémoire. Aucun dossier privé complet
n’est indexé automatiquement. Si la capture réussit mais la proposition échoue,
inspecter l’état avant de rejouer : les sources refusent l’écrasement.

Voir [installation](../../../docs/INSTALLATION.md),
[droits et isolation](../../../docs/SECURITY.md).
