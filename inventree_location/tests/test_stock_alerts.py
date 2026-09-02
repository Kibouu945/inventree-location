from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.models import (
    Groupe,
    Lieu,
    Manifestation,
    Prestation,
    RentableItem,
    Reservation,
)
from inventree_location.tests.factories import mettre_en_stock
from inventree_location.views import StockAlertListView

from part.models import Part, PartCategory

User = get_user_model()


@pytest.fixture
def manager(db):
    from django.contrib.auth.models import Group

    from inventree_location import roles

    group, _ = Group.objects.get_or_create(name=roles.GESTIONNAIRE)
    user = User.objects.create_user(
        username="manager-alert",
        password="pwd",
        email="manager@example.com",
    )
    user.groups.add(group)
    return user


@pytest.fixture
def alert_setup(db):
    now = timezone.now().replace(minute=0, second=0, microsecond=0)

    group = Groupe.objects.create(nom="G-ALERT", code="GA")
    organizer = User.objects.create_user(username="org-alert", password="pwd")
    requester = User.objects.create_user(username="requester-alert", password="pwd")

    manifestation = Manifestation.objects.create(
        nom="Camp alertes",
        date_debut=now,
        date_fin=now + timedelta(days=5),
        statut="planifiee",
        organisateur=organizer,
        groupe=group,
    )
    # ORG-01/ORG-02 : le lieu est autonome et c'est la prestation qui le
    # référence (Prestation.lieu), plus l'inverse.
    lieu = Lieu.objects.create(
        nom="Entrepot",
        adresse="1 rue des stocks",
    )
    prestation = Prestation.objects.create(
        manifestation=manifestation,
        lieu=lieu,
        nom="Prestation alertes",
        date_debut=now + timedelta(days=1),
        date_fin=now + timedelta(days=2),
    )

    category = PartCategory.objects.create(name="Cat alert")
    part = Part.objects.create(name="Gants jetables", category=category)

    RentableItem.objects.create(
        part=part,
        is_rentable=True,
        consommable=True,
        seuil_alerte_bas=20,
        seuil_alerte_haut=95,
    )
    # 100 en stock côté InvenTree : 95 réservés → 95 % de tension.
    mettre_en_stock(part, 100)

    reservation = Reservation.objects.create(
        prestation=prestation,
        demandeur=requester,
        statut="validee",
        date_retrait_prevue=now + timedelta(days=1),
        date_retour_prevue=now + timedelta(days=2),
    )
    reservation.lignes.create(part=part, quantite_demandee=95)

    return {
        "manifestation": manifestation,
        "lieu": lieu,
        "part": part,
        "reservation": reservation,
    }


@pytest.mark.django_db
def test_stock_alerts_list_includes_projected_tension(manager, alert_setup):
    factory = APIRequestFactory()
    request = factory.get("/plugin/inventree-location/alerts/stock/")
    force_authenticate(request, user=manager)

    response = StockAlertListView.as_view()(request)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1
    alert = response.data["alerts"][0]
    assert alert["part_id"] == alert_setup["part"].pk
    assert alert["projected_occupation_rate"] >= 90


@pytest.mark.django_db
def test_stock_alerts_filter_by_manifestation_and_lieu(manager, alert_setup):
    factory = APIRequestFactory()
    request = factory.get(
        "/plugin/inventree-location/alerts/stock/",
        {
            "manifestation": alert_setup["manifestation"].pk,
            "lieu": alert_setup["lieu"].pk,
        },
    )
    force_authenticate(request, user=manager)

    response = StockAlertListView.as_view()(request)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["count"] >= 1


@pytest.mark.django_db
def test_stock_alerts_notify_sends_email(manager, alert_setup, monkeypatch):
    sent = {"count": 0}

    def fake_send_mail(*args, **kwargs):
        sent["count"] += 1
        return 1

    monkeypatch.setattr("inventree_location.views.send_mail", fake_send_mail)

    factory = APIRequestFactory()
    request = factory.get(
        "/plugin/inventree-location/alerts/stock/",
        {"notify": "1"},
    )
    force_authenticate(request, user=manager)

    response = StockAlertListView.as_view()(request)

    assert response.status_code == status.HTTP_200_OK
    assert sent["count"] == 1


@pytest.mark.django_db
def test_virtual_article_never_raises_a_stock_alert(manager, alert_setup):
    """Un service n'a pas de stock physique : ni seuil, ni tension.

    Sans ce filtre il remontait en tension à 200 % de « 0 louable(s) ».
    """

    service = Part.objects.create(name="Prestation nettoyage")
    RentableItem.objects.create(
        part=service,
        is_rentable=True,
        is_virtual=True,
        seuil_alerte_haut=1,
    )
    alert_setup["reservation"].lignes.create(part=service, quantite_demandee=2)

    factory = APIRequestFactory()
    request = factory.get("/plugin/inventree-location/alerts/stock/")
    force_authenticate(request, user=manager)

    response = StockAlertListView.as_view()(request)

    part_ids = [alert["part_id"] for alert in response.data["alerts"]]
    assert service.pk not in part_ids


def test_seuils_ignores_sur_un_article_non_consommable(manager, alert_setup):
    """Les deux seuils appartiennent au consommable (US-09, CDC V06).

    Le back-office laisse saisir des seuils sur n'importe quel article : sans
    cette garde, un seuil haut posé sur du matériel louable déclenchait une
    alerte de réapprovisionnement dénuée de sens.
    """

    materiel = Part.objects.create(name="Tente 4 places")
    RentableItem.objects.create(
        part=materiel,
        is_rentable=True,
        consommable=False,
        seuil_alerte_bas=999,
        seuil_alerte_haut=1,
    )

    factory = APIRequestFactory()
    request = factory.get("/plugin/inventree-location/alerts/stock/")
    force_authenticate(request, user=manager)

    response = StockAlertListView.as_view()(request)

    seuils = [
        raison["type"]
        for alerte in response.data["alerts"]
        if alerte["part_id"] == materiel.pk
        for raison in alerte["reasons"]
        if raison["type"] in {"low_threshold", "high_threshold"}
    ]
    assert seuils == []
