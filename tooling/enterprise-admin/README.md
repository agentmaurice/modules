# Administration — cib-enterprise-admin 0.2.2

Module de consultation et administration bornée des personnes, identités
existantes, accès par service et révocations de mandats. Il réutilise
`recipe--company_admin_v1` et `recipe--application_data_v1` avec l’identité
humaine résolue côté serveur, jamais une identité fournie par le formulaire.

```sh
python3 tooling/enterprise-admin/compose.py --consumer-dir /chemin/consommateur --owner-alias veille
python3 tooling/enterprise-admin/compose.py --consumer-dir /chemin/consommateur --owner-alias veille --write
```

La route humaine Application et les brokers natifs sont des prérequis.
Les profils `cib_admin`, `cib_marketing`, `cib_service_client`, `cib_direction`
et `cib_dossiers` doivent être reliés aux personnes existantes et aux gates
`required_role`. `service_roles.py` prépare un brouillon de surface ; il ne
l’applique pas et refuse une permission existante divergente.

Le Module ne crée pas de compte, n’envoie aucune invitation et ne signe aucun
mandat. Les changements sont explicites et demandent confirmation. La
confirmation de formulaire ne remplace ni l’IAM ni une approbation native.
`cib-admin-approval-check` est une lecture locale avec `require_approval` ; seule
la personne compétente peut l’autoriser dans AM.

Les opérations sur une fiche historique sont unitaires : namespace, clé et
révision connus ; aucune liste universelle de corps privés, aucun transfert
ni partage en masse. `admin_recovery` reste limité au partage et est revalidé
par le serveur. Les 0.2.1 connues peuvent être remplacées par empreinte exacte ;
toute autre divergence est un conflit manuel. Les fiches héritées restent
privées sous leur dépositaire tant qu’un partage explicite n’est pas décidé.

Voir [installation](../../docs/INSTALLATION.md),
[droits](../../docs/SECURITY.md) et [tests](../../docs/TESTING.md).
