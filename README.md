# Company in a Box — Modules AgentMaurice

Bibliothèque privée de Modules applicatifs réutilisables pour AgentMaurice One.
Les packages contiennent des Workflows et des MiniApps, leurs tests synthétiques
et des composeurs locaux. Chaque entreprise conserve son projet consommateur,
ses identités, droits, connexions et données. Aucun One ni donnée d’entreprise
n’est inclus dans ce dépôt.

## Modules disponibles

| Module | Version | Workflows | MiniApps |
|---|---|---:|---:|
| [`cib-work-dossiers`](solutions/company-in-a-box/common-dossier/module/module.yaml) | 0.2.2 | 6 | 2 |
| [`cib-daily-routine`](solutions/company-in-a-box/daily-routine/module/module.yaml) | 0.1.0 | 4 | 3 |
| [`cib-enterprise-admin`](solutions/company-in-a-box/enterprise-admin/module/module.yaml) | 0.2.2 | 7 | 3 |
| [`cib-marketing-launch`](solutions/company-in-a-box/marketing-launch/module/module.yaml) | 0.1.0 | 9 | 6 |
| [`cib-accompagnement-memory`](solutions/company-in-a-box/memory-integration/modules/accompagnement/module.yaml) | 0.2.0 | 3 | 3 |
| [`cib-contenu-memory`](solutions/company-in-a-box/memory-integration/modules/contenu/module.yaml) | 0.2.0 | 4 | 4 |
| [`cib-veille-memory`](solutions/company-in-a-box/memory-integration/modules/veille/module.yaml) | 0.2.0 | 3 | 3 |
| [`cib-accompagnement`](solutions/company-in-a-box/modules/accompagnement/module.yaml) | 0.2.4 | 6 | 2 |
| [`cib-contenu`](solutions/company-in-a-box/modules/contenu/module.yaml) | 0.2.4 | 6 | 2 |
| [`cib-veille`](solutions/company-in-a-box/modules/veille/module.yaml) | 0.2.4 | 7 | 2 |
| [`company-memory`](solutions/company-memory/module/module.yaml) | 0.2.0 | 9 | 6 |

Les trois Modules `*-memory` raccordent chacun un rôle à la mémoire autonome.
La routine quotidienne est composée dans les trois Agents métier. Les fonctions
RH, Commerce et les packs sectoriels ne sont pas livrés dans cette bibliothèque.
Le fichier [modules.json](modules.json) est l’inventaire vérifiable.

## Démarrer

1. Lire les [prérequis et l’installation](docs/INSTALLATION.md).
2. Composer les seuls Modules utiles, en preview puis avec `--write` après revue.
3. Vérifier et committer le projet consommateur, déployer par le rail Agent Spec
   natif, puis publier sa surface Application avec les droits appropriés.
4. Tester manuellement avec des données synthétiques avant tout usage réel.

Le téléchargement GitHub ne déploie rien. L’installation automatique par URL et
le rail Module Catalog ne sont pas qualifiés par ce dépôt. Un Module installé
ne crée ni personnes, ni droits, ni connexions par simple présence de fichiers.

## Vérifier hors ligne

Python 3.12+ et Node.js 22+ sont nécessaires. Aucune dépendance Python ou Node
supplémentaire, aucun secret et aucun One ne sont requis.

```sh
python3 scripts/check.py
python3 scripts/test.py
```

Les tests utilisent des copies temporaires ; aucun runtime n’est lancé ou
modifié. La CI applique les mêmes contrôles. Voir [tests](docs/TESTING.md),
[droits et isolation](docs/SECURITY.md), [mise à jour](docs/UPGRADING.md).

Les ressources des Modules proviennent d’un instantané de sources vérifiées.
Les adaptations de publication portent sur les guides, les tests autonomes et
la CI ; elles ne changent pas les Workflows ou MiniApps. Les preuves privées de
qualification, données réelles, clés, comptes et configurations restent exclus.
Une CI hors ligne verte ne prouve pas une qualification de votre One.

Logiciel propriétaire AgentMaurice. Voir [NOTICE](NOTICE).
