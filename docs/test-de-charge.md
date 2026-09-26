# Test de charge — 10 000 réservations par an

Le volume cible est **≈10 000 réservations par an, avec des pics de 30
réservations sur un même week-end**. Ce n'est pas le cahier des charges qui
l'annonce — il ne contient aucune volumétrie — mais la réponse du client du
20 mai, reprise au ticket **PERF-01** du backlog (`BACKLOG.md:794`), classé
Must, avec un critère d'acceptation écrit : *liste paginée < 500 ms avec 10 000
lignes*.

Ce document décrit l'outillage qui permet de vérifier cette annonce, le
protocole suivi, et ce que la campagne a mesuré. Il est le livrable de PERF-01.

Il porte **deux campagnes** : celle du 22/09 (§3), qui a établi le constat, et
celle du 23/09 (§6), rejouée après correction des quatre causes.

> Les chiffres de la section « Résultats » sont datés et rattachés à une
> machine précise. Un test de charge sans son contexte matériel ne veut rien
> dire : rejouer la campagne est une commande, il n'y a aucune raison de citer
> des chiffres périmés.

---

## 1. Ce que la campagne cherche

Deux questions, qu'on confond souvent et qui n'ont pas le même remède.

**Le coût.** Combien coûte un écran quand la base contient 500, 2 000, 5 000
puis 10 000 réservations ? Un seul appelant, aucune concurrence. Si le coût
suit le volume, c'est le **code** qui est en cause, et aucun serveur plus gros
n'y changera rien : doubler la machine divise le temps par deux, quand
l'algorithme, lui, le multiplie par quatre à chaque doublement des données.

**La capacité.** Combien d'utilisateurs simultanés la machine tient-elle à
volume fixé ? C'est la question du dimensionnement — et elle n'a de sens que
si la première est saine.

On mesure des **percentiles**, jamais des moyennes. Une moyenne de 200 ms peut
cacher un utilisateur sur vingt qui attend huit secondes ; c'est celui-là qui
appelle le support.

---

## 2. L'outillage

### 2.1 `seed_charge` — le volume

Commande Django, à lancer dans le conteneur :

```bash
make manage cmd="seed_charge --total 10000"
```

Elle amène la base à N réservations réparties sur une année : manifestations,
prestations avec leur prévisionnel, réservations avec leurs lignes, statuts
répartis entre passé clôturé et futur encore bloquant.

Trois propriétés qui comptent :

- **Cumulative.** `--total 2000` puis `--total 5000` complète au lieu de tout
  refaire. On enchaîne les paliers sans que rien d'autre que le volume ne
  change entre deux mesures.
- **Écrite en `bulk_create`.** `Reservation.save()` relit la table à chaque
  insertion pour fabriquer son numéro : par la voie normale, générer le jeu
  coûterait plus longtemps que la mesure elle-même.
- **Marquée.** Tout ce qu'elle crée porte le préfixe `CHG`. `--reset` supprime
  ce jeu et lui seul — le jeu de démonstration et les vraies données restent
  en place.

Options utiles : `--stock` (défaut 500, généreux : baisser cette valeur est le
moyen de mesurer le cas où tout est en pénurie), `--articles`, `--clients`,
`--lignes-max`, `--graine` (deux exécutions donnent la même base).

### 2.2 `bench.py` — la mesure

```bash
# coût : un appelant, chaque endpoint joué trois fois
python tests/charge/bench.py --sequentiel

# capacité : dix appelants pendant trente secondes
python tests/charge/bench.py --concurrence 10 --duree 30

# écriture : création de réservations
python tests/charge/bench.py --scenario ecriture --concurrence 5
```

Le scénario de lecture rejoue les treize appels que font réellement les écrans
(liste, calendrier, conflits, alertes de stock, tournée, catalogue, contrôle
de disponibilité…), pondérés selon leur fréquence d'usage. Chaque itération
change de page, de mois et d'article : deux appels successifs ne doivent pas
taper la même chose, sinon on mesure un cache et non un serveur.

