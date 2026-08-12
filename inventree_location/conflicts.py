from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, List, Optional, Union

from django.db.models import Sum
from django.utils import timezone

DateOrDateTime = Union[date, datetime]
CONFLICT_STATUSES = {
    "confirmée",
    "livrée",
    "retournée",
    "validee",
    "livree",
    "retournee",
}


@dataclass(frozen=True)
class ReservationRecord:
    id: int
    part_id: int
    qty: int
    start: DateOrDateTime
    end: DateOrDateTime
    status: str


def normalize_to_datetime(value: DateOrDateTime, *, end: bool = False) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.combine(value, time.max if end else time.min)

    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())

    return dt


def to_day_period(
    start: DateOrDateTime,
    end: DateOrDateTime,
) -> tuple[datetime, datetime]:
    """Normalise une période sur des bornes jour entier."""

    start_dt = normalize_to_datetime(start)
    end_dt = normalize_to_datetime(end, end=True)

    return (
        datetime.combine(start_dt.date(), time.min, tzinfo=start_dt.tzinfo),
        datetime.combine(end_dt.date(), time.max, tzinfo=end_dt.tzinfo),
    )


def periods_overlap(
    start_a: DateOrDateTime,
    end_a: DateOrDateTime,
    start_b: DateOrDateTime,
    end_b: DateOrDateTime,
) -> bool:
    start_a = normalize_to_datetime(start_a)
    end_a = normalize_to_datetime(end_a, end=True)
    start_b = normalize_to_datetime(start_b)
    end_b = normalize_to_datetime(end_b, end=True)

    return start_a <= end_b and end_a >= start_b


def find_conflicting_reservations(
    reservations: Iterable[ReservationRecord],
    part_id: int,
    start: DateOrDateTime,
    end: DateOrDateTime,
    exclude_resa_id: Optional[int] = None,
) -> List[ReservationRecord]:
    conflicts: List[ReservationRecord] = []

    for reservation in reservations:
        if reservation.part_id != part_id:
            continue
        if exclude_resa_id is not None and reservation.id == exclude_resa_id:
            continue
        if reservation.status not in CONFLICT_STATUSES:
            continue
        if periods_overlap(start, end, reservation.start, reservation.end):
            conflicts.append(reservation)

    return conflicts


def compute_conflicts(
    part_id: int,
    qty: int,
    start: DateOrDateTime,
    end: DateOrDateTime,
    exclude_resa_id: Optional[int] = None,
) -> List:
    period_start, period_end = to_day_period(start, end)

    if period_start > period_end:
        raise ValueError("start must be before or equal to end")

    from .models import Reservation

    reservations = Reservation.objects.filter(
        lignes__part_id=part_id,
        statut__in=CONFLICT_STATUSES,
        date_retrait_prevue__isnull=False,
        date_retour_prevue__isnull=False,
    ).distinct()

    if exclude_resa_id is not None:
        reservations = reservations.exclude(pk=exclude_resa_id)

    return [
        reservation
        for reservation in reservations
        if periods_overlap(
            period_start,
            period_end,
            reservation.date_retrait_prevue,
            reservation.date_retour_prevue,
        )
    ]


def tension_level(occupation_rate: float) -> str:
    """Retourne le code couleur de tension selon le ratio d'occupation."""

    if occupation_rate > 98:
        return "red"
    if occupation_rate >= 90:
        return "orange"
    if occupation_rate >= 75:
        return "yellow"
    if occupation_rate >= 50:
        return "blue"
    return "green"


def compute_part_availability(
    part,
    requested_quantity: int,
    start: DateOrDateTime,
    end: DateOrDateTime,
    *,
    exclude_resa_id: Optional[int] = None,
) -> dict:
    """Calcule la disponibilité et la tension prévisionnelle d'un article."""

    from .models import LigneReservation, RentableItem

    rentable_item = RentableItem.objects.filter(part=part).first()

    if rentable_item is not None and rentable_item.is_virtual:
        return {
            "is_virtual": True,
            "total_stock": 0,
            "already_reserved_quantity": 0,
            "available_quantity": 0,
            "missing_quantity": 0,
            "has_conflict": False,
            "occupation_rate": 0.0,
            "tension_level": "green",
            "conflicting_reservations": [],
        }

    total_stock = get_part_total_stock(part, rentable_item=rentable_item)
    overlapping = compute_conflicts(
        part.pk,
        requested_quantity,
        start,
        end,
        exclude_resa_id=exclude_resa_id,
    )

    reserved = (
        LigneReservation.objects.filter(
            part=part,
            reservation__in=overlapping,
        ).aggregate(total=Sum("quantite_demandee"))["total"]
        or 0
    )

    available = total_stock - reserved
    missing = max(requested_quantity - available, 0)
    base = max(total_stock, 1)
    occupation_rate = ((reserved + requested_quantity) / base) * 100

    return {
        "is_virtual": False,
        "total_stock": total_stock,
        "already_reserved_quantity": reserved,
        "available_quantity": available,
        "missing_quantity": missing,
        "has_conflict": missing > 0,
        "occupation_rate": occupation_rate,
        "tension_level": tension_level(occupation_rate),
        "conflicting_reservations": overlapping,
    }


