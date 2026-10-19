# Dossiers et Direction — cib-work-dossiers 0.2.2

Module de dossier commun : objectif, responsable opérationnel, références,
prochaine action, blocage et preuve de clôture interne. La Direction reçoit
uniquement les fiches accessibles à la personne authentifiée.

```sh
python3 solutions/company-in-a-box/common-dossier/compose.py --consumer-dir /chemin/consommateur --owner-alias veille
python3 solutions/company-in-a-box/common-dossier/compose.py --consumer-dir /chemin/consommateur --owner-alias veille --write
```

L’Agent propriétaire doit être initialisé. Le serveur doit fournir le broker
humain `recipe--application_data_v1`, les ACL par fiche et le CAS de révision.
Les données sont dans la partition native `cib-cases`, privées par défaut.
Les jeux `usage` et `qualification` séparent travail réel et données fictives.

La sélection relit la fiche et préremplit le formulaire ; l’écriture utilise
la révision attendue. Le propriétaire peut partager une fiche en lecture ou
modification avec un membre existant, puis retirer ce droit. Le rédacteur ne
peut pas repartager. Les titres et responsables déclarés ne donnent aucun
droit. La clôture interne exige une preuve et une revue ; elle n’atteste pas
une livraison ou un engagement externe.

Le composeur refuse les divergences inconnues. Voir [installation](../../../docs/INSTALLATION.md),
[droits](../../../docs/SECURITY.md) et [tests](../../../docs/TESTING.md).
