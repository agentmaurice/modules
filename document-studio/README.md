# Document studio

Module réutilisable qui transforme un brief en document professionnel (devis,
compte rendu de réunion) : brouillon, rendu PDF à partir d'un gabarit et de la
fiche entreprise, relecture, approbation, émission avec un numéro. Tout vit
dans Storage ; rien n'est envoyé à l'extérieur.

Le Module ne contient aucun moteur de rendu. Le rendu passe par le tool MCP
`artifact--artifact_render_v1` (mode `preview` pour les brouillons, `final` pour
l'émission). Les étapes de code sont du JavaScript (`code_execution`) : pas de
WASM en V0. Aucun binaire n'est versionné ici (ni PDF ni PNG).

## Workflows

| Workflow | Rôle |
|---|---|
| `document-studio-plan` | choisit le gabarit d'après un brief, propose un titre, liste les données manquantes et les questions à poser. N'écrit rien |
| `document-studio-draft` | remplit les données du gabarit (appel modèle, puis validation stricte) et crée le dossier du document au statut `draft`. Pour un devis, les montants et les totaux sont calculés ici, en centimes entiers, à partir des lignes : le modèle ne fournit que des quantités et des prix |
| `document-studio-render` | rend l'état courant (PDF et aperçus PNG) et ajoute une révision. `data_patch` fusionne (superficiellement) des corrections dans les données, qui sont revalidées. Un document émis ou annulé ne se rend plus (`document_locked`) |
| `document-studio-finalize` | `draft` vers `approved`. Exige un rendu de la révision courante et `confirmation_manuelle` |
| `document-studio-publish` | exige `approved` et `confirmation_manuelle`. Réserve le prochain numéro, rend en mode `final`, enregistre le PDF émis, passe à `issued` |
| `document-studio-cancel` | passe à `cancelled` avec un motif. Un numéro émis n'est jamais réutilisé |
| `document-studio-export` | copie le PDF émis (ou le dernier rendu, signalé comme brouillon) vers un chemin Storage hors de `/document-studio/`, avec son empreinte SHA-256. Mail et SFTP sont hors V0 |
| `document-studio-profile-save` | valide et enregistre la fiche entreprise et la charte (`/document-studio/profile.json`), avec confirmation manuelle |
| `document-studio-list` | liste des documents (identifiant, titre, statut, numéro, révision, dernière empreinte) |
| `document-studio-review-read` | dossier complet d'un document et aperçus du dernier rendu, pour la MiniApp |
| `document-studio-template-read` | liste des gabarits, ou manifeste et schémas de données d'un gabarit |

La MiniApp `document-studio-review` charge un document par son identifiant,
affiche statut, révision, numéro, pages et le tableau des rendus (révision,
mode, empreinte, chemin), et relance un rendu. L'approbation et l'émission
passent par les formulaires des Workflows, avec la confirmation manuelle.

## Cycle de vie

`draft` (rendus successifs) → `approved` → `issued`. `cancelled` est possible
depuis tous les autres statuts. Un nouveau rendu d'un document `approved` le
ramène à `draft` : l'approbation est à refaire. La confirmation manuelle est
le champ de formulaire `confirmation_manuelle` (`oui` ou `non`) ; sans `oui`,
le Workflow refuse (`manual_confirmation_required`) avant toute lecture ou
écriture. Le Module n'approuve jamais à la place d'une personne.

## Stockage

- `/document-studio/profile.json` : la charte, au schéma `{schema_version: 1, company, brand}` du contrat de gabarit. Un exemple fictif est dans `examples/profile.example.json`.
- `/document-studio/docs/<doc_id>/record.json` : le dossier (`document-studio.record/v1`) : statut, numéro, révision (+1 à chaque écriture), données, historique, rendus (chemin, SHA-256, aperçus, provenance), émission.
- `/document-studio/docs/<doc_id>/r<révision>/` : PDF et aperçus d'un rendu.
- `/document-studio/docs/<doc_id>/issued/<numéro>.pdf` : le PDF émis.
- `/document-studio/numbers/<gabarit>/<année>/<seq sur 4 chiffres>.json` : jeton de numéro.

`doc_id` : `^[a-z0-9][a-z0-9-]{0,47}$`, choisi par l'appelant ou dérivé du
titre avec un suffixe court. Numéro : `<PRÉFIXE>-<année>-<seq>` (`DEV` pour le
devis, `CR` pour le compte rendu).

Sans fiche entreprise, `render` et `publish` échouent avec `profile_missing` :
enregistrez la charte par `document-studio-profile-save`.

## Gabarits

`examples/templates/quote` et `examples/templates/meeting-minutes` sont des
copies des gabarits de référence du contrat `agentmaurice.template/v1`, avec
les fragments partagés qu'ils importent. `tooling/document-studio/contract/PIN.json`
note le commit du contrat d'origine et l'empreinte de chaque fichier. Un seul
fichier diffère de l'original : `quote/main.typ`, qui ajoute la mention
« Ce document est un devis, ce n'est pas une facture ». Le contrôle du contrat se lance
avec le script `template_check.py` de ce contrat (`check <dossier>`) ; la CI de ce dépôt est
hors ligne et ne dépend pas de lui.

Les gabarits sont embarqués en texte dans les Workflows qui rendent. Leurs
accolades y sont écrites en séquences d'échappement, car le moteur de Workflows
lirait une double accolade dans le code comme une action de gabarit.

Données d'un devis : le brouillon porte des nombres (`quantity`, `unit_price_ht`,
`vat_rate`), jamais des montants formatés ni des totaux. Au rendu, le Workflow
produit les chaînes attendues par le gabarit (`1 250,00 €`) et les totaux HT, TVA par taux et TTC.

## Régénération et tests

```
python3 tooling/document-studio/build.py
python3 -m unittest discover -s tooling/document-studio/tests -p 'test_*.py'
```

Les tests exécutent chaque étape JavaScript sous Node, avec un Storage et un
moteur de rendu simulés, sur des données synthétiques. Ils ne prouvent pas le
comportement sur un One.

## Limites connues (V0)

- La charte est lue dans Storage seulement. Le Module `profile` garde la fiche dans un enregistrement d'application, dont le broker n'est pas encore câblé dans le One : l'appel du Workflow `cib-profile-read` fait échouer le rendu tant qu'il en est ainsi.
- Le logo est une référence (`storage://…`) ; ce Module ne la résout pas en fichier avant le rendu.
- La réservation d'un numéro n'est pas atomique : elle liste, écrit sans écrasement, relit et vérifie le propriétaire, 5 essais au plus (`number_conflict`). Un numéro réservé puis perdu (rendu en échec) reste réservé : il est repris au nouvel essai, jamais réutilisé par un autre document.
- Pas d'envoi (mail, SFTP), pas de DOCX, une seule langue (`fr`).
- `document-studio-export` lit le PDF en base64 par `read_file` ; si le runtime ne le permet pas, l'export échoue sur l'empreinte (`export_integrity_failed`).
- Pas de carte `document` du Viewer pour l'aperçu dans le chat : à vérifier ensuite.
