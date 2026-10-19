# Données, droits et isolation

Le dépôt publie du code et des exemples fictifs. Secrets, configurations,
identités runtime, bases, sauvegardes, cookies, jetons et pièces métier restent
hors Git. Le scan statique et le scan de secrets complètent la revue humaine ;
ils ne garantissent pas l’absence de toute information confidentielle.

Les rôles de service, l’appartenance à l’Application et les ACL par fiche sont
distincts. L’identité est dérivée côté serveur. Une valeur de formulaire,
un intitulé de rôle ou une confirmation ne crée aucun droit. Un rédacteur
ne devient pas gestionnaire des partages. Tester après révocation avec une
session encore valide ; une erreur de session expirée ne prouve pas le retrait.

Les 3 rôles, dossiers et Marketing réutilisent les ACL natives. La mémoire
commune et les fichiers de mesure ont leurs propres limites : ne pas annoncer
une ACL individuelle uniforme sur toutes les ressources. La mémoire exige un
Agent et des sidecars/volumes dédiés par entreprise. Sa confirmation est une
intention de partage ; elle ne remplace pas la validation d’identité du runtime.

La révocation d’un dossier ne retire pas un extrait précédemment partagé
intentionnellement à la mémoire commune. Suivre le cycle de revue de la mémoire
pour son retrait ; aucun apport de dossier privé n’est automatique.

Le nom de responsable dans un brief Marketing est une information de suivi,
pas un mandat ni une permission. Les contacts restent des références internes.
L’attestation d’un premier résultat demande preuve et date ; elle n’est ni
une vente ni une mesure d’adoption ou d’attribution.

Les effets externes restent désactivés. Les approbations natives sont prises
par la personne compétente. Ne jamais copier les grants, mandats, comptes ou
configurations d’une autre entreprise pour accélérer une installation.
