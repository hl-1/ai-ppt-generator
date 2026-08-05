.PHONY: up down install dev-api dev-web migrate test lint gen-api

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

# 前端接口类型由后端 OpenAPI 生成，两端类型不会各写一份而分叉。
# 直接从应用对象导出 schema，因此不需要先把服务跑起来。
gen-api:
	cd backend && uv run python -c "import json; from app.main import app; print(json.dumps(app.openapi(), ensure_ascii=False))" > ../frontend/openapi.json
	cd frontend && npx openapi-typescript openapi.json -o src/api/schema.d.ts

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check .
