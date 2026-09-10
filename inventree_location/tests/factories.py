"""Aides de construction d'objets pour les tests.

Deux familles. La mise en stock : le stock physique appartient à InvenTree, un
article n'a de quantité que par ses `StockItem` (hors container, l'app `stock`
factice de `tests/stock/`). Et la chaîne métier `client → manifestation →
prestation → réservation → ligne`, que chaque fichier de tests reconstruisait à
l'identique.

Les builders remplissent tout ce qui est obligatoire et créent les parents
manquants. Un test qui ne s'intéresse pas au client n'a donc plus à le nommer.

Tout est surchargeable par `**overrides` : un test qui affirme quelque chose sur
une valeur la passe explicitement.
"""

from __future__ import annotations

import itertools
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone
from django.utils.dateparse import parse_datetime

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
)

#: Quelques statuts InvenTree utiles aux tests (cf. RENTAL_STOCK_STATUSES).
STATUT_OK = 10
STATUT_ATTENTION = 50
STATUT_ENDOMMAGE = 55
STATUT_DETRUIT = 60
STATUT_QUARANTAINE = 75
STATUT_RETOURNE = 85


def mettre_en_stock(part, quantity, *, status=STATUT_OK):
    """Crée un exemplaire en stock pour `part` et le retourne."""

    from stock.models import StockItem

    return StockItem.objects.create(part=part, quantity=quantity, status=status)


def fixer_stock(part, quantity, *, status=STATUT_OK):
    """Ramène le stock de `part` à `quantity` exactement."""

    from stock.models import StockItem

    StockItem.objects.filter(part=part).delete()

    if quantity:
        return mettre_en_stock(part, quantity, status=status)

    return None


# ---------------------------------------------------------------------------
# Chaîne métier
# ---------------------------------------------------------------------------

#: Suffixe des valeurs uniques. `Client.nom` et `Client.email` le sont : un
#: défaut fixe interdirait de créer deux clients dans le même test.
_compteur = itertools.count(1)


def _maintenant():
    """Heure de référence, sans microsecondes.

    Les assertions de dates comparent des chaînes ISO renvoyées par l'API :
    des microsecondes rendaient certaines comparaisons instables.
    """

    return timezone.now().replace(microsecond=0)


def make_user(username=None, *, role=None, telephone="", **overrides):
    """Compte de test, éventuellement porteur d'un rôle plugin."""

    numero = next(_compteur)
    compte = get_user_model().objects.create_user(
        username=username or f"user{numero}",
        password=overrides.pop("password", "pwd12345"),
        **overrides,
    )

    if role:
        groupe, _ = Group.objects.get_or_create(name=role)
        compte.groups.add(groupe)

    # Profile seulement s'il porte quelque chose : un test vérifie qu'aucun
    # profil vide n'est créé.
    if telephone:
        from inventree_location.models import Profile

        Profile.objects.create(user=compte, telephone=telephone)

    return compte


def make_part(name=None, *, rentable=False, stock=None, **overrides):
    """Part native, avec son extension louable et son stock si demandés."""

    from part.models import Part

    numero = next(_compteur)
    part = Part.objects.create(name=name or f"Article {numero}", **overrides)

    if rentable:
        RentableItem.objects.create(part=part)

    if stock is not None:
        mettre_en_stock(part, stock)

    return part


def make_client(**overrides):
    numero = next(_compteur)
    overrides.setdefault("nom", f"Client {numero}")
    overrides.setdefault("email", f"client-{numero}@exemple.test")
    overrides.setdefault("type_client", "entreprise")
    return Client.objects.create(**overrides)


def make_contact(client=None, **overrides):
    numero = next(_compteur)
    overrides.setdefault("nom", f"Contact {numero}")
    overrides.setdefault("email", f"contact-{numero}@exemple.test")
    return Contact.objects.create(client=client or make_client(), **overrides)


def make_lieu(**overrides):
    overrides.setdefault("nom", f"Lieu {next(_compteur)}")
    return Lieu.objects.create(**overrides)


def make_manifestation(client=None, contact=None, **overrides):
    """Manifestation, avec son client créé au besoin.

    Le contact reste optionnel : la colonne est nullable, et la plupart des
    tests n'ont rien à en dire.
    """

    debut = overrides.pop("date_debut", None) or _maintenant()

    # Plusieurs fixtures donnent des dates en chaîne ISO.
    if isinstance(debut, str):
        debut = parse_datetime(debut)

    overrides.setdefault("nom", f"Manifestation {next(_compteur)}")
    overrides.setdefault("date_debut", debut)
    overrides.setdefault("date_fin", debut + timedelta(days=7))

    return Manifestation.objects.create(
        client=client or make_client(),
        contact=contact,
        **overrides,
    )


def make_prestation(manifestation=None, **overrides):
    manifestation = manifestation or make_manifestation()
    debut = overrides.pop("date_debut", None) or manifestation.date_debut

    if isinstance(debut, str):
        debut = parse_datetime(debut)

    overrides.setdefault("nom", f"Prestation {next(_compteur)}")
    overrides.setdefault("date_debut", debut)
    overrides.setdefault("date_fin", debut + timedelta(days=1))

    return Prestation.objects.create(manifestation=manifestation, **overrides)


def make_ligne_prestation(prestation=None, part=None, **overrides):
    overrides.setdefault("quantite", 1)
    return LignePrestation.objects.create(
        prestation=prestation or make_prestation(),
        part=part or make_part(rentable=True),
        **overrides,
    )


def make_reservation(prestation=None, demandeur=None, **overrides):
    return Reservation.objects.create(
        prestation=prestation or make_prestation(),
        demandeur=demandeur or make_user(),
        **overrides,
    )


def make_ligne(reservation=None, part=None, **overrides):
    overrides.setdefault("quantite_demandee", 1)
    return LigneReservation.objects.create(
        reservation=reservation or make_reservation(),
        part=part or make_part(rentable=True),
        **overrides,
    )


def creer_chaine(*, quantite=1, stock=None, **overrides):
    """La chaîne complète, d'un coup.

    Retourne un dictionnaire des objets créés — c'est ce que la plupart des
    fixtures reconstruisaient à la main.
    """

    client = overrides.pop("client", None) or make_client()
    demandeur = overrides.pop("demandeur", None) or make_user()
    lieu = overrides.pop("lieu", None) or make_lieu()
    part = overrides.pop("part", None) or make_part(rentable=True, stock=stock)

    manifestation = make_manifestation(client=client)
    prestation = make_prestation(manifestation=manifestation, lieu=lieu)
    reservation = make_reservation(prestation=prestation, demandeur=demandeur)
    ligne = make_ligne(reservation=reservation, part=part, quantite_demandee=quantite)

    return {
        "client": client,
        "demandeur": demandeur,
        "lieu": lieu,
        "part": part,
        "manifestation": manifestation,
        "prestation": prestation,
        "reservation": reservation,
        "ligne": ligne,
    }
