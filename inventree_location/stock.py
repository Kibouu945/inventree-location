"""STK-01 — Calcul du stock disponible au jour entier."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from django.utils import timezone

from .conflicts import CONFLICT_STATUSES, get_part_total_stock, tension_level


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


def compute_engagement_details(
    part_ids,
    date_debut,
    date_fin,
    *,
    exclude_prestation_id=None,
    exclude_reservation_id=None,
) -> dict[int, list[dict]]:
    """Détail, par article, des prestations qui l'engagent sur la période."""

    from .models import LignePrestation, LigneReservation, Reservation

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

    # Quantités indexées par (prestation, article) : la réconciliation
    # prévisionnel/réalisé se fait prestation par prestation.
    forecast: dict[tuple[int, int], int] = {}
    booked: dict[tuple[int, int], int] = {}
    noms: dict[int, str] = {}
    numeros: dict[tuple[int, int], list[str]] = {}

    lignes_prestation = LignePrestation.objects.filter(
        part_id__in=part_ids
    ).select_related("prestation")

    for excluded in (exclude_prestation_id, excluded_forecast_id):
        if excluded is not None:
            lignes_prestation = lignes_prestation.exclude(prestation_id=excluded)

    for ligne in lignes_prestation:
        prestation = ligne.prestation

        if day_ranges_overlap(
            date_debut, date_fin, prestation.date_debut, prestation.date_fin
        ):
            key = (prestation.pk, ligne.part_id)
            forecast[key] = forecast.get(key, 0) + ligne.quantite
            noms[prestation.pk] = prestation.nom

    lignes_reservation = LigneReservation.objects.filter(
        part_id__in=part_ids,
        reservation__statut__in=CONFLICT_STATUSES,
        reservation__date_retrait_prevue__isnull=False,
        reservation__date_retour_prevue__isnull=False,
    ).select_related("reservation__prestation")

    if exclude_prestation_id is not None:
        lignes_reservation = lignes_reservation.exclude(
            reservation__prestation_id=exclude_prestation_id
        )

    if exclude_reservation_id is not None:
        lignes_reservation = lignes_reservation.exclude(
            reservation_id=exclude_reservation_id
        )

    for ligne in lignes_reservation:
        reservation = ligne.reservation

        if day_ranges_overlap(
            date_debut,
            date_fin,
            reservation.date_retrait_prevue,
            reservation.date_retour_prevue,
        ):
            key = (reservation.prestation_id, ligne.part_id)
            booked[key] = booked.get(key, 0) + ligne.quantite_demandee
            noms[reservation.prestation_id] = reservation.prestation.nom
            numeros.setdefault(key, []).append(reservation.numero)

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
        total_stock = get_part_total_stock(part, rentable_item=rentable) if part else 0
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

    base = max(total_stock, 1)
    days = []
    current = start_date

    while current <= end_date:
        engagements = compute_engagement_details([part.pk], current, current).get(
            part.pk, []
        )
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
