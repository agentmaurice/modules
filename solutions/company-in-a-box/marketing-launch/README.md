# Module Marketing de lancement

Ce répertoire fournit un composeur portable pour un Module multiressources,
propriété d'un seul Agent `veille`. Il compose le parcours manuel
`campagne → contenu → demande d'essai → accompagnement → premier résultat
confirmé` dans un Agent Spec V2 déjà initialisé.

Le composeur est `compose.py`. Il exige `--consumer-dir` et `--agent-alias`,
valide `agents/<alias>/agent-spec.json`, puis lit strictement les quinze
ressources réelles de `module/agents/main/` et `module/test-plan.json`.
Ressource manquante, ressource inattendue ou ID incohérent : échec avant toute
écriture. Il ne fabrique aucun Workflow, MiniApp ou test. Le générateur `build.py`
produit des octets déterministes, indépendants de la graine de hachage Python.

Le composeur conserve les autres ressources, spécifications, dépendances et
cas de test. Le mode par défaut est une preview sans écriture ; utiliser
`--write` après revue pour copier les ressources. Il ne lance ni MauriceCLI,
ni One, ni déploiement, ni procédure de cycle.

```sh
python3 solutions/company-in-a-box/marketing-launch/compose.py \
  --consumer-dir /chemin/vers/company-in-a-box \
  --agent-alias veille

python3 solutions/company-in-a-box/marketing-launch/compose.py \
  --consumer-dir /chemin/vers/company-in-a-box \
  --agent-alias veille --write
```

Les neuf Workflows composés sont :
`cib-launch-campaign-save`, `cib-launch-content-link`,
`cib-launch-request`, `cib-launch-progress`, `cib-launch-read`,
`cib-launch-list`, `cib-launch-people`, `cib-launch-share` et
`cib-launch-summary`. Les six MiniApps sont les consoles `campaign`,
`content`, `request`, `support`, `sharing` et `direction`.

Le stockage utilise la partition native `cib-launch-marketing` du broker
`application_data_v1`. Elle ne crée aucune base de données. Les données sont
privées par défaut ; une fiche peut être partagée explicitement avec les
opérations ACL natives et une révision attendue. La liste `people` ne donne
aucun droit. Le Module reste manuel : aucun scheduler, publication, envoi,
LLM, CRM ou mémoire d'entreprise.

Le profil consommateur doit fournir les rôles `cib_marketing`,
`cib_service_client`, `cib_dossiers` et `cib_direction`. Le propriétaire
minimal reste `veille`; les contenus et accompagnements restent liés par
référence aux briques existantes. Une campagne peut référencer plusieurs
demandes d'essai et un contenu. Un premier résultat est une attestation
interne contenant une preuve et une date ; le Module n'invente ni résultat
réel ni qualification externe.

Le composeur fusionne quatre cas techniques dans le test plan consommateur,
avec des identifiants stables et sans écraser les cas existants. Ces cas
vérifient le refus d'une identité machine pour les opérations de lancement.
Toute collision d'identifiant ou divergence d'octets arrête la composition.

## Mode opérateur depuis Home

Ce parcours est prévu pour un usage manuel, avec les profils
`cib_marketing`, `cib_service_client`, `cib_dossiers` et `cib_direction`.
Depuis Home, ouvrez les six consoles suivantes. Les titres sont ceux à
rechercher :

| Console | Titre Home | Usage |
| --- | --- | --- |
| `campaign` | **Marketing — campagne** | créer et relire le brief de campagne |
| `content` | **Marketing — lier les preuves et le contenu** | lier les fiches Veille et Contenu |
| `request` | **Marketing — demande d’essai** | enregistrer une demande d’essai |
| `support` | **Accompagnement — progression de l’essai** | suivre l’accompagnement et attester un résultat |
| `sharing` | **Marketing — partager ou retirer un accès** | gérer l’ACL d’une fiche |
| `direction` | **Direction — lancement et premiers résultats** | lire les fiches accessibles |

### 1. Créer la campagne

Depuis Home, ouvrez d’abord l’Application Company in a Box, puis la console.
Dans **Marketing — campagne**, choisissez **Travail réel** (`usage`) pour
un dossier réel ou **Essais synthétiques** (`qualification`) pour un test.
Donnez un `campaign_id` stable. À la création,
`expected_revision` vaut `0`. Renseignez le brief, l’audience, la promesse,
le canal, le responsable, l’échéance et le critère de fin, puis confirmez
manuellement. Une campagne peut être reliée à un contenu et à plusieurs
demandes d’essai. Après une modification du brief, relisez la fiche et
réutilisez la révision renvoyée avant toute nouvelle liaison.

