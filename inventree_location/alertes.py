"""Ce que l'écran d'alertes ne surveille pas, et qu'il doit dire.

Recette du 7 septembre, point « Stock » : un article à 1 en stock pour un
minimum de 5 n'apparaissait pas dans les alertes. La cause n'était pas le
calcul du seuil — qui reprend bien le `minimum_stock` d'InvenTree — mais le
périmètre : seuls les articles dotés d'une fiche location sont surveillés.

Garder ce périmètre est un choix assumé — le module s'occupe du parc louable.
Ce qui a trompé le client, c'est le silence : un « Aucune alerte » vert lui
affirmait que tout allait bien, alors qu'un article n'était pas regardé.
"""

from __future__ import annotations

#: Au-delà, on ne cite plus : le compte suffit à donner l'alerte.
CITES_AU_PLUS = 10


def articles_hors_perimetre(
    articles: list[dict],
    suivis: set[int],
    cites_au_plus: int = CITES_AU_PLUS,
) -> dict:
    """Articles portant un stock minimum mais dépourvus de fiche location.

    `articles` porte des dictionnaires `{part_id, part_name, minimum_stock}` ;
    `suivis` les identifiants déjà surveillés. Le résultat donne le compte
    total et les premiers noms, rangés par nom pour une lecture stable.
    """

    oublies = [
        article
        for article in articles
        if article["part_id"] not in suivis and (article.get("minimum_stock") or 0) > 0
    ]

    oublies.sort(key=lambda article: str(article["part_name"]).lower())

    return {
        "count": len(oublies),
        "articles": oublies[:cites_au_plus],
    }
