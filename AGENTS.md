# Company in a Box — instructions de contribution

Logiciel propriétaire. Rédiger en français ; termes techniques en anglais.
Ce dépôt contient uniquement des Modules AM réutilisables et leurs tests
synthétiques. Ne jamais ajouter configuration consommateur, secret, identité
runtime, donnée d’entreprise, sauvegarde ou preuve privée.

Préserver le format Agent Spec V2. Les Modules, Agents, Workflows et MiniApps
sont des objets distincts. Ne jamais changer un runtime depuis la CI. Les
plans et approbations natives restent dans le projet consommateur ; aucune
approbation humaine ne peut être donnée par un agent de code.

Avant publication : `python3 scripts/check.py`, `python3 scripts/test.py`,
`git diff --check` et scan de secrets. Ne pas désactiver un contrôle pour
masquer un échec. Préserver les versions et empreintes des ressources publiées.
