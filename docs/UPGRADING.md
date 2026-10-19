# Mise à jour et retour de version

Épingler la révision Git distribuée et conserver les manifests des Modules
installés. Le projet consommateur, ses locks et sa surface doivent être
versionnés séparément ; sauvegarder ses données et volumes par les procédures
de l’instance avant une mise à jour. Le dépôt des Modules ne constitue pas
une sauvegarde des données de l’entreprise.

Comparer la nouvelle révision à celle installée. Exécuter le composeur en
preview ; une divergence inconnue n’est pas une permission d’écraser. Les
empreintes historiques reconnues sont explicites. Relire et résoudre les
conflits, vérifier le contrat natif, committer, puis déployer chaque Agent et
mettre à jour les versions publiées dans la surface.

Un retour de sources n’est pas un retour des données. Vérifier la compatibilité
des formats et des références avant de redéployer une ancienne ressource.
Ne jamais restaurer une base ancienne pour annuler une évolution de formulaire.
Aucune migration majeure, suppression de données ou retour automatique n’est
fourni par cette bibliothèque. Les volumes Memory/Brain restent attachés à
leur mémoire ; les changements de sidecars suivent leur plan natif séparé.
