"""Détection des clients saisis deux fois sous un nom presque identique.

`Client.nom` est déjà unique : « Mairie de Vertou » ne peut pas exister en
double à l'identique. Le doublon réel est ailleurs — « Mairie de vertou »,
« MAIRIE DE VERTOU », « Mairie  de Vertou ». La base les accepte tous, et le
fichier client se dédouble sans que personne ne s'en aperçoive.

On compare donc des noms *normalisés* : casse, accents, ponctuation et espaces
superflus retirés. Deux noms qui se ramènent à la même forme désignent le même
client. Recette Tassin du 27/09, point 4.2.4.
"""

from __future__ import annotations

import re
import unicodedata

#: Tout ce qui n'est ni lettre ni chiffre sépare deux mots.
_SEPARATEURS = re.compile(r"[^0-9a-z]+")

#: Mots trop courants pour distinguer deux clients à eux seuls.
MOTS_VIDES = frozenset({
    "de",
    "du",
    "des",
    "la",
    "le",
    "les",
    "l",
    "d",
    "et",
    "a",
    "au",
    "aux",
    "en",
})


def normaliser_nom(nom: str) -> str:
    """Forme comparable d'un nom : sans casse, accents ni ponctuation."""

    sans_accent = unicodedata.normalize("NFKD", nom or "")
    sans_accent = "".join(c for c in sans_accent if not unicodedata.combining(c))

    return _SEPARATEURS.sub(" ", sans_accent.lower()).strip()


def mots_significatifs(nom: str) -> frozenset[str]:
    """Les mots qui portent le sens, articles écartés."""

    mots = {m for m in normaliser_nom(nom).split() if m not in MOTS_VIDES}

    # Un nom entièrement fait de mots vides se compare sur ses mots bruts,
    # sinon « Le Local » et « La Locale » n'auraient plus rien à comparer.
    return frozenset(mots or normaliser_nom(nom).split())


def se_ressemblent(gauche: str, droite: str) -> bool:
    """Vrai si les deux noms désignent vraisemblablement le même client."""

    a, b = normaliser_nom(gauche), normaliser_nom(droite)

    if not a or not b:
        return False

    if a == b:
        return True

    # « Mairie de Vertou » et « Mairie Vertou » : mêmes mots porteurs.
    return mots_significatifs(gauche) == mots_significatifs(droite)


def clients_proches(nom: str, existants) -> list:
    """Les clients déjà enregistrés dont le nom ressemble à celui-ci.

    `existants` est un itérable de `Client` — à l'appelant de l'avoir réduit
    aux clients pertinents.
    """

    return [client for client in existants if se_ressemblent(nom, client.nom)]
