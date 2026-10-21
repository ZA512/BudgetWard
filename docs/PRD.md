# PRD — Prévision du compte CHARGES et calcul du disponible mensuel

**Version :** 1.0  
**Statut :** prêt pour développement  
**Nom du projet :** BudgetWard  
**Type :** application web auto-hébergée  
**Langue :** français  
**Devise :** EUR  
**Projet distinct de LootSplit**

---

# 1. Contexte

Le foyer souhaite modifier profondément sa gestion budgétaire.

L'organisation bancaire cible repose principalement sur deux comptes courants :

## Compte CHARGES

Compte joint principal.

Il reçoit les revenus et conserve l'argent nécessaire au fonctionnement du foyer :

- prélèvements ;
- crédits ;
- assurances ;
- énergie ;
- services récurrents ;
- frais scolaires ;
- cantines ;
- paiements temporaires type Oney ;
- nourriture ;
- carburant ;
- covoiturage étudiant ;
- autres dépenses considérées comme nécessaires.

Les dépenses nécessitant une carte bancaire mais considérées comme des charges pourront être payées avec une carte virtuelle dédiée au compte CHARGES.

## Compte DÉPENSES

Compte joint sans découvert autorisé.

Les cartes bancaires physiques du foyer sont rattachées à ce compte.

Il ne doit recevoir que :

1. l'argent réellement disponible pour les dépenses libres ;
2. temporairement, l'argent transféré depuis CHARGES pour effectuer une dépense protégée telle que courses ou carburant.

Le solde du compte DÉPENSES doit donc être facilement interprétable.

---

# 2. Problème à résoudre

Au début de chaque mois, la question essentielle est :

> **Combien faut-il conserver sur CHARGES pour être certain de couvrir le fonctionnement du mois, et combien peut-on transférer vers DÉPENSES ?**

Certaines dépenses sont extrêmement simples à prévoir :

- prêt ;
- assurance ;
- abonnement ;
- EDF mensualisé ;
- télécom ;
- etc.

D'autres sont beaucoup moins triviales :

- cantines scolaires ;
- dépenses scolaires ;
- paiements par chèque ;
- paiements fractionnés ;
- courses alimentaires ;
- fast-food familial ;
- carburant ;
- covoiturage étudiant ;
- charges nouvelles ;
- changement de tarif ;
- charge qui disparaît ;
- variations saisonnières.

Le logiciel doit progressivement transformer cette complexité en un système fonctionnant principalement **par exception**.

---

# 3. Philosophie générale

Le logiciel ne doit pas essayer d'être « intelligent » à chaque début de mois.

Le principe est :

> **L'humain définit le fonctionnement normal une première fois.  
> Le système calcule ensuite automatiquement.  
> L'utilisateur n'intervient que lorsqu'une situation change.**

L'IA peut faciliter considérablement l'initialisation, mais elle ne doit jamais devenir la source de vérité du système.

Principes :

```text
Algorithme -> constate
IA         -> propose/interprète
Humain     -> valide
Moteur     -> applique
```

Une règle validée ne doit jamais être modifiée silencieusement par une IA ou un algorithme.

---

# 4. Objectif principal

À partir :

- du solde réel de CHARGES ;
- des transactions historiques ;
- du catalogue des charges ;
- des budgets protégés ;
- du mois concerné ;
- des éventuels ajustements manuels ;

l'application calcule :

```text
MONTANT À CONSERVER SUR CHARGES
```

puis :

```text
SOLDE DISPONIBLE
-
MONTANT À CONSERVER
=
MONTANT TRANSFÉRABLE VERS DÉPENSES
```

---

# 5. Ce que l'application n'est pas

Le produit n'est PAS :

- un agrégateur patrimonial ;
- un outil comptable ;
- un remplacement de la banque ;
- une application de paiement ;
- un outil d'investissement ;
- un logiciel destiné à faire automatiquement des virements ;
- un système de catégorisation universelle de toutes les dépenses ;
- une IA ayant carte blanche sur les finances.

Il répond principalement à :

> **« Quelle somme devons-nous protéger sur CHARGES pour le mois ? »**

---

# 6. Projet distinct de LootSplit

Ce produit doit être développé dans un dépôt indépendant de LootSplit.

LootSplit répond à :

> « Sur mon compte d'épargne, à quelle réserve appartient chaque euro ? »

Le présent projet répond à :

> « Combien dois-je conserver sur mon compte CHARGES ? »

Ils peuvent utiliser des concepts techniques similaires :

- Woob ;
- CSV ;
- FastAPI ;
- React ;
- SQLite ;
- Docker.

Mais ils ont des modèles métier distincts.

Ne pas créer de dépendance à LootSplit pour le MVP.

Une bibliothèque bancaire commune pourra être extraite ultérieurement si cela devient réellement pertinent.

---

# 7. Comptes bancaires suivis

L'application doit pouvoir suivre plusieurs comptes.

Deux rôles principaux :

```text
CHARGES
DEPENSES
```

Le compte CHARGES est obligatoire.

DÉPENSES est fortement recommandé afin de pouvoir analyser les dépenses protégées réellement consommées.

Une transaction entre deux comptes connus du système doit pouvoir être reconnue comme :

```text
TRANSFERT_INTERNE
```

Elle ne constitue pas une dépense du foyer.

---

# 8. Connexion bancaire

Créer une abstraction :

```text
BankConnector
```

Interface minimale :

```text
get_accounts()
get_balance(account_id)
get_transactions(account_id, since, until)
```

Implémentations prévues :

```text
WoobConnector
CsvConnector
```

Éventuellement plus tard :

```text
OpenBankingConnector
```

