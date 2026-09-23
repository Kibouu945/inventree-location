"""STK-01 — Calcul du stock disponible au jour entier.

Le stock est unique et partagé entre toutes les manifestations et tous les
organisateurs. La disponibilité se calcule au **jour** : on arrondit la période
de la prestation au jour entier (conforme CDC « jour entier, quelle que soit la
plage horaire »). Les heures ne servent qu'à la logistique livraison/ramassage.

Pour un article donné :

    disponible = stock total louable − quantités déjà engagées

où « déjà engagées » couvre les **deux** façons dont le matériel est retenu sur
une période : le prévisionnel porté par les lignes de prestation (RES-09) et le
réalisé porté par les lignes des réservations bloquantes (CON-04). Voir
`compute_engaged_quantities` pour la règle de réconciliation entre les deux.
Les articles virtuels (services, ex. « nettoyage ») n'ont pas de stock physique
et sont ignorés.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import NamedTuple

from django.utils import timezone

from .conflicts import CONFLICT_STATUSES, get_parts_total_stock


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
#:
#: Le chevauchement fait foi **au jour entier** (`day_ranges_overlap`) : le
#: 2 juin à 18 h chevauche le 2 juin à 9 h, alors que le premier horodatage est
#: postérieur au second. Un filtre SQL posé tel quel sur les horodatages serait
#: donc plus strict que la règle et écarterait des lignes légitimes.
#:
#: On élargit les bornes d'un jour de chaque côté : le SQL dégrossit, Python
#: tranche. Aucun décalage de fuseau n'atteint vingt-quatre heures, si bien
#: qu'une ligne écartée par ce filtre ne pouvait pas chevaucher la période.
MARGE_FENETRE = timedelta(days=1)


class LigneDEngagement(NamedTuple):
    """Une quantité retenue sur une période, prévisionnelle ou réservée.

    Les deux tables qui décrivent le besoin matériel — `LignePrestation` pour
    le prévisionnel, `LigneReservation` pour le réalisé — se ramènent à cette
    forme commune. `reservation_id` vaut None pour le prévisionnel : c'est ce
    qui distingue les deux origines lors de la réconciliation.
    """

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
    """Charge en deux requêtes tout ce qui engage ces articles sur la période.

    Le filtre de période appartient au SQL : sans lui, chaque appel relisait
    *toutes* les lignes portant l'article, quelle que soit leur date, et le
    chevauchement était vérifié en Python ligne par ligne. Sur une base d'une
    année, cela faisait plusieurs centaines de lignes relues par appel.

    Aucune exclusion n'est appliquée ici : elles dépendent de la fenêtre
    interrogée, et le même chargement sert à en interroger plusieurs.
    """

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
    """Réconcilie prévisionnel et réalisé sur une fenêtre, sans toucher la base.

    C'est ici que vit la règle : **par prestation et par article**, on retient
    le plus grand du prévisionnel et du réservé. Les sommer double-compterait
    la réservation qui matérialise le prévisionnel de sa propre prestation ;
    n'en lire qu'un seul rendait invisible la moitié des engagements.

    Séparer cette réduction du chargement permet d'interroger plusieurs
    fenêtres sur un même chargement — ce dont le widget de conflits a besoin,
    puisque chaque réservation a la sienne.
    """

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
    """Détail, par article, des prestations qui l'engagent sur la période.

    Même règle de réconciliation que `compute_engaged_quantities` (dont c'est
    la version détaillée), mais on garde de quoi nommer le responsable d'une
    pénurie : sans cela, un conflit causé par le seul prévisionnel d'une
    prestation ne désignait rien à l'utilisateur.

    Deux tables décrivent le même besoin matériel :

    - `LignePrestation` — le **prévisionnel** : ce dont la prestation a besoin
      (RES-09) ;
    - `LigneReservation` — le **réalisé** : ce que les réservations au statut
      bloquant (cf. `CONFLICT_STATUSES`) retiennent effectivement.

    Les sommer double-compterait la réservation qui matérialise le
    prévisionnel de sa propre prestation ; n'en lire qu'une seule rendait
    invisible la moitié des engagements — c'est ce qui faussait la répartition
    d'un même article entre plusieurs réservations. On retient donc, **par
    prestation et par article**, le plus grand des deux : le prévisionnel tient
    lieu de réservation tant qu'aucune n'est posée, et s'efface dès que les
    réservations le dépassent.

    Exclusions :

    - `exclude_prestation_id` : ignore tout ce qui appartient à cette
      prestation (ses lignes **et** ses réservations) — une prestation ne se
      concurrence pas elle-même.
    - `exclude_reservation_id` : ignore cette réservation, ainsi que le
      prévisionnel de sa prestation dont elle est justement la
      matérialisation. Les **autres** réservations de la même prestation
      restent comptées.

    Retourne ``{part_id: [{"prestation_id", "prestation_nom", "quantite",
    "origine", "reservation_numeros"}]}`` où ``origine`` vaut ``"prevision"``
    ou ``"reservations"`` selon celle des deux qui l'emporte.
    """

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
    """Quantités déjà engagées par article sur la période, au jour entier.

    Vue agrégée de `compute_engagement_details`, dont la docstring porte la
    règle de réconciliation prévisionnel / réalisé et le sens des exclusions.
    """

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
    """Disponibilité au jour de chaque article demandé.

    `requested_lines` est un itérable de dicts ``{"part_id", "quantite"}``.
    Retourne ``{"has_shortage": bool, "lines": [...]}`` : une ligne par article
    non-virtuel avec stock total, quantité déjà engagée, disponible, manquant et
    drapeau de pénurie.
    """

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

    # Le stock de tous les articles en une requête. Lu article par article, il
    # coûtait ici un agrégat par ligne demandée — le catalogue et le sélecteur
    # de matériel passent par là aussi.
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
    """Disponibilité au jour d'un ensemble de parts, hors prestation existante.

    Sert au catalogue (CAT-02) et au sélecteur de matériel d'une réservation :
    on veut « combien de X reste-t-il de disponible pour telle période ? »
    sans avoir à demander une quantité précise au préalable.

    Sans période fournie, on utilise la journée courante **du fuseau métier**
    (`timezone.localdate()`, cf. INVENTREE_TIMEZONE) : `date.today()` suivait
    le fuseau du processus, si bien qu'entre minuit UTC et minuit local la
    disponibilité « du jour » portait sur la veille ou le lendemain. Les
    articles virtuels (pas de stock physique) sont absents du résultat —
    l'appelant doit les traiter à part.

    `exclude_reservation_id` sert à l'édition d'une réservation existante :
    sans lui, ses propres quantités se compteraient contre elle.
    """

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