Un dépassement de `--timeout` est compté comme un échec, pas comme un incident
du script : c'est précisément le point de rupture qu'on cherche.

### 2.3 `paliers.sh` et `synthese.py` — la campagne

```bash
tests/charge/paliers.sh                        # 500, 2 000, 5 000, 10 000
PALIERS="10000" CONCURRENCES="1 10 25" tests/charge/paliers.sh
python tests/charge/synthese.py tests/charge/resultats/
```

`paliers.sh` enchaîne : amener la base au palier, mesurer le coût, mesurer la
capacité à 1, 5, 10 et 25 appelants. Les rapports bruts sont écrits en JSON
dans `tests/charge/resultats/`, et `synthese.py` les croise en deux tableaux —
le coût par volume, la capacité par palier.

---

## 3. Résultats — campagne du 22/09/2026

### 3.1 Les deux machines mesurées

| | Poste de développement | **VPS de production** |
|---|---|---|
| Processeurs | 12 CPU (VM Docker Desktop) | **3 vCPU** |
| Mémoire | 8 Go alloués à Docker | **3,9 Go** |
| Workers gunicorn | 4 | **4** |
| Frontal | aucun | Caddy (HTTPS) |
| Base | Postgres 17, même machine | Postgres, même machine |

Le VPS est la machine qui compte : c'est celle qui sert
`inventree-location.duckdns.org`. Les mesures locales servent à établir la
**courbe** — comment le coût évolue avec le volume — ce qu'on ne peut pas
faire sur la production sans la tenir occupée une demi-journée.

Volume injecté sur le VPS : 10 000 réservations réparties sur 2026, 25 041
lignes, **3 801 réservations au statut bloquant** (celles qui pèsent sur le
calcul de disponibilité), 50 articles louables, sur un catalogue client de 797
articles. Les données ont été supprimées à l'issue de la campagne et la base
est revenue à ses compteurs d'origine.

### 3.2 Coût par écran, un seul appelant, sur la production à 10 000

| Endpoint | p50 | Verdict |
|---|---|---|
| `conflicts/` | **> 120 000 ms** | ne rend pas |
| `deliveries/` | 6 846 ms | inutilisable |
| `alerts/stock/` | 6 023 ms | inutilisable |
| `reservations/` (recherche) | 915 ms | acceptable |
| `reservations/` (page profonde) | 863 ms | acceptable |
| `catalog/` | 837 ms | acceptable |
| `reservations/` (liste) | 780 ms | acceptable |
| `ramassages/` | 589 ms | bon |
| `reservations/calendar/` | 586 ms | bon |
| `prestations/` | 180 ms | bon |
| `tournees/` | 177 ms | bon |
| `conflicts/history/` | 114 ms | bon |
| `reservations/check-stock/` | 114 ms | bon |

Neuf écrans sur treize tiennent la charge annoncée sans effort. Trois ne la
tiennent pas, et un ne répond pas.

Aucune borne supérieure n'a été établie pour `conflicts/` : les deux appels du
banc ont été abandonnés à 120 s, et un appel unique lancé ensuite depuis la
machine elle-même — sans HTTPS ni réseau — a été interrompu avant d'aboutir,
pour ne pas prolonger l'occupation de la production. On sait donc qu'il
dépasse deux minutes ; on ne sait pas de combien.

### 3.3 La courbe : le volume, pas la machine

Sur le poste de développement — quatre fois plus de processeurs que le VPS —
`conflicts/` mesuré à volume croissant :

| Réservations en base | p50 de `conflicts/` |
|---|---|
| 500 | 2 856 ms |
| 2 000 | 21 577 ms |
| 5 000 | > 45 000 ms (dépassement) |
| 10 000 (VPS) | > 120 000 ms (dépassement) |

