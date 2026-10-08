#!/bin/bash
# OPS-01 — sauvegarde quotidienne de la base, rotation sur 7 jours.
# Lancé par cron ; les dumps vivent sur /data, jamais sur le disque système.
set -euo pipefail

DIR=/data/inventree
DEST=/data/backups
KEEP=7

set -a
# shellcheck disable=SC1091
. "$DIR/.env"
set +a

mkdir -p "$DEST"
STAMP=$(date +%Y-%m-%d_%H%M)
FILE="$DEST/inventree-$STAMP.sql.gz"

# --clean : le dump se restaure sur une base déjà peuplée sans conflit.
# `exec -T` lit stdin : sans </dev/null il avale le reste du script appelant
# quand celui-ci est lui-même passé en entrée standard.
docker compose -f "$DIR/docker-compose.yml" exec -T db \
    pg_dump --clean --if-exists -U "$INVENTREE_DB_USER" "$INVENTREE_DB_NAME" \
    </dev/null | gzip >"$FILE.part"

# Renommage seulement en cas de succès : jamais de dump tronqué qui ferait
# croire à une sauvegarde valide.
mv "$FILE.part" "$FILE"
echo "$(date -Is)  ok  $FILE  $(du -h "$FILE" | cut -f1)"

# Rotation : on ne supprime que si le dump du jour existe.
find "$DEST" -name 'inventree-*.sql.gz' -mtime "+$KEEP" -delete
find "$DEST" -name '*.part' -mtime +1 -delete
