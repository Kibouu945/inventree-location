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
    prestation = Prestation.objects.create(
        manifestation=manifestation,
        nom="Prestation alertes",
        date_debut=now + timedelta(days=1),
        date_fin=now + timedelta(days=2),
    )
    lieu = Lieu.objects.create(
        prestation=prestation,
        nom="Entrepot",
        adresse="1 rue des stocks",
    )

    category = PartCategory.objects.create(name="Cat alert")
    part = Part.objects.create(name="Gants jetables", category=category)

    RentableItem.objects.create(
        part=part,
        is_rentable=True,
        consommable=True,
        stock_total=100,
        seuil_alerte_bas=20,
        seuil_alerte_haut=95,
    )

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
