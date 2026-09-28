"""Retouches du catalogue de traduction français d'InvenTree.

Recette du 27/09, point 4.3.1 : « la traduction "Liste des matériaux" est
inappropriée, on pourrait mettre "Liste des éléments" ». La chaîne appartient au
frontend natif d'InvenTree, compilé par Lingui : ni notre plugin ni
`LOCALE_PATHS` ne l'atteignent. On réécrit donc le catalogue livré.
"""

from __future__ import annotations

from pathlib import Path

#: Chaînes qu'on ne réécrit jamais, et qui n'existent que dans le catalogue
#: français : elles servent à le reconnaître. Le reconnaître par les libellés à
#: remplacer ne marcherait pas — une fois renommés ils ont disparu, et les
#: chaînes anglaises non traduites se retrouvent dans TOUS les catalogues de
#: langue, ce qui reviendrait à traduire l'allemand en français.
MARQUEURS_FRANCAIS: tuple[str, ...] = (
    "Ordres de fabrication",
    "Se désabonner des notifications",
)

#: Libellé d'origine -> libellé voulu par le client. Le remplacement est litéral
#: et porte sur le catalogue français seul.
LIBELLES: dict[str, str] = {
    "Liste des matériaux": "Liste des éléments",
    "Listes de matériaux invalides": "Listes d'éléments invalides",
    "Validation des listes de matériaux requises pour les assemblages": (
        "Validation des listes d'éléments requises pour les assemblages"
    ),
    "La liste des matériaux ne peut être modifiée, car la pièce est bloquée": (
        "La liste des éléments ne peut être modifiée, car la pièce est bloquée"
    ),
    # Recette du 7 septembre, « Module BOM » : ces chaînes-là ne sont traduites
    # dans aucune langue chez InvenTree, le client lisait donc de l'anglais.
    "Select an assembly to view Bill of Materials comparison": (
        "Choisir un assemblage pour comparer les listes d'éléments"
    ),
    "The Bill of Materials for this assembly has not been validated.": (
        "La liste des éléments de cet assemblage n'a pas été validée."
    ),
    "Compare Bill of Materials": "Comparer les listes d'éléments",
    "Bill of Materials": "Liste des éléments",
    # InvenTree dit « nomenclature » — le mot juste, mais le client a demandé
    # « éléments ». On n'aligne que le titre de l'alerte de l'onglet, pour ne
    # pas laisser deux mots pour la même chose sur un même écran ; les 24
    # autres occurrences de « nomenclature » restent telles quelles.
    "Nomenclature non validée": "Liste des éléments non validée",
}


def remplacer_libelles(contenu: str) -> tuple[str, int]:
    """Réécrit les libellés dans un catalogue, et dit combien ont été touchés.

    Les phrases longues passent avant les courtes : sans cela « Liste des
    matériaux » consommerait le début de « Listes de matériaux invalides ».
    """

    remplacements = 0

    for avant in sorted(LIBELLES, key=len, reverse=True):
        apres = LIBELLES[avant]
        nombre = contenu.count(avant)

        if nombre:
            contenu = contenu.replace(avant, apres)
            remplacements += nombre

    return contenu, remplacements


def catalogues_francais(racines: list[Path]) -> list[Path]:
    """Catalogues Lingui contenant du français, sous les racines données.

    Le nom du fichier porte un hachage de contenu et ne dit pas sa langue : on
    le reconnaît à des chaînes françaises stables, jamais réécrites.
    """

    trouves: list[Path] = []

    for racine in racines:
        if not racine.is_dir():
            continue

        for fichier in sorted(racine.rglob("messages-*.js")):
            try:
                contenu = fichier.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            if any(marqueur in contenu for marqueur in MARQUEURS_FRANCAIS):
                trouves.append(fichier)

    return trouves
