"""Retouches du catalogue de traduction français d'InvenTree.

Recette du 27/09, point 4.3.1 : « la traduction "Liste des matériaux" est
inappropriée, on pourrait mettre "Liste des éléments" ». La chaîne appartient au
frontend natif d'InvenTree, compilé par Lingui : ni notre plugin ni
`LOCALE_PATHS` ne l'atteignent. On réécrit donc le catalogue livré.
"""

from __future__ import annotations

from pathlib import Path

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
    reconnaît le bon à un libellé qu'il est seul à contenir.
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

            if any(libelle in contenu for libelle in LIBELLES):
                trouves.append(fichier)

    return trouves
