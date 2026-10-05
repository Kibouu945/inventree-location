"""Scénario « Vieilles Charrues » du cahier des charges, pour la démo live."""

import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from inventree_location import roles
from inventree_location.models import (
    Client,
    Contact,
    Lieu,
    LignePrestation,
    LigneReservation,
    Manifestation,
    Prestation,
    RentableItem,
    Reservation,
    StatutManifestation,
    StatutPrestation,
    StatutReservation,
)

DOMAINE = "demo.test"

CLIENT = "Les Charrues"
MANIFESTATION = "Les Vieilles Charrues"

#: Coordonnées du cahier des charges, § « Exemple de scénario événementiel ».
LIEUX = {
    "GLENMOR": ("Podium Glenmor", 48.272757, -3.558783),
    "KEROUAC": ("Podium Kerouac", 48.268834, -3.5584039),
    "GRALL": ("Podium Grall", 48.288825, -3.553986),
    "KERAMPUIL": ("Château de Kerampuil", 48.272452, -3.55350),
}

#: (clé, nom, référence, stock, options).
ARTICLES = [
    ("LYRE", "Projecteur lyre", "LUM-2101", 12, {}),
    ("PAR", "Projecteur PAR LED", "LUM-2102", 80, {}),
    ("MICRO", "Micro HF main", "SON-2201", 80, {}),
    ("MULTI", "Multiprise 6 prises", "ELE-2301", 80, {}),
    ("CABLE", "Câble électrique 20 m", "ELE-2302", 150, {}),
    ("MONTAGE", "Montage et démontage", "SRV-2901", 0, {"is_virtual": True}),
]

#: Les comptes que le script pilote, un par poste.
COMPTES = [roles.GESTIONNAIRE, roles.MAGASINIER, roles.LIVREUR]

CRENEAUX = [("matin", 10, 12), ("midi", 13, 16), ("soir", 20, 23)]


