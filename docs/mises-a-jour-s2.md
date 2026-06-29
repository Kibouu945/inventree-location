# Mises à jour — fin S1/S2 (juin 2026)

Ce document décrit les évolutions apportées au plugin **InvenTreeLocation** lors
de la finalisation des sprints S1/S2 : correction de l'algorithme de conflits,
complétion du backend catalogue/réservation, mise en place des rôles, et premier
écran frontend du catalogue.

> Branche : `feature/s2-backend-completion`
> Suite de tests : **148 tests backend** + **13 tests frontend**, verts.

---

## 1. Correction de bug — algorithme de conflits (CON-01)

`compute_conflicts()` filtrait les réservations sur `lignes__article_id`, un
champ **inexistant** (le modèle `LigneReservation` porte un FK `part`). En
production, l'appel levait une `FieldError`.

- ✅ Corrigé en `lignes__part_id`, exclusion conditionnelle de la réservation courante.
- ✅ Ajout de **tests base de données** couvrant `compute_conflicts` (le bug passait
  inaperçu : seule la variante en mémoire `find_conflicting_reservations` était testée).

---

## 2. Backend — complétions S2

| Ticket | Évolution |
|--------|-----------|
| **RES-02** | Filtres `statut`, `date_from`, `date_to` sur la liste des réservations ; **lignes imbriquées** en POST/PATCH (`LigneReservationSerializer`). |
| **RES-01** | Index composite `(date_retrait_prevue, date_retour_prevue, statut)` sur `Reservation`. |
| **CAT-05** | Drapeaux `rentable` / `consommable` câblés sur `RentableItem` (fin du mapping temporaire sur `active`) ; filtre par défaut « louable uniquement » ; endpoint **bulk-update**. |
| **CONSO-01** | `consommable` exposé dans le catalogue. |
| **CAT-02** | Pagination catalogue à **50 / page**. |

---

## 3. Rôles & personas (TR-03)

Sept rôles matérialisés par des **groupes Django** (`auth.Group`), créés par la
migration `0003_create_role_groups` (idempotente, réversible) :

`admin` · `gestionnaire` · `magasinier` · `livreur` · `sav` · `organisateur` · `lecteur`

Les permissions sont appliquées au niveau de l'API par des classes DRF
(`inventree_location/permissions.py`) basées sur l'appartenance aux groupes.

- Un **superutilisateur** est toujours autorisé.
- Un utilisateur **sans rôle connu** est refusé (`403`).

### Mapping appliqué aux endpoints actuels

| Ressource | Lecture | Écriture |
|-----------|---------|----------|
| Catalogue | tous les rôles | `admin`, `gestionnaire` |
| Lieux | tous les rôles | `admin`, `gestionnaire` |
| Réservations | tous les rôles | `admin`, `gestionnaire`, `organisateur` |

> Les actions retours / livraisons / SAV arriveront avec leurs endpoints aux
> sprints suivants ; magasinier, livreur, sav et lecteur sont donc en lecture
> seule sur les endpoints existants.

---

## 4. Endpoints REST (état actuel)

Tous préfixés par `/plugin/inventree-location/`.

| Méthode(s) | Chemin | Rôle requis (écriture) |
|------------|--------|------------------------|
| GET | `example/` | authentifié |
| GET, POST | `lieux/` | admin, gestionnaire |
| GET, PUT, PATCH, DELETE | `lieux/<pk>/` | admin, gestionnaire |
| GET | `geocode/?address=` | (lecture) |
| GET | `catalog/` | (lecture) |
| PATCH | `catalog/rentable/` (bulk) | admin, gestionnaire |
| GET, PATCH | `catalog/<pk>/rentable/` | admin, gestionnaire |
| GET, POST | `reservations/` | admin, gestionnaire, organisateur |
| GET, PUT, PATCH, DELETE | `reservations/<pk>/` | admin, gestionnaire, organisateur |

### Filtres du catalogue (`GET catalog/`)

- `search` : texte (nom, description, IPN)
- `category` / `categories` : id(s) de catégorie
- `active` : `true` / `false`
- `rentable` : `true` (défaut) / `false` / `all`
- `page`, `page_size`

### Création de réservation avec lignes (`POST reservations/`)

```json
{
  "prestation": 1,
  "demandeur": 4,
  "date_demande": "2026-06-26T10:00:00Z",
  "lignes": [
    { "part": 12, "quantite_demandee": 3 }
  ]
}
```

---

## 5. Frontend — catalogue (S2)

Le frontend est un **plugin InvenTree** (composants injectés, pas de routeur).

- **CAT-02 / CAT-03 — Liste catalogue** (`src/Catalog.tsx`, exposé en *dashboard item*) :
  tableau paginé (50/page), recherche debouncée (300 ms), filtre catégories
  (multi-select), filtre louable, état des filtres porté par l'URL.
- **CAT-04 / CAT-05 — Fiche location du Part** (`src/Panel.tsx`, panneau sur la
  page Part) : drapeaux louable/consommable + toggles **réservés aux
  gestionnaires** (UI masquée selon le rôle), bouton « réservations en cours ».

La logique pure des filtres (`src/catalog/catalogParams.ts`) est testée
indépendamment du rendu (vitest).

---

## 6. Lancer et tester

```bash
# Backend (hors container InvenTree)
.venv/bin/python -m pytest -q

# Frontend
cd frontend
npm run lint
npm run test
npm run build      # génère inventree_location/static/*.js

# Stack complète (InvenTree + plugin)
make up            # http://localhost:8000
```

---

## 7. Limites connues / différé

- **US-01 (mini-carte GPS)** : différée — le `Lieu` n'a pas de page hôte
  InvenTree ; à traiter avec un futur écran de gestion des lieux.
- **Catégories du filtre catalogue** : dérivées des résultats chargés (MVP).
- **Bouton « réservations en cours »** : pointe vers l'endpoint API en
  attendant l'écran réservations (S3).
- **Validation visuelle** : non effectuée hors container InvenTree (compilation,
  typage et tests unitaires uniquement).
