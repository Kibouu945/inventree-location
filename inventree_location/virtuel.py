"""Filtre « Virtuel : oui / non » des prestations et des réservations.

Recette du 27/09, point 4.5.1 : « ne pas afficher les prestations et/ou les
réservations si elles ne contiennent que des articles virtuels ». Un article
virtuel est une prestation de service (nettoyage, gardiennage) : elle n'occupe
ni stock ni camion, et brouille la lecture quand on prépare le matériel.
"""

from __future__ import annotations

from django.db.models import Count, Q

#: Valeurs acceptées sur la query string ; tout le reste ne filtre pas.
OUI = "oui"
NON = "non"

#: Noms d'annotation, préfixés pour ne pas heurter ceux des vues.
_TOTAL = "_virtuel_lignes"
_MATERIELLES = "_virtuel_lignes_materielles"


def normaliser(valeur: str | None) -> str | None:
    """Rend `oui`, `non`, ou None quand le filtre ne s'applique pas."""

    if valeur is None:
        return None

    nettoye = str(valeur).strip().lower()

    if nettoye in {OUI, "1", "true", "yes"}:
        return OUI

    if nettoye in {NON, "0", "false", "no"}:
        return NON

    return None


def filtrer(queryset, valeur: str | None, *, lignes: str):
    """Applique le filtre à un queryset de prestations ou de réservations.

    `lignes` est le `related_name` des lignes portant les articles. On compte
    plutôt que de nier un `Q` : sur une relation multi-valuée, une négation
    porte sur la ligne jointe, pas sur la fiche entière.

    Les deux réponses se complètent : une fiche sans ligne reste visible côté
    « non », pour ne pas escamoter une saisie en cours.
    """

    demande = normaliser(valeur)

    if demande is None:
        return queryset

    # Un article sans fiche location n'a pas de drapeau : il compte comme
    # matériel, faute de quoi le filtre masquerait du vrai matériel.
    materiel = Q(**{f"{lignes}__part__rentable_info__is_virtual": False}) | Q(**{
        f"{lignes}__part__rentable_info__isnull": True
    })

    compte = queryset.annotate(**{
        _TOTAL: Count(lignes, distinct=True),
        _MATERIELLES: Count(lignes, filter=materiel, distinct=True),
    })

    if demande == OUI:
        return compte.filter(**{f"{_TOTAL}__gt": 0, _MATERIELLES: 0})

    return compte.filter(Q(**{_TOTAL: 0}) | Q(**{f"{_MATERIELLES}__gt": 0}))
