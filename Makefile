.PHONY: up down migrate test build build-frontend logs shell clean manage

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

clean:
	docker compose down -v
