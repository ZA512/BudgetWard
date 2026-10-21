# Déploiement cible — Unraid, Docker Compose et GitHub Actions

Ce document fixe le modèle de déploiement de BudgetWard : Dockerfile, Compose, workflow GitHub Actions et test du conteneur avant publication sur GHCR. Le guide opérationnel est dans [UNRAID.md](UNRAID.md) ; la validation sur votre serveur reste à effectuer.

## Modèle retenu

```text
Dépôt GitHub ZA512/BudgetWard
    → GitHub Actions : vérifications, construction, test du conteneur
    → GHCR : publication de l'image testée
    → Unraid : téléchargement et démarrage avec Docker Compose
```

La référence est le fonctionnement du projet local LootSplit : `Dockerfile`, `compose.yaml` et `.github/workflows/docker.yml`. BudgetWard conserve son dépôt, son image et ses données propres, sans dépendance à LootSplit.

## Image applicative

- Image cible : `ghcr.io/za512/budgetward`.
- Plateforme initiale : `linux/amd64`, comme LootSplit.
- Construction en plusieurs étapes : compilation React/TypeScript avec Vite, puis assemblage du runtime Python/FastAPI et des fichiers statiques.
- Le backend sert l'API et l'interface compilée sur un même port interne, prévu à `8000`.
- Les dépendances sont verrouillées ; l'image inclut Woob et le module Crédit Agricole issu d'une archive officielle vérifiée. Aucun module n'est téléchargé au démarrage ou pendant une consultation bancaire.
- Le conteneur s'exécute sans privilèges root et accepte l'identité utilisateur/groupe configurée par Compose.
- Un endpoint `/health` permet de vérifier la disponibilité sans exposer de données financières.

## Construction et publication

Le workflow `.github/workflows/docker.yml` suit ces règles :

| Événement | Vérifications | Publication |
| --- | --- | --- |
| Pull request vers `main` | Tests, build et test du conteneur | Aucune |
| Push sur `main` | Tests, build et test du conteneur | `latest` et `sha-<SHA complet>` |
| Tag Git `v*` | Tests, build et test du conteneur | Tag de version et `sha-<SHA complet>`, sans déplacer `latest` |
| Déclenchement manuel | Mêmes vérifications | Publication uniquement pour `main` ou un tag `v*` |

La publication porte sur l'image qui a passé les tests, sans seconde construction. L'accès en écriture à GHCR est limité à la publication via le `GITHUB_TOKEN` du dépôt. Aucun secret bancaire ni donnée réelle du foyer n'est utilisé dans les builds ou les tests.

Les vérifications couvrent le moteur financier, la construction du frontend et un scénario Compose avec données fictives : démarrage, disponibilité, authentification et conservation des données après recréation du conteneur.

## Exécution sur Unraid

Le `compose.yaml` de production référence une image publiée avec `image:`, sans directive `build:`. Le serveur a uniquement besoin du fichier Compose, de sa configuration, des fichiers secrets et du dossier de données. Il n'a pas besoin du code source ni d'outils de compilation.

Conventions à prévoir :

| Paramètre | Rôle |
| --- | --- |
| `BUDGETWARD_IMAGE` | Image sélectionnée ; valeur par défaut `ghcr.io/za512/budgetward:latest` |
| `APPDATA_PATH` | Dossier hôte persistant ; cible Unraid `/mnt/user/appdata/budgetward` |
| `PUID` / `PGID` | Identité disposant des droits d'écriture sur ce dossier |
| `BIND_ADDRESS` / `PORT` | Adresse et port d'accès sur l'hôte, configurables pour cohabiter avec LootSplit |
| `TZ` | Fuseau horaire, par défaut `Europe/Paris` |

La base SQLite est conservée dans `/data/app.db`. Les sauvegardes et les autres fichiers qui doivent survivre à une recréation du conteneur sont également placés sous `/data`. Les secrets sont fournis séparément par fichiers montés ou Docker secrets ; ils ne sont intégrés ni à l'image ni à la base.

Compose prévoit un redémarrage `unless-stopped`, un contrôle de santé, un arrêt propre et les permissions nécessaires au volume. Le système de fichiers du conteneur est en lecture seule, avec des emplacements temporaires et persistants explicitement autorisés en écriture. SQLite et les tâches planifiées utilisent initialement une seule instance applicative.

## Mise à jour et restauration

La procédure cible est :

1. Sauvegarder la base avec une méthode compatible avec SQLite en fonctionnement et conserver les fichiers de configuration nécessaires à une restauration.
2. Choisir si nécessaire une version précise ou un digest via `BUDGETWARD_IMAGE`.
3. Exécuter `docker compose pull`, puis `docker compose up -d`.
4. Vérifier la santé du service et l'accès aux données existantes.

Les migrations de schéma sont versionnées et précédées d'une sauvegarde. Le schéma courant est en version 3 ; la migration depuis les versions 1 ou 2 ajoute les tables manquantes de reçus CSV, de groupes ignorés et d'associations bancaires sans modifier les données existantes. Les sauvegardes sont isolées par nom de base, sous `/data/backups/app.db/` pour la production. Un retour à une ancienne image peut nécessiter de restaurer la base compatible ; changer uniquement le tag ne garantit pas un retour arrière après migration.

L'option bancaire utilise `compose.bank.yaml` en complément du fichier principal. Les identifiants restent dans deux fichiers secrets montés, séparés de la clé d'accès à BudgetWard. Le guide [WOOB.md](WOOB.md) détaille la configuration et le parcours de confirmation. La stack de base reste utilisable sans ces secrets.

Le guide [UNRAID.md](UNRAID.md) détaille la création du dossier `appdata`, ses permissions, l'accès réseau ou par reverse proxy, la connexion au registre si l'image est privée, le premier démarrage, les mises à jour et la restauration.

## Livrables du premier lot

- `Dockerfile` et `.dockerignore`.
- `compose.yaml` de production et `.env.example` sans secrets.
- Workflow `.github/workflows/docker.yml`.
- Test de démarrage et de persistance du conteneur.
- Guide `docs/UNRAID.md` et procédure de sauvegarde/restauration.

Le déploiement fait partie du socle technique dès la phase 1 du PRD. Il doit permettre de livrer progressivement les fonctionnalités sans changer ce modèle d'exploitation.
