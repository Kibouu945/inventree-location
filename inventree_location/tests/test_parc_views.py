"""Tests de la vue « état du parc » du poste magasinier.

`test_parc.py` couvre les fonctions pures du module ; ici on interroge la vue,
parce que c'est elle qui décide ce qui entre dans l'écran et ce qui n'y entre
pas — un service, un article retiré du catalogue, une fiche non louable.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from inventree_location.models import (
    RentableItem,
    SavTicket,
    StatutReservation,
    StatutSavTicket,
)
from inventree_location.tests.factories import (
    make_ligne,
    make_part,
    make_reservation,
    make_user,
)
from inventree_location.views import ParcStockListView

from part.models import Part, PartCategory

PARC_URL = "/plugin/inventree-location/stock/parc/"


@pytest.fixture
def factory():
    return APIRequestFactory()


@pytest.fixture
def magasinier(db):
    from inventree_location import roles

    return make_user(username="marc", role=roles.MAGASINIER)


def _appeler(factory, user, **params):
    request = factory.get(PARC_URL, params)
    force_authenticate(request, user=user)
    return ParcStockListView.as_view()(request)


def _par_nom(response):
    return {ligne["part_name"]: ligne for ligne in response.data["results"]}


def _sortir(part, quantite, *, retour_dans_jours=3):
    """Un bon livré, pas encore rentré : c'est ça, « dehors »."""

    maintenant = timezone.now()
    reservation = make_reservation(
        statut=StatutReservation.LIVREE,
        date_retrait_prevue=maintenant,
        date_retour_prevue=maintenant + timedelta(days=retour_dans_jours),
    )
    make_ligne(reservation=reservation, part=part, quantite_demandee=quantite)
    return reservation


class TestCeQuiEntreDansLEcran:
    @pytest.mark.django_db
    def test_un_article_louable_avec_son_parc(self, factory, magasinier):
        make_part(name="Tente 4 places", rentable=True, stock=12)

        ligne = _par_nom(_appeler(factory, magasinier))["Tente 4 places"]

        assert ligne["parc"] == 12
        assert ligne["disponible"] == 12
        assert ligne["sorti"] == 0

    @pytest.mark.django_db
    def test_un_service_n_occupe_pas_d_etagere(self, factory, magasinier):
        """Un article virtuel ne se range pas : il n'a rien à faire ici."""

        service = make_part(name="Gardiennage", stock=1)
        RentableItem.objects.create(part=service, is_virtual=True)

        assert "Gardiennage" not in _par_nom(_appeler(factory, magasinier))

    @pytest.mark.django_db
    def test_un_article_non_louable_reste_dehors(self, factory, magasinier):
        cle = make_part(name="Clé hexagonale", stock=4)
        RentableItem.objects.create(part=cle, is_rentable=False)

        assert "Clé hexagonale" not in _par_nom(_appeler(factory, magasinier))

    @pytest.mark.django_db
    def test_un_article_retire_du_catalogue_disparait(self, factory, magasinier):
        make_part(name="Barnum hors service", rentable=True, stock=2, active=False)

        assert "Barnum hors service" not in _par_nom(_appeler(factory, magasinier))


class TestCeQuiEstDehors:
    @pytest.mark.django_db
    def test_un_bon_livre_retranche_du_disponible(self, factory, magasinier):
        banc = make_part(name="Banc brasserie", rentable=True, stock=80)
        _sortir(banc, 12)

        ligne = _par_nom(_appeler(factory, magasinier))["Banc brasserie"]

        assert ligne["sorti"] == 12
        assert ligne["disponible"] == 68
        assert ligne["retour_prevu"] is not None

    @pytest.mark.django_db
    def test_un_bon_seulement_valide_ne_sort_rien(self, factory, magasinier):
        """Tant qu'il n'est pas livré, le matériel est encore sur l'étagère."""

        table = make_part(name="Table pliante", rentable=True, stock=30)
        reservation = make_reservation(statut=StatutReservation.VALIDEE)
        make_ligne(reservation=reservation, part=table, quantite_demandee=10)

        ligne = _par_nom(_appeler(factory, magasinier))["Table pliante"]

        assert ligne["sorti"] == 0
        assert ligne["disponible"] == 30

    @pytest.mark.django_db
    def test_le_sav_remonte_a_part(self, factory, magasinier):
        chaise = make_part(name="Chaise pliante", rentable=True, stock=50)
        reservation = _sortir(chaise, 5)
        ligne_resa = reservation.lignes.first()
        SavTicket.objects.create(
            ligne_reservation=ligne_resa,
            reservation=reservation,
            part=chaise,
            statut=StatutSavTicket.OUVERT,
            quantite=3,
        )

        assert _par_nom(_appeler(factory, magasinier))["Chaise pliante"]["sav"] == 3


