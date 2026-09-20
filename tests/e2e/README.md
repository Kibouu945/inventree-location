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

Quatre règles font échouer une saisie improvisée, et ce n'est pas un bug :

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
avec des quantités de test — dont un ramassage de 99 pour 4 sortis, qui est
tout l'objet du cas B.

Le bon visé n'est pas fixe : `cibleRamassable()` prend le **premier** bon
`livree` ou `retournee` rendu par `/reservations/`, et ce tri est
`-date_demande`. C'est donc le bon le plus récemment demandé — en pratique
celui que `nominal.mjs` vient de créer, si on l'a joué juste avant.

Remettre en état après coup, sinon la base de démonstration ment. La commande
ci-dessous retrouve le bon par la même règle que le scénario, plutôt que par un
numéro écrit en dur qui cesserait d'être le bon dès la démonstration suivante :

```bash
docker compose exec -T inventree bash -lc \
  'cd /home/inventree/src/backend/InvenTree && python manage.py shell' <<'EOF'
from inventree_location.models import Reservation, Ramassage, ReturnIncident

bon = Reservation.objects.filter(statut__in=["livree", "retournee"]).first()

for ligne in bon.lignes.all():
    ligne.quantite_retournee = 0
    ligne.etat_retour = ""
    ligne.save(update_fields=["quantite_retournee", "etat_retour"])

ReturnIncident.objects.filter(line__reservation=bon).delete()
Ramassage.objects.filter(reservation=bon).delete()
bon.statut = "livree"
bon.save(update_fields=["statut"])
print("remis en état :", bon.numero)
EOF

make manage cmd="projeter_execution"
make manage cmd="verifier_projection"   # doit dire « Aucune divergence. »
```

Deux pièges payés ici. Le passage par `make manage cmd='shell -c "..."'`
n'encaisse pas un script sur plusieurs lignes : les guillemets se perdent en
route et Django répond `argument -c/--command: expected one argument`. Un
`heredoc` dans le conteneur passe sans échappement.

Et les quantités de retour **ne sont plus portées par la ligne** : la migration
`0021` a supprimé `quantite_ramassee`, `quantite_sav`, `quantite_detruite` et
`quantite_manquante` au profit du registre `ReturnIncident`, qui fait foi. Il
reste `quantite_livree`, `quantite_retournee` et `etat_retour`. Les incidents,
eux, se comptent en `type` et `qty`.

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

## Si la base vient d'être réinitialisée

`docker compose down -v` efface aussi ce qui n'est pas dans le code :
l'activation du plugin, les interrupteurs plugin d'InvenTree, les droits des
rôles et les tableaux de bord. Les scénarios échouent alors en cascade sur des
403 sans qu'aucun écran ne paraisse cassé.

La remise en route se fait **dans cet ordre**. Les deux premières étapes sont
celles qu'on oublie : sans elles, le plugin est chargé, `meta` est rempli, tout
a l'air normal — et pourtant `showmigrations inventree_location` répond `No
installed app with label 'inventree_location'`, parce que l'app n'entre jamais
dans `INSTALLED_APPS` et qu'aucune de ses tables n'existe.

```bash
make up

# 1. Réactiver le plugin — il revient installé mais « active: false ».
curl -s -X PATCH -u admin:admin123 -H "Content-Type: application/json" \
  -d '{"active": true}' \
  http://localhost:8000/api/plugins/inventree-location/activate/

# 2. Rallumer les interrupteurs d'InvenTree. C'est `ENABLE_PLUGINS_APP` qui
#    décide si l'app d'un plugin rejoint INSTALLED_APPS — donc si ses
#    migrations existent. Les autres servent aux URL, aux tâches et aux
#    événements.
docker compose exec -T inventree bash -lc \
  'cd /home/inventree/src/backend/InvenTree && python manage.py shell' <<'EOF'
from common.settings import set_global_setting
for cle in ("ENABLE_PLUGINS_APP", "ENABLE_PLUGINS_URL", "ENABLE_PLUGINS_NAVIGATION",
            "ENABLE_PLUGINS_SCHEDULE", "ENABLE_PLUGINS_EVENTS", "ENABLE_PLUGINS_INTERFACE"):
    set_global_setting(cle, True, None)
EOF

# 3. Redémarrer : c'est au démarrage que les migrations du plugin passent.
docker compose restart inventree
make manage cmd="showmigrations inventree_location"   # doit lister 31 × [X]

# 4. Puis seulement, les données et les droits.
make manage cmd="seed_demo"
make manage cmd="provision_role_permissions"   # sinon 403 sur /api/part/ pour tous les rôles
make manage cmd="provision_dashboards"         # sinon le tableau de bord est vide
```

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