def build_part_availability_histogram(
    part,
    *,
    scale: str = "week",
    anchor: Optional[DateOrDateTime] = None,
    manifestation_id: Optional[int] = None,
    lieu_id: Optional[int] = None,
) -> dict:
    """Construit un histogramme jour par jour de disponibilité pour un article."""

    from .models import LigneReservation, RentableItem

    horizon = {"week": 7, "month": 31, "quarter": 92}.get(scale, 7)
    start_anchor = normalize_to_datetime(anchor or timezone.now())
    start_day = datetime.combine(
        start_anchor.date(),
        time.min,
        tzinfo=start_anchor.tzinfo,
    )

    rentable_item = RentableItem.objects.filter(part=part).first()
    total_stock = get_part_total_stock(part, rentable_item=rentable_item)

    rows = []

    for offset in range(horizon):
        day_start = start_day + timedelta(days=offset)
        day_end = datetime.combine(
            day_start.date(),
            time.max,
            tzinfo=day_start.tzinfo,
        )

        overlapping = compute_conflicts(
            part.pk,
            0,
            day_start,
            day_end,
        )

        if manifestation_id is not None:
            overlapping = [
                resa
                for resa in overlapping
                if resa.prestation.manifestation_id == manifestation_id
            ]

        if lieu_id is not None:
            # ORG-01 : une prestation référence un lieu unique (Prestation.lieu),
            # là où la relation était auparavant inverse (Lieu.prestation).
            overlapping = [
                resa for resa in overlapping if resa.prestation.lieu_id == lieu_id
            ]

        reserved = (
            LigneReservation.objects.filter(
                part=part,
                reservation__in=overlapping,
            ).aggregate(total=Sum("quantite_demandee"))["total"]
            or 0
        )

        available = total_stock - reserved
        occupation_rate = (reserved / max(total_stock, 1)) * 100

        rows.append({
            "date": day_start.date().isoformat(),
            "total_quantity": total_stock,
            "reserved_quantity": reserved,
            "available_quantity": available,
            "occupation_rate": occupation_rate,
            "tension_level": tension_level(occupation_rate),
            "reservation_numbers": [resa.numero for resa in overlapping],
        })

    return {
        "part_id": part.pk,
        "part_name": getattr(part, "name", str(part)),
        "scale": scale,
        "days": rows,
    }


# ---------------------------------------------------------------------------
# Détection de conflits basée sur le stock (US-03 / SCRUM-76)
#
# Couche de plus haut niveau construite sur `compute_conflicts` : pour une
# réservation donnée, on compare la quantité demandée au stock projeté
# (stock total − quantités déjà réservées sur la période) de chaque ligne.
# ---------------------------------------------------------------------------

RESERVATION_DIRECT_LINK = "/api/plugin/inventree-location/reservations/{pk}/"


def get_part_total_stock(part, rentable_item=None) -> int:
    """Retourne le stock total disponible pour une Part.

    Priorité :
    1. ``RentableItem.stock_total`` s'il existe ;
    2. attributs natifs InvenTree (total_stock, in_stock, …) ;
    3. 0 par défaut.
    """

    from .models import RentableItem

    if rentable_item is None:
        rentable_item = RentableItem.objects.filter(part=part).first()

    if rentable_item is not None:
        return rentable_item.stock_total

    for attr in ("total_stock", "in_stock", "stock", "quantity"):
        value = getattr(part, attr, None)

        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue

    stock_method = getattr(part, "get_stock_count", None)

    if callable(stock_method):
        try:
            return int(stock_method())
        except (TypeError, ValueError):
            return 0

    return 0


