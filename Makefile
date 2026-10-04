.PHONY: help dev api web db train test seed clean

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-12s\033[0m %s\n",$$1,$$2}'

dev: ## Full stack in Docker (no API keys needed)
	docker compose up --build

api: ## API only, locally, mock backend
	cd services/api && STORE_BACKEND=mock uvicorn app.main:app --reload --port 8000

web: ## Frontend dev server
	cd web && npm install && npm run dev

db: ## Apply the schema to a running postgres
	psql $${DATABASE_URL:-postgresql://aqua:aqua@localhost:5432/aquasentinel} -f db/001_schema.sql

train-forecaster: ## Pre-train the stress forecaster (do this on day 2, not day 6)
	cd services/api && python -m app.ml.train_forecaster --out ../../models/forecaster.pkl

train-classifier: ## Fine-tune the taxon classifier
	cd services/api && python -m app.ml.classifier --data ../../data/macroinvertebrates

ingest: ## Pull external data into the measurement schema
	cd services/api && python -m app.ingest.sources --all

test: ## Smoke test every endpoint
	cd services/api && python -m app.selftest

clean:
	rm -rf services/api/.cache services/api/__pycache__ **/__pycache__
