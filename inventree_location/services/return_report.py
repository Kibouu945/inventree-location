"""Return report data builder."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.utils import timezone

from ..models import Reservation, ReturnIncidentType


def build_return_report(reservation_id: int) -> dict:
    """Build a return report summary for a reservation."""
    reservation = (
        Reservation.objects.select_related("prestation__manifestation", "demandeur")
        .prefetch_related("lignes__part", "lignes__incidents")
        .filter(pk=reservation_id)
        .first()
    )

    if reservation is None:
        raise ValueError(f"Reservation {reservation_id} not found")

    lines = []
    totals = {kind.value: 0 for kind in ReturnIncidentType}
    totals["returned"] = 0
    total_extra = Decimal("0.00")

    for line in reservation.lignes.all():
        incidents = list(line.incidents.all())
        per_type = defaultdict(int)
        for incident in incidents:
            per_type[incident.type] += incident.qty

        returned_qty = line.quantite_retournee
        missing_qty = per_type.get(ReturnIncidentType.MISSING.value, 0)
        broken_qty = per_type.get(ReturnIncidentType.BROKEN.value, 0)
        destroyed_qty = per_type.get(ReturnIncidentType.DESTROYED.value, 0)

        extra_cost = Decimal("0.00")
        rentable = getattr(line.part, "rentable_info", None)
        replacement_value = getattr(rentable, "valeur_remplacement", None)
        caution = getattr(rentable, "caution", None)

        if missing_qty and replacement_value is not None:
            extra_cost += Decimal(str(replacement_value)) * missing_qty
        if broken_qty and replacement_value is not None:
            extra_cost += Decimal(str(replacement_value)) * broken_qty
        if destroyed_qty and caution is not None:
            extra_cost += Decimal(str(caution)) * destroyed_qty

        totals["returned"] += returned_qty
        totals[ReturnIncidentType.MISSING.value] += missing_qty
        totals[ReturnIncidentType.BROKEN.value] += broken_qty
        totals[ReturnIncidentType.DESTROYED.value] += destroyed_qty
        total_extra += extra_cost

        lines.append({
            "part_id": line.part_id,
            "part_name": line.part.name,
            "quantity_delivered": line.quantite_livree,
            "quantity_returned": returned_qty,
            "missing": missing_qty,
            "broken": broken_qty,
            "destroyed": destroyed_qty,
            "comment": line.commentaire,
            "extra_cost": extra_cost,
        })

    demandeur = f"{reservation.demandeur.first_name} {reservation.demandeur.last_name}".strip()
    if not demandeur:
        demandeur = reservation.demandeur.username

    return {
        "reservation_id": reservation.pk,
        "reservation_numero": reservation.numero,
        "prestation_name": reservation.prestation.nom,
        "prestation_id": reservation.prestation_id,
        "manifestation_name": reservation.prestation.manifestation.nom,
        "demandeur": demandeur,
        "generated_at": timezone.now().isoformat(),
        "lines": lines,
        "totals": totals,
        "total_extra": total_extra,
    }