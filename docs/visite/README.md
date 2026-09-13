# Visite guidée du code

Support de préparation à la revue d'encadrement, pour quelqu'un qui ne pratique
pas Django au quotidien et devra défendre ce dépôt. Cinq étapes : la carte, le
modèle et les migrations, le sérialiseur, la vue et les permissions, l'ORM, les
tests.

```bash
python3 guide.py
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --no-pdf-header-footer \
  --print-to-pdf="$HOME/Downloads/InvenTree-Location_Visite-guidee-du-code.pdf" \
  visite.html
```

`visite.html` est une sortie intermédiaire, ignorée par git. Le contenu vit
dans `guide.py`, une entrée de `ETAPES` par étape : ajouter une séance, c'est
ajouter un dictionnaire et régénérer.

Les blocs disponibles : `titre`, `prose`, `table`, `code`, `note`, `qr`
(question de jury et sa réponse), `exo` (ce que le lecteur fait lui-même).
