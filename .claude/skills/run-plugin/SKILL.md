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

## 1 bis. Après un `make clean`, la stack ne revient PAS seule

`down -v` efface la base, donc tout ce qui vit en base : l'activation du
plugin, les interrupteurs plugin d'InvenTree, les droits des rôles et les
dispositions de tableau de bord. L'API répond, les écrans natifs s'affichent,
et **aucun widget du plugin n'existe** — c'est le symptôme qui a fait conclure
au client, en août 2026, qu'il avait « InvenTree de base ».

```bash
make clean && make up                       # attendre l'API (~25 s)

# a) les six interrupteurs plugin + l'activation, en base
make manage cmd='shell -c "
from common.models import InvenTreeSetting
for k in [\"ENABLE_PLUGINS_URL\",\"ENABLE_PLUGINS_NAVIGATION\",\"ENABLE_PLUGINS_APP\",
          \"ENABLE_PLUGINS_SCHEDULE\",\"ENABLE_PLUGINS_EVENTS\",\"ENABLE_PLUGINS_INTERFACE\"]:
    InvenTreeSetting.set_setting(k, True, None)
from plugin.models import PluginConfig
p = PluginConfig.objects.get(key=\"inventree-location\"); p.active = True; p.save()
"'
docker compose restart inventree            # recharge le registre, applique les migrations

# b) les données, les droits, les tableaux de bord
make manage cmd="seed_demo"
make manage cmd="provision_role_permissions"   # sinon 403 sur /api/part/ pour TOUS les rôles
make manage cmd="provision_dashboards"         # sinon le tableau de bord admin est vide
```

`provision_role_permissions` est celle qu'on oublie, et son absence est
sournoise : les écrans du plugin fonctionnent, mais la barre de navigation
native se réduit à « Tableau de bord », le filtre Catégories du catalogue reste
vide et la colonne Catégorie affiche « — » pour tout le monde. Vérification en
une ligne :

```bash
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Token $TOKEN" \
  http://localhost:8000/api/part/category/     # 200 attendu, sauf livreur (403 voulu)
```

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
## 8. Les deux scénarios de bout en bout

`driver.mjs` sert à écrire un cas ; ces deux-là sont écrits et rejouables.

```bash
mkdir -p /tmp/plugin-e2e && cd /tmp/plugin-e2e   # playwright doit résoudre ici
npm install playwright                            # les navigateurs sont déjà posés
cp ~/hetic/InvenTreeLocation/.claude/skills/run-plugin/{driver,nominal,alternatifs}.mjs .

node nominal.mjs           # silencieux, ~2 min
LENT=1 node nominal.mjs    # fenêtre visible et ralentie, pour une démonstration
node alternatifs.mjs
```

### `nominal.mjs` — la chaîne complète

Client → contact → manifestation → prestation → bon → validation → livraison →
ramassage → retour, en neuf étapes indépendantes : une étape qui casse
n'empêche pas les suivantes de s'exécuter, et chacune se conclut par une
capture en cas d'échec. Le bilan final dit laquelle est tombée.

**Trois règles font échouer une saisie improvisée**, et ce n'est pas un bug :

1. **Le gérant interne est obligatoire** sur un bon — « Le demandeur est
   obligatoire » au moment de soumettre.
2. **Un article virtuel est obligatoire à la soumission**, en plus du matériel.
3. **L'écran Livraisons s'ouvre sur la tournée du jour** (`horizon: 'jour'`) :
   une manifestation datée de la semaine prochaine n'y apparaît pas. Le
   scénario date donc sa manifestation sur *aujourd'hui*.

Deux pièges d'automatisation, payés une fois chacun : `Échap` ferme la
**modale** Mantine et pas seulement le calendrier — fermer un `DateTimePicker`
en cliquant le titre de la modale ; et les jours du calendrier portent un
`aria-label` complet (« 20 septembre 2026 »), donc se ciblent par
`button.mantine-DateTimePicker-day` et leur texte.

### `alternatifs.mjs` — ce qui doit être refusé, toléré ou masqué

| Cas | Attendu |
|---|---|
| A — ramassage en surplus, à l'écran | accepté (R36) ; **échoue aujourd'hui** |
| B — le même surplus, côté serveur | accepté, HTTP 200 |
| C — manquant supérieur au sorti | refusé, HTTP 400 |
| D — poste lecteur | aucun bouton d'ajout, pas de back-office |
| E — conflits de stock | l'écran liste le conflit |
| F — manifestation dont la fin précède le début | refusé, HTTP 400 |

**Les cas B et C écrivent** sur un bon livré : ils le passent en `retournee`
avec des quantités de test. Remettre en état après coup, sinon la base de
démonstration ment :

```bash
make manage cmd="shell -c '
from inventree_location.models import Reservation, ReturnIncident
from inventree_location import models as m
b = Reservation.objects.get(numero=\"RES-2026-0003\")
for l in b.lignes.all():
    l.quantite_ramassee = l.quantite_sav = l.quantite_detruite = 0
    l.quantite_manquante = l.quantite_retournee = 0
    l.save()
ReturnIncident.objects.filter(line__reservation=b).delete()
m.Ramassage.objects.filter(reservation=b).delete()
b.statut = \"livree\"; b.save()
'"
make manage cmd="projeter_execution"
make manage cmd="verifier_projection"   # doit dire « Aucune divergence. »
```

### `roles.mjs` — un poste par rôle

Se connecte successivement avec les sept comptes de démonstration, compare les
onglets réellement rendus à ceux déclarés dans `postes/definitions.tsx`, **ouvre
chaque écran** — un écran qui répond 403 pour un rôle ne se voit qu'en le
montant —, compte les actions d'écriture offertes et relève barre de navigation
native et erreurs.

Attendu : six rôles au vert, zéro erreur. `demo_sav` n'a **pas de poste** —
aucun écran ne lui est déclaré, son widget reste vide. C'est un manque connu,
pas une panne.

C'est ce scénario qui a rendu visible l'oubli de `provision_role_permissions`
sur une base fraîche : les sept comptes accumulaient des 403 sur
`/api/part/category/` sans qu'aucun écran ne paraisse cassé.
