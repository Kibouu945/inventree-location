# InvenTreeLocation

Module de gestion des locations événementielles pour InvenTree.

## Prérequis

- [Docker](https://docs.docker.com/get-docker/) et Docker Compose

## Démarrage rapide

```bash
# Lancer tous les services (db, inventree, backend, frontend)
make up
```

Au premier lancement, les migrations Django s'exécutent automatiquement et un utilisateur admin est créé.

| Service | URL | Description |
|---------|-----|-------------|
| InvenTree | http://localhost:8000 | Interface principale (admin / admin123) |
| Frontend dev | http://localhost:5174 | Serveur Vite pour le hot-reload du plugin |
| PostgreSQL | localhost:5432 | Base de données |

## Commandes disponibles

```bash
make up        # Build et démarre tous les services
make down      # Arrête tous les services
make migrate   # Exécute les migrations Django
make test      # Lance les tests du plugin
make logs      # Affiche les logs en temps réel
make shell     # Ouvre un shell dans le conteneur InvenTree
make clean     # Arrête les services et supprime les volumes
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

## Installation manuelle (sans Docker)

```bash
pip install inventree-inventree-location
```
