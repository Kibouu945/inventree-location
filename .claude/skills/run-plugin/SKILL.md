---
name: run-plugin
description: Lancer la stack InvenTree + plugin Location et la piloter au navigateur (Playwright) pour vérifier qu'un changement fonctionne réellement. À utiliser pour valider une PR, reproduire un bug d'UI, ou prendre des captures. Les tests unitaires ne couvrent pas l'UI de ce projet — la vérification navigateur est le seul filet.
---

# Lancer et piloter le plugin InvenTree Location

Le plugin vit **à l'intérieur** d'InvenTree : il n'y a pas d'app autonome à
lancer. Tout passe par la stack Docker, et l'UI du plugin est faite de
**widgets de dashboard**, pas de pages.

## 1. Démarrer la stack

```bash
open -a Docker                      # si le daemon est éteint
until docker info >/dev/null 2>&1; do sleep 2; done
docker compose up --build -d        # = make up
until curl -sf http://localhost:8000/api/ >/dev/null; do sleep 3; done
```

Services : `db` (postgres:17), `inventree` (gunicorn :8000), `backend` (worker),
`frontend` (Vite :5174). Admin : **`admin` / `admin123`**.

Token API :

```bash
TOKEN=$(curl -s -u admin:admin123 http://localhost:8000/api/user/token/ \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
```

Endpoints du plugin sous `/plugin/inventree-location/`.

## 2. Déployer un changement — le piège nº1

**Après TOUTE modification, il faut redémarrer le conteneur `inventree`.**

```bash
cd frontend && npm run build && cd ..   # écrit dans inventree_location/static/
docker compose restart inventree
until curl -sf http://localhost:8000/api/ >/dev/null; do sleep 3; done
```

Pourquoi : InvenTree sert le static **collecté** depuis
`/home/inventree/data/static/plugins/inventree-location/`, copié **au boot**.
`manage.py collectstatic` ne recopie pas le static du plugin (« 0 copied »).
Idem pour le backend : gunicorn garde la classe Python en cache, donc les
nouvelles URLs de `setup_urls` et les `default` de champs n'existent qu'après
restart.

Vérifier que le bundle servi est bien le neuf (le hash doit changer) :

```bash
curl -s http://localhost:8000/static/plugins/inventree-location/.vite/manifest.json \
  | python3 -m json.tool | grep '"file"'
```

## 3. Piloter le navigateur

Pas de MCP navigateur ici. Playwright, une fois :

```bash
npx playwright install chromium
```

Le driver réutilisable est dans `driver.mjs` à côté de ce fichier. Copier-le
dans le scratchpad, puis :

```js
import { session, shot, dumpErrors } from './driver.mjs';
const { page, errors, browser } = await session();   // login + dashboard prêts
// ... interactions ...
await shot(page, 'mon-cas');
dumpErrors(errors);
await browser.close();
```

`session()` fait le login et amène sur `/web/home`. Il installe aussi les
écouteurs `pageerror` et « réponse HTTP ≥ 400 » — **toujours les vider en fin de
scénario** : plusieurs bugs de ce projet étaient des 500 silencieux ou des
erreurs JS sans effet visible immédiat.

## 4. Où est l'UI du plugin

`get_ui_dashboard_items` dans `core.py` → **widgets de dashboard** :
Catalogue, Organisation, Réservations, Conflits actuels, Alertes stock. Les
`get_ui_panels` ne s'affichent que sur `target_model == "part"` (fiche article).

### Les widgets sont posés automatiquement à l'attribution d'un rôle

La disposition du dashboard est **propre à chaque utilisateur**, et InvenTree
n'ajoute jamais un widget de plugin de lui-même : un compte neuf tombe sur
« No Widgets Selected ». C'est ce qui a fait conclure au client, en août 2026,
qu'il avait « la version de base d'InvenTree ».