### 2. Lier les sources et le contenu

Préparez d’abord les fiches dans les rôles existants **Veille** et
**Contenu**. Dans **Marketing — lier les preuves et le contenu**, saisissez
la campagne et sa révision exacte, puis les deux identifiants et leurs révisions :
`veille_ref`, `veille_revision`, `contenu_ref`, `contenu_revision`, ainsi que
`preuve_ref`. Les révisions sont celles renvoyées par la sauvegarde ou la
lecture de chaque fiche source. Confirmez la revue manuelle. Cette étape ne
publie rien et ne copie pas les fiches sources.

### 3. Enregistrer une demande d’essai

Dans **Marketing — demande d’essai**, sélectionnez la campagne prête et sa
`campaign_revision`. Donnez à la demande un `trial_id` stable, renseignez
`personne_ref` (référence interne, sans constituer une liste de contacts), le
besoin et l’objectif, puis confirmez manuellement. Le rejeu des mêmes données
avec le même `trial_id` est dédupliqué ; un nouvel identifiant représente une
nouvelle demande. Conservez cet identifiant exact pour les étapes de partage et
d’accompagnement.

### 4. Partager la fiche d’essai puis accompagner

Dans **Marketing — partager ou retirer un accès**, sélectionnez la fiche de
l’essai, chargez les membres, ouvrez le formulaire de la personne concernée
et choisissez la permission `write`. Utilisez la révision exacte de la fiche
d’essai, confirmez manuellement, puis relisez la fiche et conservez la nouvelle
révision renvoyée. Le partage concerne cette fiche uniquement ; il ne donne pas le
droit d’utiliser un service ni de gérer les partages.

Dans **Accompagnement — progression de l’essai**, sélectionnez l’essai et utilisez
la révision relue après le partage. Référencez la fiche existante du rôle
Accompagnement avec `accompagnement_ref` et son
`accompagnement_revision`. Passez d’abord l’essai **En cours** et enregistrez.
La fiche Accompagnement doit contenir le résultat observé, sa `preuve_ref`,
la prochaine étape, aucun blocage et la confirmation manuelle. Ensuite, dans
la console de progression, choisissez `premier_resultat_confirme`, indiquez
`date_confirmation` au format `AAAA-MM-JJ` et `confirmation_resultat` à `oui`,
puis confirmez l’opération. Les confirmations sont remises à « Non » après
chaque enregistrement ; la révision courante est préremplie. La preuve et la
date doivent venir d’une observation interne ;
aucun résultat réel, vente ou conversion ne doit être inventé.

### 5. Lire la synthèse

Dans **Direction — lancement et premiers résultats**, la synthèse porte
uniquement sur les fiches auxquelles le profil courant a accès. Les demandes
et les attestations de premier résultat restent distinctes. La console ne
calcule pas automatiquement une conversion, une attribution ou un gain de
temps.

Les fiches restent privées par défaut. `people` sert seulement à connaître
les membres partageables ; l’autorisation n’existe qu’après un partage ACL
explicite. Les références Veille, Contenu et Accompagnement pointent vers
leurs fiches natives et leurs révisions ; aucune mémoire n’est ajoutée ou
reliée automatiquement. Le Module n’envoie rien, ne publie rien, n’appelle
aucun CRM et ne transforme pas automatiquement une demande en conversion.

Les tests distribués sont synthétiques et hors ligne. Ils ne prouvent aucun
résultat client réel et ne remplacent pas la qualification sur votre One.
Voir [installation](../../../docs/INSTALLATION.md),
[droits](../../../docs/SECURITY.md) et [tests](../../../docs/TESTING.md).

## Installation dans un profil CIB existant

Après composition et commit des sources, utiliser le rail Agent Spec natif
`spec check`, puis `spec deploy` et sa vérification. Ajouter les neuf Workflows
et six MiniApps à la surface de l’Application, avec leurs versions natives
réellement vérifiées. `service-gates.json` définit les rôles requis ; conserver
les rôles, membres et ressources déjà présents. Publier cette surface est une
étape distincte du déploiement des ressources. Le composeur ne la réalise pas.

Les trois Workflows de rôle `veille-save`, `contenu-save`,
`accompagnement-save` et leurs espaces natifs sont des prérequis du profil.
Le Module ne configure pas les personnes et n’accorde aucun droit au déploiement.
Pour une autre entreprise, réutiliser les mêmes ressources ; seuls les liens du
profil consommateur, les membres existants et les données changent.
