.PHONY: up down attendre migrate test build build-frontend front static dev logs \
        shell clean manage provision-plugin provision deployer traductions \
        demo-up demo-seed demo-mot-de-passe demo-semer demo-snapshot \
        demo-purge demo-down demo-prete demo-jouer demo-arreter

# Les cibles visent la stack de dev ; `make demo-*` les rejoue sur l'instance démo.
COMPOSE ?= docker compose

# ############################################################################
# 1. OBLIGATOIRE PARTOUT — en dev comme en prod, après chaque déploiement
#
#     make deployer
#
# Ces trois commandes ne se déduisent pas du code déployé : elles écrivent dans
# la base et dans le static d'InvenTree. Tant qu'elles n'ont pas tourné SUR LA
# MACHINE CIBLE, le bon code est en place et la fonctionnalité reste invisible.
#
# provision_role_permissions — InvenTree range ses droits dans des « RuleSet »
#   liés aux groupes Django ; la commande y recopie la matrice de
#   roles.ROLE_WRITE_RULESETS. Sans elle, la base n'a pas le droit `bom` en
#   écriture et la composition des packs n'apparaît pas.
#   Idempotente : la relancer ne coûte rien.
#   Déjà lancée par `deploy.sh` sur le VPS.
#
# renommer_liste_materiaux — l'onglet BOM s'appelle « Liste des matériaux »
#   dans la traduction française livrée par InvenTree lui-même : un catalogue
#   embarqué dans l'image Docker, pas un fichier à nous. On le réécrit en
#   « Liste des éléments » après coup. Le fichier revient avec l'image et tout
#   collectstatic le rétablit — donc À REJOUER après toute montée de version
#   d'InvenTree, pas seulement après un déploiement du plugin.
#   `deploy.sh` l'appelle, juste après sa collecte, sous la même garde de
#   retour arrière que les deux autres. Si le libellé reste « Liste des
#   matériaux » en production, ce n'est donc pas le script : c'est que la
#   version en ligne est antérieure à la commande, et la garde saute l'étape
#   en le disant. Le prochain tag qui la contient corrige le libellé seul.
#
# provision_dashboards — les widgets sont posés sur le signal m2m_changed de
#   User.groups, donc au moment où l'on attribue un rôle. Toute livraison qui
#   AJOUTE un widget laisse les comptes existants en arrière : leur rôle n'a
#   pas bougé, le signal ne rejoue pas. Constaté au déploiement 1.0.0, où un
#   compte voyait 5 widgets sur 9. Déjà lancée par `deploy.sh`.
# ############################################################################

# Recompile le catalogue de surcharge après toute retouche du .po. Le .mo est
# versionné : le montage du plugin masquerait celui que l'image construirait.
traductions:
	$(COMPOSE) exec -T inventree bash -lc "cd /home/inventree/plugin/inventree_location/locale/fr/LC_MESSAGES && msgfmt -o django.mo django.po && echo 'catalogue compilé'"

deployer:
	make manage cmd="provision_role_permissions"
	make manage cmd="renommer_liste_materiaux"
	make manage cmd="provision_dashboards"

# ############################################################################
# 2. OBLIGATOIRE EN DEV — la boucle du poste de travail, l'ordre compte
#
#     make dev
#
# soit, dans l'ordre :
#     make front     seulement si le frontend a changé
#     make up        si le backend a changé, ou après un git pull
#     make static    après chacun des deux, sans exception
#
# Pourquoi `static` n'est jamais facultatif : InvenTree sert le static COLLECTÉ
# depuis /home/inventree/data/static/, pas le build du plugin. `make up` recrée
# le conteneur serveur et ce static repart de l'image ; `collectstatic`, lui,
# ne recopie pas celui d'un plugin. Sans `make static`, l'écran reste sur
# l'ancienne version — ou ne charge pas du tout, sans la moindre erreur.
#
# En prod, cette boucle n'a pas d'équivalent ici : c'est `deploy.sh`, sur le
# VPS et hors dépôt, qui checkout le tag, reconstruit et republie le static.
# `make deployer` reste à lancer après lui.
# ############################################################################

front:
	cd frontend && npm run build

up:
	docker compose up --build -d

URL ?= http://localhost:8000

attendre:
	@echo "Attente du serveur..."
	@i=0; until curl -sf $(URL)/api/ >/dev/null; do \
		i=$$((i+1)); [ $$i -gt 60 ] && echo "serveur injoignable" && exit 1; \
		sleep 3; \
	done
	@echo "Serveur prêt."

static: attendre
	$(COMPOSE) exec -T inventree bash -lc \
		"cd /home/inventree/src/backend/InvenTree && python manage.py shell" \
		< docker/copier_static_plugin.py

dev: front up static

# ############################################################################
# 3. FACULTATIF — selon le besoin
#
# seed_demo — jeu de démonstration. JAMAIS en production.
#
# make provision — base de dev fraîchement montée : réglages du plugin, démo,
#   droits, widgets et libellés, d'un coup.
# ############################################################################

provision-plugin:
	$(COMPOSE) exec -T inventree bash -lc "cd /home/inventree/src/backend/InvenTree && python manage.py shell" < docker/provision_plugin_settings.py
	$(COMPOSE) restart inventree backend
	make attendre

provision: provision-plugin
	make manage cmd="seed_demo"
	make deployer
	make static

# ############################################################################
# 4. Utilitaires
# ############################################################################

down:
	docker compose down

migrate:
	$(COMPOSE) exec inventree invoke update --skip-backup

test:
	$(COMPOSE) exec inventree invoke test inventree_location

build:
	docker compose build

build-frontend:
	docker compose run --rm frontend sh -c "npm install && npm run build"

logs:
	docker compose logs -f

