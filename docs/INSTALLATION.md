# Installer dans une autre entreprise

## Préparer le consommateur

Cloner le dépôt privé avec un compte autorisé :

```sh
git clone https://github.com/agentmaurice/company-in-a-box.git
cd company-in-a-box
git rev-parse HEAD
```

Conserver ce commit dans le dossier d’installation et utiliser cette même
révision pour toute la composition. Pour rejouer une qualification, utiliser
un clone propre, vérifier `git status --porcelain`, puis faire
`git checkout <COMMIT_QUALIFIE>` avant de composer. Conserver tout travail local
existant dans son checkout.

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
- Pour le raccordement mémoire : capacités inter-Agent et `allowed_agent_ids`
  natifs, identité humaine conservée par le runtime.

Cette liste exprime des capacités à vérifier, pas une promesse de compatibilité
avec toute ancienne version du One. Le contrôle `spec check` natif et la
vérification du déploiement restent obligatoires.

## Initialiser le premier administrateur

Cette étape utilise le **control plane natif** de l’organisation, avec une
connexion d’auteur habilitée (`orga-admin` pour ces routes). Le Module Administration ne crée pas de compte,
n’invite pas de personne et ne peut pas initialiser lui-même son premier admin.
`orga-admin` est un rôle de la plateforme ; `cib_admin` est un grant métier
du Module. Attribuer le second ne confère pas le premier. La confirmation
d’un formulaire ne remplace jamais une autorisation native.

1. Vérifier l’instance, l’organisation et l’identité de la connexion avec
   `maurice --config /chemin/config.yaml whoami --json`. Utiliser une
   configuration propre au nouveau One ; ne pas sélectionner le contexte global
   d’une autre entreprise. Ne pas exposer son bearer dans le terminal, Git ou une URL.
2. Avec ce client authentifié, lire `GET /api/v1/user/me`, puis
   `GET /api/v1/organization/<ORGANIZATION_ID>/directory`. Le premier retourne
   l’identité sous `user.id` ; le second retourne `people` et `grants`.
3. Si la personne active correspondant à cette identité possède déjà
   `cib_admin`, **ne rien écrire** : passer au contrôle ci-dessous. Si l’annuaire
   est non vide sans ce rattachement, arrêter le bootstrap automatique et faire
   examiner ses personnes et grants par l’admin habilité. Ne jamais remplacer
   l’annuaire existant par l’exemple qui suit.
4. Sur un **annuaire vide seulement**, un auteur habilité peut appliquer
   `PUT /api/v1/organization/<ORGANIZATION_ID>/directory` avec le document
   suivant, après avoir remplacé les placeholders par ses valeurs vérifiées :

```json
{
  "people": [{
    "person_id": "<PERSON_ID_LOCAL_CHOISI>",
    "display_name": "Administration locale",
    "platform_user_id": "<USER_ID_VERIFIE>",
    "status": "active"
  }],
  "grants": [{
    "person_id": "<PERSON_ID_LOCAL_CHOISI>",
    "role_key": "cib_admin"
  }]
}
```

Dans un One local, le principal d’auteur peut être `local-operator` : l’utiliser
uniquement si `/user/me` le confirme. Ne jamais y substituer l’identité d’un
humain pour exécuter ou approuver à sa place. Le PUT est un remplacement global,
sans CAS dans ce contrat : réserver une fenêtre d’administration sans auteur
concurrent, relire juste avant d’écrire et arrêter si l’annuaire n’est plus vide.
Conserver un snapshot privé et vérifier la réponse avant de poursuivre.

Après publication de la surface, exécuter `cib-admin-overview` avec l’admin
habilité, via la console Administration ou le point d’entrée natif suivant :

```text
POST /api/v1/organization/<ORGANIZATION_ID>/applications/<APPLICATION_ID>/workflows/cib-admin-overview/executions
{"input": {}, "timeout_seconds": 30}
```

Exiger HTTP 200, `state=completed`, puis vérifier dans `data.people` et
`data.grants` l’identité active liée et son rôle `cib_admin`. Une seconde
exécution de cette procédure doit être une lecture sans réécriture de l’annuaire.
Une clé sans compétence ou HTTP 401/403 ne constitue pas un bootstrap réussi.

