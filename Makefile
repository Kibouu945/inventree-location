.PHONY: up down attendre migrate test build build-frontend front static dev logs \
        shell clean manage provision-plugin provision deployer

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
#   écriture et la composition des packs (recette 4.3.1) n'apparaît pas.
#   Idempotente : la relancer ne coûte rien.
#   Déjà lancée par `deploy.sh` sur le VPS.
#
# renommer_liste_materiaux — l'onglet BOM s'appelle « Liste des matériaux »
#   dans la traduction française livrée par InvenTree lui-même : un catalogue
#   embarqué dans l'image Docker, pas un fichier à nous. On le réécrit en
#   « Liste des éléments » après coup. Le fichier revient avec l'image et tout
#   collectstatic le rétablit — donc À REJOUER après toute montée de version
#   d'InvenTree, pas seulement après un déploiement du plugin.
#   ABSENTE de `deploy.sh` au 28/09/2026, alors que le script lance justement
#   un collectstatic juste avant : en prod le libellé est resté « Liste des
#   matériaux ». À ajouter au script, après la collecte.
#
# provision_dashboards — les widgets sont posés sur le signal m2m_changed de
#   User.groups, donc au moment où l'on attribue un rôle. Toute livraison qui
#   AJOUTE un widget laisse les comptes existants en arrière : leur rôle n'a
#   pas bougé, le signal ne rejoue pas. Constaté au déploiement 1.0.0, où un
#   compte voyait 5 widgets sur 9. Déjà lancée par `deploy.sh`.
# ############################################################################

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

attendre:
	@echo "Attente du serveur..."
	@i=0; until curl -sf http://localhost:8000/api/ >/dev/null; do \
		i=$$((i+1)); [ $$i -gt 60 ] && echo "serveur injoignable" && exit 1; \
		sleep 3; \
	done
	@echo "Serveur prêt."

static: attendre
	docker compose exec -T inventree bash -lc \
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
	docker compose exec -T inventree bash -lc "cd /home/inventree/src/backend/InvenTree && python manage.py shell" < docker/provision_plugin_settings.py
	docker compose restart inventree backend
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
	docker compose exec inventree invoke update --skip-backup

test:
	docker compose exec inventree invoke test inventree_location

build:
	docker compose build

build-frontend:
	docker compose run --rm frontend sh -c "npm install && npm run build"

logs:
	docker compose logs -f

shell:
	docker compose exec inventree bash

# Une commande Django, sans retaper le chemin :
#   make manage cmd="showmigrations inventree_location"
#   make manage cmd="makemigrations --check --dry-run"
manage:
	docker compose exec inventree bash -lc "cd /home/inventree/src/backend/InvenTree && python manage.py $(cmd)"

clean:
	docker compose down -v
