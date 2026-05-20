.PHONY: install provision backend frontend dev

install:
	cd backend && python3.12 -m venv .venv && . .venv/bin/activate && pip install -e .
	cd frontend && npm install

provision:
	@test -f .env || (echo "Copy .env.example to .env first" && exit 1)
	@set -a && . ./.env && set -a && python backend/scripts/provision_agent.py

backend:
	cd backend && . .venv/bin/activate && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	@echo "Run 'make backend' and 'make frontend' in separate terminals"

docker-up:
	docker compose up --build

docker-down:
	docker compose down
