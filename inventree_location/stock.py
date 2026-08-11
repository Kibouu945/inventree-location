"""STK-01 — Calcul du stock disponible au jour entier.

Le stock est unique et partagé entre toutes les manifestations et tous les
organisateurs. La disponibilité se calcule au **jour** : on arrondit la période
de la prestation au jour entier (conforme CDC « jour entier, quelle que soit la
plage horaire »). Les heures ne servent qu'à la logistique livraison/ramassage.

Pour un article donné :

    disponible = stock total louable − quantités déjà engagées

où « déjà engagées » est la somme des quantités des lignes d'**autres**
prestations dont la plage `[date_debut, date_fin]` (ramenée au jour) chevauche
celle examinée. Les articles virtuels (services, ex. « nettoyage ») n'ont pas de
stock physique et sont ignorés.
"""

from __future__ import annotations

from datetime import date, datetime

from .conflicts import get_part_total_stock


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


def compute_stock_availability(
    date_debut,
    date_fin,
    requested_lines,
    exclude_prestation_id=None,
) -> dict:
    """Disponibilité au jour de chaque article demandé.

    `requested_lines` est un itérable de dicts ``{"part_id", "quantite"}``.
    Retourne ``{"has_shortage": bool, "lines": [...]}`` : une ligne par article
    non-virtuel avec stock total, quantité déjà engagée, disponible, manquant et
    drapeau de pénurie.
    """

    from part.models import Part

    from .models import LignePrestation, RentableItem

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

    # Une seule requête pour toutes les lignes concurrentes, regroupées ensuite.
    others = LignePrestation.objects.filter(part_id__in=part_ids).select_related(
        "prestation"
    )

    if exclude_prestation_id is not None:
        others = others.exclude(prestation_id=exclude_prestation_id)

    reserved_by_part: dict[int, int] = {}

    for ligne in others:
        prestation = ligne.prestation

        if day_ranges_overlap(
            date_debut, date_fin, prestation.date_debut, prestation.date_fin
        ):
            reserved_by_part[ligne.part_id] = (
                reserved_by_part.get(ligne.part_id, 0) + ligne.quantite
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
) -> dict[int, int]:
    """Disponibilité au jour d'un ensemble de parts, hors prestation existante.

    Sert au catalogue (CAT-02) et au sélecteur de matériel d'une réservation :
    on veut « combien de X reste-t-il de disponible pour telle période ? »
    sans avoir à demander une quantité précise au préalable.

    Sans période fournie, on utilise la journée courante (disponibilité
    « à l'instant »). Les articles virtuels (pas de stock physique) sont
    absents du résultat — l'appelant doit les traiter à part.
    """

    part_ids = [int(pid) for pid in part_ids]

    if not part_ids:
        return {}

    if date_debut is None or date_fin is None:
        today = date.today()
        date_debut = date_debut or today
        date_fin = date_fin or today

    requested_lines = [{"part_id": pid, "quantite": 0} for pid in part_ids]

    result = compute_stock_availability(
        date_debut,
        date_fin,
        requested_lines,
        exclude_prestation_id=exclude_prestation_id,
    )

    return {line["part_id"]: line["available"] for line in result["lines"]}


def compute_prestation_stock(prestation) -> dict:
    """Disponibilité au jour des articles d'une prestation enregistrée.

    S'exclut elle-même du calcul du « déjà engagé » (ses propres lignes ne
    doivent pas être comptées comme concurrentes).
    """

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
