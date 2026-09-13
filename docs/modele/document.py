# -*- coding: utf-8 -*-
"""Génère le document « Modèle de données & règles métier ».

Usage :
    python3 schema.py && python3 document.py
    "…/Google Chrome" --headless --no-pdf-header-footer \
        --print-to-pdf="$HOME/Downloads/<nom>.pdf" modele.html

Sources : point de revue du 09/09/2026, cahier des charges V06 (texte **et**
annexes graphiques — les quatre maquettes et le schéma simplifié), code
existant.
"""

import re
from pathlib import Path

import schema as _schema

ICI = Path(__file__).parent

planches = [
    ((ICI / f"schema{index}.svg").read_text(), titre)
    for index, (titre, *_) in enumerate(__import__("schema").PLANCHES, start=1)
]

R = {
    "Acteurs et accès": [
        (
            "R1",
            "Un acteur interne porte <b>exactement un</b> rôle. Pas de cumul.",
            "décision client",
        ),
        ("R2", "Le superutilisateur reste exempt de tout filtrage.", "code"),
        (
            "R3",
            "Le client et ses contacts sont <b>externes</b> : aucun identifiant, aucune interface, jamais de compte Django.",
            "décision client",
        ),
        (
            "R4",
            "Un <b>gestionnaire client gère un ou plusieurs clients</b>. Un client a au plus un gestionnaire référent.",
            "décision client",
        ),
        (
            "R5",
            "Un acteur interne n'appartient à aucun client — <code>Profile.groupe</code> supprimé sans remplaçant.",
            "décision client",
        ),
        (
            "R6",
            "Le rôle <code>organisateur</code> n'existe plus : le client externe n'a pas besoin d'accès.",
            "réunion 09/09",
        ),
        (
            "R6b",
            "La <b>barre horizontale d'InvenTree s'adapte au rôle</b> : chaque onglet natif est conditionné au droit de lecture d'un ruleset (<code>getNavTabs</code> teste <code>hasViewRole</code>). Fabrication et Ventes sont réservées à l'admin ; le Dashboard reste visible pour tous et porte le poste de travail.",
            "code InvenTree",
        ),
    ],
    "Client et contact": [
        (
            "R7",
            "<code>Client</code> est une personne morale <b>ou</b> un particulier (<code>type_client</code>). Unicité métier sur <code>email</code>. Pas de <code>code</code>.",
            "décision client",
        ),
        (
            "R8",
            "Chaque personne qui contacte l'organisation est un <code>Contact</code> de ce client. <code>Contact.email</code> unique <b>globalement</b>, pas par client.",
            "réunion 09/09",
        ),
        (
            "R9",
            "Un client porteur de manifestations ne peut pas être supprimé (<code>PROTECT</code>) — question d'historique.",
            "décision client",
        ),
        (
            "R9b",
            "<b><code>Client.actif</code> et <code>Contact.actif</code> à créer.</b> Un client inactif reste consultable et ses manifestations lisibles, mais on ne peut plus créer de manifestation dessus ; un contact inactif sort des listes sans disparaître des devis qu'il a signés.",
            "déduit",
        ),
    ],
    "Hiérarchie": [
        (
            "R10",
            "<code>client → manifestation → prestation → articles</code>, portée par les clés étrangères. Aucune ressaisie.",
            "réunion 09/09",
        ),
        (
            "R11",
            "Une manifestation appartient à <b>un seul</b> client et nomme un <b>contact référent</b> : c'est lui qu'on appelle sur place, et lui <b>ou le client lui-même</b> qui signe.",
            "décision client",
        ),
        (
            "R12",
            "Une manifestation contient <b>une ou plusieurs</b> prestations. Deux prestations peuvent partager le jour et le lieu à des heures différentes, chacune avec sa liste d'articles.",
            "réunion 09/09",
        ),
        (
            "R13",
            "<code>Prestation.lieu</code> reste <b>nullable</b> — c'est ce qui autorise les brouillons.",
            "code",
        ),
        (
            "R13b",
            "<b>Permissif au stockage, strict à la transition.</b> Lieu facultatif en <code>brouillon</code> avec alerte, <b>obligatoire au passage en <code>planifiee</code></b>, devis impossible sans lieu sur toutes les prestations.",
            "déduit",
        ),
    ],
    "Devis et réservation": [
        (
            "R14",
            "Bon de réservation <b>généré automatiquement</b>, pour <b>un lieu et une prestation</b>, avec les dates de l'évènement <b>et</b> la date/heure de livraison attendue. Contient au moins un article virtuel.",
            "CDC §44",
        ),
        (
            "R15",
            "<b>Devis ↔ bons de réservation = N↔M.</b> Un client peut avoir plusieurs devis par manifestation, un devis peut couvrir plusieurs bons.",
            "CDC §45, §82",
        ),
        (
            "R16",
            "<b>Un devis signé ne bloque pas les bons.</b> Toute modification après acceptation est tracée : personne, <b>canal</b> (tél / mail / verbal / courrier), horodatage, message.",
            "CDC §45",
        ),
        (
            "R17",
            "Une ligne modifiée après acceptation prend un <b>état</b> : <code>normale</code> | <code>hors_devis</code> | <code>annulee</code>. <code>modifie_apres_devis</code> porte le drapeau au niveau prestation.",
            "CDC §45",
        ),
        (
            "R18",
            "La signature enregistre <code>date_acceptation</code>, <code>support_acceptation</code> et le signataire → <code>signataire_contact</code> (FK nullable) <b>+</b> <code>signataire_libelle</code> (snapshot figé). Refus tracé par <code>motif_refus</code>.",
            "CDC §45",
        ),
        (
            "R19",
            "Disponibilité du stock <b>au jour entier</b> : un objet ne peut servir deux prestations le même jour, quelle que soit la plage horaire. Les heures ne servent qu'à la logistique.",
            "CDC §42",
        ),
        (
            "R20",
            "Tarification : prix unitaire <b>€ HT par objet</b>, <b>taux de TVA par objet</b>, et <b>soit</b> une grille à 5 niveaux de quantité, <b>soit</b> un tableau de remises génériques à 5 niveaux. Plus la remise globale de la manifestation : trois mécanismes à hiérarchiser.",
            "CDC §46",
        ),
        (
            "R21",
            "Une facture peut concerner <b>plusieurs devis</b>, en incluant les lignes « hors devis » et en éliminant les annulées.",
            "CDC §88",
        ),
    ],
    "Livraison": [
        (
            "R22",
            "Le livreur choisit dans une liste <b>les prestations et lieux</b> à livrer, et peut faire <b>plusieurs livraisons dans une même journée</b>.",
            "CDC §48",
        ),
        (
            "R23",
            "Un bon peut être livré <b>en une ou plusieurs fois</b>, mais <b>en entier</b> au total — <b>sauf les lignes annulées</b>.",
            "CDC §83-84",
        ),
        (
            "R24",
            "<b>Échéance dure : tout livré avant le début de la prestation.</b> Seul invariant temporel, et il est contrôlable.",
            "CDC §85",
        ),
        (
            "R25",
            "La tournée affiche les objets par lieu et le nom du client, <b>plus un récapitulatif total tous lieux confondus</b> pour le chargement des véhicules.",
            "CDC §48",
        ),
        (
            "R26",
            "<b>Une livraison se rattache à la ligne de réservation</b> et porte sa <code>quantite_livree</code> — <code>DeliveryTask.IDLocation → BonDeReservation</code> dans le schéma du CDC. Le lieu est un attribut de la tâche, pas sa clé.",
            "CDC, schéma annexe",
        ),
        (
            "R27",
            "<code>quantite_rest_a_livrer</code> est <b>calculé, jamais stocké</b> : c'est un agrégat sur tous les passages.",
            "déduit",
        ),
        (
            "R28",
            "Photo possible à chaque livraison (<code>Preuves</code>). Bons imprimables tant qu'il n'y a pas d'application mobile.",
            "CDC §48, §50",
        ),
    ],
    "Ramassage et retour": [
        (
            "R29",
            "<b>Le livreur compose sa liste en choisissant des lieux</b> (CDC §49), mais <b>la saisie et le stockage se font par ligne de réservation</b> — <code>PickupTask.IDLocation → BonDeReservation</code>. Le regroupement par lieu est une <b>vue</b>, pas une clé.",
            "CDC §49, schéma annexe",
        ),
        (
            "R30",
            "Les <b>quantités attendues affichées</b> au livreur sont la somme de tous les articles de la journée sur un lieu donné, parce que des objets circulent entre lieux. C'est une règle d'<b>affichage</b> : elle n'change pas la maille de stockage (R29).",
            "réunion 09/09",
        ),
        (
            "R31",
            "<b>N↔M sur le bon papier</b> : le ramassage d'une prestation peut faire l'objet de plusieurs bons, et un bon peut couvrir plusieurs prestations terminées.",
            "CDC §86-87",
        ),
        (
            "R32",
            "Vocabulaire : <b>ok</b> = rendu conforme, réintègre le stock · <b>cassé</b> = endommagé <b>réparable</b> → ticket de réparation · <b>détruit</b> = endommagé <b>non réparable</b> · <b>manquant</b> = non retrouvé. Les trois derniers sortent du stock disponible.",
            "décision client",
        ),
        (
            "R33",
            "La saisie de ramassage offre <b>quatre compteurs par ligne</b> — récupéré, cassé, détruit, manquant — plus une photo et une bascule de facturation.",
            "CDC, maquette Ramassage",
        ),
        (
            "R34",
            "Le <b>manquant est un compteur saisi</b>, <b>pré-rempli par l'autocomparaison</b> « quantité sortie vs quantité retournée » et corrigeable à la main. Il ne se calcule pas dans le dos du livreur, et il ne se saisit pas à l'aveugle.",
            "CDC §380 + maquette",
        ),
        (
            "R35",
            "<code>ramassage_termine</code> (<code>FullPickup</code>) dit si le lieu a été entièrement ramassé ou s'il reste des objets. Ce qui reste sur un lieu non terminé n'est <b>pas</b> perdu : un autre bon viendra.",
            "CDC §49, §86",
        ),
        (
            "R36",
            "<b>Aucun plafond au ramassage.</b> Un surplus (12 retrouvés pour 10 attendus) est légitime — des objets ont été déplacés — et se répartit entre récupéré, cassé et détruit. On signale, on ne refuse pas.",
            "décision client",
        ),
        (
            "R37",
            "« À facturer » est un <b>booléen par ligne activé par le livreur</b> sur les cassés, détruits et manquants (<code>AFacturer</code>), pas une conséquence automatique du type.",
            "CDC §49 + schéma",
        ),
        (
            "R38",
            "Saisie <b>modifiable tant que le bon de réservation n'est pas clôturé</b>, plus un bouton « tout est rentré » qui pré-remplit récupéré = attendu.",
            "CDC §374, §376",
        ),
        (
            "R39",
            "Le ramassage terminé <b>déclenche</b> le workflow de retour. Statuts : à planifier → en cours → récupéré.",
            "CDC §499-503",
        ),
        (
            "R40",
            "<b>« Casse prime sur manquant »</b> : l'état de retour d'une ligne est recalculé, jamais mémorisé — supprimer un incident ramène la ligne à son état réel.",
            "code",
        ),
        (
            "R41",
            "Les <b>articles virtuels</b> sont exclus du ramassage — un bon en contient toujours au moins un, et « le nettoyage du lieu » n'a rien à faire revenir.",
            "CDC §44",
        ),
        (
            "R42",
            "Un cassé ouvre un <b>ticket de réparation</b> (<code>RepairTicket</code> : motif, quantité, durée estimée et réelle, dates, facturation). Le réparateur réintègre l'objet au stock ou le passe en destruction.",
            "CDC §669, schéma annexe",
        ),
    ],
    "Transverse": [
        (
            "R43",
            "« La journée » se calcule en Europe/Paris, jamais sur de l'UTC brut.",
            "code",
        ),
        (
            "R44",
            "Traçabilité via le suivi de stock natif ; inventaire physique = mouvement « Ajustement d'inventaire ».",
            "CDC",
        ),
        (
            "R45",
            "Un objet porte : NOI, nom (100 c.), descriptif (500 c.), URL, photo, poids unitaire, et les booléens actif, PACK (BOM native, aucun développement), vendable, virtuel, consommable.",
            "CDC §659",
        ),
    ],
}

