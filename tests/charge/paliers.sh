#!/usr/bin/env bash
#
# Campagne de charge par paliers.
#
# Amène la base à des volumes croissants et mesure à chaque palier, d'abord le
# coût d'un appelant seul (le coût algorithmique), puis la tenue à plusieurs
# appelants (la capacité). Les deux, parce qu'un endpoint qui coûte deux
# secondes à un utilisateur seul ne tiendra jamais dix utilisateurs, et qu'un
# endpoint rapide peut malgré tout s'effondrer sur le nombre de connexions.
#
#   tests/charge/paliers.sh                      # 500 2000 5000 10000
#   PALIERS="1000 10000" CONCURRENCES="1 10" tests/charge/paliers.sh
#
# Les rapports bruts vont dans --sortie (défaut : tests/charge/resultats/).

set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SORTIE="${SORTIE:-$RACINE/tests/charge/resultats}"
PALIERS="${PALIERS:-500 2000 5000 10000}"
# `-` et non `:-` : CONCURRENCES="" doit vouloir dire « aucune », pas « le défaut ».
CONCURRENCES="${CONCURRENCES-1 5 10 25}"
DUREE="${DUREE:-20}"
TIMEOUT="${TIMEOUT:-60}"
URL="${URL:-http://localhost:8000}"
PYTHON="${PYTHON:-$RACINE/.venv/bin/python}"

mkdir -p "$SORTIE"

# Le jeu de charge se génère dans le conteneur : c'est là que l'app plugin est
# installée, et `manage.py` n'est pas à la racine du dépôt.
semer() {
  docker compose -f "$RACINE/docker-compose.yml" exec -T inventree \
    bash -lc "cd /home/inventree/src/backend/InvenTree && python manage.py seed_charge --total $1" \
    | grep -v '^20[0-9-]* .* INFO ' || true
}

for palier in $PALIERS; do
  echo
  echo "### palier $palier réservations ###############################################"
  semer "$palier"

  "$PYTHON" "$RACINE/tests/charge/bench.py" \
    --url "$URL" --sequentiel --repetitions 3 --timeout "$TIMEOUT" \
    --json "$SORTIE/cout-$palier.json"

  for concurrence in ${CONCURRENCES:-}; do
    "$PYTHON" "$RACINE/tests/charge/bench.py" \
      --url "$URL" --concurrence "$concurrence" --duree "$DUREE" \
      --timeout "$TIMEOUT" \
      --json "$SORTIE/capacite-$palier-c$concurrence.json"
  done
done

echo
echo "Rapports bruts dans $SORTIE"
echo "Synthèse : $PYTHON $RACINE/tests/charge/synthese.py $SORTIE"
