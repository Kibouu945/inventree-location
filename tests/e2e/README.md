# Scénarios navigateur

`pytest` et `vitest` passent au vert sur un écran qui ne se monte pas : ils ne
rendent rien. Ces quatre scénarios pilotent l'application comme un utilisateur —
c'est le seul filet qui voit un écran cassé, un droit manquant ou une règle que
l'interface applique à l'envers du serveur.

## Lancer

La stack doit tourner, **avec le code courant déployé** : le statique est servi
depuis le conteneur, collecté à son démarrage.

```bash
cd frontend && npm run build && cd ..
docker compose restart inventree

cd tests/e2e
npm install                    # playwright ; les navigateurs, une fois :
npx playwright install chromium

npm run nominal                # le parcours complet, ~2 min
LENT=1 npm run nominal         # fenêtre visible et ralentie, pour montrer
npm run alternatifs            # les cas limites
npm run roles                  # une connexion par rôle
npm run complet                # le cycle entier, conflit compris
```

`SHOTS_DIR` dit où écrire les captures (défaut : le dossier courant).

## Ce que chacun couvre

### `nominal.mjs` — la chaîne complète

Client → contact → manifestation → prestation → bon → validation → livraison →
ramassage → retour, en neuf étapes **indépendantes** : une étape qui casse
n'empêche pas les suivantes, chacune laisse une capture en cas d'échec, et le
bilan final dit laquelle est tombée.

Cinq règles font échouer une saisie improvisée, et ce n'est pas un bug :

1. **Le gérant interne est obligatoire** sur un bon — « Le demandeur est
   obligatoire » au moment de soumettre.
2. **Un article virtuel est obligatoire à la soumission**, en plus du matériel.
3. **L'écran Livraisons s'ouvre sur la tournée du jour** : une manifestation
   datée de la semaine prochaine n'y apparaît pas. Le scénario date donc sa
   manifestation sur *aujourd'hui* — et ses dates se **calculent**, elles ne se
   figent pas : datées en dur, elles tombent dans le passé quelques jours plus
   tard et six étapes échouent d'un coup sur une application saine.
4. **L'arborescence part du client** (F3), et les clients s'ouvrent repliés. Le
   filtre client d'autrefois a disparu — il faisait doublon avec le niveau. Le
   scénario passe donc par la recherche, qui ne garde que les clients portant
   une manifestation correspondante et les déplie. Elle est différée de 300 ms :
   remplir le champ puis chercher aussitôt ne trouve rien.
5. **Livraisons et Ramassages s'ouvrent sur leur table hiérarchique** (F6, F7),
   où le numéro du bon ne paraît qu'après dépliage. Les scénarios basculent sur
   la vue « Liste », qui garde la ligne plate et ses boutons. Sans cette
   bascule, l'étape 8 cherchait une ligne absente, épuisait trente secondes
   d'attente, puis se déclarait bonne : elle ne vérifiait plus rien.

### `alternatifs.mjs` — ce qui doit être refusé, toléré ou masqué

| Cas | Attendu |
|---|---|
| Ramassage en surplus, à l'écran | accepté, signalé sans bloquer (R36) |
| Le même surplus, côté serveur | accepté, HTTP 200 |
| Manquant supérieur au sorti | refusé, HTTP 400 |
| Poste lecteur | aucun bouton d'ajout, pas de back-office |
| Conflits de stock | l'écran liste le conflit |
| Manifestation dont la fin précède le début | refusé, HTTP 400 |

**Ce scénario fabrique son propre bon** — manifestation, prestation, bon,
conduit jusqu'à « livrée » — et ne travaille que sur celui-là. Il n'y a donc
plus rien à remettre en état après coup.

Il attrapait autrefois le premier bon `livree` ou `retournee` rendu par
`/reservations/`, trié `-date_demande` : le plus récent, c'est-à-dire celui que
`nominal.mjs` venait de créer, ou n'importe lequel de la base de démonstration.
Il lui écrivait 99 récupérés dessus, et la base mentait jusqu'à ce qu'on pense
au nettoyage — dont la commande, elle-même périmée, échouait.

