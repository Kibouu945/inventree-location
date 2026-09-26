from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from inventree_location.conflicts import detect_location_reservation_conflicts
from inventree_location.models import (
    ConflictHistory,
    ConflictState,
    ConflictType,
    Lieu,
    Prestation,
    RentableItem,
    Reservation,
    StatutReservation,
)
from inventree_location.serializers import ReservationSerializer
from inventree_location.views import ConflictHistoryListView, ConflictHistoryResolveView
from inventree_location.tests.factories import make_manifestation

from part.models import Part, PartCategory

User = get_user_model()


@pytest.fixture
def manager(db):
    from django.contrib.auth.models import Group

    from inventree_location import roles

    group, _ = Group.objects.get_or_create(name=roles.GESTIONNAIRE)
    user = User.objects.create_user(username="manager", password="pwd")
    user.groups.add(group)
    return user


@pytest.fixture
def location_setup(db):
    now = timezone.now().replace(minute=0, second=0, microsecond=0)

    manifestation = make_manifestation(
        nom="Camp été",
        date_debut=now,
        date_fin=now + timedelta(days=5),
        statut="planifiee",
    )

    prestation_a = Prestation.objects.create(
        manifestation=manifestation,
        nom="Prestation A",
        date_debut=now + timedelta(days=1),
        date_fin=now + timedelta(days=2),
    )
    prestation_b = Prestation.objects.create(
        manifestation=manifestation,
        nom="Prestation B",
        date_debut=now + timedelta(days=1),
        date_fin=now + timedelta(days=2),
    )

    # ORG-02 : le lieu est autonome et c'est la prestation qui le référence.
    prestation_a.lieu = Lieu.objects.create(
        nom="Lieu A",
        adresse="10 Rue de la Paix, Paris",
        latitude=48.8566,
        longitude=2.3522,
    )
    prestation_a.save(update_fields=["lieu"])

    prestation_b.lieu = Lieu.objects.create(
        nom="Lieu B",
        adresse="10 Rue de la Paix, Paris",
        latitude=48.8566,
        longitude=2.3522,
    )
    prestation_b.save(update_fields=["lieu"])

    category = PartCategory.objects.create(name="Services")
    virtual_part = Part.objects.create(name="Nettoyage", category=category)
    RentableItem.objects.create(
        part=virtual_part,
        is_rentable=True,
        is_virtual=True,
    )

    requester = User.objects.create_user(username="requester", password="pwd")

    existing = Reservation.objects.create(
        prestation=prestation_a,
        demandeur=requester,
        statut=StatutReservation.VALIDEE,
        date_retrait_prevue=now + timedelta(days=1, hours=8),
        date_retour_prevue=now + timedelta(days=1, hours=12),
    )
    existing.lignes.create(part=virtual_part, quantite_demandee=1)

    return {
        "now": now,
        "requester": requester,
        "prestation_b": prestation_b,
        "virtual_part": virtual_part,
        # La réservation qui occupe déjà le lieu : c'est elle, la cause.
        "existing": existing,
    }


@pytest.mark.django_db
def test_location_conflict_is_journalised(location_setup):
    candidate = Reservation.objects.create(
        prestation=location_setup["prestation_b"],
        demandeur=location_setup["requester"],
        statut=StatutReservation.SOUMISE,
        date_retrait_prevue=location_setup["now"] + timedelta(days=1, hours=9),
        date_retour_prevue=location_setup["now"] + timedelta(days=1, hours=10),
    )
    candidate.lignes.create(part=location_setup["virtual_part"], quantite_demandee=1)

    # Le conflit de lieu se trace sans bloquer : l'arbitrage a lieu à la
    # validation, pas à l'enregistrement de la demande.
    ReservationSerializer()._register_conflict_history(candidate)

    history = ConflictHistory.objects.filter(
        reservation=candidate,
        conflict_type=ConflictType.LOCATION,
        state=ConflictState.OPEN,
    )
    assert history.exists()


@pytest.mark.django_db
def test_location_conflict_not_detected_when_address_differs(location_setup):
    Lieu.objects.filter(pk=location_setup["prestation_b"].lieu_id).update(
        adresse="20 Avenue des Champs, Paris",
        latitude=48.8700,
        longitude=2.3100,
    )
    # `.update()` ne touche pas l'objet en mémoire : sans relecture, la
    # prestation garde son lieu d'origine en cache et le test mesurerait
    prestation_b = Prestation.objects.get(pk=location_setup["prestation_b"].pk)

    candidate = Reservation.objects.create(
        prestation=prestation_b,
        demandeur=location_setup["requester"],
        statut=StatutReservation.SOUMISE,
        date_retrait_prevue=location_setup["now"] + timedelta(days=1, hours=9),
        date_retour_prevue=location_setup["now"] + timedelta(days=1, hours=10),
    )
    candidate.lignes.create(part=location_setup["virtual_part"], quantite_demandee=1)

    result = detect_location_reservation_conflicts(candidate)
    assert result["has_conflict"] is False


@pytest.mark.django_db
def test_conflict_history_filters_and_resolve(manager, location_setup):
    reservation = Reservation.objects.create(
        prestation=location_setup["prestation_b"],
        demandeur=location_setup["requester"],
        statut=StatutReservation.SOUMISE,
        date_retrait_prevue=location_setup["now"] + timedelta(days=1, hours=9),
        date_retour_prevue=location_setup["now"] + timedelta(days=1, hours=10),
    )
    reservation.lignes.create(part=location_setup["virtual_part"], quantite_demandee=1)

    ReservationSerializer()._register_conflict_history(reservation)

    history_item = ConflictHistory.objects.filter(reservation=reservation).first()
    assert history_item is not None

    factory = APIRequestFactory()
    list_request = factory.get(
        "/plugin/inventree-location/conflicts/history/",
        {"state": "open", "type": "location"},
    )
    force_authenticate(list_request, user=manager)

    list_response = ConflictHistoryListView.as_view()(list_request)
    assert list_response.status_code == status.HTTP_200_OK
    assert len(list_response.data) >= 1

    def resoudre():
        request = factory.patch(
            f"/plugin/inventree-location/conflicts/history/{history_item.pk}/resolve/",
            {"note": "handled"},
            format="json",
        )
        force_authenticate(request, user=manager)
        return ConflictHistoryResolveView.as_view()(request, pk=history_item.pk)

    # Tant que le lieu est occupé, clore l'entrée ne résoudrait rien : le
    # serveur refuse et nomme la cause.
    refus = resoudre()
    assert refus.status_code == status.HTTP_409_CONFLICT
    assert "occupe déjà" in refus.data["reason"]

    history_item.refresh_from_db()
    assert history_item.state == ConflictState.OPEN

    # Cause levée : la réservation concurrente est annulée.
    location_setup["existing"].statut = StatutReservation.ANNULEE
    location_setup["existing"].save(update_fields=["statut"])

    resolve_response = resoudre()
    assert resolve_response.status_code == status.HTTP_200_OK

    history_item.refresh_from_db()
    assert history_item.state == ConflictState.RESOLVED
