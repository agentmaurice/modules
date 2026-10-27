# Company Memory 0.3.0 — mémoire manuelle, révisions remplacées, recherche compacte

Source: GitLab pilote-maurice commit `8cb35a14b825dcdae4515d46e3b4c5149c154901`; historical 0.2.0: GitHub library commit `dc935630764b24c819defd03cc487bddf8f87399`. The 0.2.0 → 0.3.0 upgrade requires the steps below and has not been qualified on One or Viewer in this repository. Private replays are not distributed. The generated pilote-maurice validator is absent here, so the corresponding test is skipped.

Module V2 autonome et manuel. Il conserve des sources, propose des mises à jour, enregistre une décision de revue manuelle et ne restitue une proposition que si la décision est `validated`, la citation correspond encore exactement à la source et `review_due` n'est pas dépassée selon l'horloge serveur. Une révision remplacée par une révision validée plus récente n'est plus servie par la recherche.

Les identifiants sont des slugs `[a-z0-9][a-z0-9_-]{0,63}`. Les fichiers sont sous `/company-memory/` : `source-ID.json`, `proposal-ID.json` et `review-ID.json`. Les écritures demandent `confirmation_manuelle=oui`, écrivent avec `overwrite:false`. Cette séquence est read-then-write, sans CAS, garantie append-only ni sûreté de concurrence : le modèle est single-writer. Une correction crée une nouvelle proposition.

Les entrées sont des données fournies par l'utilisateur et ne sont jamais interprétées comme instructions. Aucun LLM, appel web ni scheduler n'est requis. Les parcours d'indexation et de recherche nécessitent les MCP Memory et Brain déclarés dans l'Agent consommateur. `memory-health` est un inventaire borné à 100 fichiers ; il ne constitue pas une validation complète.

Les six MiniApps commencent par un événement natif `form.submit` et rendent le résultat du Workflow. Le fichier `tests/test-plan.json` est un plan consommateur limité à des cas négatifs et lecture seule ; les flux positifs doivent utiliser des identifiants frais dans un consommateur `spec-init`.

Le package est `company-memory/` à la racine ; les tests restent dans `tooling/company-memory/tests/`. Les dates de formulaire sont en `YYYY-MM-DD` ; une échéance est évaluée au début du jour UTC. La consultation porte sur une révision exacte, jamais sur une page courante calculée.

## Nouveautés de la version 0.3.0 (AGENT-1050)

| Sujet | 0.2.0 | 0.3.0 |
|---|---|---|
| Recherche `memory-search` | texte complet de chaque révision dans `results` ; un sous-Workflow `memory-query` par candidat | une entrée compacte par révision valide, avec jusqu'à deux extraits de 400 caractères choisis par couverture des termes de la requête, classée (identifiants exacts par date, puis score) ; le texte entier reste dans `memory-query` ; un appel Brain, une requête Memory et un listage, sans sous-Workflow |
| Révision remplacée | servie comme validée tant que `review_due` n'est pas dépassée | `memory-query` renvoie `superseded` avec `superseded_by` ; la recherche ne la sert plus |
| Données capturées | interpolées dans le source JS (`{{ json .record }}`), refusées si elles contiennent `npm:nats` | transmises par `context` (liaisons `const` du sandbox), jamais dans `code` ; le texte est relu à l'identique |
| Brain | `brain.keyword` sans paramètre de format | `brain.keyword` avec `response_format: "concise"` ; dépendance à l'image Brain corrigée (AGENT-1049) |
| Identifiants d'action | `validate`, `write`, `revalidate`… répétés d'un Workflow à l'autre | uniques dans tout le module (préfixe du Workflow : `capture-validate`, `query-answer`, `revalidate-revision`…), vérifié par un test hors ligne ; un identifiant partagé pouvait être résolu dans la mauvaise définition (AGENT-1054) |
| Versions | module 0.2.0, Workflows en version 2 | module 0.3.0 ; `memory-search` 9, `memory-query` 7, `memory-index-revision` 8, `memory-review-update` 6, `memory-capture-source` 4, `memory-propose-update` 4, `memory-inspect` 4, `memory-health` 3, `memory-write-supersession` 2, `memory-read-supersession` 1 ; `memory-resolve-candidate` retiré ; MiniApp `memory-query-console` en version 4 |

