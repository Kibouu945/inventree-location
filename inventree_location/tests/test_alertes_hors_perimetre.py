"""Les articles qu'on ne surveille pas doivent être annoncés (recette du 7/09)."""

from __future__ import annotations

from inventree_location.alertes import articles_hors_perimetre


def _article(part_id: int, nom: str, minimum=5) -> dict:
    return {"part_id": part_id, "part_name": nom, "minimum_stock": minimum}


def test_signale_un_article_sans_fiche_location():
    """Le cas du client : une trousse de secours à surveiller, mais non louable."""

    resultat = articles_hors_perimetre([_article(1, "Trousse de secours")], set())

    assert resultat["count"] == 1
    assert resultat["articles"][0]["part_name"] == "Trousse de secours"


def test_ignore_un_article_deja_surveille():
    resultat = articles_hors_perimetre([_article(1, "Chapiteau")], {1})

    assert resultat == {"count": 0, "articles": []}


def test_ignore_un_article_sans_stock_minimum():
    """Sans seuil, personne n'attend d'alerte : le signaler serait du bruit."""

    for minimum in (0, None):
        resultat = articles_hors_perimetre([_article(1, "Banc", minimum)], set())
        assert resultat["count"] == 0


def test_range_par_nom():
    articles = [_article(1, "Zèbre"), _article(2, "abri"), _article(3, "Malle")]

    noms = [a["part_name"] for a in articles_hors_perimetre(articles, set())["articles"]]

    assert noms == ["abri", "Malle", "Zèbre"]


def test_compte_tout_mais_ne_cite_que_les_premiers():
    """Une base entière sans fiche ne doit pas gonfler la réponse."""

    articles = [_article(i, f"Article {i:02}") for i in range(30)]

    resultat = articles_hors_perimetre(articles, set(), cites_au_plus=3)

    assert resultat["count"] == 30
    assert len(resultat["articles"]) == 3
    assert resultat["articles"][0]["part_name"] == "Article 00"


def test_sans_article_la_reponse_reste_lisible():
    assert articles_hors_perimetre([], set()) == {"count": 0, "articles": []}