Le plugin pose donc les écrans lui-même (`dashboards.py` pour le calcul,
`dashboard_provisioning.py` pour le signal `m2m_changed` sur `User.groups`).
La disposition est écrite dans `users.models.UserProfile.widgets`. La fusion est
**non destructive** : les widgets du cœur InvenTree et le rangement de
l'utilisateur sont conservés, seuls les widgets du plugin devenus interdits
partent. Rattrapage des comptes existants :
`python manage.py provision_dashboards`.

**Ne pas repartir sur `get_ui_navigation_items` : c'est une impasse en 1.5.1.**
Le hook existe et la barre de nav rend bien un onglet, mais il navigue via
`navigateToLink`, qui fait **toujours** un `navigate()` react-router — et la SPA
n'a aucune route générique de page plugin. Un onglet vers
`/plugin/inventree-location/...` tombe donc sur le `path:"*"`, c'est-à-dire la
page 404.

Pour tester un widget qu'aucun rôle ne pose, l'ajouter à la main :

1. cliquer le `⋮` **de la carte du dashboard** (même ligne que le titre
   « InvenTree - admin », à droite) — pas celui du profil en haut à droite ;
2. « Add Widget » ;
3. filtrer, puis **cliquer l'icône verte à gauche du libellé**, pas le texte :
   un clic sur le libellé n'ajoute rien.

Vérifier qu'un widget est bien enregistré côté serveur, sans passer par l'UI :

```bash
curl -s -H "Authorization: Token $TOKEN" \
  http://localhost:8000/api/plugins/ui/features/dashboard/ | python3 -m json.tool
```

## 5. Vérifications qui ne sont pas ce qu'elles paraissent

- **`npx tsc --noEmit` ne vérifie RIEN.** Le `tsconfig.json` racine a
  `"files": []` et délègue à des project references. Utiliser **`npx tsc -b`**
  (c'est ce que fait `npm run build`).
- **Tests** : `pytest` à la racine (via `tests.settings` + une app `part`
  factice). **Pas** `make test` / Docker. `core.py` n'est pas importable hors
  InvenTree — la logique testable est extraite dans `roles.py`, `conflicts.py`,
  `permissions.py`, `stock.py`.
- **`pre-commit run --all-files`** avant de conclure. `biome check` **modifie**
  les fichiers : relancer une deuxième fois pour l'avoir vert.
- Compter les lignes d'un tableau : le dashboard en contient plusieurs.
  Cibler par en-tête, ex.
  `page.locator('table').filter({ hasText: 'Nb objets' })`.

## 6. Pièges déjà rencontrés (à re-tester en priorité)

- **`Select` searchable + `searchValue` contrôlé** : Mantine recopie le *label*
  de l'option dans la recherche, qui repart au serveur. Si le label est enrichi
  (« Nom — N disponible(s) »), le serveur ne matche plus, la liste se vide et la
  sélection est perdue. Ne jamais dériver l'entité choisie des seuls résultats
  de recherche. Références correctes : `PartPicker.tsx`, `ReservationForm.tsx`.
- **État d'URL partagé** : tous les widgets écrivent la même query string.
  Passer par `frontend/src/urlState.ts` (`syncOwnedParams`) et préfixer ses
  clés, sinon le dernier à se synchroniser efface les filtres des autres.
- **Migrations** : InvenTree applique celles du plugin au boot, mais un
  `0001_initial` réécrit ne se réapplique pas sur une base existante. En cas de
  dérive : `make clean` (`down -v`) puis `make up`. Vérifier :
  `SELECT name FROM django_migrations WHERE app='inventree_location';`
- **Mantine doit rester en v8** (l'hôte fournit `@mantine/core` 8.3.18 en
  global). Un `@mantine/dates` en v9 provoque `TypeError: ni is not a function`
  et le widget affiche « Error Loading Content ».
- **Registre npm** : jamais `npm.chargemap.com` dans le lockfile
  (`frontend/.npmrc` épingle `registry.npmjs.org`).

## 7. Créer un utilisateur de test avec un rôle

Passer par l'API (`POST /api/user/` exige `username`, `password`, `first_name`,
`last_name`, `email`) : ajouter un groupe en shell Django échoue tant que le
`profile` InvenTree n'existe pas (signal
`validate_primary_group_on_group_change`).