Le moteur métier ne doit jamais dépendre directement de Woob.

---

# 9. Lecture seule

L'application ne doit jamais initier de virement bancaire.

Elle peut :

- lire les comptes ;
- lire les soldes ;
- lire les transactions ;
- analyser ;
- prévoir ;
- proposer.

Les virements restent effectués par l'utilisateur dans son application bancaire.

---

# 10. Transactions bancaires

Une transaction importée est immuable.

Stocker notamment :

```text
id
account_id
provider_transaction_id
booking_date
value_date
amount_cents
currency
raw_label
normalized_label
payment_method
source
imported_at
fingerprint
```

Éventuellement :

```text
operation_date
```

si la banque fournit la date réelle d'achat par carte.

---

# 11. Date logique d'une dépense

Certaines dépenses carte sont réalisées un jour et comptabilisées plusieurs jours plus tard.

Exemple :

```text
Courses effectuées samedi
Débit bancaire lundi ou mardi
```

Pour les analyses hebdomadaires, utiliser si disponible :

1. date réelle de paiement ;
2. date extraite du libellé bancaire ;
3. sinon date comptable.

Prévoir :

```text
logical_date
```

qui peut être corrigée manuellement si nécessaire.

---

# 12. Déduplication

Une synchronisation répétée ne doit jamais créer deux transactions identiques.

Priorité :

```text
provider_transaction_id
```

Sinon créer une empreinte basée sur plusieurs attributs :

```text
account
date
montant
libellé
type
```

Ne jamais faire de déduplication approximative susceptible de supprimer deux vraies opérations similaires.

---

# 13. Les trois masses financières

Le calcul mensuel distingue obligatoirement trois masses.

## 13.1 Charges obligatoires

Dépenses envers un tiers.

Exemples :

- EDF ;
- prêt ;
- assurance ;
- ChatGPT ;
- téléphone ;
- cantine ;
- école ;
- crédit temporaire Oney ;
- etc.

## 13.2 Budgets protégés

Sommes que le foyer souhaite volontairement protéger avant de déterminer l'argent libre.

Exemples :

- courses alimentaires ;
- fast-food familial ;
- carburant ;
- covoiturage FAC.

Ce ne sont pas des factures mais l'argent doit néanmoins être conservé.

## 13.3 Marge et objectifs

Exemples :

- marge de sécurité ;
- réduction mensuelle du découvert ;
- objectif temporaire de trésorerie.

---

# 14. Résultat final

Formule conceptuelle :

```text
Charges obligatoires
+
Budgets protégés
+
Marge de sécurité
+
Objectif de trésorerie
=
MONTANT À PROTÉGER SUR CHARGES
```

Puis :

```text
Solde CHARGES utilisable
-
Montant encore nécessaire
=
TRANSFÉRABLE VERS DÉPENSES
```

Si le résultat est négatif :

```text
TRANSFÉRABLE = 0
DÉFICIT PRÉVISIONNEL = valeur absolue
```

---

# 15. Objet métier : Charge

Chaque charge connue doit devenir un objet métier.

Exemples :

```text
EDF
Cantine collège
Cantine primaire
Cantine lycée
ChatGPT
Cofidis
Oney canapé
Assurance voiture
Internet
```

Une charge existe indépendamment de ses transactions.

---

# 16. Ne pas créer une taxonomie rigide de 30 types

Éviter un enum énorme du style :

```text
FIXED_MONTHLY_ANNUAL_REVISION_TEMPORARY...
```

Décomposer plutôt le comportement d'une charge en dimensions indépendantes.

---

# 17. Variabilité d'une charge

Valeurs proposées :

```text
EXACT
STABLE_REVIEWABLE
VARIABLE
```

## EXACT

Montant normalement identique.

Exemple :

```text
Crédit : 187,42 €
```

## STABLE_REVIEWABLE

Montant stable pendant une période mais susceptible d'être révisé.

Exemple :

```text
EDF : 148 € pendant plusieurs mois
puis nouveau montant : 161 €
```

## VARIABLE

Montant réellement variable.

Exemple :

```text
Cantine
```

---

# 18. Périodicité

Valeurs possibles :

```text
MONTHLY
WEEKLY
EVERY_N_WEEKS
QUARTERLY
YEARLY
IRREGULAR
SEASONAL
MANUAL
```

Permettre également :

```text
interval_value
```

pour exprimer :

```text
toutes les 2 semaines
tous les 3 mois
```

---

# 19. Cycle de vie

Valeurs :

```text
OPEN_ENDED
END_DATE
INSTALLMENT_COUNT
```

Exemples :

EDF :

```text
OPEN_ENDED
```

Oney 4 fois :

```text
INSTALLMENT_COUNT = 4
```

Charge temporaire :

```text
END_DATE = 2027-03-31
```

---

# 20. Mode de paiement

Valeurs proposées :

```text
SEPA
CARD
VIRTUAL_CARD
TRANSFER
CHEQUE
CASH
OTHER
UNKNOWN
```

Le mode peut être proposé automatiquement lors de l'onboarding, mais reste modifiable.

---

# 21. Fenêtre de paiement

Une charge peut avoir une fenêtre attendue.

Exemple :

```text
EDF
jour moyen : 5
fenêtre : 3 -> 8
```

ou :

```text
Cantine collège
irrégulier
```

Cette information sert à détecter une charge manquante.

---

# 22. Tolérance

Une charge peut définir une tolérance de variation.

Exemple :

```text
Crédit :
±0,01 €

EDF :
±3 %

Cantine :
tolérance importante
```

Supporter :

```text
ABSOLUTE
PERCENTAGE
NONE
```

---

