"""Jeu de données de **volume**, pour le test de charge.

`seed_demo` construit une scène : quatre manifestations lisibles, un conflit
posé à la main, de quoi rejouer une démonstration. Elle ne dit rien de la
tenue du serveur, parce qu'une base de vingt lignes ne dit jamais rien de ça.

Cette commande-ci ne cherche aucune lisibilité : elle amène la base à **N
réservations réparties sur une année**, la cible annoncée par le client étant
10 000 par an (réponse du 20 mai, ticket PERF-01). Deux choses la distinguent
d'un `seed_demo --repeat` :

- elle est **cumulative**. `--total 2000` puis `--total 5000` complète au lieu
  de tout refaire : on mesure les paliers sans repayer la génération à chaque
  fois, et surtout sans que le palier suivant change autre chose que le volume.
- elle écrit en `bulk_create`. `Reservation.save()` fabrique le numéro par une
  lecture de la table à chaque insertion : 10 000 allers-retours, et une
  génération qui durerait plus longtemps que la mesure. Les numéros sont donc
  calculés ici, dans la même forme `RES-AAAA-NNNN` que le modèle.

Tout ce qu'elle crée porte le préfixe `MARQUEUR` : c'est lui qui rend `--reset`
possible sans toucher aux données de démonstration ni aux vraies.
"""

from __future__ import annotations

import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

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

#: Préfixe de tout ce que la commande crée. Sert de marqueur de suppression.
MARQUEUR = "CHG"

#: Taille des lots d'insertion. Au-delà, Postgres reçoit des requêtes dont la
#: taille dessert la vitesse ; en deçà, on paie trop d'allers-retours.
LOT = 2000

#: Taille des tranches de suppression. Bien plus petite que `LOT` : supprimer
#: coûte plus cher qu'insérer, chaque objet enfant en `CASCADE` étant chargé en
#: mémoire pour propager la suppression.
LOT_SUPPRESSION = 250

#: Répartition des statuts de réservation, pour une année déjà bien avancée.
#: Les passées sont clôturées, les proches livrées, les lointaines attendent.
#: Seuls les statuts « bloquants » pèsent sur le calcul de disponibilité — une
#: base entièrement clôturée mesurerait un serveur qui n'a rien à arbitrer.
STATUTS_PASSES = [
    (StatutReservation.CLOTUREE, 70),
    (StatutReservation.LIVREE, 20),
    (StatutReservation.ANNULEE, 10),
]
STATUTS_FUTURS = [
    (StatutReservation.VALIDEE, 55),
    (StatutReservation.SOUMISE, 30),
    (StatutReservation.BROUILLON, 15),
]


def _tirer(rng, distribution):
    """Tire une valeur dans une liste `(valeur, poids)`."""

    valeurs = [valeur for valeur, _ in distribution]
    poids = [poids for _, poids in distribution]

    return rng.choices(valeurs, weights=poids, k=1)[0]