Quatre fois plus de données, presque **huit fois** plus de temps. Un coût qui
croît plus vite que la base ne se corrige pas en changeant de serveur :
doubler la machine diviserait le temps par deux, quand doubler les données le
multiplie par près de quatre. À ce rythme, l'endpoint était déjà au-delà de la
minute vers 3 000 réservations — c'est-à-dire **au premier trimestre** d'une
année à 10 000.

### 3.4 Capacité de la production, `conflicts/` écarté

`conflicts/` monopolise les quatre workers dès qu'il est appelé ; pour savoir
ce que tient le reste de l'application, il faut le retirer du scénario.

| Appelants simultanés | Débit | Échecs | p95 du pire écran |
|---|---|---|---|
| 1 | 0,31 req/s | 0 | 7,1 s |
| 5 | **1,10 req/s** | 1 | 24,2 s |
| 10 | 0,89 req/s | 1 | 31,1 s |
| 25 | 0,78 req/s | 4 | 60,1 s |

Le débit **plafonne à cinq appelants** et décroît ensuite : au-delà, les
requêtes s'empilent devant quatre workers déjà occupés, et chacune attend plus
longtemps sans que le serveur n'en traite davantage. C'est la signature d'une
saturation, pas d'une montée en charge.

Le plafond n'est pas celui de la machine mais celui de deux écrans : à eux
seuls, `deliveries/` et `alerts/stock/` consomment presque tout le temps
disponible.

### 3.5 Capacité de la production, `conflicts/` compris

Dix appelants, scénario complet :

| | Sans `conflicts/` | Avec `conflicts/` |
|---|---|---|
| Débit | 0,89 req/s | **0,30 req/s** |
| Échecs | 1 sur 38 | **4 sur 23** |
| `reservations/` (liste), p95 | 7,6 s | **37,0 s** |

C'est le résultat le plus parlant de la campagne : la simple liste des
réservations, qui coûte 0,8 s toute seule, passe à 37 secondes. Elle n'est
pourtant devenue ni plus grosse ni plus complexe — elle attend simplement son
tour derrière un widget de tableau de bord qui occupe les quatre workers. **Un
seul écran lent rend toute l'application indisponible**, et c'est celui que le
tableau de bord charge à l'ouverture.

### 3.6 Un effet de bord : la purge est lente elle aussi

Supprimer les 10 000 réservations injectées a pris plusieurs dizaines de
minutes, sur les deux machines. `QuerySet.delete()` de Django charge en
mémoire les objets à supprimer pour propager les cascades, puis émet les
suppressions par paquets — un coût qui n'apparaît nulle part tant qu'on
travaille sur vingt lignes.

L'archivage annuel, lui, n'est **pas** concerné :
`archiving.archive_old_reservations()` pose un drapeau par un seul `UPDATE`
SQL, sans rien charger en mémoire. Le coût constaté ici ne pèse que sur une
vraie suppression de masse — reprise de données, erreur d'import — que
l'application ne fait pas en routine. À savoir le jour où il faudra en faire
une.

### 3.7 Deux plafonds durs, indépendants du serveur

**La numérotation s'arrête à 10 000 par an.** `Reservation.numero` suit la
forme `RES-AAAA-NNNN`, et le numéro suivant est calculé en relisant le plus
grand numéro de l'année — par un tri de **chaînes**. Sous 10 000, le zéro de
remplissage rend ce tri équivalent à un tri numérique. À la dix-millième, le
numéro passe à cinq chiffres et les deux ordres divergent : `RES-2026-9999`
passe devant `RES-2026-10000`, puisque « 9 » vient après « 1 ». Le générateur
propose alors éternellement 10000, se heurte à la contrainte d'unicité, et
abandonne au bout de cinq tentatives par une `IntegrityError`. La réservation
n'est pas enregistrable.

C'est exactement le volume annoncé par le client, et cela ne dépend d'aucun
serveur. Quatre tests le démontrent :
`inventree_location/tests/test_numerotation_annuelle.py`.

