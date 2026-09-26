"""STK-01 — Calcul du stock disponible au jour entier."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import NamedTuple

from django.utils import timezone

from .conflicts import (
    CONFLICT_STATUSES,
    get_part_total_stock,
    get_parts_total_stock,
    tension_level,
)


def _as_date(value) -> date:
    """Ramène une date/heure (objet ou chaîne ISO) au jour entier."""

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    # Chaîne ISO issue d'une requête (preview stock avant sauvegarde).
    text = str(value).strip()
    normalized = text.replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(normalized).date()
    except ValueError:
        return date.fromisoformat(text[:10])


def day_ranges_overlap(start_a, end_a, start_b, end_b) -> bool:
    """Vrai si les deux plages se chevauchent au jour entier (bornes incluses)."""

    return _as_date(start_a) <= _as_date(end_b) and _as_date(end_a) >= _as_date(start_b)


#: Marge du filtre SQL de période.
MARGE_FENETRE = timedelta(days=1)


class LigneDEngagement(NamedTuple):
    """Une quantité retenue sur une période, prévisionnelle ou réservée."""

    part_id: int
    prestation_id: int
    prestation_nom: str
    quantite: int
    debut: object
    fin: object
    reservation_id: int | None
    numero: str
    statut: str


def charger_lignes_engagement(part_ids, date_debut, date_fin) -> list:
    """Charge en deux requêtes tout ce qui engage ces articles sur la période."""

    from .models import LignePrestation, LigneReservation

    part_ids = [int(pid) for pid in part_ids]

    if not part_ids:
        return []

    borne_basse = _as_date(date_debut) - MARGE_FENETRE
    borne_haute = _as_date(date_fin) + MARGE_FENETRE

    lignes = []

    lignes_prestation = (
        LignePrestation.objects.filter(
            part_id__in=part_ids,
            prestation__date_fin__date__gte=borne_basse,
            prestation__date_debut__date__lte=borne_haute,
        )
        .select_related("prestation")
        .only(
            "part_id",
            "quantite",
            "prestation__id",
            "prestation__nom",
            "prestation__date_debut",
            "prestation__date_fin",
        )
    )

    for ligne in lignes_prestation:
        prestation = ligne.prestation
        lignes.append(
            LigneDEngagement(
                part_id=ligne.part_id,
                prestation_id=prestation.pk,
                prestation_nom=prestation.nom,
                quantite=ligne.quantite,
                debut=prestation.date_debut,
                fin=prestation.date_fin,
                reservation_id=None,
                numero="",
                statut="",
            )
        )

    lignes_reservation = (
        LigneReservation.objects.filter(
            part_id__in=part_ids,
            reservation__statut__in=CONFLICT_STATUSES,
            reservation__date_retrait_prevue__isnull=False,
            reservation__date_retour_prevue__isnull=False,
            reservation__date_retour_prevue__date__gte=borne_basse,
            reservation__date_retrait_prevue__date__lte=borne_haute,
        )
        .select_related("reservation__prestation")
        .only(
            "part_id",
            "quantite_demandee",
            "reservation__id",
            "reservation__numero",
            "reservation__statut",
            "reservation__date_retrait_prevue",
            "reservation__date_retour_prevue",
            "reservation__prestation__id",
            "reservation__prestation__nom",
        )
    )

    for ligne in lignes_reservation:
        reservation = ligne.reservation
        lignes.append(
            LigneDEngagement(
                part_id=ligne.part_id,
                prestation_id=reservation.prestation_id,
                prestation_nom=reservation.prestation.nom,
                quantite=ligne.quantite_demandee,
                debut=reservation.date_retrait_prevue,
                fin=reservation.date_retour_prevue,
                reservation_id=reservation.pk,
                numero=reservation.numero,
                statut=reservation.statut,
            )
        )

    return lignes


def reduire_engagements(
    lignes,
    date_debut,
    date_fin,
    *,
    exclude_prestation_id=None,
    exclude_reservation_id=None,
    excluded_forecast_id=None,
) -> dict[int, list[dict]]:
    """Réconcilie prévisionnel et réalisé sur une fenêtre, sans toucher la base."""

    forecast: dict[tuple[int, int], int] = {}
    booked: dict[tuple[int, int], int] = {}
    noms: dict[int, str] = {}
    numeros: dict[tuple[int, int], list[str]] = {}

    for ligne in lignes:
        if (
            exclude_prestation_id is not None
            and ligne.prestation_id == exclude_prestation_id
        ):
            continue

        if ligne.reservation_id is None:
            # Le prévisionnel de la prestation dont on exclut la réservation :
            # cette réservation en est justement la matérialisation.
            if (
                excluded_forecast_id is not None
                and ligne.prestation_id == excluded_forecast_id
            ):
                continue
        elif (
            exclude_reservation_id is not None
            and ligne.reservation_id == exclude_reservation_id
        ):
            continue

        if not day_ranges_overlap(date_debut, date_fin, ligne.debut, ligne.fin):
            continue

        key = (ligne.prestation_id, ligne.part_id)
        noms[ligne.prestation_id] = ligne.prestation_nom

        if ligne.reservation_id is None:
            forecast[key] = forecast.get(key, 0) + ligne.quantite
        else:
            booked[key] = booked.get(key, 0) + ligne.quantite
            numeros.setdefault(key, []).append(ligne.numero)

    details: dict[int, list[dict]] = {}

    for key in sorted(set(forecast) | set(booked)):
        prestation_id, part_id = key
        prevu = forecast.get(key, 0)
        reserve = booked.get(key, 0)

        details.setdefault(part_id, []).append({
            "prestation_id": prestation_id,
            "prestation_nom": noms.get(prestation_id, ""),
            "quantite": max(prevu, reserve),
            "origine": "reservations" if reserve >= prevu else "prevision",
            "reservation_numeros": sorted(numeros.get(key, [])),
        })

    return details


def compute_engagement_details(
    part_ids,
    date_debut,
    date_fin,
    *,
    exclude_prestation_id=None,
    exclude_reservation_id=None,
) -> dict[int, list[dict]]:
    """Détail, par article, des prestations qui l'engagent sur la période."""

    from .models import Reservation

    part_ids = [int(pid) for pid in part_ids]

    if not part_ids:
        return {}

    excluded_forecast_id = None

    if exclude_reservation_id is not None:
        excluded_forecast_id = (
            Reservation.objects.filter(pk=exclude_reservation_id)
            .values_list("prestation_id", flat=True)
            .first()
        )

    return reduire_engagements(
        charger_lignes_engagement(part_ids, date_debut, date_fin),
        date_debut,
        date_fin,
        exclude_prestation_id=exclude_prestation_id,
        exclude_reservation_id=exclude_reservation_id,
        excluded_forecast_id=excluded_forecast_id,
    )