C = [
    (
        "C1",
        "<code>NOI</code> en clé primaire",
        "<code>NOI</code> <b>est</b> l'IPN d'InvenTree : ni unique ni obligatoire. Tout le plugin joint sur l'identifiant technique de la pièce. Reste un identifiant métier affiché.",
    ),
    (
        "C2",
        "RBAC maison (<code>Role</code>, <code>Permission</code>, <code>RolePermission</code>)",
        "Décrit ce que Django fournit déjà. Les groupes natifs sont obligatoires : les droits InvenTree y sont attachés, le front lit les groupes de l'utilisateur, et ce sont eux qui filtrent la barre de navigation par rôle.",
    ),
    (
        "C3",
        "Pas de contact sur la manifestation",
        "<b><code>Manifestation.contact</code> ajouté.</b> Sans lui, un client à cinq contacts donne au livreur un numéro de standard au lieu du portable du référent.",
    ),
    (
        "C4",
        "<code>quantite_rest_a_livrer</code> en colonne",
        "Agrégat sur plusieurs passages → champ calculé.",
    ),
    (
        "C5",
        "<code>RepairTicket</code> en table neuve",
        "Devient des colonnes sur le ticket SAV existant, qui porte déjà statut, quantité et facturation.",
    ),
    (
        "C6",
        "Tables <code>Article</code>, <code>Fournisseur</code>, <code>ArticleFournisseur</code>",
        "Déjà couvertes par InvenTree. Seul <code>poids</code> manque réellement. Les recréer dédoublerait le catalogue et le référentiel fournisseurs.",
    ),
]

