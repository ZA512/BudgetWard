# Direction UX/UI — un outil de prévision du foyer

Décision du 21 octobre 2026 : construire une application de travail belle et lisible, avec les actions et les données au premier plan. La référence locale est la refonte de LootSplit décrite dans son `docs/UX-PROPOSITION.md`, et non sa première interface.

## La question à laquelle l'accueil répond

« Combien faut-il encore garder sur CHARGES et combien peut-on transférer ? »

L'écran commence par le mois, le compte et trois montants alignés : solde constaté, reste à protéger, transférable. Une date accompagne le solde. Un solde ancien est signalé. Pour un autre mois civil, l'application indique une simulation et nomme le résultat « Écart simulé » : aucun revenu futur ni solde historique n'est inventé.

Sous cette synthèse, des tableaux présentent les charges, les budgets et la réserve. Les montants sont alignés à droite avec chiffres tabulaires. Le clic sur le nom ouvre le calcul, ses occurrences et ses sources. Les actions Ajouter, Affecter, Corriger ou Modifier le solde sont nommées et proches de leur objet.

## Références consultées

Les choix ci-dessous sont des applications proposées de ces références, pas une preuve que BudgetWard est intuitif. Les essais avec des personnes qui découvrent l'outil restent nécessaires.

- [Nielsen Norman Group — 10 usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) : état visible, mots du quotidien, cohérence, prévention et récupération des erreurs. Application : mois et source visibles, absence de faux statut bancaire, enregistrement confirmé et erreurs explicites.
- [NN/g — Recognition and recall](https://www.nngroup.com/articles/recognition-and-recall/) : rendre les choix reconnaissables réduit le besoin de mémorisation. Application : navigation stable, actions libellées, montant et opération conservés dans le formulaire d'affectation.
- [GOV.UK — Table](https://design-system.service.gov.uk/components/table/) : présenter les informations comparables en lignes et colonnes. Application : prévu, payé et reste à protéger pour les charges ; calcul, financement et reste pour les budgets.
- [GOV.UK — Error summary](https://design-system.service.gov.uk/components/error-summary/) : donner une erreur accessible et permettre de la corriger. Premier lot : validation native des champs et résumé d'erreur du formulaire recevant le focus pour les erreurs serveur. La validation enrichie champ par champ reste à améliorer.

Ce sont des références de conception et d'ergonomie, pas un classement universel des « meilleurs » outils ni une promesse de courbe d'apprentissage nulle.

## Conventions de l'interface

- Navigation : Ce mois-ci, Charges, Budgets protégés, Opérations, À vérifier, Réglages. L'accueil fait aussi office de prévision détaillée ; pas de doublon Dashboard/Prévision dans ce premier lot.
- Vert profond, fond neutre, typographie sans sérif, cadres discrets. La couleur complète toujours un libellé.
- Aucune introduction promotionnelle, image décorative, série de cartes répétées ou graphique sans tâche précise.
- Les paramètres rares se trouvent dans un détail dépliable : fin d'un échéancier, nouvelle période tarifaire, référence bancaire.
- Les dialogues conservent le contexte, limitent le focus clavier et se ferment avec Échap. Les formulaires ont des libellés visibles et annoncent leur enregistrement.
- Sur mobile, la navigation défile dans sa propre zone et les tableaux financiers privilégient le nom et le reste à protéger. Les autres montants restent dans le détail. Le journal des opérations possède un défilement horizontal local.
- La démonstration est explicitement identifiée et utilise une base distincte. Le premier démarrage réel commence sans donnée fictive.

## Import et initialisation historique

L'import est accessible depuis l'en-tête et suit deux étapes : fichier et colonnes, puis aperçu et confirmation. Le compte est toujours choisi explicitement. Les erreurs par ligne et les références contradictoires bloquent l'import complet ; un doublon possible demande une décision sur la ligne. Le retour aux colonnes conserve le fichier et les choix de compte et de format. La confirmation distingue les opérations ajoutées et écartées, puis propose d'ouvrir le journal sur leur mois ou d'analyser l'historique.

Analyse historique affiche les libellés, effectifs, dernier montant et médiane dans un tableau. Le détail montre les statistiques, les paramètres modifiables et les cases de sélection des opérations. Aucun chèque ni virement générique n'est présenté comme une charge reconnue. Ignorer un groupe ne supprime aucune opération ; la décision est réversible. Le sélecteur mensuel est masqué sur cette page, puisque l'analyse porte sur toutes les dates importées du compte choisi.

Les contrôles partagés associent explicitement leur libellé accessible et séparent le texte d'aide de ce libellé. Les dialogues restent utilisables au clavier. La procédure et les limites sont détaillées dans [CSV.md](CSV.md).

## Ne pas faire croire à une certitude financière

L'absence d'opérations ne signifie pas que tout a été payé normalement. L'accueil indique le nombre d'opérations renseignées et invite à compléter charges et budgets. Une échéance passée sans paiement renseigné est nommée « Non renseigné », pas « impayé ».

Le premier lot ne déduit aucune fenêtre bancaire. Les anomalies portent sur les paiements affectés : montant différent, compte inattendu, occurrence supplémentaire. Une anomalie ne change jamais une règle. Une opération non affectée reste visible dans À vérifier.

Le financement d'un budget et sa consommation sont distincts : le détail affiche les deux. Seule la sortie de CHARGES vers DÉPENSES affectée à un budget diminue sa protection sur CHARGES ; la contrepartie entrante est un transfert interne. Aucun virement n'est initié.

## Vérification à poursuivre avec l'utilisateur

Objectifs proposés, sans prétendre à des seuils scientifiques :

1. Retrouver le solde et le transférable au premier regard.
2. Expliquer pourquoi les courses comptent cinq occurrences en octobre 2026.
3. Modifier un nombre de semaines FAC pour un mois sans changer les suivants.
4. Renseigner puis affecter un paiement et constater qu'il n'est plus protégé deux fois.
5. Reconnaître une simulation ou un solde ancien avant de décider d'un virement.

Observer les hésitations et erreurs plutôt que demander uniquement si l'écran est joli. Les parcours automatisés couvrent calcul, affectation, persistance, premier démarrage, clavier et débordement aux largeurs 320, 390, 768 et 1024 px. Ils ne remplacent pas les essais utilisateurs.
