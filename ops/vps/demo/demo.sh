#!/bin/bash
# Instance démo « Vieilles Charrues » — https://demo.inventree-location.duckdns.org
#
#   demo.sh prete    tout, d'un coup : swap, code à jour, démarrage, purge
#   demo.sh up       démarre la base et le serveur, republie le static
#   demo.sh seed     première fois : réglages du plugin, instantané vide, festival
#   demo.sh purge    retour à l'instantané vide, festival ressemé à la date du jour
#   demo.sh down     arrête tout (les volumes restent)
#   demo.sh statut   conteneurs et mémoire
#
# Depuis le portable, `make demo-prete` lance `prete` détaché (le SSH coupe
# parfois) et attend la fin.
#
# L'instantané est pris AVANT le seed : la purge ressème, donc les concerts
# tombent toujours le jour même — la tournée du livreur n'affiche que lui.
set -euo pipefail

DIR=/data/inventree-demo
COMPOSE="docker compose -f $DIR/docker-compose.yml --env-file $DIR/.env"
MANAGE=/home/inventree/src/backend/InvenTree/manage.py
VIDE=$DIR/vide.dump
set -a; . "$DIR/.env"; set +a

django() { $COMPOSE exec -T demo-server python "$MANAGE" "$@"; }

attendre() {
    local i
    printf 'attente du serveur '
    for i in $(seq 1 90); do
        if $COMPOSE exec -T demo-server curl -sf -o /dev/null http://localhost:8000/api/ 2>/dev/null; then
            echo " prêt après $((i * 5))s"
            return 0
        fi
        printf '.'
        sleep 5
    done
    echo
    echo "ABANDON : le serveur démo ne répond pas après 450s"
    $COMPOSE logs --tail 40 demo-server
    return 1
}

# DEBUG=False : Caddy sert le static depuis le volume, il faut l'y recopier.
publier_static() {
    django collectstatic --noinput 2>&1 | tail -1
    $COMPOSE exec -T demo-server python "$MANAGE" shell \
        < "$DIR/plugin/docker/copier_static_plugin.py" 2>&1 | tail -1
}

semer() {
    $COMPOSE exec -T -e CHARRUES_MOT_DE_PASSE demo-server python "$MANAGE" seed_charrues 2>&1 | tail -8
    django provision_role_permissions 2>&1 | tail -1
    django renommer_liste_materiaux 2>&1 | tail -1
    django provision_dashboards 2>&1 | tail -1
}

case "${1:-}" in
    prete)
        # Le swap est hors fstab : un redémarrage du serveur l'a peut-être retiré.
        swapon --show=NAME --noheadings | grep -q /data/swapfile || swapon /data/swapfile
        git -C "$DIR/plugin" fetch -q origin
        if [ "$(git -C "$DIR/plugin" rev-parse HEAD)" != "$(git -C "$DIR/plugin" rev-parse '@{u}')" ]; then
            git -C "$DIR/plugin" pull -q --ff-only
            docker run --rm -v "$DIR/plugin":/app -w /app/frontend node:20-alpine \
                sh -c "npm ci --no-audit --no-fund >/dev/null && npm run build >/dev/null"
            echo "code mis à jour : $(git -C "$DIR/plugin" log -1 --format='%h %s')"
        fi
        "$0" up
        "$0" purge
        CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 https://demo.inventree-location.duckdns.org/web/)
        [ "$CODE" = "200" ] || { echo "ABANDON : la démo répond $CODE en HTTPS"; exit 1; }
        echo "DÉMO PRÊTE"
        ;;
    up)
        $COMPOSE up -d
        attendre
        publier_static
        ;;
    seed)
        [ ! -s "$VIDE" ] || { echo "ABANDON : déjà semée, utiliser « demo.sh purge »"; exit 1; }
        $COMPOSE exec -T demo-server python "$MANAGE" shell \
            < "$DIR/plugin/docker/provision_plugin_settings.py" 2>&1 | tail -2
        $COMPOSE restart demo-server
        attendre
        publier_static
        $COMPOSE exec -T demo-db pg_dump -U "$INVENTREE_DB_USER" -d "$INVENTREE_DB_NAME" -Fc > "$VIDE"
        chmod 600 "$VIDE"
        echo "instantané vide : $VIDE"
        semer
        ;;
    purge)
        [ -s "$VIDE" ] || { echo "ABANDON : pas d'instantané, lancer « demo.sh seed »"; exit 1; }
        $COMPOSE stop demo-server
        $COMPOSE exec -T demo-db pg_restore -U "$INVENTREE_DB_USER" -d "$INVENTREE_DB_NAME" \
            --clean --if-exists --no-owner < "$VIDE" 2>&1 | grep -v "^pg_restore: warning" || true
        $COMPOSE start demo-server
        attendre
        semer
        echo "démo remise à zéro, festival ressemé à la date du jour"
        ;;
    down)
        $COMPOSE stop
        ;;
    statut)
        $COMPOSE ps --format 'table {{.Name}}\t{{.Status}}'
        docker stats --no-stream --format '{{.Name}}  {{.MemUsage}}' | grep inventree-demo || true
        free -m | sed -n 1,3p
        ;;
    *)
        sed -n 2,13p "$0"
        exit 1
        ;;
esac