M = [
    (
        "Planning",
        "Gantt des manifestations sur les jours, pastilles de statut (brouillon, confirmé, annulé, livré, ramassé), bascule Calendrier / Liste, fiche détaillée par manifestation : contact, nombre de personnes, lieux, volumes, état de livraison et de ramassage.",
        "<b>Livré</b> (F5) : <code>Planning</code> — Gantt en grille CSS aux échelles jour / semaine / mois / année, barres dépliables sur les prestations, fiche au survol, bascule Calendrier / Liste. L'ancien calendrier mensuel reste sous l'onglet Réservations.",
    ),
    (
        "Manifestation",
        "Arborescence dépliable <b>manifestation → prestation → bon de réservation → articles</b>, avec par ligne la quantité réservée, livrée et ramassée. Recherche, filtres Futur / Passé / Tout / À facturer, boutons d'ajout de prestation, de réservation et d'article.",
        "<b>Livré</b> (A2, F4) : arborescence dépliable, quantités par ligne, et les trois boutons d'ajout branchés sur les formulaires existants. Manquent le niveau <b>client</b> au-dessus (F3) et le filtre « À facturer », affiché désactivé faute de règle de facturation.",
    ),
    (
        "Livraison",
        "Table hiérarchique aux mêmes niveaux, compteurs −/+ et photo par ligne, cases de validation par ligne et par prestation, filtres Tous / À faire / Partiel / Complet, envoi groupé.",
        "<code>DeliveriesList</code> : liste plate et modale. Ni hiérarchie, ni compteurs, ni envoi groupé.",
    ),
    (
        "Ramassage",
        "Même table, avec <b>quatre compteurs par ligne</b> (récupéré, cassé, détruit, manquant), photo, bascule de facturation et case de ramassage complet.",
        "<code>RamassagesList</code> et son formulaire portent les quatre quantités, mais pas dans une table hiérarchique.",
    ),
]

# ---------------------------------------------------------------------------
# Plan de mise en œuvre
# ---------------------------------------------------------------------------

LIVRE = [
    (
        "D0",
        "Tables du devis et de la tarification",
        "Grille de prix, table de remises, TVA, `Devis`, `LigneDevis`, `FactureReservation`, état de ligne et journal des modifications. Tables seulement.",
        "95d89e1",
    ),
    (
        "A1",
        "Filtres d'API de l'arborescence",
        "`periode` sur les manifestations, `prestation` sur les réservations, nom et référence d'article sur les lignes.",
        "9d7e702",
    ),
    (
        "A2",
        "Écran arborescence",
        "Manifestation → prestation → bon → articles, chargé au dépliage, avec recherche, filtres et pastilles d'état.",
        "6ff1893",
    ),
    (
        "P1",
        "Postes par rôle et barre de navigation",
        "Un widget par rôle avec sa navigation verticale, et la barre horizontale d'InvenTree filtrée par les droits de lecture des rulesets.",
        "5e96c70",
    ),
    (
        "L0",
        "Factory de tests partagée",
        "Vingt-neuf fichiers reconstruisaient la même chaîne d'objets. Investissement remboursé au lot suivant : `Groupe` n'apparaissait plus que dans 5 fichiers, la bascule en a donc touché 5 au lieu de 29.",
        "824a09c",
    ),
    (
        "L1",
        "Champs manquants et jeu de démonstration",
        "Poids, statut de prestation, couleur, remise globale, description de lieu. Plus `seed_demo`, qui sert autant à rejouer une démonstration qu'à éprouver les migrations sur une base non vide.",
        "2448882",
    ),
    (
        "L2",
        "Client et contacts",
        "`Groupe` devient `Client` (e-mail, téléphone, type, SIRET, gestionnaire référent, actif), `Contact` apparaît, `Manifestation.organisateur` devient `Manifestation.contact`. Trois migrations, vérifiées sur les données réelles du conteneur.",
        "b7fd916",
    ),
    (
        "L4",
        "Rôle unique et retrait de l'organisateur",
        "Un acteur interne porte un seul rôle. Le rôle `organisateur` est supprimé — le client externe n'a pas de compte.",
        "cd2abc3",
    ),
    (
        "L5",
        "Couture d'exécution et deux trous fermés",
        "`quantite_attendue_au_retour` remplace les quatre écritures de la même règle. Unicité `(ligne, nature)` sur le registre d'incidents, déduplication par somme. Et le remplacement des lignes d'un bon qui porte un constat est refusé au lieu d'effacer le registre par cascade.",
        "df27503",
    ),
    (
        "L6",
        "Tables d'exécution et tournée du jour",
        "`Livraison` et `Ramassage` rattachées au bon, leurs quantités à la maille de la ligne. Projection recalculée depuis la vérité (`projeter_execution`), divergences affichées sans rien écrire (`verifier_projection`), et `GET /tournees/?date=` qui rend les arrêts par lieu **et** le récapitulatif tous lieux confondus.",
        "2e74fca",
    ),
    (
        "L5b",
        "Plafond du ramassage levé",
        "R36 dit depuis le début qu'un surplus est légitime ; le serveur refusait pourtant tout total supérieur au sorti, à deux endroits — la saisie de ramassage et le registre d'incidents. Seul le manquant reste borné : on ne perd pas ce qui n'est pas parti. Trois tests affirmaient l'inverse, dont un écrit au lot L5.",
        "be356a4",
    ),
    (
        "A3",
        "Filtre client sur les manifestations",
        "`client=` sur `/manifestations/`, distinct de `search` qui porte sur le nom de l'évènement : au téléphone on connaît le client, pas le nom de la manifestation. Sélecteur posé sur les deux écrans qui en listent.",
        "f012a15",
    ),
    (
        "F5",
        "Écran Planning",
        "Les manifestations étalées sur les jours, aux échelles jour / semaine / mois / année, avec leur couleur, leur statut, la fiche au survol — client, interlocuteur, volume, avancement — et la bascule Calendrier / Liste. La barre se déplie sur ses **prestations** : la maille demandée en recette, sans perdre la vue d'ensemble. Grille CSS, pas de bibliothèque de Gantt.",
        "3211735",
    ),
    (
        "F1",
        "Onglet Contacts du back-office",
        "Créer, éditer et désactiver les interlocuteurs d'un client. L'API existait depuis L2 ; aucun écran ne s'y branchait, un contact ne pouvait naître que du shell. Pas de suppression — un contact a peut-être signé un devis. Le contact déjà choisi reste proposé même désactivé, sinon rouvrir une manifestation effacerait silencieusement son interlocuteur.",
        "3f3da9e",
    ),
    (
        "F4",
        "Boutons d'ajout de l'arborescence",
        "Les trois « + » ouvrent les formulaires existants — `PrestationCreateModal`, `ReservationForm` — montés en modale plutôt que réécrits, et disparaissent sans le droit d'écriture.",
        "1c72982",
    ),
]

