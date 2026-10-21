# BudgetWard sur Unraid

Les fichiers de déploiement sont fournis ; vérifier que GitHub Actions a publié l'image avant le premier démarrage. La validation sur votre serveur reste à effectuer.

## Préparer les fichiers

Placer `compose.yaml` et une copie de `.env.example` nommée `.env` dans le dossier de votre stack Compose. Créer le dossier de données :

```sh
mkdir -p /mnt/user/appdata/budgetward
```

Générer une clé aléatoire avec `openssl rand -hex 32` et la copier dans `BUDGETWARD_ADMIN_TOKEN` ci-dessous. Elle doit contenir au moins 24 caractères. Aucun dossier `secrets` ni montage de fichier secret n'est nécessaire.

Configurer `.env` :

```dotenv
BUDGETWARD_IMAGE=ghcr.io/za512/budgetward:latest
APPDATA_PATH=/mnt/user/appdata/budgetward
BUDGETWARD_ADMIN_TOKEN='REMPLACER_PAR_LA_CLE_GENEREE'
PUID=99
PGID=100
BIND_ADDRESS=0.0.0.0
PORT=8010
BUDGETWARD_SECURE_COOKIE=false
```

Les valeurs `99:100` correspondent à la convention courante `nobody:users` ; vérifier leur adéquation avec les permissions de votre serveur. Le dossier de données doit être accessible en écriture par cette identité. Adapter le port pour éviter un conflit. `0.0.0.0` rend l'application accessible sur les interfaces réseau du serveur ; choisir l'adresse LAN du serveur pour limiter l'écoute à celle-ci.

Compose charge le `.env` et transmet les valeurs au conteneur par variables d'environnement. Garder ce fichier privé : il contient les secrets en clair et les administrateurs Docker peuvent consulter les variables du conteneur. Ne pas partager la sortie de `docker compose config` ; utiliser `docker compose config --quiet` pour vérifier la configuration sans afficher les valeurs. Les secrets ne sont pas stockés dans SQLite. Le compte CHARGES et le compte DÉPENSES ne partagent aucune donnée avec LootSplit.

## Télécharger et démarrer

Attendre que le workflow **Docker** ait publié la première image. Si le package GHCR est privé, exécuter `docker login ghcr.io` avec un identifiant GitHub autorisé à lire ce package et un jeton disposant de `read:packages`.

```sh
docker compose pull
docker compose up -d
docker compose ps
```

Ouvrir `http://ADRESSE_UNRAID:8010`, saisir la valeur de `BUDGETWARD_ADMIN_TOKEN`, puis renseigner les soldes de départ. Le suivi réel est initialement vide. Le mode démonstration n'est pas activé par Compose.

Pour un reverse proxy HTTPS, définir `BUDGETWARD_SECURE_COOKIE=true` et adapter l'adresse d'écoute au réseau du proxy. Le conteneur expose l'interface et l'API sur son port 8000. `/health` ne renvoie que l'état du service.

## Mettre à jour

1. Télécharger une sauvegarde dans **Réglages → Sauvegarde complète SQLite** et la conserver hors du serveur.
2. Choisir si souhaité un tag `v*` ou un digest dans `BUDGETWARD_IMAGE`, plutôt que `latest`.
3. Exécuter `docker compose pull`, puis `docker compose up -d`.
4. Vérifier l'état du service et le contenu de la prévision.

La base `/data/app.db` et ses copies de démarrage se trouvent dans `/mnt/user/appdata/budgetward`. Leur persistance est indépendante de l'image. Le schéma est en version 3 : lors d'une mise à niveau depuis la version 1 ou 2, une sauvegarde préalable est conservée dans `backups/app.db/before-migration/`, puis les tables manquantes de reçus CSV, de groupes ignorés et d'associations bancaires sont ajoutées. Les données existantes sont conservées. Revenir à une image plus ancienne ne garantit pas sa compatibilité avec une base migrée.

## Ajouter la connexion bancaire

Renseigner `BUDGETWARD_BANK_WEBSITE`, `BUDGETWARD_BANK_LOGIN` et `BUDGETWARD_BANK_PASSWORD` dans le même `.env`, puis exécuter `docker compose up -d` pour recréer le conteneur avec ces valeurs. Le seul `compose.yaml` suffit. Suivre [WOOB.md](WOOB.md) pour le domaine de la caisse régionale Crédit Agricole et les détails. La lecture est manuelle et demande une confirmation des opérations et des soldes. Les identifiants ne sont jamais saisis dans l'interface. La connexion réelle doit être vérifiée avec votre accès ; les validations automatiques du projet utilisent uniquement des données fictives.

## Migrer depuis les fichiers secrets

Copier le contenu de `secrets/admin_token` dans `BUDGETWARD_ADMIN_TOKEN`, celui de `secrets/bank_login` dans `BUDGETWARD_BANK_LOGIN` et celui de `secrets/bank_password` dans `BUDGETWARD_BANK_PASSWORD`. Retirer les anciennes variables `ADMIN_TOKEN_FILE`, `BANK_LOGIN_FILE` et `BANK_PASSWORD_FILE` du `.env`, remplacer `compose.yaml` par la nouvelle version puis recréer le conteneur avec `docker compose up -d`. Conserver la même clé pour se reconnecter. `compose.bank.yaml` reste accepté pour les anciennes commandes, mais n'est plus nécessaire.

## Restaurer une sauvegarde

1. Arrêter BudgetWard avec `docker compose down`.
2. Conserver le dossier de données actuel à part pour pouvoir le récupérer.
3. Préparer un **nouveau dossier vide** et y copier la sauvegarde sous le nom `app.db`. Ne pas réutiliser les fichiers `app.db-wal` ou `app.db-shm` de l'ancienne base.
4. Donner à ce dossier et à la base les permissions de l'identité `PUID:PGID`.
5. Pointer `APPDATA_PATH` sur ce nouveau dossier et choisir l'image compatible avec la sauvegarde.
6. Relancer `docker compose up -d`, se reconnecter puis vérifier les comptes, opérations et calculs.

Une copie cohérente est faite au démarrage dans `backups/app.db/`, au maximum un fichier par date, remplacé lors des redémarrages du même jour. Chaque base possède son sous-dossier pour isoler notamment les sauvegardes de démonstration. Les anciennes copies directement sous `backups/` restent conservées. Les sauvegardes quotidiennes planifiées avec rotation ne sont pas encore disponibles. Utiliser le téléchargement manuel avant toute mise à jour.
