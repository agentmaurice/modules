# Routine quotidienne — cib-daily-routine 0.1.0

Module composé dans chacun des trois rôles. Il prépare le contexte du jour,
consulte une révision mémoire choisie, relit une fiche et enregistre le temps
actif déclaré. Le temps humain, l’attente machine et l’assistance restent
séparés. Aucun gain n’est calculé sans référence comparable.

```sh
python3 tooling/daily-routine/compose.py --consumer-dir /chemin/consommateur
python3 tooling/daily-routine/compose.py --consumer-dir /chemin/consommateur --write
```

Les ressources `<role>-read` et `company-memory-query` doivent déjà exister dans
chaque rôle : composer le socle, la mémoire et leur intégration avant la routine.
Le composeur préserve les autres fichiers et refuse une divergence inconnue.
Le propriétaire du stockage natif, les accès aux relevés et la surface publiée
restent à configurer dans le consommateur ; la présence d’un formulaire ne crée
aucun droit. Ne pas présenter les fichiers de mesure comme un registre multi-
rédacteurs doté d’ACL par ligne ou d’une synchronisation transactionnelle.

Depuis Home, ouvrir l’Application puis les consoles `daily-context-console`,
`daily-report-console` et `daily-time-console` du rôle autorisé. Consigner une
durée observée et les difficultés ; une durée absente reste non renseignée.
Le Module ne planifie aucune tâche et ne produit aucun effet métier externe.
Voir [installation](../../docs/INSTALLATION.md) et
[tests](../../docs/TESTING.md).
