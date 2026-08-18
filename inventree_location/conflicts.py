from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable, List, Optional, Union

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


# ---------------------------------------------------------------------------
# Détection de conflits basée sur le stock (US-03 / SCRUM-76)
#
# Couche de plus haut niveau construite sur `compute_conflicts` : pour une
# réservation donnée, on compare la quantité demandée au stock projeté
# (stock total − quantités déjà réservées sur la période) de chaque ligne.
# ---------------------------------------------------------------------------

RESERVATION_DIRECT_LINK = "/api/plugin/inventree-location/reservations/{pk}/"


#: Statuts InvenTree dont le stock est réellement louable.
#:
#: InvenTree considère « disponibles » les statuts OK, Attention, Endommagé et
#: Retourné (`StockStatusGroups.AVAILABLE_CODES`). Le métier est plus strict :
#: « un objet endommagé sort du stock réellement disponible ; seules les
#: réservations suivantes ne voient que le stock réellement bon » (ticket
#: ramassage / SAV). On écarte donc Endommagé et Attention, en plus des
#: statuts qu'InvenTree exclut déjà (Détruit, Rejeté, Perdu, Quarantaine).
RENTAL_STOCK_STATUSES = (
    10,  # OK
    85,  # Retourné (rentré de chez un client, de nouveau louable)
)


def get_part_total_stock(part, rentable_item=None) -> int:
    """Retourne le stock physique louable d'une Part, selon InvenTree.

    InvenTree est la source de vérité du « combien en avons-nous » : le plugin
    somme les `StockItem` réellement en stock (`IN_STOCK_FILTER` natif) dont le
    statut est louable (cf. `RENTAL_STOCK_STATUSES`). Le plugin n'entretient
    plus de compteur parallèle : `RentableItem` ne porte que ce qu'InvenTree ne
    sait pas dire (louable, consommable, virtuel, caution, seuils).

    Hors container InvenTree (suite pytest sans app `stock`), on retombe sur
    les attributs de stock exposés par l'objet, puis sur 0.

    `rentable_item` n'est plus lu ; le paramètre subsiste pour les appelants
    qui l'ont déjà sous la main et éviteraient une requête.
    """

    quantity = _rental_stock_quantity(part)

    if quantity is not None:
        return quantity

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


def _rental_stock_quantity(part):
    """Somme des exemplaires louables d'une Part, ou None si `stock` est absent."""

    from django.db.models import Sum

    try:
        from stock.models import StockItem
    except ImportError:  # pragma: no cover - dépend de l'environnement
        return None

    queryset = StockItem.objects.filter(part=part, status__in=RENTAL_STOCK_STATUSES)

    # `IN_STOCK_FILTER` porte la définition InvenTree de « physiquement en
    # stock » (ni vendu, ni consommé, ni chez un client, quantité > 0). On s'y
    # adosse plutôt que de la réécrire, qui dériverait à la première évolution.
    in_stock_filter = getattr(StockItem, "IN_STOCK_FILTER", None)

    if in_stock_filter is not None:
        queryset = queryset.filter(in_stock_filter)

    total = queryset.aggregate(total=Sum("quantity"))["total"] or 0

    return int(total)


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

    from .models import RentableItem
    from .stock import compute_engagement_details

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

        # Même moteur d'engagement que le catalogue et la fiche prestation :
        # sommer ici les seules lignes de réservation ignorait le prévisionnel
        # des prestations et donnait deux disponibilités différentes pour un
        # même article à la même date.
        engagements = compute_engagement_details(
            [part.pk],
            start,
            end,
            exclude_reservation_id=reservation.pk,
        ).get(part.pk, [])

        reserved = sum(entry["quantite"] for entry in engagements)
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
                # Le stock peut être retenu par le seul prévisionnel d'une
                # prestation, sans aucune réservation à montrer : sans ce
                # détail, la pénurie n'aurait aucun responsable à désigner.
                "conflicting_prestations": engagements,
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
    """Liste les réservations actuellement en pénurie de stock, regroupées.

    Un conflit n'est **pas** un simple chevauchement : deux réservations
    peuvent porter le même article aux mêmes dates sans se gêner tant que le
    stock suffit (4 + 3 sur 10 en stock n'est pas un conflit). Ce sont les
    quantités qui décident, via `detect_reservation_conflicts` — le même
    moteur que le garde-fou de validation, pour que le widget et le formulaire
    ne se contredisent pas.

    Chaque entrée représente un *groupe* : une réservation en pénurie et les
    réservations qui se partagent avec elle l'article manquant. Les
    réservations déjà rattachées à un groupe ne réapparaissent pas comme
    entrées distinctes. `shortages` détaille les articles en cause et la
    quantité manquante ; une pénurie peut venir du seul prévisionnel d'une
    prestation, auquel cas `conflict_count` vaut 0.
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

        result = detect_reservation_conflicts(reservation)

        if not result["has_conflict"]:
            continue

        conflicting_ids = set()
        shortages = []

        for conflict in result["conflicts"]:
            conflicting_ids.update(
                item["reservation_id"] for item in conflict["conflicting_reservations"]
            )
            shortages.append({
                "part_id": conflict["part_id"],
                "part_name": conflict["part_name"],
                "missing_quantity": conflict["missing_quantity"],
            })

        conflicting_ids.discard(reservation.pk)
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
            "shortages": shortages,
        })

    return payload


def count_current_conflicts() -> int:
    """Nombre de groupes de conflit actuels (cf. ``list_current_conflicts``)."""

    return len(list_current_conflicts())