class TestAlerte:
    @pytest.mark.django_db
    def test_le_filtre_ne_garde_que_ce_qui_alerte(self, factory, magasinier):
        calme = make_part(name="Tente calme", rentable=True, stock=40)
        RentableItem.objects.filter(part=calme).update(seuil_alerte_bas=10)
        bas = make_part(name="Tente au plus bas", rentable=True, stock=2)
        RentableItem.objects.filter(part=bas).update(seuil_alerte_bas=10)

        noms = _par_nom(_appeler(factory, magasinier, alerte="1"))

        assert set(noms) == {"Tente au plus bas"}
        assert noms["Tente au plus bas"]["motifs_alerte"] == ["sous_seuil"]

    @pytest.mark.django_db
    def test_sans_le_filtre_tout_le_parc_sort(self, factory, magasinier):
        make_part(name="Tente calme", rentable=True, stock=40)
        bas = make_part(name="Tente au plus bas", rentable=True, stock=2)
        RentableItem.objects.filter(part=bas).update(seuil_alerte_bas=10)

        assert len(_par_nom(_appeler(factory, magasinier))) == 2

    @pytest.mark.django_db
    def test_sorti_au_dela_du_parc_se_signale(self, factory, magasinier):
        """Signature d'un bon forcé, ou de matériel jamais rentré."""

        malle = make_part(name="Malle", rentable=True, stock=4)
        _sortir(malle, 6)

        ligne = _par_nom(_appeler(factory, magasinier, alerte="1"))["Malle"]

        assert ligne["motifs_alerte"] == ["sorti_au_dela_du_parc"]
        assert ligne["disponible"] == 0


class TestFiltresHeritesDuCatalogue:
    @pytest.mark.django_db
    def test_la_recherche_porte_sur_le_nom(self, factory, magasinier):
        make_part(name="Tente 4 places", rentable=True, stock=1)
        make_part(name="Banc brasserie", rentable=True, stock=1)

        assert set(_par_nom(_appeler(factory, magasinier, search="tente"))) == {
            "Tente 4 places"
        }

    @pytest.mark.django_db
    def test_la_categorie_ramene_toute_la_branche(self, factory, magasinier):
        mobilier = PartCategory.objects.create(name="Mobilier")
        tables = PartCategory.objects.create(name="Tables", parent=mobilier)
        make_part(name="Buffet", rentable=True, stock=1, category=mobilier)
        make_part(name="Table brasserie", rentable=True, stock=1, category=tables)
        make_part(name="Tapis de sol", rentable=True, stock=1)

        noms = set(_par_nom(_appeler(factory, magasinier, categories=str(mobilier.pk))))

        assert noms == {"Buffet", "Table brasserie"}


@pytest.mark.django_db
def test_le_nombre_de_requetes_ne_suit_pas_le_nombre_d_articles(factory, magasinier):
    """Le coût doit rester le même à 5 articles qu'à 1 : sinon on retombe sur
    le défaut corrigé le 23/09, où trois lectures unitaires faisaient cent
    requêtes pour cinquante articles."""

    make_part(name="Seul en piste", rentable=True, stock=1)

    with CaptureQueriesContext(connection) as court:
        _appeler(factory, magasinier)

    Part.objects.all().delete()

    for i in range(5):
        _sortir(make_part(name=f"Article {i}", rentable=True, stock=10), 2)

    with CaptureQueriesContext(connection) as long:
        _appeler(factory, magasinier)

    assert len(long) == len(court)
