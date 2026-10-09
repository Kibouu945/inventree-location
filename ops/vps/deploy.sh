#!/bin/bash
# OPS-01 — déploiement de la prod par tag.
#
#   /data/inventree/deploy.sh            # livre le dernier tag poussé
#   /data/inventree/deploy.sh 0.1.0      # revient à une version précise
#   /data/inventree/deploy.sh --list     # montre les tags disponibles
#
# Poser une version depuis le poste de dev (tags en MAJEUR.MINEUR.CORRECTIF,
# sans préfixe « v », pour coller à PLUGIN_VERSION) :
#   git tag 0.2.0 && git push --tags
#
# Le bundle frontend n'est PAS versionné (.gitignore : inventree_location/static/),
# donc récupérer le code ne suffit pas : il faut reconstruire puis redémarrer.
#
# `set -e` est essentiel : `vite build --emptyOutDir` vide le dossier static
# avant d'écrire, donc un build cassé suivi d'un restart livrerait un site sans
# interface. On préfère laisser tourner l'ancienne version.
set -euo pipefail

DIR=/data/inventree
REPO=$DIR/plugin
COMPOSE="docker compose -f $DIR/docker-compose.yml"

# Attend que le serveur réponde. INDISPENSABLE avant tout restart : au premier
# démarrage, `init.sh` enchaîne migrations + collectstatic pendant plusieurs
# minutes, et le couper laisse une transaction avortée et un static vide.
wait_ready() {
    local label="$1" i
    printf 'attente (%s) ' "$label"
    for i in $(seq 1 90); do
        if $COMPOSE exec -T inventree curl -sf -o /dev/null http://localhost:8000/api/ 2>/dev/null; then
            echo " prêt après $((i * 5))s"
            return 0
        fi
        printf '.'
        sleep 5
    done
    echo
    echo "ABANDON : le serveur ne répond pas après 450s"
    $COMPOSE logs --tail 40 inventree
    return 1
}

echo "===== 1/4  sélection de la version ====="
# --force : si un tag a été déplacé côté GitHub, on prend la nouvelle cible.
git -C "$REPO" fetch --tags --prune --force --quiet origin

# Analyse des arguments. Le tag et --force peuvent venir dans n'importe quel
# ordre, et une option inconnue est refusée plutôt que prise pour un tag : un
# « deploy.sh --froce » silencieusement compris comme un nom de version livrerait
# n'importe quoi.
TAG=""
FORCE=false
LIST=false
for arg in "$@"; do
    case "$arg" in
        --list)  LIST=true ;;
        --force) FORCE=true ;;
        -*)      echo "ABANDON : option inconnue « $arg » (attendu : <tag>, --list, --force)"; exit 1 ;;
        *)
            [ -z "$TAG" ] || { echo "ABANDON : deux versions demandées, « $TAG » et « $arg »"; exit 1; }
            TAG="$arg"
            ;;
    esac
done

if [ "$LIST" = true ]; then
    echo "tags disponibles (du plus récent au plus ancien) :"
    git -C "$REPO" for-each-ref --sort=-creatordate --format='  %(refname:short)  %(creatordate:short)  %(contents:subject)' refs/tags
    exit 0
fi

if [ -z "$TAG" ]; then
    TAG=$(git -C "$REPO" for-each-ref --sort=-creatordate --format='%(refname:short)' refs/tags | head -1)
    [ -n "$TAG" ] || { echo "ABANDON : aucun tag dans le dépôt. Poser d'abord 'git tag X.Y.Z && git push --tags'"; exit 1; }
    echo "dernier tag poussé : $TAG"
else
    git -C "$REPO" rev-parse -q --verify "refs/tags/$TAG" >/dev/null \
        || { echo "ABANDON : le tag '$TAG' n'existe pas (voir deploy.sh --list)"; exit 1; }
    echo "version demandée : $TAG"
fi

