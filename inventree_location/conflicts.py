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


def to_day_period(
    start: DateOrDateTime,
    end: DateOrDateTime,
) -> tuple[datetime, datetime]:
    """Normalise une période en bornes jour entier."""

    start_dt = normalize_to_datetime(start)
    end_dt = normalize_to_datetime(end, end=True)

    start_day = datetime.combine(start_dt.date(), time.min, tzinfo=start_dt.tzinfo)
    end_day = datetime.combine(end_dt.date(), time.max, tzinfo=end_dt.tzinfo)

    return start_day, end_day


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
    """Disponibilité prévisionnelle d'un article sur une période, au jour entier."""

    from .models import RentableItem
    from .stock import compute_engagement_details

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

    engagements = compute_engagement_details(
        [part.pk],
        start,
        end,
        exclude_reservation_id=exclude_resa_id,
    ).get(part.pk, [])

    reserved = sum(entry["quantite"] for entry in engagements)
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
        "conflicting_reservations": compute_conflicts(
            part.pk,
            requested_quantity,
            start,
            end,
            exclude_resa_id=exclude_resa_id,
        ),
    }


# ---------------------------------------------------------------------------
# Détection de conflits basée sur le stock (US-03 / SCRUM-76)
# Couche de plus haut niveau construite sur `compute_conflicts` : pour une
# réservation donnée, on compare la quantité demandée au stock projeté
# (stock total − quantités déjà réservées sur la période) de chaque ligne.
# ---------------------------------------------------------------------------

RESERVATION_DIRECT_LINK = "/api/plugin/inventree-location/reservations/{pk}/"


#: Statuts InvenTree dont le stock est réellement louable.
RENTAL_STOCK_STATUSES = (
    10,  # OK
    85,  # Retourné (rentré de chez un client, de nouveau louable)
)


def get_part_total_stock(part, rentable_item=None) -> int:
    """Retourne le stock physique louable d'une Part, selon InvenTree."""

    quantity = _rental_stock_quantity(part)

    if quantity is not None:
        return quantity

    return _stock_depuis_les_attributs(part)


def get_parts_total_stock(parts) -> dict[int, int]:
    """Stock physique louable de plusieurs Parts, en **une** requête."""

    parts = list(parts)

    if not parts:
        return {}

    totaux = _rental_stock_quantities([part.pk for part in parts])

    if totaux is None:
        return {part.pk: _stock_depuis_les_attributs(part) for part in parts}

    return {part.pk: totaux.get(part.pk, 0) for part in parts}


def _stock_depuis_les_attributs(part) -> int:
    """Repli hors container InvenTree : ce que l'objet Part sait dire de lui."""

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


def _stock_louable_queryset():
    """Les `StockItem` réellement louables, ou None si l'app `stock` est absente."""

    try:
        from stock.models import StockItem
    except ImportError:  # pragma: no cover - dépend de l'environnement
        return None

    queryset = StockItem.objects.filter(status__in=RENTAL_STOCK_STATUSES)

    # `IN_STOCK_FILTER` porte la définition InvenTree de « physiquement en
    # stock » (ni vendu, ni consommé, ni chez un client, quantité > 0).
    in_stock_filter = getattr(StockItem, "IN_STOCK_FILTER", None)

    if in_stock_filter is not None:
        queryset = queryset.filter(in_stock_filter)

    return queryset


def _rental_stock_quantity(part):
    """Somme des exemplaires louables d'une Part, ou None si `stock` est absent."""

    from django.db.models import Sum

    queryset = _stock_louable_queryset()

    if queryset is None:
        return None

    total = queryset.filter(part=part).aggregate(total=Sum("quantity"))["total"] or 0

    return int(total)


def _rental_stock_quantities(part_ids):
    """Idem pour un lot d'articles, en une requête — None si `stock` est absent."""

    from django.db.models import Sum

    queryset = _stock_louable_queryset()

    if queryset is None:
        return None

    lignes = (
        queryset.filter(part_id__in=part_ids)
        .values("part_id")
        .annotate(total=Sum("quantity"))
    )

    return {ligne["part_id"]: int(ligne["total"] or 0) for ligne in lignes}