class Command(BaseCommand):
    help = "Amène la base à N réservations sur une année, pour le test de charge."

    def add_arguments(self, parser):
        parser.add_argument(
            "--total",
            type=int,
            default=10000,
            help=(
                "Nombre total de réservations de charge visé en base "
                "(cumulatif : ne crée que ce qui manque). Défaut 10000."
            ),
        )
        parser.add_argument(
            "--annee",
            type=int,
            help="Année sur laquelle étaler les réservations (défaut : en cours).",
        )
        parser.add_argument(
            "--articles",
            type=int,
            default=40,
            help="Taille du catalogue louable généré. Défaut 40.",
        )
        parser.add_argument(
            "--stock",
            type=int,
            default=500,
            help=(
                "Stock par article. Généreux par défaut : on mesure un serveur "
                "qui répond, pas un serveur dont tout est en pénurie. Baisser "
                "cette valeur est le moyen de tester le cas pathologique."
            ),
        )
        parser.add_argument(
            "--clients",
            type=int,
            default=60,
            help="Nombre de clients générés. Défaut 60.",
        )
        parser.add_argument(
            "--lieux",
            type=int,
            default=25,
            help="Nombre de lieux générés. Défaut 25.",
        )
        parser.add_argument(
            "--lignes-max",
            type=int,
            default=4,
            help="Nombre maximal d'articles par réservation. Défaut 4.",
        )
        parser.add_argument(
            "--graine",
            type=int,
            default=20260922,
            help="Graine aléatoire : deux exécutions donnent la même base.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Supprime d'abord tout le jeu de charge existant.",
        )

    def handle(self, *args, **options):
        annee = options["annee"] or timezone.localdate().year
        vise = options["total"]

        if vise < 0:
            raise CommandError("--total attend un nombre positif.")

        if options["reset"]:
            self._nettoyer()

        rng = random.Random(options["graine"])
        depart = timezone.now()

        existant = Reservation.objects.filter(numero__startswith=f"{MARQUEUR}-").count()
        manquant = vise - existant

        if manquant <= 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Déjà {existant} réservation(s) de charge en base — rien à faire."
                )
            )
            return

        self.stdout.write(
            f"{existant} en base, {manquant} à créer pour atteindre {vise}."
        )

        with transaction.atomic():
            articles = self._articles(options["articles"], options["stock"])
            lieux = self._lieux(options["lieux"])
            clients, contacts = self._clients(options["clients"])
            demandeur = self._demandeur()

            self._volume(
                rng=rng,
                annee=annee,
                depuis=existant,
                combien=manquant,
                articles=articles,
                lieux=lieux,
                clients=clients,
                contacts=contacts,
                demandeur=demandeur,
                lignes_max=options["lignes_max"],
            )

        duree = (timezone.now() - depart).total_seconds()

        self.stdout.write(
            self.style.SUCCESS(
                f"{vise} réservation(s) de charge sur {annee} — généré en {duree:.1f} s."
            )
        )

    # -- suppression --------------------------------------------------------

    def _nettoyer(self):
        """Supprime le jeu de charge, et lui seul.

        L'ordre suit les `PROTECT` du modèle : une prestation refuse de partir
        tant qu'une réservation la référence, un article tant qu'une ligne le
        cite.
        """

        from part.models import Part
        from stock.models import StockItem

        clients = Client.objects.filter(nom__startswith=f"{MARQUEUR} ")
        manifestations = Manifestation.objects.filter(client__in=clients)
        prestations = Prestation.objects.filter(manifestation__in=manifestations)

        self._supprimer_par_lots(
            Reservation.objects.filter(prestation__in=prestations), "réservation"
        )
        self._supprimer_par_lots(
            LignePrestation.objects.filter(prestation__in=prestations),
            "ligne de prestation",
        )
        self._supprimer_par_lots(prestations, "prestation")
        self._supprimer_par_lots(manifestations, "manifestation")
        Contact.objects.filter(client__in=clients).delete()
        clients.delete()
        Lieu.objects.filter(nom__startswith=f"{MARQUEUR} ").delete()

        parts = Part.objects.filter(name__startswith=f"{MARQUEUR} ")
        StockItem.objects.filter(part__in=parts).delete()
        RentableItem.objects.filter(part__in=parts).delete()
        parts.delete()

        self.stdout.write("  jeu de charge supprimé")

    def _supprimer_par_lots(self, queryset, libelle):
        """Supprime par tranches, plutôt que d'un seul `delete()`.

        Toutes les relations qui pointent vers une réservation sont en
        `CASCADE` : `delete()` charge donc en mémoire chaque objet enfant pour
        propager la suppression. Sur dix mille réservations et leurs vingt-cinq
        mille lignes, cela demande au serveur une empreinte qu'il n'a pas — la
        première version a tourné une demi-heure sur un VPS à 3,9 Go sans
        rendre la main.

        Découper borne cette empreinte et rend la progression visible. Chaque
        tranche est sa propre transaction : une interruption laisse une base
        cohérente, simplement à moitié nettoyée, et relancer la commande
        reprend là où elle s'était arrêtée.
        """

        modele = queryset.model
        total = queryset.count()

        if not total:
            return

        efface = 0

        while True:
            lot = list(queryset.values_list("pk", flat=True)[:LOT_SUPPRESSION])

            if not lot:
                break

            with transaction.atomic():
                modele.objects.filter(pk__in=lot).delete()

            efface += len(lot)
            self.stdout.write(f"    {libelle} : {efface}/{total}", ending="\r")
            self.stdout.flush()

        self.stdout.write(f"    {libelle}(s) supprimée(s) : {efface}    ")

    # -- socle --------------------------------------------------------------

    def _demandeur(self):
        """Le compte au nom duquel les réservations sont posées."""

        modele = get_user_model()
        compte = modele.objects.filter(username=f"{MARQUEUR.lower()}-gestionnaire")

        if compte.exists():
            return compte.first()

        return modele.objects.create_user(
            username=f"{MARQUEUR.lower()}-gestionnaire",
            email="gestionnaire@charge.test",
            password="Charge!2026",
            first_name="Charge",
            last_name="Gestionnaire",
        )

    def _articles(self, combien, stock):
        """Catalogue louable, avec son stock InvenTree."""

        from part.models import Part
        from stock.models import StockItem

        #: Statut « OK » d'InvenTree — cf. `factories.STATUT_OK`.
        statut_ok = 10
        articles = []

        for rang in range(combien):
            nom = f"{MARQUEUR} Article {rang:03d}"
            part, cree = Part.objects.get_or_create(
                name=nom, defaults={"IPN": f"{MARQUEUR}-{rang:04d}"}
            )

            if cree:
                RentableItem.objects.create(
                    part=part,
                    poids=round(1 + rang % 30, 2),
                    caution=10 * (1 + rang % 20),
                    seuil_alerte_bas=max(stock // 20, 1),
                    prix_location_ht=5 * (1 + rang % 12),
                )
                StockItem.objects.create(part=part, quantity=stock, status=statut_ok)

            articles.append(part)

        self.stdout.write(f"  {len(articles)} article(s) au catalogue de charge")
        return articles

    def _lieux(self, combien):
        existants = {
            lieu.nom: lieu
            for lieu in Lieu.objects.filter(nom__startswith=f"{MARQUEUR} ")
        }
        a_creer = []

        for rang in range(combien):
            nom = f"{MARQUEUR} Lieu {rang:03d}"

            if nom in existants:
                continue

            a_creer.append(
                Lieu(
                    nom=nom,
                    adresse=f"{rang + 1} rue de la Charge, Lyon",
                    # Autour de Lyon, pour que la carte des tournées reste
                    # plausible à l'œil si on ouvre l'écran pendant la mesure.
                    latitude=round(45.70 + (rang % 20) * 0.005, 6),
                    longitude=round(4.80 + (rang % 20) * 0.005, 6),
                )
            )

        Lieu.objects.bulk_create(a_creer, batch_size=LOT)

        lieux = list(
            Lieu.objects.filter(nom__startswith=f"{MARQUEUR} ").order_by("nom")
        )
        self.stdout.write(f"  {len(lieux)} lieu(x) de charge")
        return lieux

    def _clients(self, combien):
        existants = {
            client.nom: client
            for client in Client.objects.filter(nom__startswith=f"{MARQUEUR} ")
        }
        a_creer = []

        for rang in range(combien):
            nom = f"{MARQUEUR} Client {rang:03d}"

            if nom in existants:
                continue

            a_creer.append(
                Client(
                    nom=nom,
                    adresse=f"{rang + 1} avenue du Volume, Lyon",
                    email=f"client{rang:03d}@charge.test",
                    telephone="06 00 00 00 00",
                    type_client="entreprise",
                )
            )

        Client.objects.bulk_create(a_creer, batch_size=LOT)
        clients = list(
            Client.objects.filter(nom__startswith=f"{MARQUEUR} ").order_by("nom")
        )

        connus = set(
            Contact.objects.filter(client__in=clients).values_list(
                "client_id", flat=True
            )
        )
        Contact.objects.bulk_create(
            [
                Contact(
                    client=client,
                    prenom="Contact",
                    nom=f"Numéro {rang:03d}",
                    email=f"contact{rang:03d}@charge.test",
                    telephone="06 00 00 00 00",
                )
                for rang, client in enumerate(clients)
                if client.pk not in connus
            ],
            batch_size=LOT,
        )

        contacts = {
            contact.client_id: contact
            for contact in Contact.objects.filter(client__in=clients)
        }

        self.stdout.write(f"  {len(clients)} client(s) de charge")
        return clients, contacts

    # -- volume -------------------------------------------------------------

    def _volume(
        self,
        *,
        rng,
        annee,
        depuis,
        combien,
        articles,
        lieux,
        clients,
        contacts,
        demandeur,
        lignes_max,
    ):
        """Crée `combien` réservations, chacune avec sa prestation.

        Une manifestation porte plusieurs prestations — c'est le cas réel, et
        c'est aussi celui qui compte pour les écrans : l'arborescence déplie
        par manifestation, et la détection de conflit de lieu compare des
        prestations entre elles.
        """

        maintenant = timezone.now()
        debut_annee = maintenant.replace(
            year=annee, month=1, day=1, hour=8, minute=0, second=0, microsecond=0
        )

        #: Prestations par manifestation. Trois : au-delà, l'arborescence
        #: n'aurait plus la forme qu'elle a en production.
        par_manifestation = 3

        manifestations = []
        prestations = []
        lignes_prestation = []
        reservations = []
        lignes_reservation = []

        for rang in range(combien):
            indice = depuis + rang
            jour = rng.randrange(0, 365)
            duree = rng.choice([1, 1, 2, 2, 3, 5])

            debut = debut_annee + timedelta(days=jour, hours=rng.randrange(0, 10))
            fin = debut + timedelta(days=duree, hours=8)
            passe = fin < maintenant

            client = clients[indice % len(clients)]
            lieu = lieux[rng.randrange(len(lieux))]

            # Nouveau groupe — ou reprise d'une base déjà peuplée, où le
            # premier indice tombe rarement en début de groupe.
            if indice % par_manifestation == 0 or not manifestations:
                manifestations.append(
                    Manifestation(
                        nom=f"{MARQUEUR} Manifestation {indice // par_manifestation:05d}",
                        date_debut=debut,
                        date_fin=fin + timedelta(days=2),
                        statut=StatutManifestation.TERMINEE
                        if passe
                        else StatutManifestation.PLANIFIEE,
                        client=client,
                        contact=contacts.get(client.pk),
                        couleur="#2563eb",
                    )
                )

            manifestation = manifestations[-1]
            statut_resa = _tirer(rng, STATUTS_PASSES if passe else STATUTS_FUTURS)

            prestation = Prestation(
                manifestation=manifestation,
                lieu=lieu,
                nom=f"{MARQUEUR} Prestation {indice:05d}",
                date_debut=debut,
                date_fin=fin,
                statut=StatutPrestation.CLOTUREE
                if passe
                else StatutPrestation.CONFIRMEE,
            )
            prestations.append(prestation)

            choisis = rng.sample(articles, rng.randint(1, lignes_max))
            quantites = {part.pk: rng.randint(1, 12) for part in choisis}

            for part in choisis:
                lignes_prestation.append(
                    LignePrestation(
                        prestation=prestation,
                        part=part,
                        quantite=quantites[part.pk],
                    )
                )

            livree = statut_resa in (
                StatutReservation.LIVREE,
                StatutReservation.CLOTUREE,
            )
            reservation = Reservation(
                # Même forme que `models._generate_reservation_numero`, préfixée
                # du marqueur : c'est ce préfixe qui rend le jeu identifiable.
                numero=f"{MARQUEUR}-RES-{annee}-{indice + 1:05d}",
                prestation=prestation,
                demandeur=demandeur,
                statut=statut_resa,
                date_demande=debut - timedelta(days=rng.randrange(5, 40)),
                date_retrait_prevue=debut - timedelta(days=1),
                date_retour_prevue=fin + timedelta(days=1),
            )
            reservations.append(reservation)

            for part in choisis:
                lignes_reservation.append(
                    LigneReservation(
                        reservation=reservation,
                        part=part,
                        quantite_demandee=quantites[part.pk],
                        quantite_livree=quantites[part.pk] if livree else 0,
                        quantite_retournee=quantites[part.pk]
                        if statut_resa == StatutReservation.CLOTUREE
                        else 0,
                    )
                )

        # `bulk_create` ne remplit les clés étrangères des enfants que si les
        # parents ont déjà leur `pk` : d'où l'ordre, et d'où le fait de garder
        # les objets Python plutôt que de relire la base entre deux lots.
        Manifestation.objects.bulk_create(manifestations, batch_size=LOT)
        Prestation.objects.bulk_create(prestations, batch_size=LOT)
        LignePrestation.objects.bulk_create(lignes_prestation, batch_size=LOT)
        Reservation.objects.bulk_create(reservations, batch_size=LOT)
        LigneReservation.objects.bulk_create(lignes_reservation, batch_size=LOT)

        self.stdout.write(
            f"  {len(manifestations)} manifestation(s), {len(prestations)} prestation(s), "
            f"{len(reservations)} réservation(s), {len(lignes_reservation)} ligne(s)"
        )