#: État de chaque table. Dérivé à la main : le code ne dit pas si une table
#: est exploitée par un écran ou seulement créée.
ETAT_TABLES = {
    "user": ("En service", "auth"),
    "profile": ("En service", ""),
    "client": ("En service", "L2"),
    "contact": ("En service", "L2"),
    "manif": ("En service", ""),
    "presta": ("En service", "L1"),
    "lignepresta": ("En service", ""),
    "bon": ("En service", ""),
    "ligne": ("En service", ""),
    "lieu": ("En service", "L1"),
    "part": ("InvenTree", ""),
    "rentable": ("En service", "L1"),
    "tremise": ("Créée, pas encore exploitée", "D0"),
    "premise": ("Créée, pas encore exploitée", "D0"),
    "ptarif": ("Créée, pas encore exploitée", "D0"),
    "devis": ("Créée, pas encore exploitée", "D0"),
    "lignedevis": ("Créée, pas encore exploitée", "D0"),
    "facture": ("Créée, pas encore exploitée", "D0"),
    "modif": ("Créée, pas encore exploitée", "D0"),
    "livr": ("Projection, en lecture", "L6"),
    "livrl": ("Projection, en lecture", "L6"),
    "ram": ("Projection, en lecture", "L6"),
    "rama": ("Projection, en lecture", "L6"),
    "incident": ("En service", "L5"),
    "sav": ("En service", ""),
    "logresa": ("En service", ""),
    "loglivr": ("En service", ""),
    "conflit": ("En service", ""),
}

#: Recette du 11/09/2026 (Hanane), confrontée aux règles et au code.
RECETTE = [
    (
        "Remplacer groupe par client",
        "Fait",
        "L2 — migration `0026`, renommage sur place",
    ),
    (
        "Remplacer client par contact",
        "Fait",
        "L2 — `Manifestation.organisateur` → `contact`",
    ),
    (
        "Séparer création d'utilisateur et de client",
        "Fait",
        "L2 — `Profile.groupe` supprimé",
    ),
    (
        "Un client peut avoir plusieurs contacts",
        "Fait",
        "R8 — `Client 1 — 0..N Contact`",
    ),
    ("Client = personne morale, contacts à l'intérieur", "Fait", "R7"),
    (
        "Chaîne client → manifestation → prestation → réservation → matériel",
        "Fait",
        "R10, portée par les clés étrangères",
    ),
    (
        "Voir le livré et le restant à livrer",
        "Fait",
        "L6 — calculé, exposé par `/tournees/`",
    ),
    (
        "Consulter le stock sur une période donnée",
        "Fait côté API",
        "l'endpoint existe ; reste à l'exposer à l'écran",
    ),
    ("Voir les calendriers sur une période", "Fait", "planning semaine / mois / année"),
    (
        "Rôles principaux gestionnaire, livreur, magasinier",
        "Fait",
        "R1 — un seul rôle par acteur",
    ),
    (
        "Onglets Client puis Contact, côte à côte",
        "Fait",
        "**F1** — livré le 12/09",
    ),
    ("Widget client en premier chez le gestionnaire", "À faire", "**F2**"),
    (
        "Renommer le widget Organisation en Manifestations",
        "À faire",
        "une ligne dans `core.py`",
    ),
    (
        "Rechercher les manifestations d'un client défini",
        "Fait",
        "**A3** — filtre `client=`, distinct de `search`",
    ),
    (
        "Préremplir nom et dates de la manifestation à la création d'une prestation",
        "À faire",
        "front",
    ),
    (
        "Ne pas bloquer la prestation en brouillon si le stock manque",
        "À faire",
        "R13b — permissif au stockage, strict à la transition",
    ),
    (
        "Bon généré automatiquement à la modification d'une prestation",
        "À faire",
        "**L3** — c'est R14 mot pour mot",
    ),
    (
        "Livraison partielle saisie par le livreur",
        "À faire",
        "**L7** — la table existe depuis L6",
    ),
    ("Modifier l'information là où elle se trouve", "Fait", "**F4** — livré le 12/09"),
    ("Magasinier → comptage de stock", "À faire", "**F8** + R42"),
    (
        "Remplacer « OK » par « Récupéré »",
        "À faire",
        "`CheckinForm.tsx` — la colonne s'appelle déjà `quantite_recuperee`",
    ),
    ("Retirer les articles de la partie manifestation", "À faire", "revue d'écran"),
    ("Revoir l'affichage (CDC page 19)", "À faire", "maquette"),
    (
        "Retirer les dates au niveau de la réservation",
        "<b>Arbitrage</b>",
        "contredit R14 — voir ci-dessous",
    ),
    (
        "Ne pas bloquer le check-in si le retour ≠ le livré",
        "Fait",
        "**L5b** — R36 le disait déjà, le serveur l'applique enfin",
    ),
    (
        "Contraindre les saisies : plus de récupéré oui, plus de manquant non",
        "Fait",
        "**L5b** — la règle de recette, plus fine que la mienne, a remplacé R34",
    ),
    (
        "Calendrier : une ligne par prestation",
        "Fait",
        "**F5** — la barre se déplie sur ses prestations",
    ),
]

#: Les trois points de la recette qui ne se rangeaient sous aucune règle
#: existante. Colonnes : sujet, constat, décision, où ça en est.
ARBITRAGES = [
    (
        "Retirer les dates de la réservation",
        "Le CDC §44 demande que le bon porte « les dates de l'évènement <b>et</b> la date/heure de livraison attendue ». Et `date_retrait_prevue` est le champ sur lequel la tournée du livreur est filtrée : le supprimer sec casse `/tournees/`.",
        "Retirer la <b>paire</b> retrait/retour prévus, qui duplique le créneau de la prestation, et garder <b>une seule date</b> sur le bon : l'heure de livraison attendue, que la prestation ne porte pas.",
        "<b>Ouvert</b> — c'est le seul point de la recette qui attend encore une décision.",
    ),
    (
        "Le ramassage ne doit pas être plafonné",
        "R36 dit depuis le début « aucun plafond, un surplus est légitime ». Le serveur refuse pourtant tout total supérieur au sorti (`sav.py`), et le test écrit au lot L5 a gravé ce refus dans la suite. Une règle et son contraire, à trois jours d'intervalle.",
        "Lever le plafond global, le remplacer par la contrainte proposée en recette — on peut récupérer plus, on ne peut pas déclarer plus de manquants qu'il n'y a eu de demandes — et réécrire le test correspondant.",
        "<b>Tranché, livré</b> (`be356a4`) : plafond levé des deux côtés, manquant seul borné, trois tests réécrits.",
    ),
    (
        "Le planning à la maille prestation",
        "La maquette et la recette demandent une ligne par prestation. Le planning livré fait une ligne par manifestation : la maille est prise un cran trop haut.",
        "Descendre d'un niveau, ou rendre la manifestation dépliable sur ses prestations — ce qui garde la vue d'ensemble tout en donnant le détail.",
        "<b>Tranché, livré</b> (`3211735`) : la barre se déplie. Le volume d'une prestation se mesure comme celui de sa manifestation, un cran plus bas — sinon le détail ne totalise pas son ensemble.",
    ),
]