def compute_engaged_quantities(
    part_ids,
    date_debut,
    date_fin,
    *,
    exclude_prestation_id=None,
    exclude_reservation_id=None,
) -> dict[int, int]:
    """Quantités déjà engagées par article sur la période, au jour entier."""

    details = compute_engagement_details(
        part_ids,
        date_debut,
        date_fin,
        exclude_prestation_id=exclude_prestation_id,
        exclude_reservation_id=exclude_reservation_id,
    )

    return {
        part_id: sum(entry["quantite"] for entry in entries)
        for part_id, entries in details.items()
    }


def compute_stock_availability(
    date_debut,
    date_fin,
    requested_lines,
    exclude_prestation_id=None,
    exclude_reservation_id=None,
) -> dict:
    """Disponibilité au jour de chaque article demandé."""

    from part.models import Part

    from .models import RentableItem

    normalized = [
        {"part_id": int(line["part_id"]), "quantite": int(line["quantite"])}
        for line in requested_lines
        if line.get("part_id") is not None
    ]

    part_ids = [line["part_id"] for line in normalized]

    rentables = {
        item.part_id: item for item in RentableItem.objects.filter(part_id__in=part_ids)
    }
    parts = {part.pk: part for part in Part.objects.filter(pk__in=part_ids)}

    reserved_by_part = compute_engaged_quantities(
        part_ids,
        date_debut,
        date_fin,
        exclude_prestation_id=exclude_prestation_id,
        exclude_reservation_id=exclude_reservation_id,
    )

    # Le stock de tous les articles en une requête.
    stock_par_part = get_parts_total_stock(parts.values())

    result_lines = []
    has_shortage = False

    for line in normalized:
        part_id = line["part_id"]
        requested = line["quantite"]
        rentable = rentables.get(part_id)

        # Les articles virtuels n'ont pas de stock physique à arbitrer.
        if rentable is not None and rentable.is_virtual:
            continue

        part = parts.get(part_id)
        total_stock = stock_par_part.get(part_id, 0)
        reserved = reserved_by_part.get(part_id, 0)
        available = total_stock - reserved
        shortage = requested > available

        if shortage:
            has_shortage = True

        result_lines.append({
            "part_id": part_id,
            "part_name": getattr(part, "name", str(part_id)),
            "requested": requested,
            "total_stock": total_stock,
            "reserved": reserved,
            "available": available,
            "missing": max(requested - available, 0),
            "shortage": shortage,
        })

    return {"has_shortage": has_shortage, "lines": result_lines}