# 23. Date habituelle de révision

Pour une charge `STABLE_REVIEWABLE`, permettre :

```text
review_month
```

Exemple :

```text
EDF
révision habituelle : septembre
```

Cette valeur peut être proposée depuis l'historique mais validée par l'utilisateur.

---

# 24. Prévision d'une charge

Le moteur doit prendre en charge plusieurs méthodes.

```text
CURRENT_EXACT
LAST_KNOWN
RECENT_MEDIAN
RECENT_AVERAGE
SAME_PERIOD_HISTORY
MANUAL
```

L'utilisateur peut toujours imposer la méthode.

---

# 25. Versionner les règles

Lorsqu'une charge change, ne pas écraser sa définition historique.

Exemple :

```text
EDF
01/01 -> 31/08 : 148 €
à partir du 01/09 : 161 €
```

Créer des versions de règle.

Concept :

```text
ChargeRuleVersion
```

avec :

```text
effective_from
effective_until
```

Cela permet d'expliquer correctement l'historique.

---

# 26. Cas particulier : paiements fractionnés

Exemple :

```text
ONEY
64,50 €
4 échéances
```

La charge doit pouvoir contenir :

```text
installment_amount
installment_count
remaining_installments
first_due_date
expected_end_date
```

Le moteur doit prévoir les échéances restantes.

À la fin :

```text
Charge terminée comme prévu
```

Si une nouvelle échéance apparaît après la fin prévue :

```text
anomalie
```

---

# 27. Cas particulier : cantine collège

Fonctionnement connu :

- paiement par chèque ;
- environ 100 € ;
- paiement irrégulier ;
- plusieurs fois dans l'année scolaire.

Le relevé bancaire pourra seulement afficher :

```text
CHEQUE XXXXX
-100 €
```

Le système ne pourra pas reconnaître sûrement le bénéficiaire.

La première qualification sera donc humaine.

Une fois qualifiée :

```text
Charge = Cantine collège
Mode = CHEQUE
Variabilité = VARIABLE ou STABLE_REVIEWABLE
Périodicité = IRREGULAR / SEASONAL
```

Ne jamais créer une règle :

```text
tout chèque de 100 € = cantine
```

Confiance insuffisante.

---

# 28. Cantine primaire

Paiement par carte sur une plateforme internet.

Une signature bancaire pourra éventuellement être définie après qualification humaine.

Montant potentiellement variable.

---

# 29. Cantine lycée

Mode exact à confirmer par l'utilisateur.

Probablement prélèvement automatique.

Le logiciel ne doit jamais inventer cette information.

---

# 30. Objet métier : ProtectedBudget

Un budget protégé représente une somme nécessaire à la vie du foyer mais qui n'est pas une facture classique.

Exemples :

```text
Courses alimentaires
Fast-food familial
Carburant utilisateur
Carburant conjointe
Covoiturage FAC
```

---

# 31. Structure d'un ProtectedBudget

Champs possibles :

```text
id
name
active
calculation_method
reference_amount_cents
frequency
anchor_weekday
interval_value
manual_adjustment
description
```

Éventuellement :

```text
seasonality_enabled
```

mais la saisonnalité ne doit pas être obligatoire.

---

# 32. Courses alimentaires

Fonctionnement initial souhaité :

```text
jour de référence = samedi
budget hebdomadaire manuel = environ 250 à 280 €
```

Le système compte le nombre de samedis du mois.

Exemple :

```text
5 samedis
budget de référence = 270 €

5 × 270 = 1 350 €
```

Cette somme est ajoutée aux montants à protéger.

---

# 33. Moyenne réelle des courses

L'application doit pouvoir calculer la dépense hebdomadaire réellement observée à partir des transactions du compte DÉPENSES.

Elle doit afficher notamment :

```text
référence utilisateur : 270 €
moyenne observée récente : 264 €
médiane : 258 €
```

L'utilisateur décide s'il souhaite modifier la référence.

Ne jamais remplacer automatiquement 270 € par 264 €.

---

# 34. Vacances scolaires et courses

Pendant les vacances, davantage de repas sont pris à domicile.

Cela peut augmenter le budget alimentaire.

Ne pas construire une logique complexe dès le MVP.

Dans un premier temps :

```text
budget hebdomadaire × nombre de samedis
```

Le système peut ultérieurement montrer des statistiques :

```text
moyenne semaines normales
moyenne vacances
```

Si une différence significative apparaît réellement, l'utilisateur pourra décider d'activer une règle saisonnière.

---

# 35. Fast-food familial

Ce budget est séparé des courses.

Même s'il appartient globalement à l'alimentation, il est considéré comme un plaisir récurrent.

Fonctionnement typique :

```text
environ un mardi sur deux
```

mais :

- différentes enseignes ;
- montants variables ;
- utilisation possible de points fidélité.

Le budget doit donc s'appuyer sur le **montant réellement payé**, pas sur une valeur théorique du repas.

Méthode possible :

```text
EVERY_N_WEEKS
interval = 2
```

avec montant de référence basé sur l'historique ou défini manuellement.

---

# 36. Carburant utilisateur

Fonctionnement approximatif :

```text
1 plein par mois
```

si aucun déplacement exceptionnel.

ProtectedBudget :

```text
frequency = MONTHLY
```

Montant de référence :

```text
manuel puis historique
```

---

# 37. Carburant conjointe

Fonctionnement approximatif :

```text
1 plein par semaine
```

ProtectedBudget :

```text
frequency = WEEKLY
```

Le montant mensuel peut être calculé depuis le nombre de semaines/occurrences pertinentes.

---

# 38. Covoiturage FAC

Fonctionnement :

