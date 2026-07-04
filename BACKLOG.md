# Backlog complet — MVP (S1 → S6)

Détail complet des **51 tickets du MVP** (sprints S1 à S6), classés dans l'**ordre chronologique d'exécution** (n° en tête de chaque fiche, tenant compte des dépendances). Chaque ticket précise le contexte / la user story et **ce qui est attendu** (critères d'acceptation).

**Légende Épic :** A — Organisateurs/Lieux · B — Réservation · E — Visualisation stock · F — Alertes · G — Retour & SAV · I — Livraisons/Ramassages · J — Planning · K — Technique/Infra

**Validation client :** 🔴 Must · 🟠 Should (MoSCoW)

---

## 🔧 S1 — Fondations (25 mai → 7 juin)

*Objectif : poser les fondations techniques (repo, auth, BDD, rôles, CI). — Total : 20 j*

### 1 · TR-01 — Mettre en place le repo, docker-compose et le Makefile

*Épic K · 🔴 Critique · 👤 Admin · ⏱️ 3 j · Statut : Review*

En tant qu'équipe, on veut un environnement reproductible pour que tout le monde puisse cloner et lancer `make up` en moins de 5 minutes.

**Attendu :**

- Repo créé avec branch protection sur `main`
- `docker-compose.yml` lance db + inventree + backend + frontend
- `Makefile` avec `up`, `down`, `migrate`, `test`
- README documente le démarrage en moins de 5 min

### 2 · DB-01 — Concevoir le schéma BDD complet (incl. tables post-MVP)

*Épic K · 🟠 Haute · ⏱️ 2 j · Statut : Review · Validation client : 🟠 Should*

Concevoir le schéma de base de données complet dès le départ, en incluant les tables nécessaires au post-MVP (V2). Le détail des entités est documenté dans la page dédiée au schéma BDD.

**Attendu :** modèle de données validé couvrant catalogue, réservations, livraisons/ramassages, retours/SAV et audit, avec délimitation claire MVP vs V2.

### 3 · TR-04 — CI GitHub Actions backend + frontend

*Épic K · 🟠 Haute · 👤 Admin · ⏱️ 1 j · Statut : In progress*

En tant qu'équipe, on veut une CI qui valide chaque PR pour ne jamais casser `main`.

**Attendu :**

- Workflow backend : ruff + pytest
- Workflow frontend : lint + vitest
- Status check obligatoire sur `main`
- Temps total `< 3 min`

### 4 · TR-02 — Authentification login/logout via DRF Token

*Épic K · 🔴 Critique · 👤 Admin, Gestionnaire · ⏱️ 2 j · Statut : Backlog*

En tant que gestionnaire, je veux me connecter à l'app pour que mes actions soient tracées.

**Attendu :**

- Endpoint `/api/auth/login/` qui retourne un token
- Endpoint `/api/auth/logout/` qui révoque le token
- Middleware DRF qui exige le token sur tous les autres endpoints
- Front : page login + stockage token + redirection si 401

### 5 · TR-03 — Rôles : 7 groupes mappés sur les personas

*Épic K · 🔴 Critique · 👤 Admin · ⏱️ 3 j · Statut : Backlog · Validation client : 🔴 Must*

En tant qu'admin, je veux attribuer un rôle précis à chaque utilisateur pour cloisonner les accès au plugin selon les profils confirmés par Tassin (réunion du 21 mai).

**Attendu :**

- 7 groupes Django : `admin`, `gestionnaire`, `magasinier`, `livreur`, `sav`, `organisateur`, `lecteur`
- Mapping permissions par rôle — Admin : CRUD complet + config plugin ; Gestionnaire : manifestations/prestations/réservations + arbitrage conflits ; Magasinier : check-in retours + stock ; Livreur : tournées + statuts livraison/ramassage + Maps ; SAV : tickets réparation + historique 90 j ; Organisateur : ses manifestations/résas ; Lecteur : read-only
- Décorateurs / permissions DRF sur chaque vue REST
- UI masque les actions selon le rôle
- Tests : un user par rôle vérifie accès autorisés / bloqués

### 6 · TR-05 — Modèle hiérarchique Manifestation > Prestation > Lieu

*Épic B · 🔴 Critique · 👤 Gestionnaire, Admin · ⏱️ 4 j · Statut : Backlog · Validation client : 🔴 Must*

Mettre en place le modèle hiérarchique Manifestation > Prestation > Lieu, supportant le multi-sites (jusqu'à 100 lieux par manifestation).

**Attendu :** entités Manifestation, Prestation et Lieu reliées, gestion multi-sites, base du module de réservation. *(Critères détaillés à compléter sur la fiche.)*

### 7 · CAT-01 — Client API InvenTree (token + méthodes de base)

*Épic E · 🔴 Critique · 👤 Admin · ⏱️ 2 j · Statut : Backlog*

En tant que backend, on veut un client typé qui parle à InvenTree pour découpler la logique métier de l'API externe.

**Attendu :**

- Classe `InvenTreeClient` avec auth token
- Méthodes : `list_parts`, `get_part`, `list_categories`
- Gestion d'erreur HTTP (timeout, 4xx, 5xx)
- Tests unitaires avec mock HTTP

### 8 · OPS-01 — Déploiement staging + variables d'env

*Épic K · 🟠 Haute · 👤 Admin · ⏱️ 3 j · Statut : Backlog*

En tant qu'admin, on veut un environnement de démo pour la soutenance.

**Attendu :**

- Hébergement choisi (VPS Hetzner, Scaleway, ou AWS Educate)
- HTTPS via Let's Encrypt (Caddy ou Traefik)
- Variables d'env via `.env` ou secret manager
- Backup BDD quotidien automatique

---

## 🏗️ S2 — Backend core (8 → 21 juin)

*Objectif : bâtir le backend (modèles, API, catalogue). — Total : 16 j*

### 9 · RES-01 — Modèles Reservation + ReservationLine + migrations

*Épic B · 🔴 Critique · 👤 Gestionnaire · ⏱️ 2 j*

En tant que backend, on veut les modèles de données de base pour les réservations.

**Attendu :**

- Modèle `Reservation` (statut, dates, demandeur, lieu, notes, créateur)
- Modèle `ReservationLine` (FK Réservation, inventree_part_id, qty)
- Index composites sur (start_date, end_date, status)
- Migration appliquée + tests modèles

### 10 · RES-02 — API CRUD réservation (DRF)

*Épic B · 🔴 Critique · 👤 Gestionnaire · ⏱️ 2 j*

En tant que frontend, on veut consommer une API typée pour gérer les réservations.

**Attendu :**

- `GET /api/reservations/` avec filtres (statut, dates)
- `POST /api/reservations/` (avec lignes nested)
- `PATCH /api/reservations/:id/`
- `DELETE /api/reservations/:id/`
- Tests unitaires des serializers

### 11 · CAT-02 — Liste paginée du matériel

*Épic E · 🔴 Critique · 👤 Gestionnaire, Lecteur · ⏱️ 2 j*

En tant que gestionnaire, je veux voir la liste de mon matériel pour savoir ce qui est disponible à la location.

**Attendu :**

- Endpoint `/api/catalog/parts/` qui proxy vers InvenTree
- Pagination (50 par page)
- Front : tableau Mantine avec scroll infini ou pagination
- Affichage : nom, photo miniature, catégorie, stock dispo

### 12 · CAT-03 — Filtres catalogue : catégorie, état, recherche

*Épic E · 🟠 Haute · 👤 Gestionnaire · ⏱️ 2 j*

En tant que gestionnaire, je veux filtrer le catalogue pour trouver rapidement le matériel.

**Attendu :**

- Filtre par catégorie (select multi)
- Filtre par état « louable / non-louable »
- Recherche texte (debounced 300 ms)
- URL state (filtres dans la query string)

### 13 · CAT-04 — Fiche détail d'un objet

*Épic E · 🟠 Haute · 👤 Gestionnaire · ⏱️ 1 j*

En tant que gestionnaire, je veux voir la fiche complète d'un objet avant de le réserver.

**Attendu :**

- Page `/catalog/:id` chargée depuis InvenTree
- Affichage : nom, description, photos, stock dispo, catégorie
- Lien retour vers la liste
- Bouton « Voir les réservations en cours » sur cet objet

### 14 · CAT-05 — Drapeau louable oui/non sur objet

*Épic E · 🟡 Moyenne · 👤 Gestionnaire · ⏱️ 1 j*

En tant que gestionnaire, je veux marquer certains objets comme non-louables (consommables, perdus) pour qu'ils n'apparaissent pas dans le sélecteur de réservation.

**Attendu :**

- Modèle `PartFlag` (inventree_part_id, is_rentable boolean) côté nous
- Toggle dans la fiche détail
- Filtre par défaut « louable uniquement » dans la liste
- Endpoint pour bulk-update

### 15 · CONSO-01 — Modélisation des consommables

*Épic E · 🟡 Moyenne · 👤 Gestionnaire, Magasinier · ⏱️ 2 j · Statut : Backlog · Validation client : 🟠 Should*

Modéliser les consommables (objets non récupérables / non réutilisables) afin de les distinguer du matériel louable rendu après prestation.

**Attendu :** type d'objet « consommable », décrément de stock définitif (pas de retour attendu). *(Critères détaillés à compléter sur la fiche.)*

### 16 · US-01 — Ajouter coordonnées GPS aux lieux

*Épic A · 🟠 Haute · 👤 Gestionnaire, Admin · ⏱️ 2 j · Statut : Backlog*

En tant que gestionnaire, je veux saisir les coordonnées GPS d'un lieu afin de permettre aux livreurs de naviguer vers la bonne adresse.

**Attendu :**

- Champ adresse + lat/long sur l'entité Lieu
- Géocodage auto à partir de l'adresse (Nominatim ou équivalent)
- Validation visuelle (mini-carte)
- Modification possible des coordonnées

### 17 · CON-01 — Algorithme de calcul des conflits sur période

*Épic B · 🔴 Critique · 👤 Gestionnaire · ⏱️ 2 j*

En tant que backend, on veut détecter les conflits de réservation pour avertir le gestionnaire.

**Attendu :**

- Service `compute_conflicts(part_id, qty, start, end, exclude_resa_id?)` qui retourne la liste des résa en conflit
- Conflit = somme des qty réservées sur la période > stock total disponible
- Statuts pris en compte : confirmée, livrée, retournée
- Tests unitaires (sans conflit, conflit partiel, conflit total)

---

## 🧱 S3 — Vertical slice (22 juin → 5 juil)

*Objectif : livrer un slice vertical (résa bout-en-bout + calendrier). — Total : 22 j*

### 18 · RES-03 — Écran liste des réservations

*Épic B · 🔴 Critique · 👤 Gestionnaire · ⏱️ 2 j*

En tant que gestionnaire, je veux voir toutes les réservations en une seule liste filtrable.

**Attendu :**

- Tableau colonnes : numéro, demandeur, événement, dates, statut, nb objets
- Filtres : statut, période, recherche
- Tri par date desc par défaut
- Bouton « Nouvelle réservation »

### 19 · RES-04 — Formulaire création/édition d'une réservation

*Épic B · 🔴 Critique · 👤 Gestionnaire · ⏱️ 3 j*

En tant que gestionnaire, je veux saisir une nouvelle réservation pour le compte d'un demandeur.

**Attendu :**

- Champs : demandeur, événement, dates, lieu, notes
- Sélecteur de matériel (autocomplete avec qty)
- Validation client (Mantine form) + serveur (DRF)
- Sauvegarde en brouillon possible
- Édition d'une résa existante via la même UI

### 20 · CON-02 — Affichage des conflits dans le formulaire de résa

*Épic B · 🔴 Critique · 👤 Gestionnaire · ⏱️ 2 j*

En tant que gestionnaire, je veux voir en direct les conflits quand je saisis une réservation pour décider en connaissance de cause.

**Attendu :**

- Appel à l'algo conflits à chaque changement (debounced 500 ms)
- Encart d'alerte avec liste des résa en conflit (numéro, demandeur, dates)
- Bouton « Forcer malgré les conflits » avec confirmation
- Coloration de la ligne conflictuelle

### 21 · RES-05 — Workflow de statut (Brouillon → Clôturée)

*Épic B · 🟠 Haute · 👤 Gestionnaire · ⏱️ 2 j*

En tant que gestionnaire, je veux faire passer une réservation d'un statut à l'autre selon l'avancement.

**Attendu :**

- Transitions valides : Brouillon → Confirmée → Livrée → Retournée → Clôturée + Annulée à tout moment
- Endpoint `/api/reservations/:id/transition/` qui valide la transition
- UI : boutons d'action contextuels selon le statut
- Log de l'événement de transition (qui, quand, vers quoi)

### 22 · US-02 — Réserver du matériel pour une prestation

*Épic B · 🔴 Critique · 👤 Gestionnaire · ⏱️ 4 j · Statut : Backlog*

En tant que gestionnaire, je veux créer un bon de réservation rattaché à une prestation afin de réserver les objets nécessaires sur la période concernée.

**Attendu :**

- Sélection d'objets via recherche/auto-complétion (catalogue InvenTree)
- Saisie quantité + période (couvre au minimum les dates de la prestation)
- Au moins 1 article virtuel obligatoire (ex : « nettoyage »)
- Statut brouillon / validé
- Numéro auto-généré

### 23 · US-03 — Détecter et résoudre les conflits de stock

*Épic B · 🔴 Critique · 👤 Gestionnaire · ⏱️ 3 j · Statut : Backlog*

En tant que gestionnaire, je veux que le système détecte automatiquement les conflits de stock afin d'éviter les double-réservations sur une même période.

**Attendu :**

- Calcul stock projeté = stock total − somme des bons sur la période
- Alerte visuelle si conflit (qty demandée > qty dispo)
- Liste des bons en conflit (lien direct)
- Refus de validation si conflit non résolu
- Suggestion d'ajustement de période ou de quantité

### 24 · CON-03 — Vue dédiée Conflits actuels

*Épic B · 🟠 Haute · 👤 Gestionnaire · ⏱️ 1 j*

En tant que gestionnaire, je veux une vue qui liste toutes les réservations en conflit pour pouvoir les résoudre.

**Attendu :**

- Page `/conflicts` listant tous les conflits actifs
- Tri par date de début ascendante
- Click sur ligne → détail de la résa
- Compteur de conflits affiché en navbar

### 25 · DIS-01 — Calendrier mensuel des réservations (FullCalendar)

*Épic J · 🟠 Haute · 👤 Gestionnaire, Lecteur · ⏱️ 3 j*

En tant que gestionnaire, je veux voir les réservations sur un calendrier mensuel pour avoir une vision d'ensemble.

**Attendu :**

- Composant FullCalendar React monté sur `/calendar`
- Endpoint `/api/reservations/calendar?from=&to=` qui retourne les events
- Couleur par statut
- Navigation mois précédent/suivant + retour aujourd'hui

### 26 · DIS-02 — Filtres calendrier : catégorie + statut

*Épic J · 🟡 Moyenne · 👤 Gestionnaire · ⏱️ 1 j*

En tant que gestionnaire, je veux filtrer le calendrier pour ne voir qu'une catégorie ou un statut.

**Attendu :**

- Select multi catégories
- Toggle par statut
- Persistance des filtres dans l'URL
- Bouton reset filtres

### 27 · DIS-03 — Click événement calendrier → ouvre la résa

*Épic J · 🟡 Moyenne · 👤 Gestionnaire · ⏱️ 1 j*

En tant que gestionnaire, je veux ouvrir la fiche réservation directement depuis le calendrier.

**Attendu :**

- Click event → modal détail OU navigation vers `/reservations/:id`
- Affichage rapide des infos clés
- Bouton « Éditer »

---

## 🎬 S4 — Démo 60% (6 → 26 juil)

*Objectif : démo à 60% (livraisons + dashboard + alertes). — Total : 23 j*

### 28 · US-27 — Consulter le planning des manifestations

*Épic J · 🔴 Critique · 👤 Gestionnaire, Lecteur · ⏱️ 3 j · Statut : Backlog*

En tant que gestionnaire, je veux un planning calendrier ET liste des manifestations / prestations afin d'avoir une vue d'ensemble de l'activité.

**Attendu :**

- Vue calendrier (mois / semaine) + vue liste
- Filtres : statut, lieu, matériel, organisateur
- Item cliquable → fiche manifestation
- Code couleur par statut

### 29 · US-07 — Visualiser l'histogramme de disponibilité d'un objet

*Épic E · 🟠 Haute · 👤 Gestionnaire, Acheteur · ⏱️ 3 j · Statut : Backlog*

En tant que gestionnaire, je veux un histogramme jour-par-jour de la disponibilité d'un objet afin d'identifier rapidement les périodes de tension.

**Attendu :**

- Échelle temporelle configurable (semaine/mois/trimestre)
- Code couleur de tension : 🟢 <50 % · 🔵 50 % · 🟡 75 % · 🟠 90 % · 🔴 >98 %
- Tooltip : qty totale, qty réservée, bons concernés
- Filtre par lieu/manifestation

### 30 · US-08 — Tableau de bord global des bons de réservation

*Épic E · 🟡 Moyenne · 👤 Gestionnaire, Lecteur · ⏱️ 2 j · Statut : Backlog*

En tant que gestionnaire, je veux une liste filtrable de tous les bons de réservation afin de suivre l'activité et retrouver rapidement un dossier.

**Attendu :**

- Colonnes : numéro, manifestation, prestation, statut, période, montant
- Filtres : statut, lieu, période, organisateur, matériel
- Recherche full-text
- Tri sur chaque colonne

### 31 · US-09 — Configurer alertes seuils sur stock

*Épic F · 🟡 Moyenne · 👤 Acheteur, Magasinier · ⏱️ 2 j · Statut : Backlog*

En tant qu'acheteur, je veux être alerté quand un consommable atteint un seuil bas afin de déclencher un réapprovisionnement à temps.

**Attendu :**

- Seuil haut/bas configurable par objet
- Alerte visuelle (bandeau dashboard) + email
- Alerte aussi sur tension de stock projetée >90 %
- Liste des objets en alerte

### 32 · US-17 — Voir mes livraisons

*Épic I · 🟠 Haute · 👤 Livreur · ⏱️ 2 j · Statut : Backlog*

En tant que livreur, je veux voir la liste des livraisons à effectuer afin d'organiser ma tournée.

**Attendu :**

- Liste filtrable par date / lieu / statut
- Vue carte (V2) ou simple liste (MVP)
- Détail : adresse, contact organisateur, contenu, qty totale
- Bon de livraison imprimable

### 33 · US-18 — Choisir / accepter une livraison

*Épic I · 🟠 Haute · 👤 Livreur · ⏱️ 1 j · Statut : Backlog*

En tant que livreur, je veux prendre en charge une livraison disponible afin qu'elle me soit assignée et disparaisse du pool commun.

**Attendu :**

- Bouton « accepter »
- Verrou : une livraison = 1 seul livreur assigné
- Possibilité de relâcher avant le début
- Notification au gestionnaire

### 34 · US-19 — Gérer les états d'une livraison

*Épic I · 🟠 Haute · 👤 Livreur · ⏱️ 2 j · Statut : Backlog*

En tant que livreur, je veux changer l'état d'une livraison (en route, livré, problème) afin que le gestionnaire ait une visibilité temps réel.

**Attendu :**

- États : assignée → en cours → livrée / problème
- Horodatage de chaque transition
- Photo possible à la livraison
- Signature destinataire (V2)

### 35 · US-20 — Accéder au lieu via GPS

*Épic I · 🟡 Moyenne · 👤 Livreur · ⏱️ 1 j · Statut : Backlog*

En tant que livreur, je veux lancer un itinéraire GPS vers le lieu de livraison afin de ne pas chercher l'adresse manuellement.

**Attendu :**

- Bouton « ouvrir dans Google Maps / Apple Plans »
- Coordonnées passées en paramètre URL
- Fonctionne sur mobile et desktop

### 36 · US-21 — Voir mes ramassages

*Épic I · 🟠 Haute · 👤 Livreur · ⏱️ 1 j · Statut : Backlog*

En tant que livreur, je veux voir la liste des ramassages à effectuer afin de récupérer le matériel après les prestations.

**Attendu :**

- Liste des ramassages (peut couvrir plusieurs prestations)
- Filtre date / lieu / statut
- Bon de ramassage imprimable
- Récap qty totale par véhicule

### 37 · US-22 — Choisir / accepter un ramassage

*Épic I · 🟠 Haute · 👤 Livreur · ⏱️ 1 j · Statut : Backlog*

En tant que livreur, je veux prendre en charge un ramassage disponible afin de me l'assigner.

**Attendu :**

- Bouton « accepter »
- Un ramassage = 1 seul livreur
- Possible de couvrir plusieurs prestations terminées d'un même lieu
- Notification gestionnaire

### 38 · US-23 — Déclarer un ramassage terminé

*Épic I · 🟠 Haute · 👤 Livreur · ⏱️ 2 j · Statut : Backlog*

En tant que livreur, je veux clôturer un ramassage avec saisie qty récupérée afin de déclencher le workflow de retour côté magasin.

**Attendu :**

- Saisie qty effectivement ramassée par ligne
- Photo possible si différence
- Statut ramassage → terminé
- Notification magasinier pour traitement retour

### 39 · LIV-04 — Optimisation tournées V1 (ordre manuel + Maps multi-stops)

*Épic I · 🔴 Critique · 👤 Livreur, Magasinier · ⏱️ 3 j · Statut : Backlog · Validation client : 🔴 Must*

**Pourquoi :** réponse de Benoit (20 mai) sur le pain point n°1 — « effectuer les livraisons et ramassages avec un minimum de trajet et un maximum d'exactitude ». Version V1 minimale viable pour la soutenance.

**Périmètre V1 :**

- Écran tournée du jour : liste ordonnée d'arrêts (livraisons + ramassages mélangés)
- Drag & drop pour réordonner manuellement les arrêts
- Bouton « Ouvrir l'itinéraire complet dans Google Maps » (URL `maps/dir/?api=1&waypoints=...`)
- Affichage distance totale et durée estimée

**Hors périmètre V1 (→ V1.x) :** optim automatique TSP, carte interactive embed, navigation turn-by-turn.

**Attendu :** le livreur voit sa tournée du jour dans l'ordre choisi ; le lien Maps ouvre l'itinéraire complet avec tous les arrêts ; l'ordre est persisté au rechargement.

---

## 🛠️ S5 — Prod & rapport (27 juil → 30 août)

*Objectif : industrialiser (retours/SAV, perf, tests, doc). — Total : 23 j*

### 40 · RET-02 — Modèle de log incidents retour (manquant / cassé)

*Épic G · 🟠 Haute · 👤 Gestionnaire · ⏱️ 1 j*

En tant que backend, on veut un modèle de log pour tracer les incidents de retour.

**Attendu :**

- Modèle `ReturnIncident` (line, type, qty, comment, reported_at, reported_by)
- Type = enum (`missing` | `broken`)
- Migration + tests
- Sérialiseur DRF read-only

### 41 · RET-01 — Écran de check-in retour (OK / manquant / cassé)

*Épic G · 🔴 Critique · 👤 Magasinier, Gestionnaire · ⏱️ 3 j*

En tant que magasinier, je veux pointer le retour ligne par ligne pour tracer ce qui revient et dans quel état.

**Attendu :**

- Page `/reservations/:id/checkin` accessible quand statut = Livrée
- Pour chaque ligne : 3 inputs numériques (OK, manquant, cassé) + commentaire
- Validation : somme(OK + manquant + cassé) = qty initiale
- À la sauvegarde : transition Retournée → Clôturée + log incidents

### 42 · US-10 — Déclarer le retour d'une prestation

*Épic G · 🟠 Haute · 👤 Magasinier · ⏱️ 2 j · Statut : Backlog*

En tant que magasinier, je veux déclarer le retour effectif d'une prestation après ramassage afin de réintégrer le matériel en stock et clore le cycle.

**Attendu :**

- Vue ligne par ligne du bon de réservation
- Saisie qty rendue par ligne
- Statut bon : retour partiel / retour complet
- Stock physique mis à jour

### 43 · US-11 — Identifier les manquants au retour

*Épic G · 🟠 Haute · 👤 Magasinier · ⏱️ 2 j · Statut : Backlog*

En tant que magasinier, je veux marquer les objets manquants au retour afin de distinguer perte vs casse et facturer le client si besoin.

**Attendu :**

- Bouton « manquant » par ligne
- Champ commentaire libre
- Option « facturer au client » (oui/non) par ligne
- Mise à jour automatique du rapport de pertes

### 44 · US-12 — Identifier les objets cassés réparables

*Épic G · 🟠 Haute · 👤 Magasinier, SAV · ⏱️ 3 j · Statut : Backlog · Validation client : 🔴 Must*

En tant que magasinier, je veux marquer un objet en « cassé réparable » et créer un Repair Ticket afin de lancer le workflow SAV.

**Attendu :**

- Création d'un RepairTicket lié à la ligne de retour
- Stock en quarantaine (non disponible pour réservation)
- Workflow SAV : à réparer → en réparation → réparé / détruit
- Option facturation client

### 45 · US-13 — Identifier les objets détruits / perdus

*Épic G · 🟠 Haute · 👤 Magasinier, SAV · ⏱️ 2 j · Statut : Backlog · Validation client : 🔴 Must*

En tant que magasinier, je veux marquer un objet en « détruit » ou « perdu » afin de sortir définitivement l'objet du stock et tracer la perte.

**Attendu :**

- Sortie définitive du stock
- Motif obligatoire
- Inscription dans le rapport de pertes
- Option facturation client

### 46 · US-14 — Générer un rapport de retour

*Épic G · 🟡 Moyenne · 👤 Gestionnaire, Magasinier · ⏱️ 2 j · Statut : Backlog*

En tant que gestionnaire, je veux un rapport synthétique du retour d'une prestation afin d'ajuster la facture et communiquer avec le client.

**Attendu :**

- PDF imprimable + export
- Récap : rendu / manquant / cassé / détruit, par ligne
- Total à facturer en plus
- Photos jointes si dispo

### 47 · RET-03 — Vue historique des retours problématiques (90 j)

*Épic G · 🟡 Moyenne · 👤 Gestionnaire · ⏱️ 2 j*

En tant que gestionnaire, je veux voir tous les incidents de retour des 90 derniers jours pour suivre les problèmes récurrents.

**Attendu :**

- Page `/returns/history` listant les `ReturnIncident` des 90 j
- Filtres : type, objet, événement
- Tri par date desc
- Lien vers la résa parente

### 48 · PERF-01 — Indexation BDD + archivage (≈10 000 résa / an)

*Épic K · 🟠 Haute · 👤 Admin · ⏱️ 3 j · Statut : Backlog · Validation client : 🔴 Must*

**Pourquoi :** réponse de Benoit (20 mai) — volume cible ≈10 000 réservations/an, avec des pics de 30 résa sur un même week-end.

**Périmètre :**

- Index PostgreSQL sur `date_debut`, `date_fin`, `status`, `client_id`, `lieu_id`, `prestation_id`
- Pagination obligatoire sur toutes les listes (DRF `LimitOffsetPagination` / `CursorPagination`)
- Archivage : résa clôturées >2 ans → table d'archive ou flag `is_archived`
- Tests de charge : 10K résa, mesurer temps de réponse liste paginée + filtres

**Attendu :** liste paginée `< 500 ms` avec 10K rows, index visibles en `EXPLAIN ANALYZE`, mécanisme d'archivage documenté, tests pytest avec 10K fixtures.

### 49 · OPS-03 — Tests pytest sur endpoints critiques

*Épic K · 🟠 Haute · 👤 Admin · ⏱️ 3 j*

En tant qu'équipe, on veut des tests automatisés sur les endpoints clés pour ne pas régresser.

**Attendu :**

- Tests sur CRUD réservation
- Tests sur algo conflits
- Tests sur transition de statut
- Tests sur check-in retour
- Couverture cible `> 60 %` sur les apps métier

---

## 🏁 S6 — Polish & soutenance (31 août → 16 sept)

*Objectif : finaliser et préparer la soutenance. — Total : 4 j*

### 50 · TEST-01 — Tests manuels multi-navigateurs

*Épic K · 🟠 Haute · ⏱️ 2 j · Statut : Backlog · Validation client : 🟠 Should*

Tester manuellement l'application sur Safari, Chrome, Edge et Firefox.

**Attendu :** parcours clés (login, création résa, calendrier, check-in retour, conflits) validés sur chaque navigateur, anomalies de rendu corrigées. *(Critères détaillés à compléter sur la fiche.)*

### 51 · OPS-02 — Documentation utilisateur minimale

*Épic K · 🟡 Moyenne · 👤 Lecteur · ⏱️ 2 j*

En tant que lecteur, je veux une doc qui explique comment utiliser l'app pour que le client soit autonome après livraison.

**Attendu :**

- Doc Markdown dans `/docs/user/`
- 5 parcours documentés : login, créer résa, voir calendrier, check-in retour, gérer conflits
- Captures d'écran à jour
- Index lisible avec table des matières