**Le calendrier refuse le mois.** `calendrier.MAX_EVENEMENTS` plafonne à 1 000
évènements par fenêtre. À 10 000 réservations réparties sur l'année, une vue
mensuelle en demande environ 830, plus celles qui débordent de part et
d'autre : la campagne a bien reçu le refus « Plus de 1000 réservations sur
cette période ». La vue mensuelle passe encore de justesse, la vue
trimestrielle — que la borne de 92 jours autorise — est certaine d'échouer.

---

## 4. Cinq utilisateurs simultanés : est-ce assez ?

Le plafond mesuré ne veut rien dire tant qu'on ne le rapporte pas à la
population réelle d'utilisateurs. Celle-ci n'est écrite nulle part, mais elle se
déduit de ce qui est déjà tranché.

**Tous les utilisateurs sont internes.** Le cahier des charges définit huit
personas — gestionnaire, magasinier, livreur, SAV, lecteur événement, lecteur
stock, acheteur, administrateur — qui sont tous des acteurs de la structure
loueuse. Sept d'entre eux sont matérialisés en groupes Django (`roles.py:19`), à
raison d'**un seul rôle par compte** (arbitrage du 09/09, appliqué au
sérialiseur, `backoffice.py:78`). Côté client, il n'existe aucun compte : les
`Contact` (`models.py:254`) sont des personnes physiques rattachées à un
`Client`, sans identifiant de connexion, et le champ qui rattachait autrefois un
utilisateur à un client a été supprimé en migration `0028` — « un acteur interne
n'appartient à aucun client ».

**Le nombre de clients ne fait pas croître le nombre de comptes.** Un `Client`
porte un gestionnaire référent unique (`models.py:232`) et un gestionnaire tient
plusieurs clients : c'est le portefeuille, qu'alimente `?gestionnaire=me`
(`views.py:2914`). Cent associations de plus, c'est cent fiches de plus, pas
cent comptes.

**Le pic connu est un pic d'écriture, pas de concurrence.** Les « 30
réservations sur un même week-end » annoncées le 20 mai comptent des saisies
étalées sur deux jours, pas trente sessions ouvertes en même temps.

La population simultanée est donc bornée par l'effectif de la structure, de
l'ordre du nombre de rôles — une poignée de personnes, pas une foule. **Ce
n'est pas le nombre d'utilisateurs qui pose problème, c'est le coût de trois
écrans.** La preuve tient dans le §3.4 : le débit plafonne dès cinq appelants,
mais à cinq appelants le pire écran est déjà à 24 s de p95 — et il l'est parce
qu'il coûte 6,8 s *tout seul*, sans concurrence. Une machine deux fois plus
grosse déplacerait le plafond de cinq à dix ; elle ne ramènerait pas ces
6,8 secondes sous la seconde.

C'est ce qui rend la question du dimensionnement secondaire ici. Un serveur se
dimensionne pour une population : celle-ci est connue, petite, et stable — le
nombre d'associations clientes n'y change rien. Ce qui reste à corriger est du
code.

---

## 5. Réponse à la question posée

**Le serveur tient 10 000 réservations par an en stockage. Il ne tient pas les
écrans qui vont avec.** Le critère écrit de PERF-01 — liste paginée sous 500 ms
à 10 000 lignes — n'est pas atteint (780 ms), trois écrans dépassent les six
secondes pour un seul appelant, et `conflicts/` ne rend pas du tout. En prime,
l'ouverture du tableau de bord par un seul utilisateur rend l'application
indisponible pour tous les autres, et la dix-mille-unième réservation de l'année
n'est pas enregistrable.

Le nombre d'utilisateurs simultanés, lui, n'est pas le facteur limitant (§4).

Les quatre causes sont identifiées, et aucune n'est un problème de
dimensionnement. Elles ont depuis été corrigées : chacune porte ci-dessous la
correction apportée, et le §6 donne la mesure d'après. Le constat de cette
section reste celui du 22/09 — on ne réécrit pas une mesure datée.