Pour les humains, faire accepter l’accès à l’organisation par le parcours AM
natif, puis utiliser Administration pour rattacher les identités existantes à
leurs personnes et à l’Application : `directory_upsert_person`,
`directory_link_user`, `application_people_add` et `directory_grant_role`.
Vérifier les accès depuis Home avec les comptes réels prévus. Ne pas attribuer
un rôle administrateur global aux comptes de test pour contourner un refus.
Les rôles de service restent distincts des ACL de chaque fiche.

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

## Attendre Memory et Brain sans modifier leurs données

Installer les connecteurs existants dans le Registry du **nouveau One** et
provisionner des sidecars avec des volumes persistants propres à l’entreprise,
par les plans natifs applicables. Conserver tags et digests d’images dans le
dossier privé d’installation ; ne pas réutiliser une base ou un volume client.
Le manuel Aurore du 19 octobre 2026 a utilisé Memory 1.0.17 et Brain 1.1.8 ;
ces versions observées ne garantissent pas la compatibilité de toute version AM.

Découvrir le catalogue avec les identifiants réels du consommateur :

```sh
maurice --config /chemin/config.yaml tools list --organization <ORGANIZATION_ID> --deployment <MEMORY_AGENT_ID> --json
```

Vérifier les outils déclarés dans le manifest du Module :
`memory.entities.upsert`, `memory.query`, `brain.document.upsert` et
`brain.keyword`. Le catalogue CLI retourne leur nom métier sous `display_name`
et le nom d’appel sous `name` ; vérifier aussi `mcp_server_id` et
`availability=available`. Ne pas copier un suffixe de nom d’outil d’un autre One.
Respecter la pagination de la CLI si l’inventaire est tronqué.

Lorsque le Registry est provisionné par le premier `spec deploy`, il est normal
que ce contrôle ne soit possible qu’après ce provisionnement ; un catalogue
vide avant déploiement n’autorise pas à annoncer la mémoire opérationnelle.

Si le catalogue expose aussi `memory.health` et `brain.health`, utiliser ces
diagnostics facultatifs en appelant les **noms retournés** :

```sh
maurice --config /chemin/config.yaml tools call <MEMORY_HEALTH_CALL_NAME> --organization <ORGANIZATION_ID> --deployment <MEMORY_AGENT_ID> --timeout 15 --json
maurice --config /chemin/config.yaml tools call <BRAIN_HEALTH_CALL_NAME> --organization <ORGANIZATION_ID> --deployment <MEMORY_AGENT_ID> --timeout 15 --json
```

Pour chaque health exposé, exiger une réponse native sans erreur, `status=ok`
et `result.status=ok`. L’absence d’un health non déclaré par le manifest ne
bloque pas à elle seule l’installation : la noter, puis tester le parcours
mémoire effectif. `memory-health` du Module est un inventaire de fichiers : il ne
remplace pas `memory.health`. La version renvoyée par un health peut être une
chaîne ancienne ; vérifier l’image réellement déployée par son digest.

**Attente bornée :** pendant au plus cinq minutes, relire le catalogue et refaire
seulement ces appels de lecture si les outils sont encore absents, marqués
`not ready`, ou en cas de timeout de préparation du catalogue ou de transport
MCP au démarrage. Attendre
dix secondes entre essais ; borner chaque requête HTTP à quinze secondes
côté client et ne pas démarrer un appel au-delà de la durée restante. Le
`--timeout` de `tools call` borne l’exécution demandée ; la CLI peut attendre
plus longtemps pour la préparation/HTTP. La borne globale de 300 secondes et celle de 15 secondes par requête
nécessitent donc un client HTTP ainsi borné ou un superviseur externe de la CLI.
Conserver heure, résultat et cause de chaque essai dans les preuves privées.
Les routes équivalentes sont `GET /api/v1/organization/<ORGANIZATION_ID>/deployment/<MEMORY_AGENT_ID>/tools?format=verbose`
et `POST /api/v1/organization/<ORGANIZATION_ID>/deployment/<MEMORY_AGENT_ID>/tools/call` ;
pour ce dernier, envoyer `{"tool_name":"<CALL_NAME>","arguments":{},"timeout_sec":15}`.
Ne transmettre ce bearer qu’à l’instance vérifiée, par le client authentifié ;
ne pas l’afficher ni le stocker dans les preuves.
Arrêter sur expiration, identité/instance incohérente, HTTP 401/403, refus
d’approbation ou erreur métier ; ne pas traiter ces erreurs comme une attente MCP.
Ne pas rejouer automatiquement une écriture, une indexation ou un déploiement.