class Command(BaseCommand):
    help = (
        "Sème le festival des Vieilles Charrues sur une instance de démonstration "
        "vide : client, lieux GPS, concerts, bons, projecteurs en tension et un "
        "bon livré à ramasser"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date-pivot",
            help="Jour des concerts (AAAA-MM-JJ, défaut aujourd'hui)",
        )
        parser.add_argument(
            "--mot-de-passe",
            help="Mot de passe des comptes demo_* (défaut : $CHARRUES_MOT_DE_PASSE)",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Autorise une base qui contient déjà d'autres données",
        )

    def handle(self, *args, **options):
        pivot = self._pivot(options.get("date_pivot"))
        mot_de_passe = options.get("mot_de_passe") or os.environ.get(
            "CHARRUES_MOT_DE_PASSE"
        )

        if not mot_de_passe:
            raise CommandError(
                "Mot de passe absent : --mot-de-passe ou CHARRUES_MOT_DE_PASSE"
            )

        self._garde_fou(force=options["force"])

        with transaction.atomic():
            comptes = self._comptes(mot_de_passe)
            client, contacts = self._client(comptes[roles.GESTIONNAIRE])
            lieux = self._lieux()
            articles = self._articles()
            manifestation = self._manifestation(pivot, client, contacts)
            self._concerts(pivot, manifestation, lieux, articles, comptes)
            self._loges(pivot, manifestation, lieux, articles, comptes)
            self._balances(pivot, manifestation, lieux, articles, comptes)

        self.stdout.write(
            self.style.SUCCESS(
                f"Vieilles Charrues prêtes, concerts le {pivot:%d/%m/%Y}"
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
        """Refuse une base déjà semée, ou qui porte de la vraie donnée."""

        from part.models import Part

        if Manifestation.objects.filter(nom=MANIFESTATION).exists():
            raise CommandError(
                "Festival déjà semé : restaurer l'instantané de départ avant de "
                "relancer"
            )

        if force:
            return

        # Un article homonyme verrait son stock écrasé : la base doit être vide.
        clients = Client.objects.count()
        articles = Part.objects.count()

        if clients or articles:
            raise CommandError(
                f"{clients} client(s) et {articles} article(s) déjà en base : "
                "cette commande attend une instance de démonstration vide "
                "(--force pour passer outre)"
            )

    # -- construction -------------------------------------------------------

    def _comptes(self, mot_de_passe):
        from django.contrib.auth.models import Group

        from inventree_location.models import Profile

        comptes = {}

        for index, role in enumerate(COMPTES, start=1):
            compte, _ = get_user_model().objects.get_or_create(
                username=f"demo_{role}",
                defaults={
                    "email": f"{role}@{DOMAINE}",
                    "first_name": role.capitalize(),
                    "last_name": "Démo",
                },
            )
            compte.set_password(mot_de_passe)
            compte.save(update_fields=["password"])

            groupe, _ = Group.objects.get_or_create(name=role)
            compte.groups.set([groupe])

            Profile.objects.update_or_create(
                user=compte, defaults={"telephone": f"06 00 00 00 {index:02d}"}
            )
            comptes[role] = compte

        self.stdout.write(
            f"  {len(comptes)} compte(s) : demo_{', demo_'.join(COMPTES)}"
        )
        return comptes

    def _client(self, gestionnaire):
        client = Client.objects.create(
            nom=CLIENT,
            adresse="Kerampuil, 29270 Carhaix-Plouguer",
            email=f"contact@charrues.{DOMAINE}",
            telephone="02 98 00 00 00",
            gestionnaire=gestionnaire,
        )

        # Le second sert à montrer la désactivation pendant la démo.
        contacts = {
            "direction": Contact.objects.create(
                client=client,
                prenom="Yann",
                nom="Le Goff",
                email=f"yann.legoff@charrues.{DOMAINE}",
                telephone="06 12 34 56 78",
            ),
            "ancien": Contact.objects.create(
                client=client,
                prenom="Marion",
                nom="Kervella",
                email=f"marion.kervella@charrues.{DOMAINE}",
                telephone="06 87 65 43 21",
            ),
        }

        self.stdout.write(f"  client « {CLIENT} » et {len(contacts)} contacts")
        return client, contacts

    def _lieux(self):
        lieux = {
            cle: Lieu.objects.create(
                nom=nom,
                adresse="Site de Kerampuil, Carhaix-Plouguer",
                latitude=lat,
                longitude=lon,
            )
            for cle, (nom, lat, lon) in LIEUX.items()
        }

        self.stdout.write(f"  {len(lieux)} lieux géolocalisés")
        return lieux

    def _articles(self):
        from part.models import Part

        from inventree_location.tests.factories import mettre_en_stock

        articles = {}

        for cle, nom, ref, stock, options in ARTICLES:
            part = Part.objects.create(name=nom, IPN=ref)
            RentableItem.objects.create(part=part, is_rentable=True, **options)

            if stock:
                mettre_en_stock(part, stock)

            articles[cle] = part

        self.stdout.write(f"  {len(articles)} articles au catalogue")
        return articles

    def _manifestation(self, pivot, client, contacts):
        manifestation = Manifestation.objects.create(
            nom=MANIFESTATION,
            client=client,
            contact=contacts["direction"],
            date_debut=self._instant(pivot, -1, 8),
            date_fin=self._instant(pivot, 3, 23),
            statut=StatutManifestation.EN_COURS,
            couleur="#b45309",
        )

        self.stdout.write(f"  manifestation « {MANIFESTATION} », cinq jours")
        return manifestation

    def _concerts(self, pivot, manifestation, lieux, articles, comptes):
        """Trois concerts par podium, le jour pivot ; Grall soir reste sans bon."""

        nombre = 0

        for cle in ("GLENMOR", "KEROUAC", "GRALL"):
            for creneau, debut, fin in CRENEAUX:
                prestation = self._prestation(
                    manifestation,
                    f"{lieux[cle].nom} — concert du {creneau}",
                    lieux[cle],
                    self._instant(pivot, 0, debut),
                    self._instant(pivot, 0, fin),
                )

                # Le bon de Grall soir se crée en direct, et il bute sur les lyres.
                if (cle, creneau) == ("GRALL", "soir"):
                    continue

                materiel = {"PAR": 8, "MICRO": 4, "CABLE": 6, "MULTI": 4}

                if creneau == "soir":
                    materiel["LYRE"] = 4

                self._bon(
                    prestation,
                    materiel,
                    articles,
                    comptes,
                    retrait=self._instant(pivot, 0, debut - 2),
                    retour=self._instant(pivot, 0, fin),
                    statut=StatutReservation.VALIDEE,
                )
                nombre += 1

        self.stdout.write(f"  9 concerts, {nombre} bons validés à livrer ce jour")

    def _loges(self, pivot, manifestation, lieux, articles, comptes):
        prestation = self._prestation(
            manifestation,
            "Loges artistes",
            lieux["KERAMPUIL"],
            self._instant(pivot, -1, 8),
            self._instant(pivot, 3, 23),
        )
        self._bon(
            prestation,
            {"LYRE": 2, "PAR": 6, "MULTI": 10},
            articles,
            comptes,
            retrait=self._instant(pivot, -1, 8),
            retour=self._instant(pivot, 3, 23),
            statut=StatutReservation.LIVREE,
        )
        self.stdout.write("  loges artistes, livrées pour tout le festival")

    def _balances(self, pivot, manifestation, lieux, articles, comptes):
        """Le bon livré la veille, que le magasinier ramasse pendant la démo."""

        prestation = self._prestation(
            manifestation,
            f"{lieux['KEROUAC'].nom} — balances",
            lieux["KEROUAC"],
            self._instant(pivot, -1, 9),
            self._instant(pivot, -1, 18),
        )
        self._bon(
            prestation,
            {"MICRO": 12, "MULTI": 20, "CABLE": 40},
            articles,
            comptes,
            retrait=self._instant(pivot, -1, 8),
            retour=self._instant(pivot, 0, 9),
            statut=StatutReservation.LIVREE,
        )
        self.stdout.write("  balances Kerouac, livrées hier, à ramasser")

    # -- briques ------------------------------------------------------------

    def _prestation(self, manifestation, nom, lieu, debut, fin):
        return Prestation.objects.create(
            manifestation=manifestation,
            nom=nom,
            lieu=lieu,
            date_debut=debut,
            date_fin=fin,
            statut=StatutPrestation.CONFIRMEE,
        )

    def _bon(self, prestation, materiel, articles, comptes, *, retrait, retour, statut):
        livree = statut == StatutReservation.LIVREE

        reservation = Reservation.objects.create(
            prestation=prestation,
            demandeur=comptes[roles.GESTIONNAIRE],
            validateur=comptes[roles.GESTIONNAIRE],
            statut=statut,
            date_retrait_prevue=retrait,
            date_retour_prevue=retour,
            date_retrait_reelle=retrait if livree else None,
            livreur_assigne=comptes[roles.LIVREUR] if livree else None,
        )

        # Le prévisionnel de la prestation suit le bon : le moteur d'engagement
        # retient le plus grand des deux, autant qu'ils disent la même chose.
        for cle, quantite in materiel.items():
            LignePrestation.objects.create(
                prestation=prestation, part=articles[cle], quantite=quantite
            )
            LigneReservation.objects.create(
                reservation=reservation,
                part=articles[cle],
                quantite_demandee=quantite,
                quantite_livree=quantite if livree else 0,
            )

        LigneReservation.objects.create(
            reservation=reservation,
            part=articles["MONTAGE"],
            quantite_demandee=1,
            quantite_livree=1 if livree else 0,
        )

        return reservation

    def _instant(self, pivot, jours, heure):
        """Datetime en heure locale : le calcul « du jour » est en Europe/Paris."""

        naif = timezone.datetime.combine(
            pivot + timedelta(days=jours),
            timezone.datetime.min.time().replace(hour=heure),
        )

        return timezone.make_aware(naif)
