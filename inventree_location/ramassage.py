"""Périmètre d'un ramassage : ce qu'on récupère physiquement."""

from __future__ import annotations


def lignes_a_ramasser(reservation):
    """Lignes d'une réservation qui reviennent physiquement à l'entrepôt."""

    lignes = []

    for ligne in reservation.lignes.all():
        # Reverse OneToOne : `RelatedObjectDoesNotExist` hérite
        # d'AttributeError, donc le défaut de `getattr` s'applique quand la
        rentable = getattr(ligne.part, "rentable_info", None)

        if rentable is not None and rentable.is_virtual:
            continue

        lignes.append(ligne)

    return lignes
