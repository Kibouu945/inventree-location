# Modèle de données & règles métier

Générateur du document remis au client et au jury : le schéma du modèle cible,
les 45 règles métier avec leur source, les écarts assumés par rapport au schéma
soumis, le plan de mise en œuvre, et l'écart entre les maquettes du cahier des
charges et l'existant.

## Régénérer

```bash
cd docs/modele
python3 schema.py      # → schema.svg  : le diagramme
python3 document.py    # → modele.html : le document complet

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$HOME/Downloads/InvenTree-Location_Modele-de-donnees.pdf" \
  modele.html
```

Chrome sert d'imprimante : il rend le SVG et les sauts de page CSS correctement.
WeasyPrint, utilisé par le plugin pour le rapport de retour, demande des
bibliothèques natives absentes hors conteneur.

`schema.svg` et `modele.html` sont des sorties : elles ne sont pas versionnées.

## Où modifier quoi

| Fichier | Contenu |
|---|---|
| `schema.py` | `BOXES` : entités, champs, position et couleur. `LINKS` : relations et cardinalités. |
| `document.py` | `R` : les règles par section. `C` : les écarts au schéma soumis. `LIVRE` / `RESTE` / `GELE` : le plan. `M` : les maquettes. |

Une règle qui change se corrige à un endroit, et on relance les deux scripts.
Penser à incrémenter le numéro de révision dans l'en-tête de `document.py` : la
révision 2 corrigeait trois règles fausses de la révision 1, et le document dit
lesquelles.

## Sources

- point de revue client du 09/09/2026 ;
- cahier des charges V06 — le texte **et** les annexes graphiques. Le document
  est un `.docx` : ses quatre maquettes et son schéma simplifié sont des images,
  invisibles à une extraction de texte. Elles se sortent avec
  `zipfile` depuis `word/media/`, et l'ordre d'apparition se retrouve dans
  `word/document.xml` ;
- le code existant.