### 5.1 `list_current_conflicts` — une boucle imbriquée

`conflicts.list_current_conflicts()` parcourt les 3 801 réservations
bloquantes ; pour chacune, `detect_reservation_conflicts()` parcourt ses
lignes ; pour chaque ligne, `compute_engagement_details()` est appelé **deux
fois** (une fois directement, une fois via `compute_part_availability`), et
chaque appel relit **toutes** les lignes de prestation et de réservation
portant cet article, sans filtre de date en SQL — le chevauchement est ensuite
vérifié en Python, ligne par ligne.

Soit, à 10 000 réservations : environ 9 500 lignes à traiter — les 3 801
réservations bloquantes à 2,5 lignes en moyenne — et chacune relit plusieurs
centaines de lignes, les 25 041 lignes de la base se répartissant sur 40
articles. Plusieurs millions d'objets construits en Python pour afficher un
widget.

*Correction :* une seule passe. Charger en une requête les lignes qui
chevauchent la période — le filtre de date appartient au SQL, pas à la boucle
— les regrouper par `(prestation, article)`, et comparer au stock. Le coût
redevient proportionnel au volume.

l**Corrigé.** Le moteur d'engagement est coupé en deux : `charger_lignes_engagement`
lit la base, `reduire_engagements` réconcilie prévisionnel et réalisé. La règle
de réconciliation — par prestation et par article, le plus grand des deux — n'a
pas bougé d'une ligne ; seul l'endroit d'où viennent les données a changé.

Cette séparation permet d'interroger **plusieurs fenêtres sur un même
chargement**, ce dont le widget a précisément besoin puisque chaque réservation
a la sienne. Un `ContexteDeConflits` charge une fois la nature des articles,
leur stock, leurs engagements et les réservations concurrentes ; le parcours
arbitre ensuite en mémoire.

Le filtre de période est passé en SQL, avec **un jour de marge de chaque
côté** : le chevauchement fait foi au jour entier, si bien qu'un filtre posé tel
quel sur les horodatages serait plus strict que la règle et écarterait des
lignes légitimes. Le SQL dégrossit, Python tranche — et le résultat reste
identique, ce que les tests existants vérifient.

`detect_reservation_conflicts` reste l'unique arbitre : le garde-fou du
formulaire lui passe un contexte d'une seule réservation, le widget un contexte
partagé. Deux chemins de calcul auraient fini par se contredire.

Mesuré sur une base saine — sans pénurie, donc chaque réservation arbitrée
jusqu'au bout, le cas le plus coûteux :

| Réservations | Requêtes avant | Temps avant | Requêtes après | Temps après |
|---|---|---|---|---|
| 100 | 3 102 | 0,95 s | **8** | 0,02 s |
| 200 | 5 898 | 2,48 s | **8** | 0,03 s |
| 400 | > 9 000 | 6,55 s | **8** | 0,06 s |

Le temps d'avant croît plus vite que le volume — 0,95 s, 2,48 s, 6,55 s pour
100, 200 puis 400 — ce qui est bien la signature relevée sur la production.
Après, il suit le volume, et le nombre de requêtes ne bouge plus.

*(Au-delà de 9 000 requêtes, Django cesse de les journaliser : le chiffre de la
dernière ligne est une borne inférieure.)*

### 5.2 `DeliveryListView` — la seule liste non paginée

Toutes les vues de liste du plugin portent une `pagination_class`, sauf
`DeliveryListView` (`views.py:640`). Elle renvoie donc **toutes** les
réservations validées ou livrées, avec sept jointures et trois préchargements.
À 10 000 par an, cela fait plusieurs milliers de bons sérialisés à chaque
appel, pour un écran qui en montre vingt.

*Correction :* lui donner la pagination que ses voisines ont déjà.