#: Tâches front. Colonnes : ce que la tâche fait, où, de quoi elle dépend.
FRONT = [
    (
        "F2",
        "Accueil du gestionnaire : ses clients",
        "« Le gestionnaire doit voir en priorité la liste de ses clients dès la connexion, et pouvoir les retrouver rapidement lors d'un appel téléphonique » (réunion du 09/09). Son poste ouvre aujourd'hui sur l'arborescence. <b>L'API est prête</b> : `/clients/?gestionnaire=me` ne rend que ses clients, `gestionnaire_nom` donne le nom du référent.",
        "Nouvel écran en <b>première</b> entrée du poste gestionnaire (`postes/definitions.tsx`), plus le champ « gestionnaire référent » au formulaire de `ClientsTab.tsx` — `Select` alimenté par `/users/?roles=gestionnaire`.",
        "rien — prêt à prendre",
        "`demo_gestionnaire` ouvre son poste sur ses clients, et l'admin peut changer le référent depuis le back-office.",
    ),
    (
        "F3",
        "Niveau client dans l'arborescence",
        "L'arbre démarre à la manifestation ; la maquette et la réunion demandent client → manifestation → prestation → articles. Le niveau manquait parce que `Client` n'existait pas — <b>il existe maintenant</b>.",
        "`arborescence/Arborescence.tsx` : un niveau au-dessus, alimenté par `/clients/`. Le composant est déjà écrit par niveaux, chacun chargeant ses enfants au dépliage. Le filtre client (A3) et les boutons d'ajout (F4) y sont posés depuis le 12/09 : le niveau s'insère au-dessus sans les défaire, et le filtre devient redondant avec lui — à retirer, pas à empiler.",
        "rien — prêt à prendre",
        "un client se déplie sur ses manifestations, la recherche et les filtres Futur / Passé marchent encore, et les clés d'URL restent préfixées.",
    ),
    (
        "F6",
        "Maquette Livraison",
        "Table hiérarchique aux quatre niveaux, compteurs −/+ et photo par ligne, cases de validation par ligne et par prestation, filtres Tous / À faire / Partiel / Complet, envoi groupé.",
        "`delivery/DeliveriesList.tsx` (liste plate aujourd'hui). La hiérarchie et le chargement au dépliage sont déjà résolus dans `arborescence/Arborescence.tsx` : le lire avant d'écrire.",
        "L6 est livré ; la saisie attend L7",
        "la tournée du jour s'affiche en quatre niveaux avec les quantités demandée / livrée / restante, les filtres opèrent, et le tout se vérifie avec `demo_livreur`.",
    ),
    (
        "F7",
        "Maquette Ramassage",
        "Même table, avec <b>quatre compteurs par ligne</b> — récupéré, cassé, détruit, manquant —, la photo, la bascule de facturation et la case de ramassage complet. Deux règles contre-intuitives : le manquant se <b>déduit</b> (R31) et n'est calculé qu'une fois le lieu déclaré entièrement ramassé (R32) ; et il n'y a <b>aucun plafond</b> (R33), un surplus est légitime.",
        "`ramassage/RamassagesList.tsx` et son formulaire, qui portent déjà les quatre quantités mais pas la table hiérarchique.",
        "L7 pour la saisie, F6 pour la structure",
        "les quatre compteurs se saisissent par ligne, le manquant se déduit, et rien n'est déclaré perdu tant que le lieu n'est pas terminé.",
    ),
    (
        "F8",
        "Écran stock du magasinier",
        "« Le magasinier gère le stock physique ; le catalogue et les clients ne le concernent pas » (09/09). Son poste affiche pourtant le catalogue, faute d'écran stock : c'est aujourd'hui le seul qui donne l'état article par article.",
        "Nouvel écran, puis remplacer l'entrée Catalogue du poste magasinier dans `postes/definitions.tsx`.",
        "rien — prêt à prendre",
        "`demo_magasinier` voit l'état article par article sans passer par le catalogue.",
    ),
    (
        "F9",
        "Écrans du devis",
        "Génération, envoi, signature, états de ligne « hors devis » et « annulée », et la provenance de chaque modification (personne, canal, horodatage).",
        "Écrans neufs, plus une entrée Devis et une entrée Factures au poste gestionnaire — les deux manquent au CDC §95-101.",
        "L3",
        "un devis se génère depuis une prestation, s'envoie, se signe, et une ligne ajoutée après signature ressort « hors devis ».",
    ),
]

#: Tâches back.
BACK = [
    (
        "L3",
        "Devis : implémentation",
        "Génération automatique du bon, résolution du prix (paliers de quantité, table de remises, remise globale), signature, états de ligne. Les tables existent depuis D0.",
        "L2 — débloqué",
    ),
    (
        "L7",
        "Écriture des tables d'exécution",
        "Greffe sur les trois points d'écriture déjà transactionnels : le journal de livraison, le passage de statut, la saisie de ramassage. Se découpe en trois lots indépendants. La projection et sa commande de vérification sont en place : chaque greffe se prouve par « aucune divergence ».",
        "L6 — débloqué",
    ),
]

#: Mise en route d'un poste de développement. Commandes vérifiées sur le conteneur.
DEMARRAGE = [
    (
        "Démarrer la stack",
        "make up",
        "Quatre services : `db`, `inventree` (port 8000), `backend` (worker), `frontend` (Vite).",
    ),
    (
        "Peupler la base",
        "docker compose exec inventree bash -lc \\<br>'cd /home/inventree/src/backend/InvenTree &amp;&amp; python manage.py seed_demo'",
        "Trois clients et leurs contacts, seize articles, quatre manifestations autour d'aujourd'hui, des réservations dans tous les statuts, un retour avec incidents, un conflit de stock. <b>Sans elle, la base est vide et les écrans muets.</b> `--force` si la base contient déjà des données, `--date-pivot AAAA-MM-JJ` pour décaler les dates.",
    ),
    (
        "Se connecter",
        "admin / admin123 — puis demo_&lt;role&gt; / Demo!2026",
        "Un compte par rôle : `demo_gestionnaire`, `demo_magasinier`, `demo_livreur`, `demo_acheteur`, `demo_admin`. <b>Tester avec le compte du rôle concerné</b>, jamais avec l'admin : la barre de navigation et les postes sont filtrés par les droits, donc un écran correct en admin peut être invisible pour sa persona.",
    ),
    (
        "Déployer un changement",
        "cd frontend &amp;&amp; npm run build — puis docker compose restart inventree",
        "InvenTree sert le static <b>collecté au boot</b> du conteneur. Sans le redémarrage, on regarde l'ancien bundle et on cherche un bug déjà corrigé. `collectstatic` ne recopie pas le static du plugin.",
    ),
    (
        "Vérifier la projection",
        "python manage.py verifier_projection",
        "Recalcule les tables d'exécution depuis les bons et **affiche** les écarts sans rien écrire ; `projeter_execution` les rattrape. C'est le garde-fou de la stratégie additive : tant que les colonnes du bon font foi, une projection qui dérive ne se verrait nulle part.",
    ),
    (
        "Vérifier avant de pousser",
        "npx tsc -b · npx vitest run · pre-commit run --all-files",
        "`pre-commit` deux fois de suite : `biome` et `ruff format` modifient les fichiers, la première passe échoue donc légitimement.",
    ),
]

