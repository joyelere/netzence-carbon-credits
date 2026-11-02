up:
	docker compose up --build

down:
	docker compose down

fresh:
	docker compose down -v && docker compose up --build

# runs the suite against the real Postgres test database (netzence_test)
test:
	docker compose build api && docker compose run --rm api pytest -v

migrate:
	docker compose exec api alembic upgrade head

migration:
	docker compose exec api alembic revision -m "$(name)"