### Données transmises par `context`

Chatserver évalue `context` avant le sandbox (`internal/recipes/mcp_executor.go`, branche `code_execution`) : une expression seule `{{ nom }}` garde le type de la valeur, une expression `{{ default "" .nom }}` donne `""` pour une clé absente. Le sandbox écrit le contexte en JSON (`context.json`, `internal/business/core/sandbox_service.go`) et lie chaque clé en `const` dans le module généré (`generateUserModule`). Le contrôle statique `natsClientImport` (`internal/business/core/sandbox_host_channel.go`) ne lit que `code` : un texte capturé qui contient `npm:nats`, des backticks, `${...}`, `{{ }}` ou du JavaScript passe donc sans être interprété.

Le comportement de la résolution a été vérifié sur le résolveur de chatserver (`template_utils.go`) : type conservé, texte restitué à l'identique, clé requise absente = échec fermé, `default` pour l'optionnel.

Les huit Workflows qui portent des étapes `code_execution`, toutes alimentées par `context` :

| Workflow | Version | Étapes `code_execution` |
|---|---|---|
| `memory-capture-source` | 4 | `capture-validate` |
| `memory-propose-update` | 4 | `propose-validate`, `propose-check-evidence`, `propose-check-absent` |
| `memory-review-update` | 6 | `review-validate`, `review-parse-proposal`, `review-check-evidence`, `review-check-absent`, `assemble`, `plan-supersession` |
| `memory-inspect` | 4 | `inspect-validate`, `inspect-parse-proposal`, `inspect` |
| `memory-query` | 7 | `query-validate`, `query-parse-proposal`, `find-marker`, `query-answer` |
| `memory-search` | 9 | `search-validate`, `candidates`, `build-revision-query`, `search-answer` |
| `memory-index-revision` | 8 | `index-validate`, `prepare`, `check-copy`, `finish` |
| `memory-health` | 3 | `health` |

## Workflows et MiniApps

| Workflow | Rôle |
|---|---|
| `memory-capture-source` | capture une source (texte, référence, date ISO) après confirmation |
| `memory-propose-update` | propose une révision, sa citation exacte et son échéance ; `previous_revision` optionnel |
| `memory-review-update` | enregistre une décision finale `validated`, `refused` ou `disputed` |
| `memory-inspect` | relit une proposition, sa source et la preuve avant décision |
| `memory-query` | consulte une révision exacte, avec statut, citation et lien de remplacement |
| `memory-search` | recherche BM25 bornée (dix résultats Brain), revalidation des candidats sur la copie Memory et les marqueurs natifs, réponse compacte avec extraits par couverture des termes |
| `memory-index-revision` | indexe une révision validée dans Memory puis dans Brain |
| `memory-health` | inventaire borné des fichiers `/company-memory` |

Les MiniApps (`memory-capture`, `memory-propose`, `memory-review`, `memory-query-console`, `memory-index-console`, `memory-search-console`) n'ont pas de logique propre ; `memory-query-console` affiche désormais « Remplacée par ».

## Formats de sortie

### `memory-search`

```json
{
  "status": "revalidated_revisions",
  "search_mode": "bm25",
  "results": [
    {
      "proposal_id": "rev-plafond-six",
      "title": "Plafond de chantiers simultanés",
      "date": "2026-10-21",
      "date_kind": "source",
      "source_ref": "company-memory-source:decision-2026-10-21",
      "review_due": "2099-01-01T00:00:00.000Z",
      "excerpts": [
        "Le plafond de chantiers simultanés est fixé à six … (400 caractères au plus)",
        "[…] La dérogation précise la durée … (400 caractères au plus) […]"
      ]
    }
  ],
  "summary": "rev-plafond-six | source 2026-10-21 | Plafond de chantiers simultanés | company-memory-source:decision-2026-10-21 | Le plafond … […] … [une ligne par révision]",
  "candidate_count": 2,
  "suppressed_count": 1,
  "excerpt_budget_chars": 8160,
  "warning": "bounded_search_excerpts_full_text_via_memory_query"
}
```

