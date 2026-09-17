# Scénarios navigateur

`pytest` et `vitest` passent au vert sur un écran qui ne se monte pas : ils ne
rendent rien. Ces trois scénarios pilotent l'application comme un utilisateur —
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
```

`SHOTS_DIR` dit où écrire les captures (défaut : le dossier courant).

## Ce que chacun couvre

### `nominal.mjs` — la chaîne complète

Client → contact → manifestation → prestation → bon → validation → livraison →
ramassage → retour, en neuf étapes **indépendantes** : une étape qui casse
n'empêche pas les suivantes, chacune laisse une capture en cas d'échec, et le
bilan final dit laquelle est tombée.

Trois règles font échouer une saisie improvisée, et ce n'est pas un bug :

1. **Le gérant interne est obligatoire** sur un bon — « Le demandeur est
   obligatoire » au moment de soumettre.
2. **Un article virtuel est obligatoire à la soumission**, en plus du matériel.
3. **L'écran Livraisons s'ouvre sur la tournée du jour** : une manifestation
   datée de la semaine prochaine n'y apparaît pas. Le scénario date donc sa
   manifestation sur *aujourd'hui*.

### `alternatifs.mjs` — ce qui doit être refusé, toléré ou masqué

| Cas | Attendu |
|---|---|
| Ramassage en surplus, à l'écran | accepté, signalé sans bloquer (R36) |
| Le même surplus, côté serveur | accepté, HTTP 200 |
| Manquant supérieur au sorti | refusé, HTTP 400 |
| Poste lecteur | aucun bouton d'ajout, pas de back-office |
| Conflits de stock | l'écran liste le conflit |
| Manifestation dont la fin précède le début | refusé, HTTP 400 |

**Deux de ces cas écrivent** sur un bon livré : ils le passent en `retournee`
avec des quantités de test. Remettre en état après coup, sinon la base de
démonstration ment :

```bash
make manage cmd='shell -c "
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
"'
make manage cmd="projeter_execution"
make manage cmd="verifier_projection"   # doit dire « Aucune divergence. »
```

### `roles.mjs` — un poste par rôle

Se connecte avec les sept comptes de démonstration, **ouvre chaque écran**
déclaré — un 403 propre à un rôle ne se voit qu'en le montant —, compare les
onglets rendus à `postes/definitions.tsx` et relève barre de navigation native
et erreurs.

Attendu : six rôles au vert, zéro erreur. `demo_sav` n'a pas de poste : aucun
écran ne lui est déclaré, son widget reste vide. Manque connu, pas panne.

## Si la base vient d'être réinitialisée

`docker compose down -v` efface aussi ce qui n'est pas dans le code :
l'activation du plugin, les interrupteurs plugin d'InvenTree, les droits des
rôles et les tableaux de bord. Les scénarios échouent alors en cascade sur des
403 sans qu'aucun écran ne paraisse cassé.

```bash
make manage cmd="seed_demo"
make manage cmd="provision_role_permissions"   # sinon 403 sur /api/part/ pour tous les rôles
make manage cmd="provision_dashboards"         # sinon le tableau de bord est vide
```

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