#: Pièges du dépôt, chacun déjà payé d'une session.
PIEGES = [
    (
        "Mantine doit rester en <b>v8</b>",
        "L'hôte fournit `@mantine/core` 8.3.18 en global. Un paquet Mantine en v9 dans le lockfile et le widget affiche « Error Loading Content ».",
    ),
    (
        "Un composant réutilisé par un poste n'importe que des <b>types</b> depuis `@inventreedb/ui`",
        "Un import de valeur fait entrer `@lingui` sans `i18n` initialisé : le poste rend une page blanche avec `Cannot read properties of undefined (reading 'i18n')`.",
    ),
    (
        "Toute clé de query string passe par `urlState.ts`, <b>préfixée</b> par le widget",
        "Tous les widgets écrivent la même URL : sans préfixe, le dernier à se synchroniser efface les filtres des autres.",
    ),
    (
        "`Select` cherchable : ne jamais dériver l'entité choisie des seuls résultats de recherche",
        "Mantine recopie le libellé de l'option dans le champ de recherche, qui repart au serveur. Si le libellé est enrichi (« Nom — N disponible(s) »), le serveur ne matche plus, la liste se vide et la sélection est perdue. Références correctes : `PartPicker.tsx`, `ReservationForm.tsx`.",
    ),
    (
        "`npx tsc --noEmit` <b>ne vérifie rien</b>",
        'Le `tsconfig.json` racine a `"files": []` et délègue à des project references. La commande qui vérifie est `npx tsc -b`.',
    ),
]

#: Répartition des six tâches front restantes. Un fichier, un auteur.
REPARTITION = [
    (
        "Joseph",
        "F3 — niveau client dans l'arborescence",
        "F9 — écrans du devis, quand L3 est posé",
        "`arborescence/`, `organisation/`",
    ),
    (
        "Maxime",
        "F6 — Livraison, <b>en lecture</b>",
        "F7 — Ramassage, sur la table de F6",
        "`delivery/`, `ramassage/`",
    ),
    (
        "Hanane",
        "F2 — accueil gestionnaire : ses clients",
        "F8 — écran stock du magasinier",
        "`backoffice/`, `postes/definitions.tsx`",
    ),
    (
        "Back",
        "L3 — devis : prix, génération, signature",
        "L7 — écriture des tables d'exécution",
        "hors `frontend/`",
    ),
]

GELE = [
    (
        "Renommage des classes `Reservation` et `LigneReservation`",
        "378 occurrences hors tests, 27 fichiers front, aucun changement de comportement — et l'invalidation des contrats d'API pendant que d'autres construisent dessus.",
    ),
    (
        "Montants et écrans de facture",
        "Suppose des règles de tarification qui n'existent pas encore, sur un socle dont les plafonds de quantité se contredisent déjà.",
    ),
    (
        "Contraintes de quantités en base",
        "Les deux plafonds existants divergent : une même ligne passe l'un et échoue l'autre. Unifier la règle d'abord, contraindre ensuite.",
    ),
    (
        "Fork du frontend d'InvenTree",
        "Inutile : la barre de navigation se filtre par les droits de lecture des rulesets, ce que le lot P1 a fait sans toucher à leur code.",
    ),
]


def rows(items):
    return "".join(
        f'<tr><td class="id">{i}</td><td>{t}</td><td class="src">{s}</td></tr>'
        for i, t, s in items
    )


sections = "".join(
    f"<h2>{titre}</h2><table><thead><tr><th>#</th><th>Règle</th><th>Source</th></tr></thead><tbody>{rows(items)}</tbody></table>"
    for titre, items in R.items()
)


def mono(texte):
    """`x` devient du monospace : les tableaux de plan sont écrits en dos d'accent."""

    return re.sub(r"`([^`]+)`", r"<code>\1</code>", texte)


livre = "".join(
    f'<tr><td class="id">{i}</td><td><b>{t}</b><br><span class="det">{d}</span></td><td class="src">{c}</td></tr>'
    for i, t, d, c in ((i, t, mono(d), c) for i, t, d, c in LIVRE)
)
front = "".join(
    f'<tr><td class="id">{i}</td>'
    f'<td><b>{t}</b><br><span class="det">{mono(d)}</span>'
    f'<span class="fin"><b>Fini quand</b> {mono(fini)}</span></td>'
    f'<td class="det">{mono(ou)}</td><td class="src">{dep}</td></tr>'
    for i, t, d, ou, dep, fini in FRONT
)
back = "".join(
    f'<tr><td class="id">{i}</td><td><b>{t}</b><br><span class="det">{d}</span></td><td class="src">{dep}</td></tr>'
    for i, t, d, dep in ((i, t, mono(d), dep) for i, t, d, dep in BACK)
)
demarrage = "".join(
    f'<tr><td><b>{etape}</b></td><td class="cmd"><code>{cmd}</code></td><td class="det">{mono(pourquoi)}</td></tr>'
    for etape, cmd, pourquoi in DEMARRAGE
)
pieges = "".join(
    f'<tr><td class="id">{index}</td><td>{mono(piege)}</td><td class="det">{mono(effet)}</td></tr>'
    for index, (piege, effet) in enumerate(PIEGES, start=1)
)
repartition = "".join(
    f'<tr><td><b>{qui}</b></td><td>{mono(un)}</td><td>{mono(deux)}</td><td class="det">{mono(fichiers)}</td></tr>'
    for qui, un, deux, fichiers in REPARTITION
)
gele = "".join(f"<tr><td><b>{mono(t)}</b></td><td>{mono(d)}</td></tr>" for t, d in GELE)
_relations_par_table = {}

for _src, _dst, _cs, _cd, _lib in _schema.RELATIONS:
    _relations_par_table.setdefault(_src, []).append(
        f"→ {_schema.TABLES[_dst][0].split('  ')[0]} ({_cs}–{_cd})"
    )
    _relations_par_table.setdefault(_dst, []).append(
        f"← {_schema.TABLES[_src][0].split('  ')[0]} ({_cd}–{_cs})"
    )

inventaire = "".join(
    f"<tr><td><b>{_schema.TABLES[cle][0]}</b><br>"
    f'<span class="det">{" · ".join(_schema.TABLES[cle][1])}</span></td>'
    f'<td class="det">{"<br>".join(_relations_par_table.get(cle, ["—"]))}</td>'
    f'<td class="src">{etat}</td><td class="src">{lot or "—"}</td></tr>'
    for cle, (etat, lot) in ETAT_TABLES.items()
)

recette_fait = sum(1 for _, statut, _ in RECETTE if statut.startswith("Fait"))
recette_reste = sum(1 for _, statut, _ in RECETTE if statut.startswith("À faire"))
recette_autres = len(RECETTE) - recette_fait - recette_reste

avancement = "".join(
    f"<tr><td><b>{chantier}</b></td><td>{mono(fait)}</td>"
    f'<td class="det">{mono(reste)}</td></tr>'
    for chantier, fait, reste in [
        (
            "Front",
            "L'arborescence (A2), l'onglet Contacts (F1), les boutons d'ajout (F4), le Planning jusqu'à la maille prestation (F5) et le filtre client (A3).",
            f"{len(FRONT)} tâches, toutes attribuées : F2 puis F8 pour Hanane, F3 puis F9 pour Joseph, F6 puis F7 pour Maxime.",
        ),
        (
            "Back",
            "D0 et L0 à L6 : tables du devis, client et contacts, rôle unique, couture d'exécution, tournée du jour. Plus L5b, le plafond du ramassage levé.",
            f"{len(BACK)} lots : L3, le devis — dont F9 dépend — et L7, l'écriture des tables d'exécution, dont F6 et F7 ont besoin pour la saisie.",
        ),
        (
            "Recette du 11/09",
            f"{recette_fait} points sur {len(RECETTE)}, dont six réglés depuis la révision 7.",
            f"{recette_reste} à faire, et {recette_autres} arbitrage ouvert — les dates portées par le bon, seul point qui attend encore une décision.",
        ),
        (
            "Maquettes du cahier des charges",
            "Planning et Manifestation, aux détails près listés en fin de document.",
            "Livraison (F6) et Ramassage (F7) : les deux tables hiérarchiques, en lecture d'abord.",
        ),
    ]
)

