"""Périmètre d'un ramassage : ce qu'on récupère physiquement.

Module à part, et volontairement sans dépendance : `serializers` et `sav` en ont
tous deux besoin, et `serializers` importe déjà `sav` — le poser dans l'un des
deux créait un cycle d'imports.
"""

from __future__ import annotations


def lignes_a_ramasser(reservation):
    """Lignes d'une réservation qui reviennent physiquement à l'entrepôt.

    Un article virtuel — « nettoyage du lieu », « prestation montage » — n'a
    aucune existence physique : il n'y a rien à faire revenir. Le laisser dans
    le bon obligeait le livreur à pointer un service, et dans la saisie retour
    à ventiler des quantités « au SAV » ou « détruites » sur une prestation.
    Même raison que le `filter(is_virtual=False)` des alertes de stock.

    Les consommables restent listés, à l'inverse de ce que demande le CDC V06
    (« un consommable n'entre pas dans les listes de ramassage ») : leur
    décrément définitif, prévu par CONSO-01, n'est pas implémenté, et la colonne
    « manquante » de cette saisie est aujourd'hui le seul levier qui les sort du
    stock réellement disponible. Les filtrer ici avant CONSO-01 les rendrait
    éternellement « possédés ». À faire une fois le décrément livré.

    L'appelant doit précharger `lignes__part__rentable_info`, sinon c'est une
    requête par ligne.
    """

    lignes = []

    for ligne in reservation.lignes.all():
        # Reverse OneToOne : `RelatedObjectDoesNotExist` hérite d'AttributeError,
        # donc le défaut de `getattr` s'applique quand la Part n'a pas
        # d'extension louable.
        rentable = getattr(ligne.part, "rentable_info", None)

        if rentable is not None and rentable.is_virtual:
            continue

        lignes.append(ligne)

    return lignes
