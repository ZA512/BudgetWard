# BudgetWard

Prévoir ce qui doit rester sur le compte CHARGES et calculer le disponible du foyer. Application auto-hébergée en français, indépendante de LootSplit. [PRD](docs/PRD.md) · [Direction UX/UI](docs/UX-UI.md) · [Import CSV et analyse](docs/CSV.md) · [Connexion bancaire](docs/WOOB.md) · [Déploiement Unraid](docs/UNRAID.md).

## Fonctionnalités disponibles

Interface React/TypeScript pensée comme un outil : synthèse du mois, tableaux de charges et budgets, explication du calcul, opérations à affecter et écarts à vérifier. Backend FastAPI/SQLAlchemy, SQLite et montants entiers en centimes.

Disponibles : comptes CHARGES/DÉPENSES et soldes constatés manuellement ; charges à montant exact, fréquences mensuelle, hebdomadaire, toutes les deux semaines, trimestrielle et annuelle ; fin de charge et échéancier ; nouvelles périodes tarifaires conservant l'historique ; budgets calculés par occurrences ; ajustements de nombre pour un mois ; réserve et dépenses ponctuelles ; opérations réelles renseignées manuellement et affectations corrigibles ; financement distinct de la consommation ; anomalies de montant, de compte et d'occurrence supplémentaire ; export JSON et sauvegarde SQLite.

Le deuxième lot ajoute l'import CSV avec mapping des colonnes, formats et encodage configurables, aperçu préalable et validation atomique. Les références bancaires et les fichiers déjà traités empêchent les réimports ; les doublons possibles sans référence nécessitent une décision humaine, sans fusion approximative. L'analyse historique regroupe les débits non affectés, affiche les statistiques et propose une fréquence probable. La création d'une charge ou le rattachement à une charge existante exige de valider les paramètres et les opérations choisies. Les groupes ignorés restent consultables et rétablissables.

Le troisième lot ajoute la lecture bancaire Crédit Agricole via Woob : secrets côté serveur, choix explicite des comptes, lecture manuelle, aperçu puis confirmation des opérations et des soldes. Les deux comptes sont mis à jour ensemble ou ne le sont pas. Les erreurs conservent les données précédentes. La démonstration utilise un connecteur exclusivement fictif ; la connexion bancaire réelle reste à valider avec votre accès. Voir [le guide bancaire](docs/WOOB.md).

L'application ne couvre pas encore tout le PRD : détection des fenêtres de paiement manquantes, charges variables et méthodes statistiques de prévision, reconnaissance automatique par règles validées, statistiques hebdomadaires des budgets et IA restent à développer. Les ajustements ponctuels sont retirés manuellement après paiement. Le rapprochement des charges se fait par mois comptable et ordre des échéances, sans recherche automatique de correspondance entre mois. Les références des budgets sont fixées à leur création ; leur édition versionnée reste à ajouter.

## Essayer la démonstration locale

Prérequis : Python 3.12 à 3.14, uv, Node.js 22.12 ou supérieur.

Depuis la racine, sous PowerShell :

```powershell
uv sync --frozen
npm --prefix frontend ci
npm --prefix frontend run build
$env:BUDGETWARD_DEMO = 'true'
uv run uvicorn budgetward.api:app_factory --factory --host 127.0.0.1 --port 8010 --no-access-log
```

