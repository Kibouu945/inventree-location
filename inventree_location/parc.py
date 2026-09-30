"""État du parc, pour le poste magasinier.

Le catalogue dit ce que l'on possède ; il ne dit ni ce qui est dehors, ni quand
ça revient, ni ce qui dort au SAV. Le magasinier avait donc trois écrans à
recouper pour savoir sur quoi il pouvait compter.

Chaque grandeur se charge en **une** requête groupée par article. Appelées
article par article, elles rejoueraient le défaut corrigé le 23/09 sur les
alertes de stock, où trois lectures unitaires faisaient cent requêtes pour
cinquante articles.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional

from django.db.models import Case, F, Min, Sum, When

from .models import (
    LigneReservation,
    SavTicket,
    StatutReservation,
    StatutSavTicket,
)

#: Un bon livré et pas encore rentré : c'est cela, « dehors ».
STATUTS_DEHORS = (StatutReservation.LIVREE,)

#: Un ticket qui immobilise encore l'article.
STATUTS_SAV_OUVERTS = (StatutSavTicket.OUVERT, StatutSavTicket.EN_REPARATION)


def charger_sorties(part_ids: Iterable[int]) -> dict[int, dict]:
    """Quantité dehors et prochain retour attendu, par article, en une requête."""

    part_ids = list(part_ids)

    if not part_ids:
        return {}

    lignes = (
        LigneReservation.objects.filter(
            part_id__in=part_ids,
            reservation__statut__in=STATUTS_DEHORS,
            reservation__date_retour_reelle__isnull=True,
        )
        .values("part_id")
        .annotate(
            # Ce qui a été remis en main propre s'il a été compté, et à défaut
            # ce qui était demandé : un bon marqué livré dont la ligne porte
            # zéro n'est pas une livraison vide, c'est un comptage non saisi.
            sorti=Sum(
                Case(
                    When(quantite_livree__gt=0, then=F("quantite_livree")),
                    default=F("quantite_demandee"),
                )
                - F("quantite_retournee")
            ),
            retour_prevu=Min("reservation__date_retour_prevue"),
        )
    )

    return {
        ligne["part_id"]: {
            "sorti": max(ligne["sorti"] or 0, 0),
            "retour_prevu": ligne["retour_prevu"],
        }
        for ligne in lignes
    }


def charger_sav(part_ids: Iterable[int]) -> dict[int, int]:
    """Quantité immobilisée par un ticket SAV ouvert, par article."""

    part_ids = list(part_ids)

    if not part_ids:
        return {}

    tickets = (
        SavTicket.objects.filter(part_id__in=part_ids, statut__in=STATUTS_SAV_OUVERTS)
        .values("part_id")
        .annotate(quantite=Sum("quantite"))
    )

    return {t["part_id"]: t["quantite"] or 0 for t in tickets}


def _jour(valeur) -> Optional[str]:
    """Date ISO d'un horodatage, ou None. Le magasinier raisonne au jour."""

    if valeur is None:
        return None

    if isinstance(valeur, datetime):
        return valeur.date().isoformat()

    if isinstance(valeur, date):
        return valeur.isoformat()

    return str(valeur)


def motifs_alerte(parc: int, sorti: int, seuil_bas: Optional[int]) -> list[str]:
    """Pourquoi cette ligne mérite l'œil du magasinier. Vide si tout va bien.

    Deux situations, qui ne se confondent pas : le parc est tombé sous le seuil
    que l'on s'est fixé, ou bien il est sorti plus d'unités qu'on n'en possède —
    ce qui signale une réservation forcée, ou du matériel jamais rentré.
    """

    motifs = []

    if seuil_bas is not None and parc < seuil_bas:
        motifs.append("sous_seuil")

    if sorti > parc:
        motifs.append("sorti_au_dela_du_parc")

    return motifs


def construire_ligne(
    part,
    *,
    parc: int,
    sortie: Optional[dict],
    sav: int,
    rentable=None,
) -> dict:
    """Une ligne de l'état du parc, prête à sérialiser."""

    sorti = (sortie or {}).get("sorti", 0)
    seuil_bas = getattr(rentable, "seuil_alerte_bas", None) if rentable else None

    return {
        "part_id": part.pk,
        "part_name": getattr(part, "name", str(part)),
        "categorie": getattr(getattr(part, "category", None), "name", "") or "",
        "parc": parc,
        "sorti": sorti,
        # Ce sur quoi le magasinier peut compter aujourd'hui, sans présumer
        # des réservations futures : c'est l'histogramme qui les projette.
        "disponible": max(parc - sorti, 0),
        "retour_prevu": _jour((sortie or {}).get("retour_prevu")),
        "sav": sav,
        "seuil_alerte_bas": seuil_bas,
        "consommable": bool(getattr(rentable, "consommable", False)),
        "motifs_alerte": motifs_alerte(parc, sorti, seuil_bas),
    }


def construire_lignes(parts, stocks: dict[int, int]) -> list[dict]:
    """L'état du parc pour un lot d'articles, en trois requêtes groupées."""

    parts = list(parts)
    ids = [part.pk for part in parts]
    sorties = charger_sorties(ids)
    sav = charger_sav(ids)

    return [
        construire_ligne(
            part,
            parc=stocks.get(part.pk, 0),
            sortie=sorties.get(part.pk),
            sav=sav.get(part.pk, 0),
            rentable=getattr(part, "rentable_info", None),
        )
        for part in parts
    ]
