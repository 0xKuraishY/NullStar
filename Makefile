.PHONY: help up down logs restart build shell db-shell collect reset test

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

up:        ## Build and start the stack
	docker compose up -d --build
	@echo "→ http://127.0.0.1:$${HTTP_PORT:-8080}  (first visit creates the admin account)"

down:      ## Stop the stack (data is kept)
	docker compose down

logs:      ## Follow application logs
	docker compose logs -f web

restart:   ## Restart the web container
	docker compose restart web

build:     ## Rebuild the image without starting
	docker compose build

shell:     ## Shell inside the web container
	docker compose exec web /bin/bash

db-shell:  ## psql inside the database container
	docker compose exec db psql -U $${POSTGRES_USER:-nullstar} -d $${POSTGRES_DB:-nullstar}

collect:   ## Trigger a collection run immediately
	docker compose exec web python -c "from app.collector.pipeline import run_collection; print(run_collection('cli'))"

reset:     ## DESTROY all data and start fresh
	docker compose down -v
	docker compose up -d --build

test:      ## Run the test suite locally
	.venv/bin/python -m pytest tests -q