class ContexteDeConflits:
    """Tout ce qu'il faut pour arbitrer des conflits, chargé une fois."""

    def __init__(self, part_ids, date_debut, date_fin):
        from part.models import Part

        from .models import RentableItem
        from .stock import charger_lignes_engagement

        self.part_ids = sorted({int(pid) for pid in part_ids})

        self.rentables = {
            item.part_id: item
            for item in RentableItem.objects.filter(part_id__in=self.part_ids)
        }
        # Les articles sont portés ici plutôt que joints aux lignes de chaque
        # réservation : une jointure posée sur le manager de relation ignore le
        self.parts = {
            part.pk: part for part in Part.objects.filter(pk__in=self.part_ids)
        }

        self.lignes_par_part: dict[int, list] = {}

        for ligne in charger_lignes_engagement(self.part_ids, date_debut, date_fin):
            self.lignes_par_part.setdefault(ligne.part_id, []).append(ligne)

        self._stock: dict[int, int] | None = None

    def stock_de(self, part_id) -> int:
        """Le stock louable de l'article, tiré d'un agrégat groupé unique."""

        if self._stock is None:
            self._stock = get_parts_total_stock(self.parts.values())

        return self._stock.get(part_id, 0)

    def nom_de(self, part_id) -> str:
        """Le nom de l'article, pour le libellé de la pénurie."""

        part = self.parts.get(part_id)

        return getattr(part, "name", str(part_id)) if part is not None else str(part_id)

    def engagements(
        self,
        part_id,
        debut,
        fin,
        *,
        exclude_reservation_id=None,
        exclude_prestation_forecast_id=None,
    ):
        """Le détail des engagements d'un article sur une fenêtre donnée."""

        from .stock import reduire_engagements

        return reduire_engagements(
            self.lignes_par_part.get(part_id, []),
            debut,
            fin,
            exclude_reservation_id=exclude_reservation_id,
            excluded_forecast_id=exclude_prestation_forecast_id,
        ).get(part_id, [])

    def partageurs(self, part_id, debut, fin, *, exclude_reservation_id=None):
        """Les réservations bloquantes qui se partagent l'article sur la période."""

        from .stock import day_ranges_overlap

        vues = {}

        for ligne in self.lignes_par_part.get(part_id, []):
            if ligne.reservation_id is None:
                continue
            if ligne.reservation_id == exclude_reservation_id:
                continue
            if ligne.reservation_id in vues:
                continue
            if not day_ranges_overlap(debut, fin, ligne.debut, ligne.fin):
                continue

            vues[ligne.reservation_id] = {
                "reservation_id": ligne.reservation_id,
                "numero": ligne.numero,
                "statut": ligne.statut,
                "direct_link": RESERVATION_DIRECT_LINK.format(pk=ligne.reservation_id),
            }

        return [vues[cle] for cle in sorted(vues)]


