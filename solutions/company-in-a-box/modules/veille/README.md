# Veille manuelle

Import explicite de sources et faits fournis, affectation manuelle et contrôle des champs/date (30 jours). Aucun accès web ni jugement de modèle. Le champ suffisant ne prouve pas la véracité des faits. Dossiers dans le stockage privé de l’Agent. Répertoire fixe, identifiant borné, confirmation explicite.

## Contrat de partage des fiches

Les MiniApps des rôles `veille`, `contenu` et `accompagnement` soumettent le
formulaire de partage avec les champs fermés `share_dossier_id`,
`share_expected_revision`, `share_subject_user_id`, `share_permission` et
`share_confirmation_manuelle`, auxquels s’ajoute `selection_dossier_id` pour
lier la sélection des membres à la fiche relue. Les valeurs de permission
sont `read`, `write` et `none` (`none` retire l’accès). Les cinq champs
`share_*` restent obligatoires et la confirmation revient à `non` après une
opération réussie. Un appel natif au workflow `*-share` doit adapter ses
paramètres canoniques vers ces champs formels ; le workflow ne lit pas les
clés canoniques directement.