```text
35 € / semaine lorsqu'il y a FAC
```

L'application doit permettre de calculer :

```text
nombre de semaines FAC × 35 €
```

Pour le MVP, le nombre de semaines peut être ajusté manuellement pour le mois.

Ne pas imposer immédiatement une intégration avec le calendrier universitaire.

Une automatisation pourra être ajoutée ultérieurement.

---

# 39. Budgets protégés et compte DÉPENSES

L'argent de ces budgets reste initialement sur CHARGES.

Avant utilisation :

```text
CHARGES -> DÉPENSES
```

Puis paiement avec la carte de DÉPENSES.

Les virements entre comptes doivent être reconnus comme transferts internes et ne doivent pas être comptés comme dépenses du foyer.

---

# 40. Financement d'un ProtectedBudget

Pour permettre un suivi précis en cours de mois, une transaction interne :

```text
CHARGES -> DÉPENSES
```

peut être affectée à un ProtectedBudget.

Exemple :

```text
+270 € vers DÉPENSES
motif : Courses
```

Cela permet de distinguer :

```text
Budget mensuel prévu : 1 350 €
Déjà transféré pour courses : 540 €
Reste encore protégé sur CHARGES : 810 €
```

L'affectation peut être :

- automatique via libellé ;
- ou manuelle.

---

# 41. Consommation réelle d'un ProtectedBudget

Les transactions carte sur DÉPENSES peuvent être affectées à un ProtectedBudget.

Exemple :

```text
LECLERC -> Courses
TOTAL -> Carburant
MC DONALDS -> Fast-food
```

Ces affectations servent :

- aux statistiques ;
- aux moyennes historiques ;
- à comparer prévu/réel.

Elles ne doivent pas être confondues avec le financement depuis CHARGES.

---

# 42. Différence financement / consommation

Conserver deux notions distinctes :

```text
FUNDED
SPENT
```

Exemple :

```text
Courses prévues : 270 €
Transféré vers DÉPENSES : 270 €
Réellement dépensé : 258 €
```

Les 12 € restants ne doivent pas être inventés ou redistribués automatiquement.

---

# 43. Classification des dépenses protégées

La classification pourra être assistée par des règles.

Exemple :

```text
LECLERC -> Courses
INTERMARCHE -> Courses
TOTAL -> Carburant
DOMINOS -> Fast-food
```

Mais une transaction doit toujours pouvoir être corrigée manuellement.

Attention :

```text
LECLERC
```

peut contenir des achats non alimentaires.

La classification n'a pas vocation à produire une comptabilité parfaite.

Elle sert à établir une moyenne suffisamment fiable.

---

# 44. Assistant d'initialisation historique

L'un des principaux besoins est de réduire le travail de mise en place initial.

Créer un module :

```text
Analyse historique
```

L'utilisateur importe idéalement environ 12 mois de transactions.

Sources possibles :

```text
Woob
CSV
```

Comptes analysés :

```text
CHARGES
DEPENSES
```

---

# 45. Pipeline d'onboarding

```text
Historique bancaire
        ↓
Normalisation
        ↓
Détection moyen de paiement
        ↓
Regroupement statistique
        ↓
Détection périodicité
        ↓
Détection variabilité
        ↓
Détection fenêtre
        ↓
Détection changement de régime
        ↓
Assistance IA facultative
        ↓
Propositions
        ↓
VALIDATION HUMAINE
        ↓
Catalogue
```

---

# 46. Analyse déterministe avant IA

Le système doit calculer lui-même :

- fréquence ;
- nombre d'occurrences ;
- intervalles entre opérations ;
- moyenne ;
- médiane ;
- minimum ;
- maximum ;
- variance ;
- écart-type ;
- dates habituelles ;
- mode de paiement lorsqu'identifiable ;
- changement brutal de montant ;
- disparition estivale ;
- stabilité du libellé ;
- stabilité du créancier.

L'IA ne doit pas recalculer ces informations.

---

# 47. Exemple EDF

Historique :

```text
05/01 148,20 €
05/02 148,20 €
05/03 148,20 €
...
05/08 148,20 €
05/09 161,50 €
05/10 161,50 €
```

Proposition :

```text
Nom : EDF
Périodicité : mensuelle
Mode : SEPA
Variabilité : STABLE_REVIEWABLE
Montant actuel : 161,50 €
Fenêtre : jours 3 à 8
Révision détectée : septembre
```

L'utilisateur valide ou corrige.

---

# 48. Exemple paiement fractionné

Historique :

```text
ONEY 64,50 €
ONEY 64,50 €
ONEY 64,50 €
```

Le système peut proposer :

```text
Paiement temporaire probable
Montant stable : 64,50 €
Périodicité : mensuelle
```

L'IA peut suggérer :

```text
Probable paiement en plusieurs fois
```

Mais l'utilisateur doit indiquer si nécessaire :

```text
4 échéances au total
```

---

# 49. Exemple ambigu : chèques

Historique :

```text
CHEQUE 100 €
CHEQUE 100 €
CHEQUE 100 €
```

Ne pas conclure automatiquement :

```text
Cantine
```

Afficher :

```text
Groupe ambigu
3 chèques de 100 €
```

L'utilisateur peut sélectionner les opérations correspondant réellement à :

```text
Cantine collège
```

---

# 50. Rôle de l'IA lors de l'onboarding

L'IA peut aider à :

- proposer un nom humain ;
- reconnaître un fournisseur ;
- expliquer un pattern ;
- suggérer qu'une charge est mensuelle ;
- suggérer une saisonnalité scolaire ;
- suggérer qu'une série correspond à un paiement fractionné ;
- proposer de regrouper des variantes de libellé ;
- identifier des groupes qui semblent correspondre au même service ;
- proposer une première configuration.

