.PHONY: up down install dev-api dev-web migrate test lint

up:
	docker compose up -d

down:
	docker compose down

install:
	cd backend && uv sync
	cd frontend && npm install

dev-api:
	cd backend && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 39800

dev-web:
	cd frontend && npm run dev

migrate:
	cd backend && uv run alembic upgrade head

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .
