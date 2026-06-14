.PHONY: dev migrate test lint bootstrap down

dev:
	docker compose up --build

migrate:
	docker compose run --rm api alembic upgrade head

test:
	pytest

lint:
	ruff check app tests

bootstrap:
	python -m app.cli.bootstrap dify
	python -m app.cli.bootstrap neo4j

down:
	docker compose down