# Information : on liste les branches contenant le tag plutôt que de tester
# `main` seule, sinon le message afficherait toujours « non » et perdrait tout
# intérêt.
# Le '|| true' est indispensable : sur un tag orphelin la sortie est vide, donc
# 'grep -v HEAD' renvoie 1 et, avec 'set -o pipefail', l'affectation echoue et
# 'set -e' tue le script -- exactement le cas que le message ci-dessous est
# cense signaler.
BRANCHES=$(git -C "$REPO" branch -r --contains "refs/tags/$TAG" --format='%(refname:short)' 2>/dev/null \
    | grep -v HEAD | paste -sd', ' - || true)
echo "contenu dans      : ${BRANCHES:-AUCUNE BRANCHE — tag orphelin, code jamais fusionné}"

# Garde-fou, bloquant depuis le 2026-08-26 : `main` est la seule branche où
# tourne la CI, donc livrer un tag qu'elle ne contient pas, c'est livrer du code
# que rien n'a vérifié. `--force` existe pour les exceptions (cf. 0.2.1, patch de
# durée de session posé hors branche) — ça reste un geste conscient, pas la
# routine. On teste l'ascendance plutôt que la liste ci-dessus : un tag peut être
# contenu dans une branche dont le nom ressemble à `main` sans être dans `main`.
if git -C "$REPO" rev-parse -q --verify refs/remotes/origin/main >/dev/null; then
    :
else
    echo "ABANDON : refs/remotes/origin/main introuvable — 'git -C $REPO fetch origin' d'abord." >&2
    exit 1
fi

if git -C "$REPO" merge-base --is-ancestor "refs/tags/$TAG^{commit}" refs/remotes/origin/main; then
    echo "dans main         : oui"
elif [ "$FORCE" = true ]; then
    echo "dans main         : NON — livraison forcée (--force), code hors CI, exception assumée"
else
    {
        echo "ABANDON : le tag « $TAG » n'est pas contenu dans main."
        echo "          main est la seule branche où tourne la CI : livrer autre chose,"
        echo "          c'est livrer du code que rien n'a vérifié."
        echo "          Fusionner develop dans main puis reposer un tag, ou assumer"
        echo "          explicitement l'exception :"
        echo "              deploy.sh $TAG --force"
    } >&2
    exit 1
fi

git -C "$REPO" checkout --detach --quiet "refs/tags/$TAG"
git -C "$REPO" log -1 --format='commit livré      : %h  %s  (%ad)' --date=short

# Le code exécuté vient du montage, pas de l'image : `setuptools_scm` n'a
# aucune prise ici. On écrit le numéro du tag là où `__init__.py` le lit.
printf 'version = "%s"\n' "$TAG" > "$REPO/inventree_location/_version.py"

VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' "$REPO/inventree_location/_version.py")
echo "PLUGIN_VERSION    : $VERSION"
# Le tag et PLUGIN_VERSION doivent être identiques (mêmes MAJEUR.MINEUR.CORRECTIF,
# sans préfixe) : c'est PLUGIN_VERSION qu'InvenTree affiche dans son panneau.
[ "$TAG" = "$VERSION" ] || echo "  (note : le tag et PLUGIN_VERSION diffèrent — InvenTree affichera $VERSION)"

echo
echo "===== 2/4  build du frontend ====="
# Node tourne dans un conteneur jetable : rien à installer sur la machine.
docker run --rm \
    -v "$REPO":/app \
    -w /app/frontend \
    node:20-alpine \
    sh -c "npm ci --no-audit --no-fund && npm run build"

COUNT=$(find "$REPO/inventree_location/static" -name '*.js' | wc -l)
echo "static reconstruit : $COUNT fichiers .js"
[ "$COUNT" -gt 0 ] || { echo "ABANDON : build vide, la prod n'est pas touchée"; exit 1; }

echo
echo "===== 3/4  démarrage / mise à jour des conteneurs ====="
$COMPOSE up -d --build
wait_ready "init"

# Le code Python est monté en volume : le restart est ce qui le recharge et
# republie le static du plugin.
$COMPOSE restart inventree worker
wait_ready "après restart"