shell:
	$(COMPOSE) exec inventree bash

# Une commande Django, sans retaper le chemin :
#   make manage cmd="showmigrations inventree_location"
#   make manage cmd="makemigrations --check --dry-run"
manage:
	$(COMPOSE) exec inventree bash -lc "cd /home/inventree/src/backend/InvenTree && python manage.py $(cmd)"

clean:
	docker compose down -v

# ############################################################################
# 5. Démo live « Vieilles Charrues »
#
#     make demo-prete      avant de passer : tout est remis à zéro, à la date du jour
#     make demo-jouer      devant le jury : le script déroule les six temps (~5 min)
#     make demo-arreter    après
#
# Par défaut sur l'instance en ligne (VPS, /data/inventree-demo/demo.sh) ;
# `CIBLE=local` pour l'instance du portable, sur http://localhost:8001.
# `demo-jouer` enregistre toujours une vidéo de secours (tests/e2e/videos-charrues).
#
# Les cibles demo-up, demo-seed et demo-purge font le détail en local.
# L'instantané est pris AVANT le seed : la purge ressème, donc les concerts
# tombent toujours le jour même — la tournée du livreur n'affiche que lui.
# ############################################################################

CIBLE ?= vps
VPS = inventree-vps
SSH = ssh -o ConnectionAttempts=6 -o ConnectTimeout=15 $(VPS)
DEMO_SH = /data/inventree-demo/demo.sh
DEMO_LOG = /data/inventree-demo/prete.log
TEMPO ?= 1

ifeq ($(CIBLE),local)
DEMO_URL = http://localhost:8001
DEMO_MDP = .demo/mot-de-passe
else
DEMO_URL = https://demo.inventree-location.duckdns.org
DEMO_MDP = .demo/mot-de-passe-vps
endif

demo-prete:
ifeq ($(CIBLE),local)
	@mkdir -p .demo
	@test -s $(DEMO_MDP) || (umask 077 && python3 -c "import secrets;print('Ch-'+secrets.token_urlsafe(12))" > $(DEMO_MDP))
	make demo-up
	@if test -s $(DEMO_DUMP); then \
		CHARRUES_MOT_DE_PASSE=$$(cat $(DEMO_MDP)) make demo-purge; \
	else \
		CHARRUES_MOT_DE_PASSE=$$(cat $(DEMO_MDP)) make demo-seed; \
	fi
else
	@# Détaché sur le serveur : une coupure SSH ne l'interrompt pas.
	$(SSH) 'rm -f $(DEMO_LOG); nohup sh -c "$(DEMO_SH) prete || echo ABANDON" > $(DEMO_LOG) 2>&1 < /dev/null &'
	@echo "Préparation sur le VPS (3 à 5 minutes)…"
	@until $(SSH) 'grep -q "DÉMO PRÊTE\|ABANDON" $(DEMO_LOG)' 2>/dev/null; do sleep 15; done
	@$(SSH) 'grep -v "INFO\|info " $(DEMO_LOG) | tail -4'
	@$(SSH) 'grep -q "DÉMO PRÊTE" $(DEMO_LOG)'
endif

demo-jouer:
	@test -s $(DEMO_MDP) || (echo "$(DEMO_MDP) absent : lancer make demo-prete" && exit 1)
	@test -d tests/e2e/node_modules/playwright || (cd tests/e2e && npm ci --silent && npx playwright install chromium)
	cd tests/e2e && DEMO_URL=$(DEMO_URL) CHARRUES_MOT_DE_PASSE=$$(cat ../../$(DEMO_MDP)) \
		TEMPO=$(TEMPO) VIDEO=1 node charrues.mjs

demo-arreter:
ifeq ($(CIBLE),local)
	make demo-down
else
	$(SSH) '$(DEMO_SH) down'
endif

DEMO = docker compose -p charrues -f docker-compose.yml -f docker-compose.demo.yml
DEMO_DUMP = .demo/charrues-vide.dump
DEMO_MAKE = make COMPOSE="$(DEMO)" URL=http://localhost:8001

demo-up:
	$(DEMO) up --build -d
	$(DEMO_MAKE) attendre

demo-seed: demo-mot-de-passe
	$(DEMO_MAKE) provision-plugin
	$(DEMO_MAKE) static
	make demo-snapshot
	make demo-semer

demo-mot-de-passe:
	@test -n "$$CHARRUES_MOT_DE_PASSE" || (echo "CHARRUES_MOT_DE_PASSE manquant" && exit 1)

demo-semer: demo-mot-de-passe
	$(DEMO) exec -T -e CHARRUES_MOT_DE_PASSE inventree bash -lc \
		"cd /home/inventree/src/backend/InvenTree && python manage.py seed_charrues"
	$(DEMO_MAKE) deployer

demo-snapshot:
	@mkdir -p .demo
	$(DEMO) exec -T db pg_dump -U $${INVENTREE_DB_USER:-pguser} -d $${INVENTREE_DB_NAME:-inventree} -Fc > $(DEMO_DUMP)
	@echo "Instantané : $(DEMO_DUMP)"

demo-purge: demo-mot-de-passe
	@test -s $(DEMO_DUMP) || (echo "Pas d'instantané : lancer make demo-seed" && exit 1)
	$(DEMO) stop inventree backend
	$(DEMO) exec -T db pg_restore -U $${INVENTREE_DB_USER:-pguser} -d $${INVENTREE_DB_NAME:-inventree} --clean --if-exists --no-owner < $(DEMO_DUMP)
	$(DEMO) start inventree backend
	$(DEMO_MAKE) attendre
	make demo-semer
	@echo "Démo remise à zéro, festival ressemé à la date du jour."

demo-down:
	$(DEMO) down