Le `/ready` du One, un heartbeat MQTT et les health ne suffisent pas : le
catalogue peut encore être en synchronisation. Après déploiement et publication,
qualifier également le **parcours mémoire complet** ci-dessous.

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
Si la vérification échoue parce que les outils MCP ne sont pas prêts, conserver
le plan et ses diagnostics, vérifier le rollback natif et l’état réellement
restant, puis terminer l’attente bornée. Si le rollback est confirmé sans dérive,
l’opérateur peut décider explicitement de relancer le déploiement depuis les
mêmes sources committées et relire le nouveau plan, **hors de la boucle
readiness** ; appliquer une nouvelle approbation si le nouveau plan l’exige. Ne pas réutiliser une approbation attachée à un ancien plan ni
réinitialiser les volumes ; arrêter sur rollback incomplet ou état inconnu.

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


## Valider la mémoire après installation ou redémarrage

Depuis Home, avec les comptes de chaque service :

1. Créer une fiche synthétique propre à cette entreprise, proposer un extrait
   explicitement partageable à la mémoire, puis faire sa revue et son indexation
   manuellement avec le rôle habilité. Garder l’identifiant exact de la révision.
   Si ce jeu existe déjà, le réutiliser en lecture ; ne pas le réindexer à chaque essai.
2. Pour Veille, Contenu et Accompagnement, exécuter leurs requêtes mémoire et
   leurs recherches, via les MiniApps du bon Agent. Exiger une révision
   `validated`, non périmée et citée, puis que la recherche retourne cette
   révision attendue. Une recherche vide ne prouve pas la récupération du jeu.
3. Pour un client HTTP authentifié autorisé sur la surface publiée, les lectures
   équivalentes utilisent le contrat suivant :

```text
POST /api/v1/organization/<ORGANIZATION_ID>/applications/<APPLICATION_ID>/workflows/<WORKFLOW_ID>/executions
{"input": {"proposal_id": "<REVISION_SYNTHETIQUE_VALIDEE>"}, "timeout_seconds": 15}
```

Pour les trois rôles, remplacer `<WORKFLOW_ID>` par `veille-memory-query`,
`contenu-memory-query` ou `accompagnement-memory-query`. Exiger HTTP 200,
`state=completed`, `data.status=validated` et des `data.citations` non vides.
Pour `veille-memory-search`, `contenu-memory-search` ou
`accompagnement-memory-search`, envoyer `input: {"query": "<MOT_CLE_DU_JEU>"}`
et vérifier la présence de la révision attendue dans `data.results`.
Répéter seulement ces lectures lors d’un `mcp servers not ready`, dans la même
borne de cinq minutes que le catalogue et les health. Une erreur métier ou un
refus de droits arrête l’essai. Ne jamais élargir un rôle pour obtenir un vert.

En cas de redémarrage de qualification, capturer les données et ACL avant,
redémarrer **seulement ce One** par ses commandes natives et son `--data-dir`
explicite, puis refaire ces lectures et l’accès depuis Home. Vérifier que les
révocations subsistent, que les données sont conservées et que les volumes
restent distincts des autres entreprises. Un démarrage du One ne prouve pas la
reconnexion effective des deux MCP.

Les IDs `daily-context`, `daily-time-save` et `daily-report` existent sur trois
Agents : les qualifier via leurs MiniApps contextualisées par Agent, sans
lookup global par le seul ID de Workflow ni filtre API inventé.

L’essai manuel Aurore a vérifié le bootstrap initial, puis sa réutilisation sans
réécriture de l’annuaire et les lectures mémoire des trois rôles après attente.
Le dossier consommateur conserve les preuves privées ; aucune identité réelle,
session, donnée d’entreprise ou capture n’est fournie dans ce dépôt. Cette
procédure ne qualifie pas une installation automatique par URL/Module Catalog,
une nouvelle approbation humaine réelle, ni des effets métier externes.
