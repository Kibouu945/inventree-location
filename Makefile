.PHONY: up down migrate test build build-frontend logs shell clean manage provision-plugin provision

up:
	docker compose up --build -d

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


provision-plugin:
	docker compose exec -T inventree bash -lc "cd /home/inventree/src/backend/InvenTree && python manage.py shell" < docker/provision_plugin_settings.py
	docker compose restart inventree backend
	@echo "Attente du redémarrage du serveur..."
	@timeout 90 bash -c 'until curl -sf http://localhost:8000/api/ >/dev/null; do sleep 2; done'

provision: provision-plugin
	make manage cmd="seed_demo"
	make manage cmd="provision_role_permissions"
	make manage cmd="provision_dashboards"

clean:
	docker compose down -v
