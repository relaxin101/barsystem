.PHONY: dev shell migrate migrate-create create-admin db db-stop \
        test test-v test-cov \
        prod prod-logs prod-down prod-rebuild install

FLASK_APP ?= app:create_app

# --- Development (local, no container) ---

dev: db
	set -a; . ./.env; set +a; APP_ENV=development DATABASE_HOST=localhost uv run python app.py

shell:
	FLASK_APP=$(FLASK_APP) APP_ENV=development uv run flask shell

migrate:
	FLASK_APP=$(FLASK_APP) APP_ENV=development uv run flask db upgrade

migrate-create:
	FLASK_APP=$(FLASK_APP) APP_ENV=development uv run flask db migrate -m "$(msg)"

create-admin:
	FLASK_APP=$(FLASK_APP) APP_ENV=development uv run flask create-admin

# Start only the database container for local development
db:
	docker compose up db -d

db-stop:
	docker compose stop db

# --- Testing ---

test:
	APP_ENV=testing uv run pytest

test-v:
	APP_ENV=testing uv run pytest -v

test-cov:
	APP_ENV=testing uv run pytest --cov=. --cov-report=html

# --- Production (Docker) ---

prod:
	docker compose up --build -d

prod-logs:
	docker compose logs -f app

prod-down:
	docker compose down

prod-rebuild:
	docker compose up --build --force-recreate -d

prod-update:
	git log --tags --pretty="%h %d %s" --decorate=full -n 1 | cat  # Vorherige Version der App, für den Fall der Fälle notieren
	docker compose down # Stoppe die App
	git fetch # Checke nach updates
	git add . && git stash # Um die customizations (Farben, Logo, etc.) etc. zu speichern und für git zu clearen
	git reset --hard origin/master # Wendet die updates an
	git stash pop # Um die customizations wiederherzustellen
	docker compose up --build -d # Startet die App neu und führt ggf. Datenbank-Migrationen durch

# --- Setup ---

install:
	uv sync --group dev