# Avec DEBUG=False, rien n'est servi depuis les sources : il faut recopier les
# assets dans STATIC_ROOT, que Caddy lit ensuite dans le volume. Le restart
# republie le static du plugin, mais pas celui du cœur d'InvenTree.
echo "-- collecte des fichiers statiques --"
$COMPOSE exec -T inventree \
    python /home/inventree/src/backend/InvenTree/manage.py collectstatic --noinput 2>&1 \
    | tail -2

echo
# Les groupes de rôles sont créés sans aucun droit InvenTree : sans cette pose,
# un compte non-superutilisateur ne voit même pas les boutons de création des
# écrans natifs — c'est ce qui empêchait le client d'enregistrer un fournisseur
# (`company_company` relève du ruleset `purchase_order`). Idempotent : ne
# réécrit que ce qui a dérivé de la matrice déclarée dans
# `inventree_location/roles.py`. Ici et pas au démarrage du plugin, pour ne pas
# réécrire les permissions à chaque boot et lutter contre un réglage fait à la
# main dans l'admin.
# Le test d'existence couvre le retour arrière : `deploy.sh <tag antérieur>`
# livre une version où la commande n'existe pas encore, et `set -e` tuerait
# alors le déploiement juste après le restart. On saute dans ce seul cas ; une
# commande présente qui échoue reste fatale.
MANAGE=/home/inventree/src/backend/InvenTree/manage.py

# L'onglet BOM s'appelle « Liste des matériaux » dans la traduction française
# livrée par InvenTree : un catalogue embarqué dans l'image, pas un fichier à
# nous. Le collectstatic ci-dessus vient justement de le rétablir, d'où la
# reprise ici et pas ailleurs. Même garde que les blocs suivants, pour le
# retour arrière vers une version où la commande n'existe pas.
if $COMPOSE exec -T inventree \
        python "$MANAGE" help renommer_liste_materiaux >/dev/null 2>&1; then
    echo "-- libellé de l'onglet BOM --"
    $COMPOSE exec -T inventree \
        python "$MANAGE" renommer_liste_materiaux 2>&1 | tail -3
else
    echo "-- libellé BOM : commande absente de cette version, étape sautée --"
fi

if $COMPOSE exec -T inventree \
        python "$MANAGE" help provision_role_permissions >/dev/null 2>&1; then
    echo "-- pose des droits InvenTree par rôle --"
    $COMPOSE exec -T inventree \
        python "$MANAGE" provision_role_permissions 2>&1 | tail -3
else
    echo "-- droits InvenTree : commande absente de cette version, étape sautée --"
fi

# Même logique pour les tableaux de bord, et pour une raison qui n'est pas le
# simple rattrapage des comptes anciens : les widgets sont posés sur le signal
# `m2m_changed` de `User.groups`, donc au moment où l'on attribue un rôle. Toute
# livraison qui *ajoute* un widget laisse les comptes existants en arrière —
# leur rôle n'a pas bougé, le signal ne rejoue pas. Constaté au déploiement
# 1.0.0 : tassin voyait 5 widgets sur 9, et trois comptes en voyaient zéro.
if $COMPOSE exec -T inventree \
        python "$MANAGE" help provision_dashboards >/dev/null 2>&1; then
    echo "-- pose des tableaux de bord par rôle --"
    $COMPOSE exec -T inventree \
        python "$MANAGE" provision_dashboards 2>&1 | tail -3
else
    echo "-- tableaux de bord : commande absente de cette version, étape sautée --"
fi

echo "===== 4/4  vérification ====="
$COMPOSE ps --format 'table {{.Name}}\t{{.Status}}'
CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 https://inventree-location.duckdns.org/)
echo "HTTPS public : $CODE (302 = redirection vers la connexion, attendu)"

echo
echo "$TAG déployé — https://inventree-location.duckdns.org"
echo "retour arrière : deploy.sh <tag précédent>   (deploy.sh --list pour les voir)"