**Corrigé.** `DeliveryPagination` : 100 bons par page, 500 au plus. Le coût par
bon était déjà borné — jointures et préchargements, vérifiés par un test de
budget de requêtes existant — mais leur *nombre* ne l'était pas, et l'horizon
« à venir » ne pose pas de `date_to`.

Le client a suivi, parce que la forme de la réponse change. La tournée se lit
d'un bloc — carte et calendrier consomment le même jeu que le tableau — donc il
demande une page large plutôt qu'une navigation qui les désynchroniserait, et
signale la troncature quand `count` dépasse ce qu'il a reçu. C'est déjà ce que
l'écran fait pour les ramassages.

### 5.3 `StockAlertListView` — une requête par article

`_projected_tension()` est appelée une fois par article louable, et chacune
lance son propre `aggregate`. `get_part_total_stock()` en fait autant. Avec 50
articles louables, cent requêtes là où deux suffiraient.

*Correction :* une agrégation groupée par article, en une requête.

**Corrigé.** Trois grandeurs étaient lues article par article : le stock
possédé, la disponibilité du jour, et la tension projetée sur trente jours. La
deuxième était déjà groupée ; les deux autres le sont désormais —
`get_parts_total_stock` regroupe l'agrégat des `StockItem` par article, et
`_projected_tensions` fait de même pour les quantités engagées.

Le premier de ces deux agrégats se cachait aussi **dans**
`compute_stock_availability`, qui appelait `get_part_total_stock` dans sa propre
boucle. Le catalogue et le sélecteur de matériel passent par là : ils gagnent la
correction sans l'avoir demandée.

Mesuré par le test de budget, sur un nombre croissant d'articles louables :

| Articles louables | Requêtes avant | Requêtes après |
|---|---|---|
| 5 | 24 | **9** |
| 15 | 69 | **9** |
| 30 | 159 | **9** |

Trois requêtes par article, devenues zéro. C'est l'égalité entre deux mesures —
et non un plafond chiffré, qui se périmerait à la première jointure ajoutée —
qui tient lieu de garde-fou.

### 5.4 La numérotation — quatre chiffres et un tri de chaînes

*Correction :* trier sur la partie numérique plutôt que sur la chaîne, ou
tenir un compteur par année. Élargir le format ne suffit pas : c'est le tri
qui est faux, pas la largeur.

**Corrigé.** `_generate_reservation_numero` relit désormais un maximum
numérique calculé par la base, sur le suffixe converti en entier. Les numéros
existants ne changent pas — quatre chiffres restent un minimum, la largeur
s'étend d'elle-même au-delà de 9 999 — et aucune migration n'est nécessaire.

La conversion est restreinte aux suffixes composés de chiffres : sous
PostgreSQL elle est stricte, et un seul numéro mal formé hérité d'une reprise
de données empêcherait *toute* création ultérieure. Sous SQLite, où tournent
les tests, la conversion est laxiste et ne révélerait pas ce cas : il a été
vérifié directement sur le moteur de la stack.

La boucle de réessai de `Reservation.save()` est conservée. Elle ne masque plus
un tri faux : elle protège la course entre deux créations simultanées, qui
liraient le même maximum.

---

## 6. Après correction — campagne du 23/09/2026

Les quatre causes de la section 5 ont été corrigées, puis le banc rejoué.

> **Sur le poste de développement, pas sur la production.** Les chiffres de
> cette section ne se comparent donc pas à ceux du §3.2, mesurés sur le VPS et
> sur une machine quatre fois plus petite. Ils se comparent au **§3.3**, la
> courbe locale, prise sur la même machine à un jour d'intervalle. Rejouer la
> campagne sur la production demande d'y réinjecter dix mille réservations :
> c'est une décision à prendre, pas un geste de vérification.

### 6.1 Le coût, avant et après, sur la même machine

p95 en millisecondes, un appelant, pour les quatre endpoints corrigés :