Ce qu'il laisse : le bon fabriqué, **clôturé**. On ne peut pas le supprimer, le
serveur ne supprimant qu'un brouillon ; clôturé, il sort des écrans Livraisons
et Ramassages, dont la requête exclut `cloturee`. Sa manifestation s'appelle
« Cas alternatifs <horodatage> », pour qu'on sache d'où il sort. Une exécution
laisse donc une manifestation, une prestation et un bon clos — aucun autre bon
n'est touché, ce qui était tout l'objet de la réécriture.

Pour les faire disparaître d'une base de démonstration, quand elles se sont
accumulées :

```bash
docker compose exec -T inventree bash -lc \
  'cd /home/inventree/src/backend/InvenTree && python manage.py shell' <<'EOF'
from inventree_location.models import Reservation, Prestation, Manifestation

vise = {"prestation__manifestation__nom__startswith": "Cas alternatifs"}
Reservation.objects.filter(**vise).delete()
Prestation.objects.filter(manifestation__nom__startswith="Cas alternatifs").delete()
Manifestation.objects.filter(nom__startswith="Cas alternatifs").delete()
print("campagnes de test effacées")
EOF
```

L'ORM passe outre le refus de l'API, qui ne supprime qu'un brouillon — c'est
voulu côté métier, et c'est pour cela que le scénario clôture au lieu de
supprimer.

### `roles.mjs` — un poste par rôle

Se connecte avec les sept comptes de démonstration, **ouvre chaque écran**
déclaré — un 403 propre à un rôle ne se voit qu'en le montant —, compare les
onglets rendus à `postes/definitions.tsx` et relève barre de navigation native
et erreurs.

Attendu : six rôles au vert, zéro erreur. `demo_sav` n'a pas de poste : aucun
écran ne lui est déclaré, son widget reste vide. Manque connu, pas panne.

Il relève en plus deux `HTTP 403 /api/news/`. C'est un point d'API natif
d'InvenTree, pas du plugin, et le rôle n'y a pas droit : ne pas le chercher de
notre côté.

### `complet.mjs` — le cycle entier, conflit compris

Le scénario de démonstration. Il crée un client, son contact, une manifestation,
**deux prestations sur deux lieux**, puis des bons jusqu'à mettre le parc en
tension — et montre ce qu'un tableur ne sait pas faire.

| Étape | Ce qu'elle démontre |
|---|---|
| 1 – 4 | Client, contact, manifestation, deux prestations |
| 5 | Deux bons sur le même article rare, créés depuis l'arbre **et** depuis l'écran Réservations |
| 6 | **Le serveur refuse d'engager au-delà du stock** — et chiffre le manque |
| 7 | Un troisième bon de trop : le refus à l'écran, avec le taux d'occupation |
| 8 | Le gestionnaire complète le parc, le bon passe |
| 9 | Le livreur accepte, démarre, livre |
| 10 | Le magasinier ouvre l'arborescence de ramassage jusqu'au bon |

Deux points de méthode qui rendent le scénario rejouable sur n'importe quelle
base. La quantité par bon se **calcule sur le stock du jour** — une constante en
dur cessait d'être juste dès qu'on ajoutait du matériel. Et chaque lot de stock
créé en cours de route est **rendu à la fin** : le scénario ne laisse que le
client et sa manifestation.

Les `HTTP 400` sur `/transition/` dans le journal sont **attendus** : ce sont les
refus de validation que le scénario provoque exprès.

Ce que le scénario a appris sur le produit, et qui mérite d'être su :

- **Un conflit ne naît pas d'une validation** : le serveur l'interdit au-delà du
  stock (`Validation refusée : conflit de stock détecté`, forçable avec trace).
  Le registre « Conflits actuels » recense les pénuries sur des bons **déjà
  engagés**, quand le parc diminue après coup.