- **Chemin.** Un appel Brain (`brain.keyword`, dix résultats), une seule requête Memory (`memory.query` sur `v_entities` : révisions validées dont l'identifiant est un candidat ou dont `previous_revision` est un candidat, `maxRows` 60) et un listage de `/company-memory` (marqueurs `superseded-ID.json`), sans sous-Workflow. Les identifiants sont inlinés dans le SQL après contrôle du slug ; la liste ne contient jamais la chaîne vide. Sans candidat Brain, le moteur n'ayant pas d'étape conditionnelle, la requête Memory est une requête qui ne renvoie rien (`external_id IN ('')`, sans clause `previous_revision`, qui renverrait toutes les révisions sans prédécesseur) et la réponse est vide : zéro résultat, `candidate_count` 0, `suppressed_count` 0. Le texte vient de `name`, `review_due` de `expires_at`, `title`, `date` et `date_kind` des attributs `title`, `source_date` et `reviewed_at`, `source_ref` de l'attribut `source_ref`, que `memory-index-revision` écrit depuis 0.3.0 ; à défaut, de la première citation de `citations`, lue en tableau, en chaîne JSON de tableau ou en chaîne rendue à la Go `[référence]` (une seule citation, l'intérieur des crochets tel quel). Un paramètre d'outil qui référence un tableau seul est rendu en texte Go par chatserver (`ResolveTemplateMap`) : `citations` est donc écrit avec `{{ json .record.citations }}`.
- **Exclusions.** Un candidat sans ligne Memory validée, remplacé (ligne validée dont `previous_revision` vaut son identifiant, ou marqueur natif), ou dont l'échéance est dépassée ou illisible est exclu et compté dans `suppressed_count`. `rows: null` est un résultat vide ; une erreur d'outil, une forme inattendue ou `truncated: true` font échouer la recherche.
- **Révisions indexées avant ces attributs.** Le titre est dérivé de la référence de source (fragment entre le premier « # » et le dernier « @ », sinon l'identifiant) ; `date` est vide et `date_kind` vaut `inconnue`. Rejouer `memory-index-revision` rétablit titre et date.
- **Ordre.** D'abord les candidats `match_type: "exact_identifier"`, par date décroissante (date de la source, à défaut de la revue) : une correction récente précède la section qu'elle corrige. Ensuite les autres, par score décroissant.
- **Extraits.** Jusqu'à deux fenêtres de 400 caractères par révision, choisies pour couvrir le plus de termes distincts de la requête (mots de plus de deux lettres, accents et casse ignorés). Elles ne se chevauchent pas et sont présentées dans l'ordre du texte. Une fenêtre qui ne commence pas au début du texte est préfixée de « […] » ; une fenêtre qui s'arrête avant la fin est suivie de « […] ». Si aucun terme n'est trouvé, l'extrait est le début du texte.
- **Borne.** 10 résultats × 2 fenêtres × (400 caractères et deux marqueurs) = 8 160 caractères au plus par réponse (`excerpt_budget_chars`).
- **Champs.** Chaque ligne porte `proposal_id`, `title`, `date`, `date_kind`, `source_ref`, `review_due`, `match_type` (`exact_identifier` ou `other`), `excerpts`, et `superseded_by` seulement s'il existe (ne devrait pas apparaître après filtrage). Les champs textuels sont normalisés : toute suite de blancs, retours compris, devient une espace ; le titre est borné à 200 caractères, la référence de source à 300.
- **Résumé.** Une ligne par révision (une ligne garantie même si un champ contient des retours à la ligne) : identifiant, date, titre, référence de source, `remplacée par` si `superseded_by` existe, puis les extraits.
- **Texte entier.** Il reste dans `memory-query`, avec `proposal_id`.
- **Taille.** Exemple type (deux révisions retenues dont une de 1 400 caractères, une révision remplacée, requête « plafond chantiers ») : 1 932 octets en JSON compact, dont 987 caractères de résultats. Référence 0.2.0 sur un exemple voisin (deux révisions de 1 200 caractères, une remplacée) : 3 777 octets. Mesures hors One, par exécution du code de l'étape `answer`.
- **Choix d'extraits.** Un extrait de début de texte manque la preuve située au milieu d'un long texte. Mesure du laboratoire sur les 606 révisions du banc : preuve visible dans 29 % des cas avec le début, 85 % avec deux fenêtres de 260 caractères choisies par couverture, 91 % avec deux fenêtres de 400 caractères.

### `memory-query`

`status` vaut :

| Statut | Sens | `answer` |
|---|---|---|
| `validated` | révision valide, citation intacte, échéance non dépassée | texte de la révision |
| `superseded` | révision remplacée par une révision validée plus récente (`superseded_by`) | texte conservé pour consultation explicite |
| `successor_conflict` | deux révisions validées ou plus pointent vers cette révision | vide ; arbitrage manuel |
| `expired` | échéance de revue dépassée | vide |
| `refused`, `disputed` | décision de revue | vide |
| `evidence_changed` | la citation n'est plus dans la source | vide |
| `review_invalid`, `review_date_invalid` | revue ou échéance incohérente | vide |

Champs ajoutés en 0.3.0 : `title`, `source_date`, `reviewed_at`, `previous_revision` (vide si absent), `superseded_by` (vide si aucun), `successor_ids`. Une lecture sans revue reste une erreur de lecture native.

## Remplacement de révision

La vérité est native. Quand `memory-review-update` valide une révision Y dont `previous_revision` vaut X, il écrit **après** la revue validée de Y un marqueur natif `/company-memory/superseded-X.json` (`overwrite:false`), de contenu `{"superseded": X, "successor": Y, "reviewed_at": ...}`, si bien qu'un marqueur n'existe jamais sans revue validée de Y. Ce marqueur ne dépend pas de l'indexation de Y.

- `memory-review-update` refuse de valider Y (`successor_conflict`, avant toute écriture) si le marqueur de X existe déjà : une révision ne peut être remplacée qu'une fois. Une décision `refused` ou `disputed` n'écrit aucun marqueur.
- `memory-query` lit ce marqueur (listage de `/company-memory`, puis lecture seulement s'il existe, par le Workflow enfant `memory-read-supersession`) et l'unit aux successeurs trouvés dans Memory (`memory.query`, révisions validées dont `previous_revision` vaut X). Un successeur unique : statut `superseded` avec `superseded_by`, texte conservé. Plusieurs successeurs distincts : `successor_conflict`, sans réponse.
- `memory-search` ne sert que les révisions validées présentes dans Memory, sans successeur validé dans Memory ni marqueur natif, et dont l'échéance n'est pas dépassée : une révision remplacée est comptée dans `suppressed_count`. Un conflit de successeurs est traité comme un remplacement : la révision n'est pas servie.
- `memory-index-revision` refuse une révision qui n'est plus `validated`.
- L'écriture du marqueur `memory-write-supersession` (version 2) et la lecture `memory-read-supersession` (version 1) sont des Workflows enfants internes.

Pourquoi ce mécanisme : le fichier natif porte la décision au moment où elle est prise, avant toute indexation ; un écart d'indexation ne peut plus laisser X servie. Pour `memory-query`, la copie Memory reste une seconde source, lue pour compléter, comme avant. Pour `memory-search`, elle porte le texte servi, et le marqueur natif est relu (listage) à chaque recherche : un successeur validé mais pas encore indexé masque déjà X. Le marqueur est un fichier par révision remplacée, écrit une seule fois, ce qui rend le double remplacement détectable sans lire de contenu. Une recherche des successeurs dans tous les `proposal-*.json` serait non bornée.

Conséquences à connaître :

- Une successeur qui expire reste un remplacement : X n'est pas rétablie automatiquement.
- Deux successeurs distincts (marqueur et copie Memory) donnent `successor_conflict` : X n'est servie ni en réponse ni en recherche, jusqu'à arbitrage.
- Échec de l'écriture de la revue de Y : aucun marqueur n'est écrit, X reste servie. Échec du marqueur après la revue (exécution `failed`, revue de Y enregistrée et finale) : X reste servie jusqu'à l'indexation de Y, dont la ligne Memory `previous_revision` la remplace ; c'est le côté conservateur. Le marqueur manquant s'écrit à la main si besoin, et sans lui une seconde validation remplaçant X n'est pas refusée d'emblée : elle aboutit à `successor_conflict` une fois les deux successeurs indexés.
- Les révisions validées avant 0.3.0 n'ont pas de marqueur. Voir la migration.
- Les fichiers natifs ne reçoivent aucun statut `superseded` ; le statut est calculé à la consultation.

## Recherche Brain (dépendance)

`memory-search` appelle `brain.keyword` avec `tenant_id: company-memory`, `max_results: 10` et `response_format: "concise"`. Le paramètre et la forme concise (URI, identifiant de passage, score, extrait borné) viennent de la correction Brain AGENT-1049 ; **le module n'est pas utilisable avec une image Brain antérieure**. Le comportement exact d'une image qui ignore `response_format` n'est pas qualifié : la recherche doit échouer, jamais renvoyer un résultat vide silencieux, ce point figure dans le plan de requalification.

L'unique endroit qui lit la réponse Brain est l'étape `candidates` de `memory-search`. Elle lit l'URI de chaque résultat (champ `uri`), son `match_type` (valeur `exact_identifier` pour l'ordre des résultats) et son `score` (le meilleur par révision). Ces noms de champs sont à confirmer avec AGENT-1049 ; à défaut, `match_type` vaut `other` et `score` vaut 0. Elle échoue fermée : une réponse en forme détaillée (`document.file_path`, image Brain antérieure à la forme concise) renvoie l'erreur `brain_concise_unsupported`, sans repli silencieux ; des résultats sans aucune URI renvoient `invalid_brain_response`. Les extraits Brain ne servent jamais de réponse : le texte et la citation viennent de la copie Memory, écrite par `memory-index-revision` à partir d'une révision revalidée sur les fichiers natifs.

**À faire quand l'image Brain d'AGENT-1049 sera publiée** : épingler son digest dans l'Agent consommateur ; confirmer le nom du champ URI et l'absence de dépendance à `document.file_path` ; retirer le repli détaillé ; relancer le test `test_candidates_read_concise_uri_and_fail_closed` avec la forme figée ; exécuter les cas Brain du plan de requalification.

## Migration depuis 0.2.0

1. Déployer une image Brain corrigée (AGENT-1049) et l'épingler par digest dans l'Agent consommateur. Sans elle, `memory-search` échoue.
2. Composer en 0.3.0 avec `--update`. Sans cette option, le composeur refuse les fichiers 0.2.0 qui diffèrent, et n'écrit rien.

   ```bash
   python3 tooling/company-memory/compose.py --consumer-dir <consommateur> --agent-alias memory --update           # liste would_replace_files
   python3 tooling/company-memory/compose.py --consumer-dir <consommateur> --agent-alias memory --update --write   # remplace, liste replaced_files
   ```

   `--update` ne remplace que les fichiers possédés par le Module : les dix Workflows, les six MiniApps et `tests/test-plan.json`. Il ne supprime aucun fichier du consommateur, et ne touche pas aux identités ni aux connexions. `memory-resolve-candidate` est retiré du Module : le composeur le signale (`retired_files_present`) sans le supprimer ; retirer `workflows/memory-resolve-candidate.json` du consommateur à la main avant `spec check`, car il épingle une version de `memory-query` qui n'est plus livrée. `agent-spec.json` reçoit les `mcp_requirements` comme à chaque composition. Relire le diff du consommateur avant tout commit.
3. Vérifier puis déployer :

   ```bash
   maurice --config <config> spec check --dir <consommateur> --env integration_test --agent-alias memory --json
   maurice --config <config> spec deploy --dir <consommateur> --env integration_test --agent-alias memory --tests auto --json
   ```

   Vérifier que le service d'exécution charge bien la nouvelle définition (limite notée pour 0.2.0). Cette étape n'est pas qualifiée sur un One : elle figure dans le plan de requalification.
4. Les révisions déjà validées et indexées en 0.2.0 n'ont pas d'attribut `previous_revision`. Pour chaque révision qui en remplace une autre, rejouer `memory-index-revision` avec le même identifiant : l'indexation est idempotente sur `externalId` et `document_uri`. Sans ce rejeu, la révision remplacée reste servie.
5. Les fichiers natifs (`source-*`, `proposal-*`, `review-*`) gardent leur format : aucune migration de fichiers. Les révisions indexées avant l'ajout des attributs `title`, `source_date`, `reviewed_at` et `source_ref` restent servies avec un titre dérivé de la citation et une date `inconnue` ; rejouer `memory-index-revision` sur chacune les complète et réécrit `citations` en JSON.
6. Révisions validées avant 0.3.0 : leur `previous_revision` n'a pas été écrit en marqueur natif. Une révision Y validée en 0.2.0 et remplaçant X n'empêche donc X d'être servie qu'après indexation (étape 4). Pour fermer l'écart sans réindexer, écrire à la main `/company-memory/superseded-X.json` avec le contenu décrit ci-dessus, après contrôle de la revue de Y. Cette opération n'est pas qualifiée.
7. Les appelants de `memory-search` qui lisaient `results[].answer`, `results[].citations` ou `results[].excerpt` doivent lire `excerpts` (liste) et `source_ref`, puis appeler `memory-query` pour le texte complet.

## Vérification hors ligne

```bash
python3 -m unittest discover -s tooling/company-memory/tests -p 'test_*.py'
maurice module validate --file company-memory/module.yaml --json
maurice module test --file company-memory/module.yaml --json
```

- `tests/test_compose.py` : composition, conflits, provider MCP, `--update` (remplacement limité aux fichiers du Module, liste imprimée, rien écrit en cas de refus), signalement du Workflow retiré sans suppression.
- `tests/test_module_offline.py` : versions du manifeste, validation Agent Spec V2 des Workflows, MiniApps et plan de test (validateur généré `contracts/agent-authoring/v2/generated/python/validator.gen.py`) ; absence de `{{ }}` et de texte `npm:nats` dans les `code` ; contexte bindable ; requête Memory de remplacement ; fenêtres d'extraits (terme au milieu d'un long texte, deux termes distants, repli, accents), ordre des identifiants exacts par date, borne de taille ; requête Memory unique de la recherche (slugs inlinés, refus d'un identifiant hors slug, `rows: null`, `truncated`, attributs en objet ou en chaîne, remplacement par ligne et par marqueur, candidat absent, échéance, titre dérivé, attribut `source_ref`, `citations` en tableau, chaîne JSON ou chaîne Go) ; rendu texte Go des paramètres d'outil dans le faux moteur, comme `ResolveTemplateMap` ; unicité des identifiants d'action dans le module ; exécution des étapes `code` sous node (`tests/code_step_harness.mjs`, liaisons `const` comme le sandbox) ; enchaînement capture → proposition → revue → consultation → indexation → recherche sur des faux Memory et Brain, y compris remplacement, conflit, expiration, refus et cas négatifs.
- Les tests de code exigent `node` et les tests de contrat `jsonschema` ; sans eux, ils sont ignorés avec motif affiché.
- Les faux Memory et Brain vérifient la forme des requêtes (tenant, SQL, `response_format`) mais ne prouvent pas le comportement réel du One. La qualification réelle reste à faire.

## Qualification

- **0.2.0** : 33 cas runtime et six MiniApps Viewer réussis sur deux Agents dédiés (historique, backend `fe7e5970`). Le rejeu `tests/mcp-replay.py` (33 cas) et `tests/search-replay.py` ont été adaptés au format compact, mais ne sont pas réexécutés ici.
- **0.3.0** : non qualifiée sur un One. Le plan de requalification est `tests/requalification-plan.json` (commandes, cas à rejouer, cas nouveaux). Il n'a pas été exécuté.

## Épinglage des sidecars (0.3.0)

Les sidecars sont épinglés par digest dans le registre MCP de l'instance, pas dans le module : `mcp_requirements` ne porte qu'un nom de registre (`company_memory`, `brain`) et la plateforme prend l'entrée active de ce nom. Les fichiers de référence sont dans [`tests/registry/`](tests/registry/) :

| Fichier | Nom de registre | Version | Digest de l'image |
|---|---|---|---|
| `tests/registry/memory-1.1.0.json` | `company_memory` | 1.1.0 | `sha256:10ec6f7ebd498127137edf9007b06286b9395ef92a89dc5ffa9a6ec7fa3cae7f` |
| `tests/registry/brain-1.2.0.json` | `brain` | 1.2.0 | `sha256:fbdf0122fb6c4c043940588441c9df2af7a019ce97cdff4268fa468d7f2f848b` |

Les noms sont uniques dans le registre : une nouvelle version met à jour l'entrée existante (`PUT /api/v1/registry/entries/<nom>`), elle ne s'y ajoute pas. Les versions précédentes (memory 1.0.16, brain 1.1.7) sont documentées dans le dépôt pilote ; elles ne sont pas incluses ici. Après une mise à jour, le sidecar actif porte encore l'ancienne image : le plan signale `provider or image drift` jusqu'au retrait de ce sidecar (`DELETE /api/v1/mcp/servers/<id>`, qui conserve le volume de données) puis au redéploiement.

## Composition dans un autre consommateur

Prérequis : One joignable, Agent de test créé par `maurice test setup --fresh --save=false --json`, puis Agent Spec V2 initialisée avec cet identifiant. Utiliser explicitement le fichier de configuration du One visé pour toutes les commandes CLI. Un alias différent ne crée pas une nouvelle frontière de données : il faut un déploiement et un stockage effectivement isolés.

```bash
python3 tooling/company-memory/compose.py --consumer-dir /chemin/consommateur --agent-alias memory
python3 tooling/company-memory/compose.py --consumer-dir /chemin/consommateur --agent-alias memory --write
# Mise à jour d'une composition 0.2.0 : remplace seulement les fichiers du Module qui diffèrent
python3 tooling/company-memory/compose.py --consumer-dir /chemin/consommateur --agent-alias memory --update --write
maurice --config /chemin/config.yaml spec check --dir /chemin/consommateur --env local --agent-alias memory --json
# Relire et commiter les fichiers dans le consommateur avant deploy.
maurice --config /chemin/config.yaml spec deploy --dir /chemin/consommateur --env local --agent-alias memory --tests auto --json
```

Le composeur refuse d'écraser des fichiers différents, sauf avec `--update` (voir Migration). Les identités, politiques, connexions et locks restent dans le consommateur. Ce chemin compose les octets du Module dans l'Agent Spec ; il ne constitue pas une installation via Module Catalog. La qualification courante utilise un environnement `integration_test` et son autorisation native de plan. Une installation Catalog conserve son approbation spécifique ; ne pas contourner une demande d'approbation humaine.

**Prérequis d'isolation : un Agent et des sidecars/volumes dédiés par mémoire.** Le tenant fixe `company-memory` n'isole pas deux entreprises sur un sidecar partagé. Le composeur reporte `requires.mcp` dans `agent-spec.json.mcp_requirements`.

## Qualification plan availability

The [requalification plan](tests/requalification-plan.json) separates local
composition commands from historical runtime commands. The `mcp-replay.py`
and `search-replay.py` tools belong to the authorized canonical pilot checkout
and are not distributed in this library. Their paths are external source
references, not commands runnable from this repository. The owning session must
prepare an isolated One and the corresponding external tools before runtime
qualification; repository reorganization does not provide that qualification.

## Limites de cette version

- Pas de statut `superseded` écrit dans les fichiers natifs ; le statut est calculé à la consultation à partir de la copie Memory.
- Pas de tête de page courante, de résolution atomique d'une modification concurrente, ni de résolution automatique d'un conflit de successeurs.
- La confirmation manuelle est une déclaration d'intention, pas une preuve d'identité humaine ni une approbation d'architecture.
- `memory-health` liste au maximum 100 fichiers, sans synthèse des incohérences.
- Pas de recherche sémantique, d'ingestion automatique, de synthèse LLM, d'appel inter-Agents ni de permissions fines.
- L'isolation rejouée concerne deux déploiements distincts sur le provider filesystem d'un même One. Elle ne prouve pas le cloisonnement de deux entreprises, deux utilisateurs ou un bucket S3 partagé.
- Le contrôle de confirmation et le tenant restent dans les Workflows, pas dans un contrôle plateforme. Un tenant absent donne zéro résultat sans erreur côté Brain et Memory ; le Module le passe toujours explicitement.
