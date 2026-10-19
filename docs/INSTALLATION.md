# Installer dans une autre entreprise

## Préparer le consommateur

Cloner le dépôt privé avec un compte autorisé :

```sh
git clone https://github.com/agentmaurice/company-in-a-box.git
cd company-in-a-box
```

Il faut un One opérationnel, son MauriceCLI compatible Agent Spec V2 et un
projet consommateur séparé. Ce dépôt ne contient ni binaire One ni configuration
d’authentification. Utiliser les commandes de connexion et d’initialisation
retournées par votre instance, avec ses identifiants réels ; ne pas inventer
les identifiants ni copier ceux d’un autre environnement.

Le profil complet utilise quatre Agents initialisés dans ce projet :
`veille`, `contenu`, `accompagnement` et `memory`. Un Module autonome peut être
composé seulement dans l’Agent dont il a besoin. Le consommateur doit disposer
de `agentmaurice.project.json`, ses environnements et ses Agent Specs V2.
La configuration CLI reste à l’extérieur de ce dépôt.

## Compatibilité à contrôler

- Workflows V2, MiniApps/forms et `code_execution` disponibles.
- Pour les rôles, dossiers, Marketing et administration des fiches : broker
  humain `recipe--application_data_v1`, ACL par donnée et révisions CAS natives.
- Pour l’administration : `recipe--company_admin_v1`, annuaire et rôles natifs.
- Pour la mémoire : stockage persistant, Agent et sidecars dédiés par entreprise,
  outils Memory/Brain déclarés dans le manifest et disponibles au déploiement.
- Pour le raccordement mémoire : capacités inter-Agent et `allowed_callers`
  natifs, identité humaine conservée par le runtime.

Cette liste exprime des capacités à vérifier, pas une promesse de compatibilité
avec toute ancienne version du One. Le contrôle `spec check` natif et la
vérification du déploiement restent obligatoires.

## Composer en preview puis écrire après revue

Exécuter depuis la racine de ce dépôt. Remplacer `/chemin/consommateur` par le
projet de votre entreprise. Chaque commande est une preview sans écriture ;
relire le résultat puis relancer avec `--write` pour composer les fichiers.

```sh
# Les trois rôles
python3 solutions/company-in-a-box/template/compose.py --consumer-dir /chemin/consommateur
# Mémoire autonome
python3 solutions/company-memory/compose.py --consumer-dir /chemin/consommateur --agent-alias memory
# Liaison des rôles à la mémoire, après composition des quatre Agents
python3 solutions/company-in-a-box/memory-integration/compose.py --consumer-dir /chemin/consommateur
# Routine quotidienne, après les liaisons mémoire
python3 solutions/company-in-a-box/daily-routine/compose.py --consumer-dir /chemin/consommateur
# Services optionnels sur l’Agent Veille existant
python3 solutions/company-in-a-box/common-dossier/compose.py --consumer-dir /chemin/consommateur --owner-alias veille
python3 solutions/company-in-a-box/enterprise-admin/compose.py --consumer-dir /chemin/consommateur --owner-alias veille
python3 solutions/company-in-a-box/marketing-launch/compose.py --consumer-dir /chemin/consommateur --agent-alias veille
```

Une divergence inconnue provoque un refus ; conserver les modifications locales
et résoudre le conflit avant d’écrire. Aucun composeur ne déploie à votre place.
Relire les guides de chaque Module, notamment les limites mémoire.

## Vérifier et déployer par le contrat natif

Après composition, vérifier et committer les fichiers dans le consommateur.
Pour chaque Agent concerné, avec la configuration de votre instance :

```sh
maurice --config /chemin/config.yaml spec check --dir /chemin/consommateur --env local --agent-alias memory --json
# Revue, git diff et commit dans le consommateur avant déploiement.
maurice --config /chemin/config.yaml spec deploy --dir /chemin/consommateur --env local --agent-alias memory --tests auto --json
```

Déployer mémoire, puis veille, contenu et accompagnement en changeant
`--agent-alias`. Vérifier le résultat et committer le lock après chaque Agent.
Si AM demande une approbation, la personne compétente décide dans AM ; aucune
commande ou clé de service ne doit la remplacer.

## Publier la surface et les accès

Déployer les ressources et les rendre accessibles sont deux étapes distinctes.
Récupérer la surface récente de l’Application avec les commandes `maurice app`
de votre CLI. Ajouter uniquement les nouvelles ressources, aux versions natives
retournées par le déploiement, en conservant les ressources et entrypoints
existants. Ne pas confondre version déclarée et version runtime.

`template/surface.example.json` est un exemple documentaire à placeholders,
**pas un fichier prêt à appliquer**. `memory-integration/surface.py` et
`enterprise-admin/service_roles.py` préparent des brouillons selon leur `--help`.
Le Marketing fournit `service-gates.json` pour ses neuf Workflows.

Le fichier relu doit contenir `public_surface` et les entrypoints conservés :

```sh
maurice --config /chemin/config.yaml app surface set <APPLICATION_ID> --organization <ORGANIZATION_ID> --file /chemin/surface-relue.json --json
maurice --config /chemin/config.yaml app surface publish <APPLICATION_ID> --organization <ORGANIZATION_ID> --bump minor --json
```

Relier les personnes existantes aux services appropriés. Marketing utilise
`cib_marketing`, Accompagnement `cib_service_client`, Dossiers `cib_dossiers`,
Direction `cib_direction`, administration `cib_admin`. Aucun rôle ne donne
implicitement accès à une fiche privée : partager cette fiche explicitement.

Depuis Home, ouvrir l’Application avec les comptes prévus, tester un parcours
synthétique, les refus, le partage unitaire et son retrait. Un appel par clé
machine refusé ne constitue pas une qualification des parcours humains.
Aucun envoi, publication, paiement ou campagne réelle ne découle du clonage.
