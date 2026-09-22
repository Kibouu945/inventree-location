# InvenTreeLocation

Module de gestion des locations événementielles pour InvenTree.

## Prérequis

- [Docker](https://docs.docker.com/get-docker/) et Docker Compose

## Démarrage rapide

```bash
# Lancer tous les services (db, inventree, backend, frontend)
make up

make provision
```

Au premier lancement, les migrations Django s'exécutent automatiquement et un utilisateur admin est créé.

| Service      | URL                   | Description                                           |
| ------------ | --------------------- | ----------------------------------------------------- |
| InvenTree    | http://localhost:8000 | Interface principale (identifiants admin dans `.env`) |
| Frontend dev | http://localhost:5174 | Serveur Vite pour le hot-reload du plugin             |
| PostgreSQL   | localhost:5432        | Base de données                                       |

## Commandes disponibles

```bash
make up               # Build et démarre tous les services
make provision        # Active le plugin + intégrations, données de démo, permissions, dashboards
make provision-plugin # Juste l'activation du plugin + des intégrations (sans les données de démo)
make down              # Arrête tous les services
make migrate           # Exécute les migrations Django
make test               # Lance les tests du plugin
make logs                # Affiche les logs en temps réel
make shell                # Ouvre un shell dans le conteneur InvenTree
make clean                 # Arrête les services et supprime les volumes (refaire `make provision` après)
```

## Architecture

```
docker-compose.yml
├── db         → PostgreSQL 17
├── inventree  → Serveur web InvenTree (gunicorn) + plugin installé
├── backend    → Worker background (django-q2) pour le traitement des événements
└── frontend   → Serveur Vite (hot-reload des composants React)
```

Le code Python du plugin (`inventree_location/`) est monté en volume dans les conteneurs InvenTree. Les modifications sont prises en compte après un redémarrage (`docker compose restart inventree backend`).

Le code React (`frontend/src/`) bénéficie du hot-reload via Vite. Les composants du plugin sont chargés par InvenTree depuis le serveur de dev.

## Configuration

Copier `.env.docker` vers `.env` pour personnaliser les variables d'environnement :

```bash
cp .env.docker .env
```

## Authentification

Le plugin **réutilise l'authentification d'InvenTree** (DRF Token). Aucun
endpoint `/api/auth/login` ou `/api/auth/logout` n'est exposé par le plugin
lui-même.

Pour obtenir un token, appeler l'endpoint standard d'InvenTree. Les credentials
ci-dessous sont des **placeholders** : remplace-les par tes propres identifiants
et ne commit jamais de vrais secrets dans le repo.

```bash
# Dev local uniquement.
curl -u <USERNAME>:<PASSWORD> http://localhost:8000/api/user/token/
# → {"token": "<TOKEN>"}
```

Tous les endpoints du plugin (`/plugin/inventree-location/...`) exigent le
header `Authorization: Token <token>` :

```bash
curl -H "Authorization: Token <TOKEN>" \
     http://localhost:8000/plugin/inventree-location/example/
```

Une requête sans token reçoit `401 Unauthorized`. La déconnexion (révocation
du token) se fait via l'UI ou l'API d'InvenTree.

## Client Python `InvenTreeClient`

Le plugin fournit une classe `InvenTreeClient` pour interroger l'API REST
d'InvenTree depuis du code Python (vues, scripts, tâches, tests d'intégration) :

```python
from inventree_location.clients import InvenTreeClient

with InvenTreeClient(base_url="http://localhost:8000", token="<TOKEN>") as c:
    categories = c.list_categories()
    parts = c.list_parts(category=3, active=True)
    part = c.get_part(42)
```

Pour récupérer un client préconfiguré à partir des variables `INVENTREE_API_URL`
et `INVENTREE_API_TOKEN` (settings Django ou environnement) :

```python
from inventree_location.clients import get_default_client

client = get_default_client()
```

## Installation manuelle (sans Docker)

```bash
pip install inventree-inventree-location
```