def detect_reservation_conflicts(reservation) -> dict:
    """Détecte les conflits de stock d'une réservation, ligne par ligne.

    Pour chaque ligne : stock projeté = stock total − somme des quantités
    déjà réservées sur la période (réservations dont le statut est bloquant,
    cf. ``CONFLICT_STATUSES``). Un conflit est levé quand la quantité
    demandée dépasse le stock projeté.

    Les articles virtuels (services, ex. « nettoyage ») sont ignorés : ils
    ne portent pas de contrainte de stock physique.

    Retourne ``{"has_conflict": bool, "reservation": pk, "conflicts": [...]}``.
    """

    from django.db.models import Sum

    from .models import LigneReservation, RentableItem

    empty = {"has_conflict": False, "reservation": reservation.pk, "conflicts": []}

    start = reservation.date_retrait_prevue
    end = reservation.date_retour_prevue

    if not start or not end:
        return empty

    if normalize_to_datetime(start) > normalize_to_datetime(end, end=True):
        return empty

    conflicts = []

    for ligne in reservation.lignes.select_related("part").all():
        part = ligne.part
        requested = ligne.quantite_demandee

        rentable_item = RentableItem.objects.filter(part=part).first()

        # Les articles virtuels n'ont pas de stock physique à arbitrer.
        if rentable_item is not None and rentable_item.is_virtual:
            continue

        total_stock = get_part_total_stock(part, rentable_item=rentable_item)

        overlapping = compute_conflicts(
            part.pk,
            requested,
            start,
            end,
            exclude_resa_id=reservation.pk,
        )

        reserved = (
            LigneReservation.objects.filter(
                part=part,
                reservation__in=overlapping,
            ).aggregate(total=Sum("quantite_demandee"))["total"]
            or 0
        )

        available = total_stock - reserved

        if requested > available:
            safe_available = max(available, 0)

            conflicts.append({
                "part_id": part.pk,
                "part_name": getattr(part, "name", str(part)),
                "requested_quantity": requested,
                "total_stock": total_stock,
                "already_reserved_quantity": reserved,
                "available_quantity": available,
                "missing_quantity": requested - available,
                "conflicting_reservations": [
                    {
                        "reservation_id": resa.pk,
                        "numero": resa.numero,
                        "statut": resa.statut,
                        "direct_link": RESERVATION_DIRECT_LINK.format(pk=resa.pk),
                    }
                    for resa in overlapping
                ],
                "suggestions": [
                    f"Réduire la quantité demandée à {safe_available}.",
                    "Choisir une autre période de réservation.",
                    "Libérer ou modifier une réservation existante en conflit.",
                ],
            })

    return {
        "has_conflict": bool(conflicts),
        "reservation": reservation.pk,
        "conflicts": conflicts,
    }


def reservation_has_conflicts(reservation) -> bool:
    """Retourne True si la réservation présente au moins un conflit de stock."""

    return detect_reservation_conflicts(reservation)["has_conflict"]


def list_current_conflicts() -> List[dict]:
    """Liste les réservations actuellement en conflit, regroupées.

    Chaque entrée représente un *groupe* de conflit : une réservation et
    l'ensemble des réservations qui la chevauchent sur un même article. Les
    réservations déjà rattachées à un groupe ne réapparaissent pas comme
    entrées distinctes.
    """

    from .models import Reservation

    queryset = (
        Reservation.objects.select_related("prestation", "demandeur")
        .prefetch_related("lignes")
        .filter(
            statut__in=CONFLICT_STATUSES,
            date_retrait_prevue__isnull=False,
            date_retour_prevue__isnull=False,
        )
        .order_by("date_retrait_prevue", "date_retour_prevue", "pk")
    )

    payload = []
    processed_ids = set()

    for reservation in queryset:
        if reservation.pk in processed_ids:
            continue

        conflicting_ids = set()

        for ligne in reservation.lignes.all():
            conflicts = compute_conflicts(
                ligne.part_id,
                ligne.quantite_demandee,
                reservation.date_retrait_prevue,
                reservation.date_retour_prevue,
                exclude_resa_id=reservation.pk,
            )

            conflicting_ids.update(
                conflict.pk for conflict in conflicts if conflict.pk != reservation.pk
            )

        if not conflicting_ids:
            continue

        processed_ids.update({reservation.pk, *conflicting_ids})

        payload.append({
            "id": reservation.pk,
            "numero": reservation.numero,
            "statut": reservation.statut,
            "date_retrait_prevue": reservation.date_retrait_prevue,
            "date_retour_prevue": reservation.date_retour_prevue,
            "prestation_nom": reservation.prestation.nom,
            "demandeur_nom": (
                reservation.demandeur.get_full_name() or reservation.demandeur.username
            ),
            "conflict_count": len(conflicting_ids),
            "conflicting_reservation_ids": sorted(conflicting_ids),
        })

    return payload


def count_current_conflicts() -> int:
    """Nombre de groupes de conflit actuels (cf. ``list_current_conflicts``)."""

    return len(list_current_conflicts())