Elle ne doit jamais valider elle-même.

---

# 51. Données envoyées à l'IA

Le système doit pouvoir fonctionner sans IA.

Si IA activée, préférer envoyer des données agrégées et minimisées.

Exemple :

```text
merchant/group: EDF
12 occurrences
dates: [...]
amounts: [...]
payment_method: SEPA
```

Plutôt que transmettre l'ensemble du relevé bancaire brut lorsque ce n'est pas nécessaire.

---

# 52. Fournisseur IA

Prévoir une abstraction :

```text
AIAnalyzer
```

Possibilités futures :

```text
OpenAI
Ollama
autre API
```

Mais le moteur métier ne doit pas dépendre d'un fournisseur.

---

# 53. MVP et IA

L'application doit rester totalement fonctionnelle sans clé API.

Une première version acceptable peut proposer :

```text
Exporter le dossier d'analyse IA
```

au format JSON/Markdown.

L'utilisateur peut alors l'analyser manuellement avec ChatGPT.

Une intégration API native pourra venir ensuite.

---

# 54. Validation humaine de l'onboarding

Chaque proposition doit avoir :

```text
Valider
Modifier
Ignorer
```

Exemple :

```text
EDF

12 opérations
1 831 € sur l'année

Proposition
------------
Charge : oui
Mensuelle
SEPA
Montant actuel : 161,50 €
Fenêtre : 3 -> 8
Révision annuelle probable : septembre

[Valider]
[Modifier]
[Ignorer]
```

---

# 55. Score de confiance

Le système peut calculer un score d'aide à l'utilisateur.

Exemple :

```text
99 % : très régulier
83 % : probable
42 % : ambigu
```

Ce score ne doit pas permettre à l'application de valider seule une charge pendant l'onboarding initial.

---

# 56. Catalogue des charges

Après onboarding, le système contient un catalogue stable.

Exemple :

```text
EDF
Assurance maison
Internet
ChatGPT
Cantine collège
Cantine primaire
Cantine lycée
Cofidis
Oney canapé
...
```

Le travail quotidien se fait ensuite principalement par détection des différences.

---

# 57. Matching d'une transaction à une charge

Utiliser plusieurs indices :

- identifiant créancier SEPA ;
- libellé ;
- marchand ;
- mode de paiement ;
- montant ;
- périodicité ;
- fenêtre de date ;
- compte attendu.

Ne jamais utiliser uniquement le montant comme identifiant.

---

# 58. Niveaux de matching

Conceptuellement :

```text
STRONG
MEDIUM
WEAK
```

### STRONG

Exemple :

```text
créancier SEPA connu
```

### MEDIUM

Exemple :

```text
OPENAI + montant proche + mensuel
```

### WEAK

Exemple :

```text
CHEQUE 100 €
```

Un matching faible doit demander confirmation.

---

# 59. Gestion par exception

Une fois le catalogue créé, le système compare en permanence :

```text
attendu
vs
réel
```

Si tout est normal :

```text
silence
```

Si quelque chose change :

```text
anomalie / demande de validation
```

---

# 60. Types d'anomalies

Prévoir au minimum :

```text
NEW_TRANSACTION_PATTERN
AMOUNT_CHANGED
EXPECTED_CHARGE_MISSING
EXTRA_OCCURRENCE
PAYMENT_METHOD_CHANGED
WRONG_ACCOUNT
INSTALLMENT_OVERDUE
INSTALLMENT_ENDED_EARLY
UNKNOWN_TRANSACTION
RULE_OUTDATED
```

---

# 61. Nouvelle charge probable

Exemple :

```text
DISNEY+
9,99 €
```

apparaît pour la première fois.

Ne pas forcément créer une alerte forte immédiatement.

Au deuxième ou troisième mois :

```text
Cette opération semble devenir récurrente.
Créer une charge ?
```

---

# 62. Changement de montant

Exemple :

```text
EDF attendu : 148 €
Réel : 161 €
```

Afficher :

```text
Montant différent du modèle.
```

Proposer :

```text
Occurrence exceptionnelle
Mettre à jour la règle
Nouvelle période tarifaire
```

---

# 63. Charge absente

Exemple :

EDF attendu entre le 3 et le 8.

Le 10, aucune opération correspondante.

Afficher :

```text
EDF n'a pas été détecté dans sa fenêtre habituelle.
```

Ne pas retirer automatiquement EDF du prévisionnel.

---

# 64. Charge sur mauvais compte

Exemple :

Oney est défini comme :

```text
Compte attendu = CHARGES
```

mais apparaît sur DÉPENSES.

Afficher :

```text
Charge connue détectée sur un compte inattendu.
```

Cela permet de contrôler également la discipline du nouveau système bancaire.

---

# 65. Prévision mensuelle

Créer un objet :

```text
MonthlyPlan
```

Il représente un mois civil.

Exemple :

```text
2026-11
```

---

# 66. Prévision des charges

Pour chaque charge active, calculer son montant attendu pour le mois.

Exemples :

```text
Crédit : exact
EDF : dernier montant connu
Cantine : estimation historique
Oney : échéance exacte
```

---

# 67. Prévision des budgets protégés

Exemples :

Courses :

```text
nombre de samedis × référence hebdomadaire
```

Fast-food :

```text
nombre d'occurrences prévues × coût moyen/référence
```

Carburant hebdomadaire :

```text
nombre de semaines × montant
```

Covoiturage :

```text
semaines FAC × 35 €
```

---

# 68. Ajustements manuels mensuels