recette = "".join(
    f'<tr><td>{mono(point)}</td><td class="src">{statut}</td>'
    f'<td class="det">{mono(ou)}</td></tr>'
    for point, statut, ou in RECETTE
)

arbitrages = "".join(
    f'<tr><td><b>{mono(sujet)}</b></td><td class="det">{mono(constat)}</td>'
    f'<td class="det">{mono(proposition)}</td><td class="det">{mono(etat)}</td></tr>'
    for sujet, constat, proposition, etat in ARBITRAGES
)

planches_html = "".join(
    f"<h3>Planche {index} — {titre}</h3>{svg}"
    + ('<div class="page"></div>' if index < len(planches) else "")
    for index, (svg, titre) in enumerate(planches, start=1)
)
corr = "".join(
    f'<tr><td class="id">{i}</td><td>{t}</td><td>{d}</td></tr>' for i, t, d in C
)
maq = "".join(
    f'<tr><td class="mq">{n}</td><td>{a}</td><td class="ec">{e}</td></tr>'
    for n, a, e in M
)

html = f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Modèle de données</title>
<style>
@page {{ size: A4; margin: 14mm 12mm 16mm; }}
* {{ box-sizing: border-box; }}
body {{ font: 10.5pt/1.45 -apple-system, "Helvetica Neue", Arial, sans-serif; color:#111827; margin:0; }}
h1 {{ font-size: 21pt; margin:0 0 4px; letter-spacing:-.4px; }}
.sub {{ color:#6b7280; font-size:10pt; margin-bottom:18px; }}
h2 {{ font-size:12.5pt; margin:20px 0 7px; padding-bottom:4px; border-bottom:2px solid #2563eb; color:#1e3a8a;
     break-after:avoid; page-break-after:avoid; }}
table {{ width:100%; border-collapse:collapse; margin-bottom:6px; }}
th {{ text-align:left; font-size:8.5pt; text-transform:uppercase; letter-spacing:.5px; color:#6b7280;
      border-bottom:1px solid #d1d5db; padding:4px 6px; }}
td {{ padding:5px 6px; border-bottom:1px solid #eef2f7; vertical-align:top; font-size:9.7pt; }}
tr {{ break-inside:avoid; page-break-inside:avoid; }}
td.id {{ font-weight:700; color:#1d4ed8; white-space:nowrap; width:38px; }}
td.src {{ color:#6b7280; font-size:8.6pt; white-space:nowrap; width:118px; }}
table.inv td:nth-child(1) {{ width:26%; }}
table.inv td:nth-child(2) {{ width:44%; font-size:8.6pt; }}
table.front {{ table-layout:fixed; }}
table.front th:nth-child(1) {{ width:34px; }}
table.front th:nth-child(2) {{ width:40%; }}
table.front th:nth-child(3) {{ width:34%; }}
table.front th:nth-child(4) {{ width:auto; }}
table.front td.src {{ white-space:normal; width:auto; }}
table.front td {{ overflow-wrap:break-word; }}
table.front code {{ font-size:8.7pt; overflow-wrap:break-word; }}
td.cmd {{ width:31%; overflow-wrap:anywhere; }}
td.cmd code {{ font-size:8.2pt; }}
td.mq {{ font-weight:700; color:#1d4ed8; width:92px; }}
td.ec {{ color:#6b7280; font-size:9pt; width:34%; }}
.det {{ color:#4b5563; font-size:8.8pt; }}
.fin {{ display:block; margin-top:3px; color:#065f46; font-size:8.6pt; }}
code {{ font:9.2pt ui-monospace, Menlo, monospace; background:#f3f4f6; padding:.5px 3px; border-radius:3px; }}
.page {{ break-after:page; page-break-after:always; }}
.legend {{ margin-top:10px; font-size:9pt; color:#4b5563; }}
.legend span {{ display:inline-block; margin-right:14px; }}
.dot {{ display:inline-block; width:9px; height:9px; border-radius:2px; margin-right:4px; vertical-align:-1px; }}
.note {{ background:#fffbeb; border-left:3px solid #f59e0b; padding:8px 10px; font-size:9.5pt; margin:12px 0 0; }}
footer {{ margin-top:22px; padding-top:8px; border-top:1px solid #e5e7eb; color:#9ca3af; font-size:8.5pt; }}
</style></head><body>

<h1>Modèle de données &amp; règles métier</h1>
<div class="sub">InvenTree Location — gestion de location de matériel événementiel<br>
Révision 8 · 12/09/2026 · Sources : point de revue du 09/09/2026, cahier des charges V06
(texte <b>et</b> annexes graphiques), code existant</div>

<h2>Où on en est — 12/09/2026</h2>
<p>Le point en une page. Chaque ligne est détaillée plus loin : le plan de mise
en œuvre pour ce qui est livré, les deux tableaux « à faire » pour le reste, et
la répartition pour savoir qui prend quoi.</p>
<table><thead><tr><th>Chantier</th><th>Ce qui est fait</th><th>Ce qui reste</th></tr></thead>
<tbody>{avancement}</tbody></table>
<div class="note"><b>Les six tâches front restantes sont indépendantes deux à deux</b> — chacune
sur ses propres fichiers, donc trois personnes peuvent avancer en parallèle sans conflit de
fusion. Seules F6 et F7 s'enchaînent, dans cet ordre, et F9 attend que le devis (L3) soit
posé côté back.</div>

<h2>Schéma du modèle de données</h2>
<p>Vingt-six tables et cinquante-deux relations, relevées dans le code et non de
mémoire. Trois planches plutôt qu'une : sur une seule page, les libellés
deviendraient illisibles. Les tables déjà montrées sur une planche précédente
sont <b>rappelées en gris</b>, pour que chacune se lise seule.</p>

<div class="note"><b>Comment lire les cardinalités.</b> Elles se lisent aux deux
bouts d'un trait : <code>Client 1 — 0..N Contact</code> se dit « un client porte
zéro à plusieurs contacts, et un contact appartient à un et un seul client ».
<code>M — N</code> signale une relation portée par une table de liaison — il n'y
en a que deux : un devis couvre plusieurs bons et un bon peut figurer sur
plusieurs devis, une facture couvre plusieurs devis.</div>

<div class="note"><b>Rappel : la normalisation.</b> Un schéma est normalisé quand
chaque fait n'est écrit qu'une fois et au bon endroit.
<b>1<sup>re</sup> forme</b> : pas de valeur répétée dans une colonne — d'où
<code>LigneReservation</code> plutôt qu'une liste d'articles dans le bon.
<b>2<sup>e</sup> forme</b> : chaque colonne dépend de la clé <i>entière</i> —
d'où <code>RamassageArticle</code>, où les quatre compteurs dépendent du couple
(passage, ligne) et non du seul passage.
<b>3<sup>e</sup> forme</b> : aucune colonne ne dépend d'une autre colonne — d'où
le nom du client absent de la manifestation, qui le tient de sa clé étrangère.
<br>Le modèle a été dénormalisé <b>une fois</b>, sciemment :
<code>Devis.signataire_libelle</code> fige le nom du signataire au moment de la
signature. Un devis signé doit rester lisible tel qu'il a été signé, même si le
contact est renommé ou désactivé ensuite — c'est un instantané, pas une
duplication.</div>

<div class="note"><b>La faute inverse, corrigée en cours de route.</b> Le bon de
réservation portait sept colonnes de quantités de retour — <code>ok</code>,
<code>manquant</code>, <code>casse</code>, <code>sav</code>… — alimentées par
trois écrans différents avec trois vocabulaires. Trois écrivains pour un même
fait : les chiffres divergeaient. La migration <code>0021</code> les a
supprimées au profit d'un registre unique, <code>ReturnIncident</code>, et les
totaux se recalculent. C'est l'exemple à citer si l'on demande ce que la
normalisation apporte concrètement.</div>

<div class="page"></div>

{planches_html}

{sections}

<h2>Écarts assumés par rapport au schéma soumis</h2>
<table><thead><tr><th>#</th><th>Point du schéma</th><th>Correction et raison</th></tr></thead><tbody>{corr}</tbody></table>

<div class="page"></div>

<h2>Les tables en jeu</h2>
<p>Les vingt-six tables du modèle, leurs relations avec leurs cardinalités, et
leur état réel — car une table peut exister en base sans qu'aucun écran ne
l'utilise encore. Les cardinalités se lisent <b>(côté de cette table – côté de
l'autre)</b> : sur <code>Contact</code>, « ← Client (0..N–1) » se dit « ce
client porte zéro à plusieurs contacts, ce contact appartient à un seul
client ».</p>
<table class="inv"><thead><tr><th>Table</th><th>Relations</th><th>État</th><th>Lot</th></tr></thead>
<tbody>{inventaire}</tbody></table>

<div class="page"></div>

<h2>Recette du 11/09/2026</h2>
<p>Les points relevés en équipe, confrontés un par un aux règles et au code.
<b>{recette_fait} sur {len(RECETTE)}</b> sont faits — six sont passés à « fait » depuis la
révision 7 —, {recette_reste} restent à faire, et {recette_autres} attend encore un
arbitrage : il est repris dans le tableau suivant.</p>
<table><thead><tr><th>Point</th><th>Statut</th><th>Où ça tombe</th></tr></thead>
<tbody>{recette}</tbody></table>

<h2>Les trois arbitrages — deux tranchés</h2>
<table><thead><tr><th>Sujet</th><th>Le constat</th><th>La proposition</th><th>Où ça en est</th></tr></thead>
<tbody>{arbitrages}</tbody></table>

<div class="page"></div>

<h2>Plan de mise en œuvre — livré</h2>
<table><thead><tr><th>#</th><th>Lot</th><th>Commit</th></tr></thead><tbody>{livre}</tbody></table>

<h2>À faire — front</h2>
<table class="front"><thead><tr><th>#</th><th>Tâche</th><th>Où</th><th>Dépend de</th></tr></thead><tbody>{front}</tbody></table>
<div class="note"><b>Trois des six tâches restantes ne dépendent de rien</b> — F2, F3, F8 —
et portent sur des fichiers distincts, donc sans conflit de fusion. F6 et F7 s'enchaînent
dans cet ordre, sur les mêmes fichiers. F9 attend L3.<br>
F1, F4 et F5 ont quitté ce tableau : elles sont livrées, et figurent au plan ci-dessus avec
leur commit.</div>

<h2>À faire — back</h2>
<table><thead><tr><th>#</th><th>Lot</th><th>Dépend de</th></tr></thead><tbody>{back}</tbody></table>

<div class="page"></div>

<h2>Répartition proposée</h2>
<table><thead><tr><th>Qui</th><th>D'abord</th><th>Ensuite</th><th>Fichiers qui lui appartiennent</th></tr></thead><tbody>{repartition}</tbody></table>
<div class="note"><b>Un fichier, un auteur</b> : c'est ce qui rend les quatre chantiers simultanés
sans conflit de fusion. Une branche par tâche, depuis <code>develop</code>, PR vers
<code>develop</code> — jamais vers <code>main</code>.<br>
<b>F6 et F7 se font en lecture d'abord</b> : compteurs et validations ont besoin des tables
d'exécution (lot L6). Ce n'est pas un retard, c'est le découpage — à dire avant, sinon la
personne attend.<br>
<b>F9 (devis) attend L3</b> : les écrans n'ont rien à montrer tant que le prix ne se résout pas.
C'est pour cela qu'il vient en second chez Joseph, derrière F3 qui, lui, est prenable
tout de suite.</div>

<div class="note"><b>Ce qui a bougé depuis la révision 7</b> (11/09). F1 — l'onglet Contacts —,
F4 — les boutons d'ajout de l'arborescence — et F5 — le Planning, jusqu'à la maille prestation
demandée en recette — sont livrés, ainsi que le filtre client (A3) et la levée du plafond de
ramassage (L5b). Joseph et Hanane changent donc de première tâche : F3 et F2. Maxime garde
F6 puis F7, inchangés.</div>

<h2>Mise en route</h2>
<table><thead><tr><th>Étape</th><th>Commande</th><th>Pourquoi</th></tr></thead><tbody>{demarrage}</tbody></table>

<h2>Pièges du dépôt — à lire avant d'écrire</h2>
<table><thead><tr><th>#</th><th>Règle</th><th>Ce qu'on voit si on l'ignore</th></tr></thead><tbody>{pieges}</tbody></table>

<div class="page"></div>

<h2>Gelé jusqu'après la soutenance</h2>
<table><thead><tr><th>Sujet</th><th>Raison</th></tr></thead><tbody>{gele}</tbody></table>

<h2>Maquettes du cahier des charges &amp; écart avec l'existant</h2>
<table><thead><tr><th>Écran</th><th>Ce que la maquette demande</th><th>Ce qui existe</th></tr></thead><tbody>{maq}</tbody></table>
<div class="note"><b>Révision 2.</b> Le schéma simplifié de l'annexe du cahier des charges rattache
<code>DeliveryTask</code> et <code>PickupTask</code> à la <b>ligne de réservation</b>
(<code>IDLocation → BonDeReservation</code>), et la maquette Ramassage montre le manquant comme un
compteur saisi. La révision 1 de ce document affirmait l'inverse — un stockage à la maille
lieu × journée et un manquant déduit. Les règles R29 à R34 ont été corrigées en conséquence, et
l'écart qui reprochait au schéma client de rattacher le ramassage à la réservation a été retiré :
il était infondé.</div>

<footer>Document généré le 12/09/2026 — projet InvenTree Location, groupe 6.</footer>
</body></html>"""

(ICI / "modele.html").write_text(html)
print("html ok", len(html), "octets")
