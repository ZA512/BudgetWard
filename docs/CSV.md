# Import CSV et analyse historique

L'import fonctionne sans connexion bancaire et sans IA. Il alimente les opérations réelles ; il ne remplace jamais le solde constaté dans la banque et ne crée aucune charge sans validation.

## Importer un relevé

1. Ouvrir **Importer un CSV**, disponible dans l'en-tête.
2. Choisir le fichier et, si nécessaire, l'encodage UTF-8 ou Windows-1252 et le séparateur point-virgule, virgule ou tabulation.
3. Sélectionner explicitement le compte qui figure sur le relevé. Importer les comptes CHARGES et DÉPENSES séparément.
4. Vérifier les colonnes proposées, les dates et le séparateur décimal. Les propositions de colonnes restent modifiables.
5. Ouvrir l'aperçu et vérifier les montants, les lignes invalides et les doublons possibles.
6. Confirmer l'import. Toute ligne invalide ou en conflit bloque l'ensemble : aucune écriture partielle.

Le fichier doit commencer par une ligne d'en-tête sans colonnes homonymes. Les préambules bancaires doivent être retirés avant import. Limites : 2 Mo côté fichier, 5 000 opérations par import ; plusieurs imports permettent de constituer l'historique. Les champs CSV entre guillemets peuvent contenir des séparateurs et des retours à la ligne.

## Colonnes et formats

| Champ | Obligatoire | Contenu |
| --- | --- | --- |
| Date comptable | Oui | `31/10/2026`, `2026-10-31` ou `31-10-2026`, selon le format choisi |
| Libellé bancaire | Oui | Texte de 1 à 250 caractères |
| Montant signé | Si utilisé | En euros : débit négatif, crédit positif |
| Débit / Crédit | À la place du montant signé | Colonnes positives ; une seule peut être non nulle par ligne |
| Date d'achat | Non | Date réelle, antérieure ou égale à la date comptable |
| Référence bancaire | Non, recommandée | Identifiant unique de l'opération sur ce compte, 120 caractères maximum |

Les montants utilisent la virgule ou le point choisi, avec deux décimales maximum. Les espaces de milliers français et le symbole `€` sont acceptés ; les autres ponctuations de milliers ne sont pas devinées. Les valeurs sont converties directement en centimes entiers, sans calcul en virgule flottante. Les montants nuls, dates futures et dates d'achat postérieures à la comptabilisation sont refusés.

Exemple fictif avec point-virgule, dates françaises et montants signés :

```csv
Date;Libellé;Montant;Référence
05/07/2026;PRLV ENERGIE EXEMPLE;-98,50;energie-juillet
05/08/2026;PRLV ENERGIE EXEMPLE;-98,50;energie-aout
05/09/2026;PRLV ENERGIE EXEMPLE;-105,00;energie-septembre
```

La démonstration propose **Charger un exemple fictif** ; ce bouton remplit le fichier d'exemple, sans importer avant confirmation.

## Doublons et immutabilité

- Une référence bancaire déjà présente sur le même compte est écartée si date, montant et libellé concordent. Si ces données diffèrent, l'import est bloqué : l'original n'est pas réécrit.
- Deux références bancaires différentes restent deux opérations, même si leurs date, montant et libellé sont identiques.
- Sans référence, deux lignes identiques dans un premier fichier restent deux opérations. Un relevé chevauchant des opérations déjà présentes demande un choix explicite **Conserver cette opération** ou **Écarter comme doublon**. Aucune ressemblance approximative ne supprime une opération.
- Le même fichier, pour le même compte et les mêmes paramètres, n'est traité qu'une fois, y compris sans identifiants bancaires. Les décisions d'écartement sont enregistrées dans le reçu d'import. Un contenu ou un mapping différent peut demander une nouvelle vérification.
- Si une modification entre l'aperçu et la confirmation change la décision à prendre sur une ligne, l'aperçu est refusé ; revenir aux colonnes pour le recalculer. Les sélections de compte et de format sont conservées.

La confirmation est transactionnelle et les imports concurrents sont sérialisés. Le solde du compte et les règles restent inchangés. Les données bancaires importées restent immuables ; leurs affectations peuvent être corrigées séparément.

## Examiner l'historique

**Analyse historique** porte sur toutes les dates importées du compte sélectionné, indépendamment du mois de prévision. Elle examine uniquement les débits non affectés. Les crédits et les opérations déjà qualifiées comme transfert, charge, budget ou autre opération ne sont pas proposés.

Le regroupement utilise le libellé en majuscules, sans accents et avec espaces normalisés. Les numéros et le reste du texte sont conservés : `CHEQUE 123` et `CHEQUE 456` ne sont pas fusionnés. Chaque groupe montre effectif, dernier montant, moyenne, médiane, minimum, maximum et liste des opérations. Les statistiques monétaires sont arrondies au centime par calcul entier.

Une fréquence mensuelle est seulement proposée lorsqu'une opération apparaît dans chacun d'au moins deux mois consécutifs. Les propositions hebdomadaires ou toutes les deux semaines demandent au moins trois opérations et des intervalles proches de 7 ou 14 jours. Ces heuristiques sont des indices, pas une certitude ; la fréquence reste à valider. Les chèques, retraits et libellés de virements génériques restent explicitement ambigus.

Actions disponibles :

- **Examiner** : revoir les statistiques et les transactions ; choisir le nom, la référence, la fréquence et la première échéance avant de créer une charge, ou rattacher la sélection à une charge existante sans modifier sa règle.
- **Ignorer** : masquer ce groupe de la liste de propositions, en conservant toutes ses opérations.
- **Voir aussi les groupes ignorés**, puis **Rétablir** : revenir sur une décision.

Les groupes ambigus n'ont aucune opération présélectionnée. Dans les autres groupes, la liste reste entièrement modifiable avant validation. Un rattachement concurrent ou une sélection devenue obsolète est refusé.

Pour une nouvelle charge, la règle démarre à la première échéance choisie. Les opérations antérieures sont conservées comme historique réel ; aucune prévision rétroactive n'est inventée et elles ne génèrent pas une fausse anomalie de paiement supplémentaire. Elles ne consomment pas une nouvelle échéance postérieure au démarrage, même au sein du même mois.

Ce lot ne crée pas de reconnaissance automatique pour les prochains imports, ne reconstitue pas les périodes tarifaires anciennes et ne déduit ni bénéficiaire de chèque ni fin de crédit fractionné. Ces informations restent à fournir ou à valider explicitement.