Avant validation du mois, l'utilisateur doit pouvoir ajouter :

```text
Dépense ponctuelle connue
```

Exemple :

```text
Contrôle technique
80 €
```

ou modifier exceptionnellement un budget.

L'ajustement concerne uniquement le mois sélectionné et ne modifie pas la règle globale sauf demande explicite.

---

# 69. Marge de sécurité

Prévoir une marge configurable.

V1 :

```text
montant fixe
```

Exemple :

```text
100 €
```

Plus tard :

```text
marge suggérée selon erreurs historiques
```

Mais aucune modification automatique.

---

# 70. Réduction du découvert / objectif de trésorerie

Permettre un objectif temporaire :

```text
Amélioration de trésorerie : 150 €
```

Cette somme est considérée comme indisponible.

Exemple :

```text
Besoin fonctionnel : 4 100 €
Marge : 100 €
Réduction découvert : 150 €

À protéger : 4 350 €
```

L'utilisateur peut changer cet objectif chaque mois ou le désactiver.

---

# 71. Calcul au début du mois

Exemple :

```text
CHARGES OBLIGATOIRES

Prêts / assurances / services   1 845 €
École / cantines                  283 €
Autres                            192 €
                               -------
                                 2 320 €

BUDGETS PROTÉGÉS

Courses : 5 × 270 €            1 350 €
Fast-food : 2 × 40 €              80 €
Carburant utilisateur              75 €
Carburant conjointe               220 €
Covoiturage FAC                    140 €
                               -------
                                 1 865 €

Marge                              100 €
Réduction découvert                150 €
                               -------

À CONSERVER                      4 435 €
```

Si le compte contient :

```text
4 970 €
```

alors :

```text
TRANSFÉRABLE VERS DÉPENSES
535 €
```

---

# 72. Recalcul en cours de mois

Le système doit également pouvoir répondre :

> Combien devons-nous encore conserver aujourd'hui ?

Prendre en compte :

- charges déjà passées ;
- charges restantes ;
- budgets protégés déjà financés ;
- budgets restant à financer ;
- marge restante ;
- ajustements.

Éviter de compter deux fois une charge déjà payée.

---

# 73. Dashboard

Le dashboard doit être extrêmement lisible.

L'interface doit être conçue comme un outil de travail : montants comparables en tableaux,
actions explicites près des éléments concernés, contexte du compte et du mois toujours visible.
La qualité graphique doit servir la lecture et l'action. Les détails et réglages avancés se
dévoilent au besoin, sans imposer un apprentissage du modèle technique pour les tâches courantes.

Le solde, le reste à protéger et le transférable constituent la première lecture. La date du solde,
les données manquantes et le caractère simulé d'un autre mois doivent être explicites. Aucun état
« tout est conforme » ne doit être déduit de l'absence de transactions importées.

La direction UX/UI et ses références sont détaillées dans [UX-UI.md](UX-UI.md).

Exemple :

```text
OCTOBRE 2026

Compte CHARGES
4 970 €

À protéger encore
4 435 €

TRANSFÉRABLE
535 €

-------------------------

Charges
2 320 €

Budgets protégés
1 865 €

Marge
100 €

Réduction découvert
150 €

-------------------------

État

23 charges conformes
2 changements à vérifier
1 nouvelle opération
0 charge manquante
```

---

# 74. Page Prévision

Afficher :

```text
Prévision du mois
```

Sections :

```text
Charges obligatoires
Budgets protégés
Ajustements
Marge
Objectif de trésorerie
Résultat
```

Chaque montant doit être explicable.

L'utilisateur doit pouvoir cliquer sur n'importe quelle ligne pour comprendre son origine.

---

# 75. Explicabilité

Exemple :

```text
Courses : 1 350 €

Pourquoi ?

Budget hebdomadaire : 270 €
Samedis ce mois : 5
Calcul : 270 × 5
```

Ou :

```text
EDF : 161,50 €

Pourquoi ?

Montant actuel de la règle :
161,50 €

Derniers paiements :
161,50
161,50
161,50
```

Aucun chiffre important ne doit apparaître comme une boîte noire.

---

# 76. Page Charges

Liste :

```text
Nom
Montant prévu
Périodicité
Mode paiement
Prochaine occurrence
État
```

Actions :

```text
Créer
Modifier
Suspendre
Terminer
Historique
```

---

# 77. Page Protected Budgets

Afficher :

```text
Courses
270 €/semaine
Moyenne observée : 264 €

Fast-food
40 €/2 semaines
Moyenne observée : 36 €

Carburant conjointe
55 €/semaine
Moyenne observée : ...
```

Permettre de modifier les références manuellement.

---

# 78. Page À vérifier

Regrouper :

- charge différente ;
- charge absente ;
- transaction inconnue ;
- nouveau pattern ;
- mauvaise affectation ;
- paiement sur mauvais compte ;
- changement de montant ;
- règle potentiellement obsolète.

Objectif :

```text
gestion par exception
```

---

# 79. Historique d'une charge

Exemple :

```text
EDF

2026-10 161,50 €
2026-09 161,50 €
2026-08 148,20 €
2026-07 148,20 €
```

Afficher également les changements de règle.

---

# 80. Historique d'un ProtectedBudget

Exemple :

```text
Courses

Octobre
Prévu : 1 080 €
Réel : 1 043 €

Septembre
Prévu : 1 080 €
Réel : 1 119 €
```

Afficher éventuellement un petit graphique annuel.

---

# 81. Statistiques utiles

Limiter les statistiques à celles qui aident réellement à prévoir :

