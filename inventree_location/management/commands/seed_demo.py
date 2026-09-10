"""Jeu de données de démonstration.

Deux usages. Rejouer une démonstration devant le client ou le jury sans une
heure de resaisie. Et surtout **éprouver les migrations de données sur une base
non vide** : sur une base fraîche, une reprise passe verte sans avoir rien fait.

Les comptes sont créés par l'ORM avec `create_user`, pas par l'API : un
`POST /api/user/` accepte le champ `password` et l'ignore, ce qui livre des
comptes inutilisables.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from inventree_location import roles
from inventree_location.models import (
    Groupe,
    Lieu,
    LignePrestation,
    LigneReservation,
    Manifestation,
    Prestation,
    RentableItem,
    Reservation,
    ReturnIncident,
    ReturnIncidentType,
    StatutManifestation,
    StatutPrestation,
    StatutReservation,
)

#: Marqueur des données de démonstration : c'est lui qui rend `--reset`
#: possible sans toucher à de la vraie donnée.
DOMAINE = "demo.test"

MOT_DE_PASSE = "Demo!2026"

#: Lieux réels autour de Lyon, pour que la carte des tournées affiche des
#: points et non un océan à l'ouest de l'Afrique.
LIEUX = [
    (
        "Salle des fêtes de Tassin",
        "Place Hippolyte Péragut, Tassin-la-Demi-Lune",
        45.7644,
        4.7846,
        "Grande salle, accès camion par l'arrière",
    ),
    (
        "Gymnase de Charbonnières",
        "Avenue Général de Gaulle, Charbonnières-les-Bains",
        45.7817,
        4.7519,
        "Parquet — pas de chariot à roues dures",
    ),
    (
        "Parc de Lacroix-Laval",
        "Chemin de l'Étoile, Marcy-l'Étoile",
        45.7861,
        4.7167,
        "Plein air, prévoir des lests",
    ),
    (
        "Halle Tony Garnier",
        "20 Place Docteurs Charles et Christophe Mérieux, Lyon",
        45.7325,
        4.8236,
        "Quai de déchargement niveau -1",
    ),
]

#: Articles : (nom, référence, poids kg, caution, seuil bas, stock, options).
ARTICLES = [
    ("Table brasserie 220x80", "MOB-1487", 18.5, 40, 10, 40, {}),
    ("Banc brasserie 220", "MOB-1495", 9.2, 20, 20, 80, {}),
    ("Chaise pliante", "MOB-1502", 3.4, 10, 30, 120, {}),
    ("Tente pliante 3x3", "STR-1002", 32.0, 150, 4, 12, {}),
    ("Praticable 2x1 m", "STR-1206", 26.0, 120, 6, 20, {}),
    ("Pied de praticable 60 cm", "STR-1212", 2.1, 15, 24, 96, {}),
    ("Sono portable 300 W", "SON-1516", 11.0, 250, 2, 6, {}),
    ("Micro HF main", "SON-1550", 0.4, 120, 4, 10, {}),
    ("Projecteur PAR LED", "LUM-1551", 2.8, 90, 6, 24, {}),
    ("Câble électrique 20 m", "ELE-1305", 4.5, 25, 10, 30, {}),
    ("Borne électrique 8 prises", "ELE-1333", 6.0, 60, 4, 8, {}),
    ("Barrière Vauban", "SEC-1610", 14.0, 30, 20, 60, {}),
    # Sous son seuil : alimente le widget d'alertes.
    ("Chapiteau 5x8", "STR-1700", 210.0, 900, 3, 1, {}),
    # Consommable, avec un seuil haut.
    (
        "Gobelet réutilisable",
        "CON-1801",
        0.05,
        0,
        200,
        1500,
        {"consommable": True, "seuil_alerte_haut": 2000},
    ),
    # Alertes coupées volontairement : montre le cas.
    ("Rallonge 5 m (lot)", "ELE-1350", 2.0, 10, 5, 2, {"alertes_desactivees": True}),
    # Article virtuel : une prestation, rien à ramasser.
    ("Nettoyage du lieu", "SRV-9001", None, 0, None, 0, {"is_virtual": True}),
]

CLIENTS = [
    ("Pionniers de Mantes", "PIO", "12 rue des Peupliers, Mantes-la-Jolie"),
    ("Mairie d'Évreux", "EVR", "Place du Général de Gaulle, Évreux"),
    ("École des beaux-arts", "EBA", "8 quai Saint-Vincent, Lyon"),
]


class Command(BaseCommand):
    help = (
        "Crée un jeu de données de démonstration : clients, comptes par rôle, "
        "catalogue, manifestations, prestations, réservations, retours et un "
        "conflit de stock"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date-pivot",
            help=(
                "Date de référence (AAAA-MM-JJ, défaut aujourd'hui). Les "
                "manifestations sont placées autour d'elle : une démonstration "
                "rejouée trois mois plus tard doit encore montrer un « en cours »"
            ),
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Supprime d'abord les données de démonstration existantes",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Autorise l'exécution sur une base qui contient déjà des données",
        )

    def handle(self, *args, **options):
        pivot = self._pivot(options.get("date_pivot"))

        if options["reset"]:
            self._nettoyer()

        self._garde_fou(force=options["force"])

        with transaction.atomic():
            clients = self._clients()
            comptes = self._comptes()
            lieux = self._lieux()
            articles = self._articles()
            self._manifestations(pivot, clients, comptes, lieux, articles)
            self._conflit(pivot, clients, comptes, lieux, articles)

        self.stdout.write(
            self.style.SUCCESS(
                f"Démonstration prête autour du {pivot:%d/%m/%Y} — "
                f"mot de passe des comptes : {MOT_DE_PASSE}"
            )
        )

    # -- garde-fous ---------------------------------------------------------

    def _pivot(self, valeur):
        if not valeur:
            return timezone.localdate()

        date = parse_date(valeur)

        if date is None:
            raise CommandError("--date-pivot attend une date AAAA-MM-JJ")

        return date

    def _garde_fou(self, *, force):
        """Refuse une base qui porte déjà autre chose que de la démonstration."""

        if force:
            return

        autres = Groupe.objects.exclude(nom__in=[nom for nom, _, _ in CLIENTS])

        if autres.exists():
            raise CommandError(
                f"{autres.count()} client(s) hors démonstration en base. "
                "Relancer avec --force si c'est voulu, ou --reset pour repartir "
                "des seules données de démonstration."
            )

    def _nettoyer(self):
        """Supprime ce que la commande a créé, repéré par le domaine e-mail."""

        comptes = get_user_model().objects.filter(email__endswith=f"@{DOMAINE}")
        manifestations = Manifestation.objects.filter(organisateur__in=comptes)

        Reservation.objects.filter(
            prestation__manifestation__in=manifestations
        ).delete()
        Prestation.objects.filter(manifestation__in=manifestations).delete()
        manifestations.delete()
        comptes.delete()
        Groupe.objects.filter(nom__in=[nom for nom, _, _ in CLIENTS]).delete()

        self.stdout.write("  données de démonstration supprimées")

    # -- construction -------------------------------------------------------

    def _clients(self):
        clients = {}

        for nom, code, adresse in CLIENTS:
            clients[code], _ = Groupe.objects.get_or_create(
                nom=nom, defaults={"code": code, "adresse": adresse}
            )

        self.stdout.write(f"  {len(clients)} client(s)")
        return clients

    def _comptes(self):
        from django.contrib.auth.models import Group

        from inventree_location.models import Profile

        comptes = {}

        for index, role in enumerate(roles.ALL_ROLES, start=1):
            username = f"demo_{role}"
            compte, cree = get_user_model().objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{role}@{DOMAINE}",
                    "first_name": role.capitalize(),
                    "last_name": "Démo",
                },
            )

            if cree:
                compte.set_password(MOT_DE_PASSE)
                compte.save(update_fields=["password"])

            groupe, _ = Group.objects.get_or_create(name=role)
            compte.groups.set([groupe])

            # Téléphone : le bon de livraison doit imprimer quelque chose.
            Profile.objects.update_or_create(
                user=compte, defaults={"telephone": f"06 00 00 00 {index:02d}"}
            )

            comptes[role] = compte

        self.stdout.write(f"  {len(comptes)} compte(s), un par rôle")
        return comptes

    def _lieux(self):
        lieux = []

        for nom, adresse, lat, lon, description in LIEUX:
            lieu, _ = Lieu.objects.get_or_create(
                nom=nom,
                defaults={
                    "adresse": adresse,
                    "latitude": lat,
                    "longitude": lon,
                    "description": description,
                },
            )
            lieux.append(lieu)

        self.stdout.write(f"  {len(lieux)} lieu(x) géolocalisé(s)")
        return lieux

    def _articles(self):
        from part.models import Part

        from inventree_location.tests.factories import fixer_stock

        articles = []

        for nom, ref, poids, caution, seuil_bas, stock, options in ARTICLES:
            part, _ = Part.objects.get_or_create(name=nom, defaults={"IPN": ref})

            RentableItem.objects.update_or_create(
                part=part,
                defaults={
                    "poids": poids,
                    "caution": caution,
                    "seuil_alerte_bas": seuil_bas,
                    **options,
                },
            )

            fixer_stock(part, stock)
            articles.append(part)

        self.stdout.write(f"  {len(articles)} article(s) au catalogue")
        return articles

    def _manifestations(self, pivot, clients, comptes, lieux, articles):
        """Une terminée, une en cours, deux à venir."""

        gestionnaire = comptes[roles.GESTIONNAIRE]
        livreur = comptes[roles.LIVREUR]

        plan = [
            (
                "Festival de printemps",
                clients["PIO"],
                -30,
                -25,
                StatutManifestation.TERMINEE,
                StatutReservation.CLOTUREE,
            ),
            (
                "Séminaire municipal",
                clients["EVR"],
                -1,
                2,
                StatutManifestation.EN_COURS,
                StatutReservation.LIVREE,
            ),
            (
                "Gala de fin d'année",
                clients["EBA"],
                12,
                15,
                StatutManifestation.PLANIFIEE,
                StatutReservation.VALIDEE,
            ),
            (
                "Camp d'été",
                clients["PIO"],
                45,
                52,
                StatutManifestation.PLANIFIEE,
                StatutReservation.SOUMISE,
            ),
        ]

        for rang, (nom, client, debut, fin, statut, statut_resa) in enumerate(plan):
            manifestation, _ = Manifestation.objects.get_or_create(
                nom=nom,
                defaults={
                    "date_debut": self._instant(pivot, debut, 9),
                    "date_fin": self._instant(pivot, fin, 19),
                    "statut": statut,
                    "organisateur": gestionnaire,
                    "groupe": client,
                    "couleur": ["#2563eb", "#059669", "#b45309", "#be185d"][rang],
                },
            )

            # Deux prestations par manifestation, sur deux lieux : c'est le cas
            # que la maquette montre, et celui qui fait sens pour une tournée.
            for pas in range(2):
                lieu = lieux[(rang + pas) % len(lieux)]
                prestation, cree = Prestation.objects.get_or_create(
                    manifestation=manifestation,
                    nom=f"{nom} — zone {pas + 1}",
                    defaults={
                        "lieu": lieu,
                        "date_debut": self._instant(pivot, debut, 10 + pas * 4),
                        "date_fin": self._instant(pivot, fin, 18),
                        "statut": StatutPrestation.CONFIRMEE
                        if statut_resa != StatutReservation.SOUMISE
                        else StatutPrestation.PLANIFIEE,
                    },
                )

                if not cree:
                    continue

                choisis = articles[pas * 3 : pas * 3 + 3]

                for part in choisis:
                    LignePrestation.objects.create(
                        prestation=prestation, part=part, quantite=4
                    )

                reservation = Reservation.objects.create(
                    prestation=prestation,
                    demandeur=gestionnaire,
                    statut=statut_resa,
                    date_retrait_prevue=self._instant(pivot, debut, 8),
                    date_retour_prevue=self._instant(pivot, fin, 20),
                    # Une seule est prise en charge : les autres restent dans le
                    # pool commun, que tout livreur peut se servir.
                    livreur_assigne=livreur if (rang, pas) == (1, 0) else None,
                    etat_livraison="en_cours" if (rang, pas) == (1, 0) else "",
                )

                for part in choisis:
                    ligne = LigneReservation.objects.create(
                        reservation=reservation,
                        part=part,
                        quantite_demandee=4,
                        quantite_livree=4
                        if statut_resa
                        in (StatutReservation.LIVREE, StatutReservation.CLOTUREE)
                        else 0,
                    )

                    # La manifestation terminée porte un retour incomplet :
                    # de quoi alimenter le SAV et le rapport de pertes.
                    if statut_resa == StatutReservation.CLOTUREE and part is choisis[0]:
                        ReturnIncident.objects.create(
                            line=ligne,
                            type=ReturnIncidentType.BROKEN,
                            qty=1,
                            comment="Pied tordu au démontage",
                            reported_by=comptes[roles.MAGASINIER],
                            bill_client=True,
                        )
                        ReturnIncident.objects.create(
                            line=ligne,
                            type=ReturnIncidentType.MISSING,
                            qty=1,
                            comment="Non retrouvé sur le lieu",
                            reported_by=comptes[roles.MAGASINIER],
                        )

        self.stdout.write(f"  {len(plan)} manifestation(s) et leurs prestations")

    def _conflit(self, pivot, clients, comptes, lieux, articles):
        """Deux réservations sur le même article, au même moment, stock trop court.

        Sans ça, l'écran des conflits reste vide et la démonstration ne montre
        pas l'arbitrage.
        """

        from inventree_location.tests.factories import fixer_stock

        rare = articles[6]
        fixer_stock(rare, 4)

        manifestation, _ = Manifestation.objects.get_or_create(
            nom="Deux concerts le même soir",
            defaults={
                "date_debut": self._instant(pivot, 20, 18),
                "date_fin": self._instant(pivot, 20, 23),
                "statut": StatutManifestation.PLANIFIEE,
                "organisateur": comptes[roles.GESTIONNAIRE],
                "groupe": clients["EBA"],
            },
        )

        for pas in range(2):
            prestation, cree = Prestation.objects.get_or_create(
                manifestation=manifestation,
                nom=f"Concert {pas + 1}",
                defaults={
                    "lieu": lieux[pas],
                    "date_debut": self._instant(pivot, 20, 18 + pas * 2),
                    "date_fin": self._instant(pivot, 20, 20 + pas * 2),
                    "statut": StatutPrestation.PLANIFIEE,
                },
            )

            if not cree:
                continue

            reservation = Reservation.objects.create(
                prestation=prestation,
                demandeur=comptes[roles.GESTIONNAIRE],
                statut=StatutReservation.VALIDEE,
                date_retrait_prevue=self._instant(pivot, 20, 16),
                date_retour_prevue=self._instant(pivot, 21, 10),
            )
            # 3 + 3 demandés pour 4 en stock : il en manque 2.
            LigneReservation.objects.create(
                reservation=reservation, part=rare, quantite_demandee=3
            )

        self.stdout.write("  1 conflit de stock")

    def _instant(self, pivot, jours, heure):
        """Datetime en heure locale : le calcul « du jour » est en Europe/Paris."""

        naif = timezone.datetime.combine(
            pivot + timedelta(days=jours),
            timezone.datetime.min.time().replace(hour=heure),
        )

        return timezone.make_aware(naif)
