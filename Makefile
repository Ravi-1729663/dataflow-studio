.PHONY: install migrate makemigrations seed run worker beat test lint format docker-up docker-down clean

install:            ## Install dev + runtime dependencies
	pip install -r requirements-dev.txt

makemigrations:     ## Create new migrations
	python manage.py makemigrations

migrate:            ## Apply migrations
	python manage.py migrate

seed:               ## Seed a demo user + datasource + pipeline and run it end-to-end
	python manage.py seed_demo

run:                ## Run the API (dev server)
	python manage.py runserver 0.0.0.0:8000

worker:             ## Run a Celery worker
	celery -A config worker -l info

beat:               ## Run the Celery beat scheduler
	celery -A config beat -l info

test:               ## Run the test suite
	pytest

lint:               ## Lint with ruff
	ruff check .

format:             ## Format with black + ruff
	black . && ruff check --fix .

docker-up:          ## Start the full stack (web, worker, db, redis, prometheus, grafana)
	docker compose up --build

docker-down:        ## Stop the stack
	docker compose down -v

clean:              ## Remove caches and local db
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage db.sqlite3
	find . -type d -name __pycache__ -exec rm -rf {} +
