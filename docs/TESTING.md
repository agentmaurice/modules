# Tests distribués

Depuis la racine :

```sh
python3 scripts/check.py
python3 scripts/test.py
git diff --check
```

`check.py` vérifie l’inventaire, les manifests, les ressources, les liens locaux
et les fichiers interdits. `test.py` exécute sept suites unittest, un contrat
ACL Python et cinq scripts Node, dans une copie temporaire des sources.
Les tests portent sur la composition, la conservation de fichiers étrangers,
les conflits, les règles métier, les contrôles ACL déclarés, la publication
sélective vers la mémoire, les mesures et les Workflows générés.

Tous les exemples sont synthétiques. Aucun test ne contacte un One, n’appelle
un modèle ou un service externe, ni ne publie un contenu ou une campagne.
Les replays privés du pilote ne sont pas distribués. Un ancien test de version
a été aligné sur le manifest Dossiers ; les tests Administration utilisent une
fixture de ressource antérieure avec empreinte exacte, sans lire l’historique
Git du dépôt d’origine. Les assertions de refus sont conservées.

Ces contrôles ne prouvent pas la compatibilité de votre binaire One, les droits
réels de vos comptes ou un résultat client. Après installation, qualifier vos
parcours manuels et révocations dans un environnement séparé, avec des données
fictives et les politiques d’approbation natives.