| Endpoint | 500 | 2 000 | 5 000 | 10 000 |
|---|---|---|---|---|
| `conflicts/` **avant** | 2 879 | 22 278 | > 45 000 | *non atteint* |
| `conflicts/` **après** | **268** | **374** | **1 225** | **2 789** |
| `alerts/stock/` avant | 127 | 312 | 615 | *non atteint* |
| `alerts/stock/` après | **32** | **30** | **38** | **45** |
| `deliveries/` avant | 59 | 289 | 509 | *non atteint* |
| `deliveries/` après | 69 | **151** | **61** | **54** |
| `catalog/` avant | 308 | 535 | 806 | *non atteint* |
| `catalog/` après | **225** | **192** | **208** | **521** |

Le palier de 5 000 est le dernier que la campagne d'avant ait atteint, et
encore : `conflicts/` y était un dépassement de la borne de 45 s, donc une
borne inférieure. Le palier de 10 000 n'avait jamais pu être mesuré en local.

`catalog/` n'était pas dans la liste des causes : il profite du regroupement
fait pour les alertes, puisque `compute_stock_availability` lui est commun.

### 6.2 Le coût suit-il encore le volume ?

C'était la vraie question. Facteur entre le premier et le dernier palier, à
volume multiplié par vingt (500 → 10 000) :

| Endpoint | Facteur |
|---|---|
| `reservations/` (page profonde) | 12,7× |
| `conflicts/` | 10,4× |
| `reservations/` (recherche) | 6,4× |
| `catalog/` | 2,3× |
| `alerts/stock/` | 1,4× |
| `deliveries/` | 0,8× |

Vingt fois plus de données, dix fois plus de temps sur le pire endpoint : le
coût croît désormais **moins vite que la base**. Avant, `conflicts/` prenait
15,6× pour 10× de données — plus vite qu'elle. C'est ce renversement qui
compte, davantage que les millisecondes : il dit que le volume n'est plus
l'ennemi.

`conflicts/` reste le plus lent des treize, à 2,4 s de p50 sur 10 000. Il
répond, ce qui n'était pas le cas, mais il n'est pas *rapide* : le prochain
gain serait de ne plus parcourir l'année entière pour un widget qui montre les
conflits du moment.

### 6.3 La capacité ne plafonne plus

Dix mille réservations en base, scénario de lecture complet — `conflicts/`
**compris**, là où il avait fallu l'écarter pour obtenir une mesure :

| Appelants simultanés | Débit |
|---|---|
| 1 | 3,8 req/s |
| 5 | 8,9 req/s |
| 10 | **10,7 req/s** |

Le débit monte avec le nombre d'appelants au lieu de décroître. La saturation
décrite au §3.4 venait bien des écrans, pas de la machine.

### 6.4 Ce qui échoue encore

Onze appels sur 246 échouent à dix appelants, et tous pour la même raison :
`400 — « Plus de 1000 réservations sur cette période : resserrez la fenêtre »`.

C'est le second plafond dur du §3.7, et il n'est pas un problème de
performance : à 10 000 réservations par an, une vue mensuelle en demande plus
de mille. Aucune optimisation ne le lèvera, parce qu'afficher trois mille
évènements dans un calendrier n'a pas de sens pour celui qui le lit. C'est un
arbitrage produit — agréger par jour au-delà d'un seuil, ou restreindre la
fenêtre — et il reste à prendre.

---

## 7. Rejouer la campagne

```bash
# en local
tests/charge/paliers.sh

# sur une instance distante, jeton obtenu dans Paramètres → Jetons d'API
python tests/charge/bench.py --url https://exemple.tld --token inv-... --sequentiel
python tests/charge/bench.py --url https://exemple.tld --token inv-... --concurrence 5 --duree 20
```

Sur une instance de production, la marche à suivre est celle qui a été
appliquée ici : sauvegarde `pg_dump` d'abord, répétition de l'injection **et
de la suppression** sur une cinquantaine de réservations avec vérification des
compteurs, puis seulement la campagne, puis `seed_charge --total 0 --reset` et
nouvelle vérification des compteurs.
