.PHONY: install install-dev lint format test test-cov run-api run-ui ingest docker-up docker-down docker-build health

install:
	uv sync

install-dev:
	uv sync --extra dev

lint:
	uv run ruff check src/ scripts/ tests/

format:
	uv run ruff format src/ scripts/ tests/

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ --cov=src --cov-report=term-missing

run-api:
	uv run uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000

run-ui:
	uv run streamlit run src/channels/streamlit_app.py

ingest:
	uv run python scripts/ingest.py

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

health:
	curl -s http://localhost:8000/health | python -m json.tool