def compute_parts_availability(
    part_ids,
    date_debut=None,
    date_fin=None,
    exclude_prestation_id=None,
    exclude_reservation_id=None,
) -> dict[int, int]:
    """Disponibilité au jour d'un ensemble de parts, hors prestation existante."""

    part_ids = [int(pid) for pid in part_ids]

    if not part_ids:
        return {}

    if date_debut is None or date_fin is None:
        today = timezone.localdate()
        date_debut = date_debut or today
        date_fin = date_fin or today

    requested_lines = [{"part_id": pid, "quantite": 0} for pid in part_ids]

    result = compute_stock_availability(
        date_debut,
        date_fin,
        requested_lines,
        exclude_prestation_id=exclude_prestation_id,
        exclude_reservation_id=exclude_reservation_id,
    )

    return {line["part_id"]: line["available"] for line in result["lines"]}


def compute_prestation_stock(prestation) -> dict:
    """Disponibilité au jour des articles d'une prestation enregistrée."""

    lignes = [
        {"part_id": ligne.part_id, "quantite": ligne.quantite}
        for ligne in prestation.lignes_prestation.all()
    ]

    return compute_stock_availability(
        prestation.date_debut,
        prestation.date_fin,
        lignes,
        exclude_prestation_id=prestation.pk,
    )


MAX_HISTOGRAM_DAYS = 92


def compute_part_availability_calendar(part, date_debut, date_fin) -> list[dict]:
    """Disponibilité d'un article jour par jour, pour l'histogramme (CDC §99)."""

    from .models import RentableItem

    rentable_item = RentableItem.objects.filter(part=part).first()

    if rentable_item is not None and rentable_item.is_virtual:
        return []

    total_stock = get_part_total_stock(part, rentable_item=rentable_item)

    start_date = _as_date(date_debut)
    end_date = _as_date(date_fin)

    if end_date < start_date:
        start_date, end_date = end_date, start_date

    end_date = min(end_date, start_date + timedelta(days=MAX_HISTOGRAM_DAYS - 1))

    lignes = charger_lignes_engagement([part.pk], start_date, end_date)

    # Un stock nul ne doit pas diviser par zéro, et `tension_level` lit un
    # pourcentage : même base que `compute_part_availability`.
    base = max(total_stock, 1)
    days = []
    current = start_date

    while current <= end_date:
        engagements = reduire_engagements(lignes, current, current).get(part.pk, [])
        reserved = sum(entry["quantite"] for entry in engagements)
        occupation_rate = (reserved / base) * 100

        days.append({
            "date": current.isoformat(),
            "total_stock": total_stock,
            "reserved": reserved,
            "available": total_stock - reserved,
            "occupation_rate": occupation_rate,
            "tension_level": tension_level(occupation_rate),
        })

        current += timedelta(days=1)

    return days
