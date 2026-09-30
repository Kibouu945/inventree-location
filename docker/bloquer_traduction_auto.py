"""Empêche le navigateur de retraduire une interface déjà traduite.

InvenTree fige `<html lang="en">` dans son gabarit alors que l'interface est
servie en français : Chrome propose donc de traduire vers le français un texte
qui l'est déjà, et produit « Actions boursières » pour « Stock actions »,
« Économiser » pour « Save », « Annuleur » pour « Cancel ». Recette du 6 et du
7 septembre, points « Saisie des articles pour réservation » et « Traduction ».

Nos propres écrans s'en protègent déjà (`LocaleFrame` pose `lang`,
`translate="no"` et la classe `notranslate`), mais pas les écrans du cœur —
« Parties », « Ajouter du stock » — où le client a justement buté.

Le chemin du gabarit est en dur volontairement : si une version future
d'InvenTree le déplace, le build échoue ici, au lieu de livrer une prod où la
retouche est ignorée en silence.
"""

from pathlib import Path

GABARIT = Path("/home/inventree/src/backend/InvenTree/web/templates/web/index.html")
ANCRE = '<meta charset="UTF-8" />'
GARDE = '<meta name="google" content="notranslate" />'

contenu = GABARIT.read_text(encoding="utf-8")

if ANCRE not in contenu:
    raise SystemExit(
        f"Gabarit d'InvenTree modifié : « {ANCRE} » introuvable dans {GABARIT}."
    )

if GARDE in contenu:
    print("Traduction automatique déjà bloquée.")
else:
    GABARIT.write_text(contenu.replace(ANCRE, f"{ANCRE}\n  {GARDE}"), encoding="utf-8")
    print("Traduction automatique bloquée dans le gabarit d'InvenTree.")