def detect_reservation_conflicts(reservation, contexte=None) -> dict:
    """Détecte les conflits de stock d'une réservation, ligne par ligne."""

    empty = {"has_conflict": False, "reservation": reservation.pk, "conflicts": []}

    start = reservation.date_retrait_prevue
    end = reservation.date_retour_prevue

    if not start or not end:
        return empty

    if normalize_to_datetime(start) > normalize_to_datetime(end, end=True):
        return empty

    lignes = list(reservation.lignes.all())

    if contexte is None:
        contexte = ContexteDeConflits([ligne.part_id for ligne in lignes], start, end)

    conflicts = []

    for ligne in lignes:
        part_id = ligne.part_id
        requested = ligne.quantite_demandee

        rentable_item = contexte.rentables.get(part_id)

        # Les articles virtuels n'ont pas de stock physique à arbitrer.
        if rentable_item is not None and rentable_item.is_virtual:
            continue

        # Le détail nominatif sert deux fois : il donne la quantité engagée, et
        # il nomme la prestation responsable quand la pénurie ne vient que du
        engagements = contexte.engagements(
            part_id,
            start,
            end,
            exclude_reservation_id=reservation.pk,
            exclude_prestation_forecast_id=reservation.prestation_id,
        )

        total_stock = contexte.stock_de(part_id)
        reserved = sum(entry["quantite"] for entry in engagements)
        available = total_stock - reserved
        missing = max(requested - available, 0)

        if missing <= 0:
            continue

        occupation_rate = ((reserved + requested) / max(total_stock, 1)) * 100

        conflicts.append({
            "part_id": part_id,
            "part_name": contexte.nom_de(part_id),
            "requested_quantity": requested,
            "total_stock": total_stock,
            "already_reserved_quantity": reserved,
            "available_quantity": available,
            "missing_quantity": missing,
            "occupation_rate": occupation_rate,
            "tension_level": tension_level(occupation_rate),
            "conflicting_reservations": contexte.partageurs(
                part_id, start, end, exclude_reservation_id=reservation.pk
            ),
            "conflicting_prestations": engagements,
            "suggestions": [
                f"Réduire la quantité demandée à {max(available, 0)}.",
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
    """Liste les réservations actuellement en pénurie de stock, regroupées."""

    from django.db.models import Max, Min

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

    # Un seul chargement pour tout le parcours.
    bornes = queryset.aggregate(
        debut=Min("date_retrait_prevue"), fin=Max("date_retour_prevue")
    )

    if bornes["debut"] is None:
        return []

    reservations = list(queryset)
    part_ids = {
        ligne.part_id
        for reservation in reservations
        for ligne in reservation.lignes.all()
    }

    contexte = ContexteDeConflits(part_ids, bornes["debut"], bornes["fin"])

    payload = []
    processed_ids = set()

    for reservation in reservations:
        if reservation.pk in processed_ids:
            continue

        result = detect_reservation_conflicts(reservation, contexte=contexte)

        if not result["has_conflict"]:
            continue

        conflicting_ids = set()
        # Un nombre ne suffit pas pour arbitrer : il faut savoir contre qui.
        numeros_par_id = {}
        shortages = []

        for conflict in result["conflicts"]:
            for item in conflict["conflicting_reservations"]:
                conflicting_ids.add(item["reservation_id"])
                numeros_par_id[item["reservation_id"]] = item["numero"]
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
            "conflicting_reservation_numeros": [
                numeros_par_id[pk] for pk in sorted(conflicting_ids)
            ],
            "shortages": shortages,
        })

    return payload


def sync_conflict_registry(current_conflicts=None) -> int:
    """Inscrit au registre les pénuries en cours qui n'y figurent pas encore."""

    from .models import ConflictHistory, ConflictState, ConflictType, Reservation

    if current_conflicts is None:
        current_conflicts = list_current_conflicts()

    ouvertes = 0

    for entree in current_conflicts:
        reservation = Reservation.objects.filter(pk=entree["id"]).first()

        if reservation is None:
            continue

        # Une pénurie peut n'être due qu'au prévisionnel d'une prestation :
        # dans ce cas aucune réservation concurrente n'est à désigner.
        concurrentes = entree.get("conflicting_reservation_ids") or [None]

        for shortage in entree.get("shortages", []):
            for concurrente_id in concurrentes:
                _, cree = ConflictHistory.objects.get_or_create(
                    conflict_type=ConflictType.STOCK,
                    state=ConflictState.OPEN,
                    reservation_id=reservation.pk,
                    conflicting_reservation_id=concurrente_id,
                    part_id=shortage["part_id"],
                    period_start=reservation.date_retrait_prevue,
                    period_end=reservation.date_retour_prevue,
                    defaults={
                        "details": {
                            "part_name": shortage["part_name"],
                            "missing_quantity": shortage["missing_quantity"],
                            "source": "registre synchronisé",
                        }
                    },
                )

                if cree:
                    ouvertes += 1

    return ouvertes


def register_stock_conflict_history(reservation, conflict_result: dict) -> None:
    """Enregistre les conflits de stock détectés dans l'historique."""

    from .models import ConflictHistory, ConflictState, ConflictType

    if not conflict_result.get("has_conflict"):
        return

    for conflict in conflict_result.get("conflicts", []):
        conflicting_ids = [
            item.get("reservation_id")
            for item in conflict.get("conflicting_reservations", [])
            if item.get("reservation_id")
        ]

        if not conflicting_ids:
            conflicting_ids = [None]

        for conflicting_id in conflicting_ids:
            # Clés étrangères passées par `_id`, jamais par instance : le
            # chargeur de plugins importe `models` deux fois et une instance
            ConflictHistory.objects.get_or_create(
                conflict_type=ConflictType.STOCK,
                state=ConflictState.OPEN,
                reservation_id=reservation.pk,
                conflicting_reservation_id=conflicting_id,
                part_id=conflict.get("part_id"),
                period_start=reservation.date_retrait_prevue,
                period_end=reservation.date_retour_prevue,
                defaults={
                    "details": {
                        "part_name": conflict.get("part_name"),
                        "requested_quantity": conflict.get("requested_quantity"),
                        "available_quantity": conflict.get("available_quantity"),
                        "missing_quantity": conflict.get("missing_quantity"),
                        "occupation_rate": conflict.get("occupation_rate"),
                        "tension_level": conflict.get("tension_level"),
                    }
                },
            )


def detect_location_reservation_conflicts(reservation) -> dict:
    """Détecte les conflits de lieu (même adresse/GPS, même jour)."""

    from .models import Reservation

    empty = {"has_conflict": False, "reservation": reservation.pk, "conflicts": []}

    start = reservation.date_retrait_prevue
    end = reservation.date_retour_prevue

    if not start or not end or not reservation.prestation_id:
        return empty

    # ORG-02 : une prestation se déroule sur un *seul* lieu.
    current_place = reservation.prestation.lieu

    if current_place is None:
        return empty

    period_start, period_end = to_day_period(start, end)

    candidates = (
        Reservation.objects.select_related(
            "prestation", "prestation__lieu", "demandeur"
        )
        .filter(
            statut__in=CONFLICT_STATUSES,
            date_retrait_prevue__isnull=False,
            date_retour_prevue__isnull=False,
        )
        .exclude(pk=reservation.pk)
    )

    conflicts = []

    for candidate in candidates:
        if not periods_overlap(
            period_start,
            period_end,
            candidate.date_retrait_prevue,
            candidate.date_retour_prevue,
        ):
            continue

        existing_place = candidate.prestation.lieu

        if existing_place is None:
            continue

        current_address = (current_place.adresse or "").strip().lower()
        other_address = (existing_place.adresse or "").strip().lower()

        same_address = bool(current_address and current_address == other_address)
        same_gps = (
            current_place.latitude is not None
            and current_place.longitude is not None
            and existing_place.latitude is not None
            and existing_place.longitude is not None
            and str(current_place.latitude) == str(existing_place.latitude)
            and str(current_place.longitude) == str(existing_place.longitude)
        )

        if not same_address and not same_gps:
            continue

        conflicts.append({
            "reservation_id": candidate.pk,
            "numero": candidate.numero,
            "statut": candidate.statut,
            "prestation_nom": candidate.prestation.nom,
            "lieu_nom": existing_place.nom,
            "adresse": existing_place.adresse,
            "latitude": existing_place.latitude,
            "longitude": existing_place.longitude,
        })

    return {
        "has_conflict": bool(conflicts),
        "reservation": reservation.pk,
        "conflicts": conflicts,
    }


def location_key_of(conflict: dict) -> str:
    """Clé d'un lieu : son adresse normalisée, sinon ses coordonnées."""

    adresse = (conflict.get("adresse") or "").strip().lower()

    return adresse or f"{conflict.get('latitude')}:{conflict.get('longitude')}"


def conflict_still_active(conflict) -> tuple[bool, str]:
    """Dit si la cause d'une entrée d'historique tient encore, et laquelle."""

    from .models import ConflictType

    reservation = conflict.reservation

    if reservation is None:
        return False, ""

    if conflict.conflict_type == ConflictType.STOCK:
        for detail in detect_reservation_conflicts(reservation)["conflicts"]:
            if conflict.part_id and detail["part_id"] != conflict.part_id:
                continue

            return True, (
                f"il manque {detail['missing_quantity']} × {detail['part_name']}"
            )

        return False, ""

    for detail in detect_location_reservation_conflicts(reservation)["conflicts"]:
        if conflict.location_key and location_key_of(detail) != conflict.location_key:
            continue

        return True, f"{detail['numero']} occupe déjà {detail['lieu_nom']}"

    return False, ""


def register_location_conflict_history(reservation, conflict_result: dict) -> None:
    """Enregistre les conflits de lieu détectés dans l'historique."""

    from .models import ConflictHistory, ConflictState, ConflictType

    if not conflict_result.get("has_conflict"):
        return

    for conflict in conflict_result.get("conflicts", []):
        location_key = location_key_of(conflict)

        # Même raison qu'au-dessus : clés étrangères par `_id`, pas par instance.
        ConflictHistory.objects.get_or_create(
            conflict_type=ConflictType.LOCATION,
            state=ConflictState.OPEN,
            reservation_id=reservation.pk,
            conflicting_reservation_id=conflict.get("reservation_id"),
            period_start=reservation.date_retrait_prevue,
            period_end=reservation.date_retour_prevue,
            location_key=location_key,
            defaults={
                "details": {
                    "prestation_nom": conflict.get("prestation_nom"),
                    "lieu_nom": conflict.get("lieu_nom"),
                    "adresse": conflict.get("adresse"),
                    "latitude": str(conflict.get("latitude") or ""),
                    "longitude": str(conflict.get("longitude") or ""),
                }
            },
        )


def count_current_conflicts() -> int:
    """Nombre de groupes de conflit actuels (cf. ``list_current_conflicts``)."""

    return len(list_current_conflicts())
