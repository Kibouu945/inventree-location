.PHONY: up down migrate test build build-frontend logs shell clean

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

clean:
	docker compose down -v