- moyenne ;
- médiane ;
- minimum ;
- maximum ;
- tendance récente ;
- erreur moyenne de prévision ;
- historique mensuel ;
- historique hebdomadaire pour les budgets concernés.

Pas de dashboard analytique inutile.

---

# 82. IA mensuelle facultative

Une fois le moteur déterministe opérationnel, l'utilisateur peut éventuellement demander une relecture IA du mois.

L'application prépare un dossier contenant :

- prévision ;
- historique pertinent ;
- anomalies ;
- nouvelles opérations ;
- écarts passés.

La demande à l'IA doit être de type :

> Vérifie la cohérence du prévisionnel. Cherche une dépense probablement oubliée ou une hypothèse manifestement fragile. Ne recalcule pas arbitrairement les charges certaines.

La réponse est un **avis**, jamais une modification automatique.

---

# 83. Priorité de l'IA

Priorité :

```text
1. onboarding initial
2. aide ponctuelle
3. contrôle facultatif
```

Elle n'est pas nécessaire pour le calcul mensuel normal.

---

# 84. Modèle de données proposé

## Account

```text
id
name
role
provider_account_id
masked_iban
current_balance_cents
last_sync_at
```

`role` :

```text
CHARGES
DEPENSES
OTHER
```

## BankTransaction

```text
id
account_id
provider_transaction_id
booking_date
operation_date
logical_date
amount_cents
currency
raw_label
normalized_label
payment_method
source
fingerprint
imported_at
```

## Charge

```text
id
name
description
status
expected_account_id
created_at
ended_at
```

## ChargeRuleVersion

```text
id
charge_id
effective_from
effective_until
variability
cadence
interval_value
payment_method
forecast_method
reference_amount_cents
tolerance_type
tolerance_value
window_start
window_end
review_month
lifecycle_type
installment_count
expected_end_date
```

## ChargeTransaction

```text
id
charge_id
transaction_id
match_type
confidence
validated_by_user
```

## ProtectedBudget

```text
id
name
status
calculation_method
reference_amount_cents
frequency
interval_value
anchor_weekday
description
```

## ProtectedBudgetTransaction

```text
id
protected_budget_id
transaction_id
type
validated_by_user
```

`type` :

```text
FUNDED
SPENT
```

## MonthlyPlan

```text
id
year
month
created_at
status
current_balance_snapshot_cents
safety_margin_cents
treasury_target_cents
```

## MonthlyAdjustment

```text
id
monthly_plan_id
name
amount_cents
reason
```

## Anomaly

```text
id
type
entity_type
entity_id
transaction_id
status
message
created_at
resolved_at
```

## ClassificationRule

```text
id
target_type
target_id
matcher_type
matcher_value
strength
active
```

---

# 85. Invariants métier

## Invariant 1

Une transaction bancaire importée est immuable.

## Invariant 2

Un transfert entre comptes connus n'est pas une dépense.

## Invariant 3

Une règle validée par l'utilisateur n'est jamais modifiée silencieusement.

## Invariant 4

Un calcul mensuel doit être entièrement explicable.

## Invariant 5

L'IA ne peut créer, modifier ou supprimer aucune règle sans validation humaine.

## Invariant 6

Une transaction réelle ne peut jamais être ignorée parce qu'elle ne correspond pas au modèle.

## Invariant 7

Une anomalie n'entraîne jamais une correction financière automatique.

## Invariant 8

Les montants monétaires sont stockés en centimes entiers, jamais en float.

---

# 86. Écrans principaux

Navigation MVP :

```text
Dashboard
Prévision
Charges
Budgets protégés
Transactions
À vérifier
Analyse historique
Paramètres
```

---

# 87. Architecture technique

Proposition cohérente avec LootSplit :

Backend :

```text
Python
FastAPI
SQLAlchemy
SQLite
```

Frontend :

```text
React
TypeScript
Vite
```

Graphiques :

```text
Recharts
```

Déploiement :

```text
Docker
Docker Compose
Unraid
GitHub Actions
GitHub Container Registry (GHCR)
```

La cible de production est le serveur Unraid du foyer.

Le modèle de livraison reprend celui de LootSplit :

- une image Docker unique embarquant le frontend compilé et le backend ;
- une construction et des tests dans GitHub Actions ;
- la publication de l'image testée dans `ghcr.io/za512/budgetward` ;
- un déploiement Docker Compose sur Unraid depuis cette image, sans compilation sur le serveur ;
- les données SQLite et les fichiers persistants dans un dossier dédié sous `/mnt/user/appdata/budgetward`, monté dans `/data` ;
- une configuration externe dans `.env`, transmise par variables d'environnement ;
- des versions identifiables et une procédure documentée de mise à jour, sauvegarde et restauration.

Le contrat de déploiement est détaillé dans [DEPLOYMENT.md](DEPLOYMENT.md).

Connecteurs :

```text
Woob
CSV
```

---

# 88. Sécurité

Exigences :

- lecture bancaire uniquement ;
- aucune initiation de paiement ;
- secrets jamais stockés en clair dans SQLite ;
- secrets dans `.env` côté serveur, exclus de Git et de l'image ; compatibilité avec les fichiers secrets pour les installations personnalisées ;
- aucun secret dans les logs ;
- aucune donnée bancaire dans une télémétrie externe ;
- pas d'analytics tiers ;
- IBAN masqués ;
- authentification locale ;
- sauvegarde régulière de SQLite ;
- export des données ;
- IA désactivable intégralement.

---

# 89. Import CSV

Le CSV est une fonctionnalité de premier rang, pas seulement un fallback.

Il sert notamment à :

- initialiser 12 mois d'historique ;
- analyser les charges passées ;
- reconstruire les moyennes ;
- fonctionner lorsque Woob est indisponible.