- **L'état d'une livraison et le statut d'un bon sont deux choses.** Le livreur
  fait avancer l'état — assignée, en cours, livrée ; le statut du bon bascule,
  lui, par le bouton de sa ligne.

## Si la base vient d'être réinitialisée

`docker compose down -v` efface aussi ce qui n'est pas dans le code :
l'activation du plugin, les interrupteurs plugin d'InvenTree, les droits des
rôles et les tableaux de bord. Les scénarios échouent alors en cascade sur des
403 sans qu'aucun écran ne paraisse cassé.

`make provision` (voir le README à la racine, et `docker/provision_plugin_settings.py`) fait exactement ça en
un seul appel : réactive le plugin, rallume les interrupteurs d'InvenTree (`ENABLE_PLUGINS_APP` en premier —
c'est lui qui décide si l'app d'un plugin rejoint `INSTALLED_APPS`, donc si ses migrations existent), redémarre,
puis charge les données de démo et les droits :

```bash
make up
make provision
make manage cmd="showmigrations inventree_location"   # doit lister 31 × [X]
```

Sans le réglage `ENABLE_PLUGINS_APP`, le plugin est chargé, `meta` est rempli, tout a l'air normal — et pourtant
`showmigrations inventree_location` répond `No installed app with label 'inventree_location'`, parce que l'app
n'entre jamais dans `INSTALLED_APPS` et qu'aucune de ses tables n'existe.

Enfin, **laisser la pile chauffer** avant de lancer un scénario. Joué dans la
foulée du redémarrage, `nominal.mjs` a échoué sur ses neuf étapes — trente
secondes de `locator.click: Timeout` chacune — alors que l'application était
saine : rejoué deux minutes plus tard, sans rien changer, il est passé en 1:48.
Attendre que `/api/` réponde ne suffit pas.

## Pièges d'automatisation, payés une fois chacun

- **`Échap` ferme la modale Mantine**, pas seulement le calendrier : refermer un
  `DateTimePicker` en cliquant le titre de la modale.
- **Les jours du calendrier portent un `aria-label` complet** (« 20 septembre
  2026 ») : les cibler par `button.mantine-DateTimePicker-day` et leur texte.
- **Les listes déroulantes vivent dans un portail**, hors de la modale : cibler
  `[role="option"]:visible`, sinon on clique dans la liste d'un autre champ
  restée dans le DOM.
- **« Manifestations » nomme deux onglets** — la navigation du poste et un
  onglet interne de l'écran Fiches. La navigation du poste porte
  `data-placement="left"`.
- **Le sélecteur Arborescence / Liste est un `SegmentedControl`** : Mantine le
  rend en `label`, pas en `button`. `getByRole('button', { name: 'Liste' })` ne
  le trouve jamais ; le cibler par
  `page.locator('label').filter({ hasText: /^Liste$/ })`.
- **Un `catch` sur un localisateur rend une étape muette.** Écrite
  `…allInnerTexts().catch(() => [])`, l'étape 8 passait au vert sur un écran
  qu'elle n'avait pas trouvé. Faire échouer — `waitFor`, puis une assertion —
  plutôt que d'avaler : une étape qui ne peut pas tomber ne prouve rien.
- **`if (await X.count())` est la même faute déguisée.** « Si c'est là, je
  clique » saute en silence quand ce n'est pas là. L'étape 10 de `complet.mjs`
  cumulait deux de ces gardes et un ternaire qui rendait une phrase de succès
  dans ses deux branches : elle se déclarait bonne sans avoir rien ouvert. Ce
  garde ne vaut que pour ce qui est **vraiment** facultatif — une modale qui
  peut ne pas s'ouvrir —, jamais pour l'objet de l'étape.
- **Un scénario qu'on ne joue pas pourrit.** `complet.mjs` sélectionnait encore
  le filtre client supprimé par F3 : sept étapes tombaient en cascade, et
  personne ne l'avait vu parce qu'il n'était pas rejoué. Les quatre scénarios
  se passent ensemble, ou l'un d'eux ment.
