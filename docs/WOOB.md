# Connexion bancaire — Crédit Agricole

BudgetWard propose une connexion en lecture seule au Crédit Agricole, via Woob et son module `cragr`. Le premier périmètre concerne les comptes courants en euros accessibles par un même accès bancaire. Les cartes, l’épargne et les opérations à venir ne sont pas importées.

Le connecteur reprend le principe de processus isolé utilisé dans LootSplit, sans dépendre de son installation ni partager ses données ou ses identifiants. Aucun appel bancaire ne se produit au démarrage de BudgetWard ou à l’ouverture d’une page. La lecture est déclenchée manuellement.

Les tests utilisent des comptes fictifs ; la compatibilité avec votre accès bancaire réel reste à vérifier après configuration. Un refus d’authentification, une validation demandée par la banque ou une indisponibilité laisse les opérations et soldes précédents intacts. L’import CSV reste accessible.

## Configurer sur Unraid

Renseigner les identifiants dans le même `.env` que la clé d'accès à BudgetWard. Aucun formulaire de l'application ne demande ces identifiants. Ajouter :

```dotenv
# Domaine de la caisse régionale, comme dans LootSplit, sans chemin de page.
BUDGETWARD_BANK_WEBSITE=www.ca-VOTRE-CAISSE.fr
BUDGETWARD_BANK_LOGIN='VOTRE_IDENTIFIANT'
BUDGETWARD_BANK_PASSWORD='VOTRE_CODE_PERSONNEL'
```

Les apostrophes préservent les caractères `$` et `#`, ainsi que les zéros initiaux. Garder `.env` privé, hors Git et hors du dossier de données. Le seul fichier `compose.yaml` suffit :

```sh
docker compose config --quiet
docker compose pull
docker compose up -d
```

Le domaine ci-dessus est un exemple à remplacer. Les secrets sont transmis par variables d'environnement et lus uniquement par le serveur. La clé d'accès à BudgetWard (`BUDGETWARD_ADMIN_TOKEN`) reste indépendante des identifiants bancaires. Pour une stack sans connexion bancaire, laisser les trois variables bancaires vides. Après modification du `.env`, exécuter `docker compose up -d` pour recréer le conteneur ; un simple redémarrage ne recharge pas ses variables.

## Choisir les comptes et importer

1. Au premier démarrage, choisir **Choisir mes comptes dans la banque**, ou utiliser **Banque → Découvrir les comptes** si le suivi existe déjà.
2. Désigner explicitement le compte CHARGES et, facultativement, le compte DÉPENSES. Aucun compte n’est présélectionné ; un même compte ne peut pas remplir les deux rôles. Les noms, quatre derniers caractères d’IBAN et soldes aident à vérifier le choix. Un compte courant sans solde disponible, par exemple en cours de création, n'est pas proposé et un avertissement indique combien de comptes sont concernés. Les autres comptes restent sélectionnables, y compris avec un solde nul. Relancer la découverte lorsque la banque fournit le solde pour pouvoir associer le nouveau compte. Un solde au format invalide continue de bloquer la découverte ; aucun montant n'est remplacé par zéro. Si le solde d'un compte déjà associé devient indisponible, la lecture des comptes associés échoue sans modifier les soldes ni les opérations.
3. Confirmer l’association. Lors du premier démarrage, les soldes proposés peuvent être corrigés et doivent être confirmés avec leur date. Pour un suivi existant, l’association seule ne change aucun solde.
4. Dans **Banque**, sélectionner le début d’historique, puis préparer l’aperçu. Les deux comptes sont lus dans la même session bancaire. La lecture peut durer trois minutes maximum. Un intervalle d’une minute sépare deux tentatives réelles ; une seule lecture peut être active à la fois.
5. Vérifier les opérations proposées et les anciens/nouveaux soldes. L’aperçu est conservé dix minutes en mémoire et reste accessible après rechargement du navigateur. Un redémarrage du serveur le supprime. La prévision utilise toujours les soldes précédents tant que l’aperçu n’est pas confirmé.
6. Décider pour chaque doublon possible, puis confirmer explicitement l’import et le remplacement des soldes. Les deux comptes sont mis à jour dans une seule transaction SQLite. Un conflit sur l’un empêche l’écriture sur l’autre.
7. Affecter les opérations et identifier les virements internes dans **Opérations**. La présence d’un virement ne crée pas automatiquement une consommation ou une règle de charge. Utiliser ensuite **Historique** pour valider les charges récurrentes.