Créer un système de mapping des colonnes si plusieurs formats sont possibles.

---

# 90. Phase 1 — moteur financier

Développer sans IA et avec données fictives :

```text
Accounts
Transactions
Internal transfers
Charges
Charge rules
Protected budgets
Monthly planning
Forecast engine
Anomalies
Tests
```

---

# 91. Phase 2 — onboarding historique

Ajouter :

```text
CSV 12 mois
normalisation
groupement
statistiques
propositions
validation humaine
```

---

# 92. Phase 3 — Woob

Brancher les comptes CHARGES et DÉPENSES.

Valider :

- transactions carte ;
- prélèvements ;
- chèques ;
- virements ;
- transferts internes ;
- dates disponibles.

---

# 93. Phase 4 — tableaux de bord et statistiques

Ajouter :

- moyennes ;
- historique ;
- graphiques simples ;
- prévu/réel ;
- évolution des charges.

---

# 94. Phase 5 — assistance IA

Ajouter `AIAnalyzer` ou export d'un dossier IA.

Ne pas bloquer la livraison du produit sur cette phase.

---

# 95. Critères d'acceptation

## AC01 — Charge fixe

Une charge mensuelle de 100 € doit être automatiquement prévue à 100 €.

## AC02 — Révision tarifaire

Si une charge passe durablement de 100 à 110 €, le système doit signaler le changement et proposer de modifier la règle.

## AC03 — Absence

Une charge normalement attendue dans une fenêtre doit être signalée si elle n'apparaît pas.

## AC04 — Nouvelle charge

Une nouvelle opération récurrente doit être progressivement proposée comme nouvelle charge.

## AC05 — Paiement temporaire

Un paiement 4× doit pouvoir être configuré et disparaître du prévisionnel après sa dernière échéance.

## AC06 — Courses

Un mois comportant cinq samedis avec une référence à 270 € doit prévoir :

```text
1 350 €
```

## AC07 — Covoiturage

Quatre semaines FAC à 35 € doivent prévoir :

```text
140 €
```

## AC08 — Transfert interne

Un virement CHARGES -> DÉPENSES ne doit jamais être compté comme une dépense supplémentaire.

## AC09 — Consommation protégée

Les achats alimentaires affectés à Courses doivent alimenter la moyenne réelle du budget Courses.

## AC10 — Débit retardé

Une transaction effectuée samedi mais comptabilisée lundi doit pouvoir être rattachée à la bonne semaine si la date d'opération est disponible.

## AC11 — Calcul final

Le système doit fournir :

```text
À conserver
Transférable
```

sans double compter une charge déjà payée.

## AC12 — IA

Aucune proposition IA ne doit modifier les données métier tant que l'utilisateur ne l'a pas explicitement validée.

---

# 96. Exemple complet de fonctionnement

Début novembre.

Solde CHARGES après revenus :

```text
4 970 €
```

Le moteur connaît :

```text
EDF                       161,50 €
Assurances                230,00 €
Prêts                     950,00 €
Services                  185,00 €
Cantines estimées         283,00 €
Autres charges            510,50 €
```

Total charges :

```text
2 320 €
```

Budgets protégés :

```text
Courses
5 × 270 € =             1 350 €

Fast-food
2 × 40 € =                 80 €

Carburant utilisateur      75 €
Carburant conjointe       220 €

Covoiturage
4 × 35 € =                140 €
```

Total protégé :

```text
1 865 €
```

Plus :

```text
Marge sécurité             100 €
Réduction découvert        150 €
```

Donc :

```text
À CONSERVER
4 435 €
```

Et :

```text
TRANSFÉRABLE
535 €
```

L'utilisateur effectue ensuite manuellement le virement de 535 € vers DÉPENSES.

---

# 97. Expérience après quelques mois

L'objectif final est de ne plus devoir refaire un budget complet.

Début du mois :

```text
NOVEMBRE

À conserver
4 435 €

Transférable
535 €
```

Puis éventuellement :

```text
À vérifier : 2
```

L'utilisateur ouvre uniquement les exceptions :

```text
EDF a changé de tarif
Oney arrive à sa dernière échéance
```

Il valide.

Le mois est prêt.

---

# 98. Définition du produit réussi

Le produit est réussi si, après la phase d'initialisation, la préparation financière mensuelle ne nécessite plus de reconstruire mentalement toutes les charges du foyer.

L'utilisateur doit pouvoir répondre en quelques minutes à :

> **« Combien peut-on retirer du compte CHARGES sans mettre en danger le mois ? »**

Le système doit être suffisamment transparent pour que la réponse puisse toujours être expliquée.

La finalité n'est pas de prédire parfaitement chaque dépense.

La finalité est de disposer d'une estimation prudente, compréhensible et améliorable au fil du temps, avec une préférence assumée pour un léger surplus sur CHARGES plutôt qu'un sous-provisionnement.

---

# 99. Instruction générale pour Codex

Ne pas chercher à rendre le produit artificiellement « intelligent ».

Priorités :

```text
1. modèle métier propre
2. calcul déterministe
3. explicabilité
4. gestion des exceptions
5. historique
6. onboarding assisté
7. IA en dernier
```

Si une fonctionnalité IA peut être remplacée par une règle statistique simple et fiable, préférer la règle statistique.

Si une information ne peut pas être déduite de manière fiable, demander à l'utilisateur.

Si une information a été validée par l'utilisateur, la considérer comme vérité métier jusqu'à ce qu'une anomalie nécessite une nouvelle validation.

Le produit doit devenir plus silencieux à mesure qu'il connaît mieux le fonctionnement du foyer.
