up:
	docker compose up --build

down:
	docker compose down

fresh:
	docker compose down -v && docker compose up --build

test:
	docker compose exec api pytest -v

migrate:
	docker compose exec api alembic upgrade head

migration:
	docker compose exec api alembic revision -m "$(name)"
