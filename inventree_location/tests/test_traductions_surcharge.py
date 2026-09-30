"""Le catalogue de surcharge compilé suit-il sa source ?

Le `.mo` est versionné — le montage du plugin masque celui que l'image
construirait — donc rien n'empêche de retoucher le `.po` et d'oublier
`make traductions`. Ce test le rend impossible.
"""

from __future__ import annotations

import gettext
import re
from pathlib import Path

import pytest

CATALOGUE = (
    Path(__file__).resolve().parent.parent / "locale" / "fr" / "LC_MESSAGES"
)
SOURCE = CATALOGUE / "django.po"
COMPILE = CATALOGUE / "django.mo"


def _entrees_du_po(contenu: str) -> dict[str, str]:
    """Les couples msgid/msgstr d'un `.po` simple, en-tête exclu."""

    entrees: dict[str, str] = {}
    msgid: str | None = None

    for ligne in contenu.splitlines():
        ligne = ligne.strip()

        if depart := re.match(r'^msgid\s+"(.*)"$', ligne):
            msgid = depart.group(1)
        elif arrivee := re.match(r'^msgstr\s+"(.*)"$', ligne):
            if msgid:
                entrees[msgid] = arrivee.group(1)
            msgid = None

    return entrees


@pytest.fixture(scope="module")
def attendues() -> dict[str, str]:
    return _entrees_du_po(SOURCE.read_text(encoding="utf-8"))


def test_le_catalogue_compile_existe():
    assert COMPILE.is_file(), (
        f"{COMPILE} manquant : lancer `make traductions` après avoir touché au .po."
    )


def test_la_surcharge_porte_au_moins_une_correction(attendues):
    assert attendues, "Un catalogue de surcharge vide n'a aucune raison d'exister."


def test_le_compile_dit_la_meme_chose_que_la_source(attendues):
    """Sans quoi le `.po` relu en revue ne décrirait pas ce qui est livré."""

    with COMPILE.open("rb") as flux:
        traductions = gettext.GNUTranslations(flux)

    for msgid, msgstr in attendues.items():
        assert traductions.gettext(msgid) == msgstr, (
            f"« {msgid} » : le .mo rend « {traductions.gettext(msgid)} » alors "
            f"que le .po dit « {msgstr} ». Lancer `make traductions`."
        )


def test_la_correction_du_stock_est_la(attendues):
    """La chaîne qui a motivé le chantier, citée telle qu'InvenTree l'émet."""

    assert attendues.get("Stock transaction notes") == "Notes sur le mouvement de stock"
