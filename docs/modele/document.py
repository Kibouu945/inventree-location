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

ICI = Path(__file__).parent

svg = (ICI / "schema.svg").read_text()

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
        "<code>ReservationCalendar</code> : calendrier mensuel des réservations. Ni Gantt, ni volumes, ni fiche.",
    ),
    (
        "Manifestation",
        "Arborescence dépliable <b>manifestation → prestation → bon de réservation → articles</b>, avec par ligne la quantité réservée, livrée et ramassée. Recherche, filtres Futur / Passé / Tout / À facturer, boutons d'ajout de prestation, de réservation et d'article.",
        "<code>OrganisationPanel</code> : trois onglets plats. L'arborescence n'existe pas.",
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
]

#: Tâches front. Colonnes : ce que la tâche fait, où, de quoi elle dépend.
FRONT = [
    (
        "F1",
        "Onglet Contacts du back-office",
        "Créer et éditer les contacts d'un client. <b>L'API est prête et complète</b> — `/backoffice/contacts/`, filtrable par client, avec recherche, désactivation et `client_nom` pour la liste tous clients confondus. Il n'existe simplement aucun écran : un contact ne peut aujourd'hui être créé que par le shell.",
        "Nouveau `backoffice/ContactsTab.tsx`, troisième onglet de `UsersBackOffice.tsx`. Copier la structure de `ClientsTab.tsx`, qui fait le même travail pour les clients ; les types et l'URL existent déjà. Pas de suppression : un contact se désactive, il a peut-être signé un devis. E-mail vide envoyé en `null`, jamais en chaîne vide.",
        "rien — prêt à prendre",
        "on crée un contact depuis l'écran, le compteur « Contacts » du client s'incrémente, et la désactivation le sort du sélecteur de `ManifestationsTab` sans le faire disparaître de la liste.",
    ),
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
        "`arborescence/Arborescence.tsx` : un niveau au-dessus, alimenté par `/clients/`. Le composant est déjà écrit par niveaux, chacun chargeant ses enfants au dépliage.",
        "rien — prêt à prendre",
        "un client se déplie sur ses manifestations, la recherche et les filtres Futur / Passé marchent encore, et les clés d'URL restent préfixées.",
    ),
    (
        "F4",
        "Boutons d'ajout de l'arborescence",
        "Les trois `+` de la maquette sont visibles mais <b>désactivés</b>, avec l'explication au survol. La création passe par l'écran « Fiches ».",
        "Extraire les formulaires de `ManifestationsTab.tsx` et `PrestationsTab.tsx` (dossier `organisation/`) en composants réutilisables, puis les ouvrir depuis l'arbre. C'est l'extraction qui fait le travail, pas le bouton.",
        "rien, mais chevauche F3",
        "on crée une manifestation, une prestation et une ligne depuis l'arbre, sans passer par l'écran « Fiches ».",
    ),
    (
        "F5",
        "Maquette Planning",
        "Gantt des manifestations sur les jours, pastilles de statut, bascule calendrier / liste, fiche détaillée au survol avec contact, volumes et état de livraison. L'existant est un calendrier mensuel des réservations : ni Gantt, ni volumes, ni fiche.",
        "`ReservationCalendar.tsx` (dossier `reservation/`) à remplacer ou doubler. `Manifestation.couleur` est en base depuis L1 et n'est pas encore utilisée.",
        "rien — prêt à prendre",
        "la même manifestation se lit en Gantt et en liste, avec sa couleur et son état de livraison.",
    ),
    (
        "F6",
        "Maquette Livraison",
        "Table hiérarchique aux quatre niveaux, compteurs −/+ et photo par ligne, cases de validation par ligne et par prestation, filtres Tous / À faire / Partiel / Complet, envoi groupé.",
        "`delivery/DeliveriesList.tsx` (liste plate aujourd'hui). La hiérarchie et le chargement au dépliage sont déjà résolus dans `arborescence/Arborescence.tsx` : le lire avant d'écrire.",
        "L6 pour la saisie ; lecture faisable avant",
        "la tournée du jour s'affiche en quatre niveaux avec les quantités demandée / livrée / restante, les filtres opèrent, et le tout se vérifie avec `demo_livreur`.",
    ),
    (
        "F7",
        "Maquette Ramassage",
        "Même table, avec <b>quatre compteurs par ligne</b> — récupéré, cassé, détruit, manquant —, la photo, la bascule de facturation et la case de ramassage complet. Deux règles contre-intuitives : le manquant se <b>déduit</b> (R31) et n'est calculé qu'une fois le lieu déclaré entièrement ramassé (R32) ; et il n'y a <b>aucun plafond</b> (R33), un surplus est légitime.",
        "`ramassage/RamassagesList.tsx` et son formulaire, qui portent déjà les quatre quantités mais pas la table hiérarchique.",
        "L6, et F6 pour la structure",
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
        "L5",
        "Couture d'exécution et deux bugs",
        "Une seule fonction nommée pour la quantité attendue au retour ; contrainte d'unicité sur le registre d'incidents ; et surtout la garde sur `_replace_lignes`, qui efface aujourd'hui le registre de retour par cascade à chaque édition d'une réservation.",
        "rien — prêt à prendre",
    ),
    (
        "L6",
        "Tables d'exécution, en lecture",
        "`Livraison` et `Ramassage` rattachées à la ligne de réservation, avec leurs quantités, plus les commandes de projection et de vérification.",
        "L5",
    ),
    (
        "L7",
        "Écriture des tables d'exécution",
        "Greffe sur les trois points d'écriture déjà transactionnels : le journal de livraison, le passage de statut, la saisie de ramassage. Se découpe en trois lots indépendants.",
        "L6",
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

#: Répartition proposée. Un fichier, un auteur.
REPARTITION = [
    (
        "Joseph",
        "F3 — niveau client dans l'arborescence",
        "F4 — boutons d'ajout (extraction des formulaires)",
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
        "F1 — onglet Contacts du back-office",
        "F2 — accueil gestionnaire, puis F8 — écran stock",
        "`backoffice/`, `postes/definitions.tsx`",
    ),
    (
        "Back",
        "L5 — couture d'exécution et deux bugs",
        "L3 — devis, puis L6 et L7 — tables d'exécution",
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
Révision 5 · 10/09/2026 · Sources : point de revue du 09/09/2026, cahier des charges V06
(texte <b>et</b> annexes graphiques), code existant</div>

<h2>Schéma du modèle cible</h2>
{svg}
<div class="legend">
<span><i class="dot" style="background:#4f46e5"></i>Acteur interne</span>
<span><i class="dot" style="background:#059669"></i>Client (externe)</span>
<span><i class="dot" style="background:#2563eb"></i>Cœur métier</span>
<span><i class="dot" style="background:#b45309"></i>Devis &amp; facturation</span>
<span><i class="dot" style="background:#be185d"></i>Exécution terrain</span>
<span><i class="dot" style="background:#475569"></i>Référentiel</span>
</div>
<div class="page"></div>

{sections}

<h2>Écarts assumés par rapport au schéma soumis</h2>
<table><thead><tr><th>#</th><th>Point du schéma</th><th>Correction et raison</th></tr></thead><tbody>{corr}</tbody></table>

<div class="page"></div>

<h2>Plan de mise en œuvre — livré</h2>
<table><thead><tr><th>#</th><th>Lot</th><th>Commit</th></tr></thead><tbody>{livre}</tbody></table>

<h2>À faire — front</h2>
<table class="front"><thead><tr><th>#</th><th>Tâche</th><th>Où</th><th>Dépend de</th></tr></thead><tbody>{front}</tbody></table>
<div class="note"><b>Cinq des neuf tâches front ne dépendent de rien</b> — F1, F2, F3, F5, F8 —
et F4 ne chevauche que F3. Elles portent sur des fichiers distincts, donc
sans conflit de fusion. F1 est la plus courte et la plus isolée : l'API est complète, il n'y a
qu'un écran à écrire en copiant celui des clients.</div>

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
<b>F5 (Planning) et F9 (devis) sont un troisième tour</b>, au premier qui se libère. F5 consomme
les formes de données que les autres sont en train de fixer ; F9 attend L3.</div>

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

<footer>Document généré le 10/09/2026 — projet InvenTree Location, groupe 6.</footer>
</body></html>"""

(ICI / "modele.html").write_text(html)
print("html ok", len(html), "octets")