Ouvrir [BudgetWard](http://127.0.0.1:8010/). La démonstration utilise exclusivement `data/demo.db`, sans connexion bancaire ni authentification. Elle démarre en octobre 2026 avec des données fictives correspondant au calcul de 4 435 € à protéger et 535 € transférables. Les modifications de démonstration persistent. Ne pas activer ce mode pour des données réelles.

Pour développer le frontend avec rechargement automatique : `npm --prefix frontend run dev`. Vite transmet `/api` au backend local sur le port 8010.

## Démarrer un vrai suivi

Créer un fichier secret `secrets/admin_token` contenant une clé aléatoire d'au moins 24 caractères. Le fichier et `.env` sont ignorés par Git. Pour générer ce fichier sans afficher la clé :

```powershell
New-Item -ItemType Directory -Path secrets -Force
uv run python -c "import secrets; from pathlib import Path; Path('secrets/admin_token').write_text(secrets.token_urlsafe(48), encoding='utf-8')"
$env:BUDGETWARD_DEMO = 'false'
$env:BUDGETWARD_ADMIN_TOKEN_FILE = (Resolve-Path secrets/admin_token).Path
uv run uvicorn budgetward.api:app_factory --factory --host 127.0.0.1 --port 8010 --no-access-log
```

La base réelle est `data/app.db`. La page demande la clé, puis les comptes et leurs soldes à une date commune. La session utilise un cookie HttpOnly de huit heures et une protection CSRF. Aucun identifiant n'est conservé dans le stockage du navigateur. Les redémarrages invalident les sessions. En HTTPS, activer `BUDGETWARD_SECURE_COOKIE=true`.

## Livraison Docker

`compose.yaml` utilise l'image préconstruite `ghcr.io/za512/budgetward:latest`. Le workflow GitHub Actions effectue les vérifications, construit l'image Linux amd64, la teste avec Compose puis publie cette même image. Pull requests : tests sans publication. `main` : `latest` et tag du commit. Tags `v*` : version et tag du commit.

La publication est déclenchée par les pushs sur `main` et les tags `v*` ; son résultat est visible dans [GitHub Actions](https://github.com/ZA512/BudgetWard/actions). Sur Unraid, suivre [le guide](docs/UNRAID.md) ; aucune compilation n'est nécessaire sur le serveur.

## Vérifications

```powershell
uv run pytest -q
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
npm --prefix frontend run build
npm --prefix frontend test
npm --prefix frontend run format:check
```

Pour les parcours navigateur, depuis `frontend` :

```powershell
npx playwright install chromium
npm run test:e2e
```

Les tests démarrent des serveurs sur 8765, 8766 et 8767 avec des bases temporaires et des connecteurs fictifs. Ils ne touchent pas à `data/app.db`.

Avec Docker disponible : `uv run python scripts/smoke_compose.py`. Pour vérifier une image déjà construite sans build ni téléchargement : `uv run python scripts/smoke_compose.py --image budgetward:smoke`.

Le schéma SQLite est en version 3. La mise à niveau depuis les versions 1 ou 2 sauvegarde d'abord la base sous `data/backups/app.db/before-migration/`, puis ajoute les tables manquantes de reçus d'import, de groupes ignorés et d'associations bancaires ; les opérations, affectations et règles existantes sont conservées. Une copie SQLite cohérente est créée à chaque démarrage dans `data/backups/app.db/startup-AAAA-MM-JJ.db` ; un autre démarrage le même jour remplace cette copie. Chaque base utilise son propre sous-dossier, notamment `demo.db` pour la démonstration. Les anciennes copies directement sous `data/backups/` restent intactes. Le téléchargement manuel est disponible dans Réglages. La planification quotidienne avec rotation reste à développer ; conserver des copies hors du serveur dès l'utilisation de données réelles.

Validation locale du 21 octobre 2026 : 88 tests Python, 7 tests monétaires frontend et 9 parcours Playwright réussis ; compilation TypeScript/Vite, formatage et Ruff ; image Docker construite et scénario Compose réussi avec chargement du module Woob, authentification, CSV, validation historique, sauvegarde et persistance après recréation. Les tests couvrent aussi les doublons entre sources, les imports simultanés, les aperçus obsolètes, l'atomicité bancaire sur deux comptes, les erreurs du fournisseur, les migrations depuis les versions 1 et 2 et l'isolation de la démonstration. Captures ordinateur et mobile examinées. Le déploiement Unraid, les essais bancaires réels et les essais d'intuitivité avec des utilisateurs restent à effectuer.