La période demandée est inclusive, jusqu’à aujourd’hui, limitée à deux ans et à 5 000 opérations par compte. La banque peut fournir moins d’historique. La date comptable pilote les mois ; la date d’achat, lorsqu’elle existe, reste informative. Les montants sont convertis exactement en centimes.

Les références bancaires déjà présentes ne créent pas de doublons. Une référence contradictoire bloque l’import. En l’absence de référence comparable, une opération ayant la même date comptable, le même montant et le même libellé nécessite une décision humaine si ses dates d’achat sont compatibles ou absentes. Aucun rapprochement approximatif n’est appliqué. Les données bancaires originales restent immuables ; les affectations sont séparées.

Un changement local de solde ou un autre import après préparation peut rendre l’aperçu obsolète : il faut alors le recalculer. Les dates **Dernière tentative de lecture** et **Dernier import confirmé** distinguent une lecture d’une mise à jour réellement enregistrée. Les associations existantes ne peuvent pas être remplacées silencieusement par d’autres comptes.

## Validation demandée ou erreur

Si la banque demande une validation, ouvrir son site officiel ou son application, accomplir la validation, puis relancer la lecture ici. BudgetWard ne propose pas de formulaire OTP et n’entretient pas de session bancaire persistante. Si la banque impose un parcours interactif incompatible, utiliser le CSV.

Les erreurs affichées sont des messages prédéfinis ; les réponses, traces et exceptions brutes du fournisseur ne sont pas renvoyées au navigateur. Aucun virement ne peut être déclenché depuis BudgetWard.

Un HTTP 502 avec le code `data` indique que BudgetWard a rejeté les données pendant leur lecture ou leur validation. Pendant la découverte des comptes, les comptes sans solde sont écartés avec un avertissement ; le champ `diagnostic` distingue un solde invalide (`balance_invalid`), une réponse au mauvais format (`accounts_format`), un compte invalide (`account_invalid`), des identifiants dupliqués (`accounts_duplicate`), plus de 100 comptes (`accounts_limit`) et une erreur interne (`discovery_unexpected`). L'interface affiche le message correspondant. Ces diagnostics ne contiennent aucun identifiant, solde ou réponse brute de la banque. Conserver le message et le diagnostic pour le dépannage ; un ancien message générique seul ne permet pas d'identifier la cause exacte.

## Installation et fonctionnement techniques

L’image Docker inclut Woob verrouillé par `uv.lock` ainsi que le module officiel `cragr`. L’archive est récupérée pendant le build depuis la révision `3bc0f159c65fc2685c8b8787d0e25ff55f896f73`, vérifiée par SHA-256 `147b7d39bb12a7ef1750fceba0999a8acdff8382e01cbb734b5fd9f17e989e2e`. Le script n’extrait qu’une liste de fichiers autorisés et conserve les licences Woob dans `/app/bank_modules`. Aucune mise à jour de module n’est téléchargée lors d’une consultation bancaire ; mettre à jour le module exige de livrer une nouvelle image.

Pour le développement local :

```powershell
uv sync --frozen
uv run python scripts/fetch_woob_modules.py
uv run --env-file .env uvicorn budgetward.api:app_factory --factory --host 127.0.0.1 --port 8010 --no-access-log
```

Chaque lecture lance un processus Python temporaire. Les identifiants lui sont transmis sur son entrée standard, jamais comme arguments de commande. Les variables contenant la clé d'accès et les identifiants sont retirées de l'environnement hérité par ce processus. La sortie des bibliothèques et leurs logs sont neutralisés. Le processus utilise uniquement les capacités de consultation de Woob. Les identifiants des comptes associés restent côté serveur : les réponses publiques utilisent des choix opaques temporaires et des IBAN masqués. L’export JSON exclut ces associations ; la sauvegarde SQLite complète contient naturellement les identifiants techniques des comptes associés, mais aucun secret de connexion.

Le mode démonstration ignore les secrets bancaires, utilise un connecteur fictif sans réseau et le signale dans la page Banque. Les tests navigateur utilisent des bases temporaires ; leur connecteur est également fictif, même pour le parcours de premier démarrage authentifié.

Références officielles : [capacités bancaires Woob](https://woob.dev/api/capabilities/bank/base/) et [chargement local avec WoobBase](https://woob.dev/api/core/woob/).

Pour les installations personnalisées existantes, le serveur accepte encore `BUDGETWARD_ADMIN_TOKEN_FILE`, `BUDGETWARD_BANK_LOGIN_FILE` et `BUDGETWARD_BANK_PASSWORD_FILE` si la variable correspondante sans `_FILE` est absente. Une variable présente, même vide, prend la priorité. Le Compose fourni utilise désormais exclusivement les valeurs du `.env`.
