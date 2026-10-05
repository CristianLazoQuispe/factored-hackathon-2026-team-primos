-include .env
export

.PHONY: build up smoke down logs llm setup data data-lite bronze sample fixtures silver db-up db-load demo-data models dev web test lint docker telegram-local db-proxy etl-cloud deploy-api deploy-web api-cors deploy telegram-webhook diagrams

# Mirrors Settings.provider (app/config.py): Ollama unless LLM_PROVIDER says otherwise or APP_ENV isn't local.
LLM_PROVIDER_RESOLVED := $(or $(LLM_PROVIDER),$(if $(filter local,$(or $(APP_ENV),local)),ollama,google_genai))
OLLAMA_MODEL := $(or $(LLM_MODEL_FAST),qwen3.5:4b)
URL := http://localhost:8080
WEB_URL := http://localhost:3000
# Written only when `make llm` starts Ollama, so `make down` never kills an Ollama you run yourself.
OLLAMA_PID := /tmp/factored-ollama.pid
KOKORO_FILES := https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0

build:            ## Build the images (seed, app, web)
	docker compose build

up: $(if $(filter ollama,$(LLM_PROVIDER_RESOLVED)),llm)  ## Build and start everything (local LLM + db + seed + API + web), then smoke-test it
	docker compose up -d --build --wait app web
	@$(MAKE) --no-print-directory smoke
	@echo "The stack is up -> web $(WEB_URL), API $(URL)  (Postgres on localhost:5432, user/pass agent)"

smoke:            ## Check the running stack: API, db, LLM, web and one chat round-trip
	@curl -sf $(URL)/health >/dev/null || { echo "FAIL api: not answering on $(URL) (make up / make logs)"; exit 1; }
	@echo "ok   api"
	@curl -sf -o /dev/null $(WEB_URL)/ || { echo "FAIL web: $(WEB_URL)/ is not served"; exit 1; }
	@echo "ok   web"
	@ready=$$(curl -s $(URL)/health/ready); echo "     deps $$ready"; \
		curl -sf -o /dev/null $(URL)/health/ready || { echo "FAIL deps (see above)"; exit 1; }
	@reply=$$(curl -sf -m 60 $(URL)/api/chat -H 'content-type: application/json' \
		-d '{"message":"Responde solo: ok"}') || { echo "FAIL chat: no reply (make logs)"; exit 1; }; \
		echo "ok   chat $$reply"

down:             ## Stop everything, incl. the Ollama that `make llm` started (V=1 also deletes the database)
	docker compose down $(if $(V),-v,)
	@if [ -f $(OLLAMA_PID) ]; then kill $$(cat $(OLLAMA_PID)) 2>/dev/null; rm -f $(OLLAMA_PID); echo "ok   ollama stopped"; fi

logs:             ## Follow the logs of all services
	docker compose logs -f

llm:              ## Start local Ollama (native, uses the GPU) and pull the local model
	@command -v ollama >/dev/null || { echo "Ollama not found: brew install ollama"; exit 1; }
	@curl -sf http://localhost:11434 >/dev/null || { \
		OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_MAX_LOADED_MODELS=1 \
		nohup ollama serve >/tmp/ollama.log 2>&1 & echo $$! > $(OLLAMA_PID); sleep 2; }
	@ollama list | grep -q "^$(OLLAMA_MODEL) " || ollama pull $(OLLAMA_MODEL)
	@echo "ok   ollama $(OLLAMA_MODEL)"

setup:            ## Install Python and web dependencies, enable the pre-commit lint hook
	uv sync
	cd web && npm ci
	git config core.hooksPath .githooks

data:             ## Download the full dataset (~5.4 GB CSV)
	uv run python -m data_pipeline.download

data-lite:        ## Download everything except digital_events (~1.6 GB)
	uv run python -m data_pipeline.download --skip digital_events

bronze:           ## Raw CSV -> Parquet per table
	uv run python -m data_pipeline.bronze

sample:           ## Rebuild the committed mini-set data/sample/ from bronze (needs S3 data)
	uv run python -m data_pipeline.sample

fixtures:         ## Regenerate the team-made demo customers: 8 dispute scenarios + 2 for khipear (data/sample/fixtures/)
	uv run python -m data_pipeline.fixtures

silver:           ## Clean + contracts: data/sample -> data/silver (SOURCE=full reads data/bronze)
	uv run python -m data_pipeline.silver --source $(or $(SOURCE),sample)

db-up:            ## Start local Postgres (docker compose)
	docker compose up -d --wait db

db-load:          ## Load silver + fixtures into Postgres core schema (idempotent; SOURCE as in `make silver`)
	uv run python -m data_pipeline.load --source $(or $(SOURCE),sample)

demo-data: db-up silver db-load  ## One command from a fresh clone: Postgres with the mini-set

models:           ## Download the speech models to ./models, for `make dev` (the image has its own)
	mkdir -p models
	curl -fL -o models/kokoro-v1.0.onnx $(KOKORO_FILES)/kokoro-v1.0.onnx
	curl -fL -o models/voices-v1.0.bin $(KOKORO_FILES)/voices-v1.0.bin
	uv run python -c "from faster_whisper import download_model; download_model('small', output_dir='models/whisper-small')"

dev:              ## API with reload on :8080
	uv run uvicorn app.adapters.inbound.http:app --reload --port 8080

web:              ## Next.js dev server on :3000
	cd web && npm run dev

test:
	uv run pytest -q

lint:
	.githooks/pre-commit
	cd web && npx eslint .

docker:           ## Build and run the production image locally
	docker compose up --build

telegram-local:   ## Telegram bot with long polling (no public URL needed)
	uv run python -m app.adapters.inbound.telegram

# ---------- GCP: factored-api + factored-web on Cloud Run, Postgres on Cloud SQL ----------
GCLOUD := gcloud --account $(GCP_ACCOUNT) --project $(GCP_PROJECT_ID)
TAG := $(shell git rev-parse --short HEAD)
REGISTRY := $(GCP_REGION)-docker.pkg.dev/$(GCP_PROJECT_ID)/factored
SQL_CONNECTION := $(GCP_PROJECT_ID):$(GCP_REGION):$(CLOUD_SQL_INSTANCE)
SERVICE_URL = $$($(GCLOUD) run services describe $(1) --region $(GCP_REGION) --format='value(status.url)' 2>/dev/null)
# Cloud Run answers on two URLs per service; CORS must allow both, comma-separated.
WEB_ORIGINS = $$($(GCLOUD) run services describe factored-web --region $(GCP_REGION) --format='value(metadata.annotations."run.googleapis.com/urls")' 2>/dev/null | tr -d '[]" ')

db-proxy:         ## Tunnel to Cloud SQL on 127.0.0.1:5433 (leave running; needs cloud-sql-proxy)
	cloud-sql-proxy --port 5433 $(SQL_CONNECTION)

etl-cloud:        ## Full ETL into Cloud SQL through `make db-proxy`: raw CSV -> bronze -> silver -> core (replaces core; CONFIRM=yes)
	@test "$(CONFIRM)" = yes || { echo "This replaces core on the shared Cloud SQL with the full dataset in data/raw. Re-run with CONFIRM=yes."; exit 1; }
	uv run python -m data_pipeline.bronze
	uv run python -m data_pipeline.silver --source full
	@DATABASE_URL=postgresql://agent:$$($(GCLOUD) secrets versions access latest --secret factored-db-password)@127.0.0.1:5433/agent \
		uv run python -m data_pipeline.load --source full
	cp data/silver/_quality_report.json docs/documentation/technical/data/quality_report_full.json
	@echo "ok   evidence in docs/documentation/technical/data/quality_report_full.json (data/silver now holds the full set: make demo-data rebuilds the sample)"

deploy-api:       ## Build the API image and deploy factored-api (keeps CORS pointed at factored-web)
	$(GCLOUD) builds submit --region $(GCP_REGION) --tag $(REGISTRY)/api:$(TAG) .
	web=$(WEB_ORIGINS); \
	$(GCLOUD) run deploy factored-api --image $(REGISTRY)/api:$(TAG) --region $(GCP_REGION) \
		--service-account factored-api@$(GCP_PROJECT_ID).iam.gserviceaccount.com \
		--add-cloudsql-instances $(SQL_CONNECTION) \
		--set-secrets DATABASE_URL=factored-database-url:latest,JWT_SECRET=jwt-secret:latest,OPERATOR_KEY=operator-key:latest,LANGFUSE_PUBLIC_KEY=langfuse-public-key:latest,LANGFUSE_SECRET_KEY=langfuse-secret-key:latest \
		--set-env-vars "^;^APP_ENV=cloud;GOOGLE_GENAI_USE_VERTEXAI=true;GOOGLE_CLOUD_PROJECT=$(GCP_PROJECT_ID);GOOGLE_CLOUD_LOCATION=$(GCP_REGION);CORS_ORIGINS=$${web:-http://localhost:3000};DEMO_CUSTOMER_IDS=$(DEMO_CUSTOMER_IDS);LANGFUSE_BASE_URL=https://us.cloud.langfuse.com" \
		--memory 4Gi --cpu 4 --cpu-boost --max-instances 1 --allow-unauthenticated

deploy-web:       ## Build the web against factored-api's URL, deploy factored-web, then allow it in CORS
	api=$(call SERVICE_URL,factored-api); test -n "$$api" || { echo "deploy factored-api first"; exit 1; }; \
	$(GCLOUD) builds submit web --region $(GCP_REGION) --config web/cloudbuild.yaml \
		--substitutions _IMAGE=$(REGISTRY)/web:$(TAG),_API_URL=$$api
	$(GCLOUD) run deploy factored-web --image $(REGISTRY)/web:$(TAG) --region $(GCP_REGION) \
		--port 8080 --allow-unauthenticated
	@$(MAKE) --no-print-directory api-cors

api-cors:         ## Allow factored-web's URLs in factored-api's CORS_ORIGINS
	web=$(WEB_ORIGINS); test -n "$$web" || { echo "deploy factored-web first"; exit 1; }; \
	$(GCLOUD) run services update factored-api --region $(GCP_REGION) --update-env-vars "^;^CORS_ORIGINS=$$web"

deploy: deploy-api deploy-web  ## Deploy both services
	@echo "web $(call SERVICE_URL,factored-web)"; echo "api $(call SERVICE_URL,factored-api)"

telegram-webhook: ## Point the Telegram bot at the deployed webhook
	curl -s "https://api.telegram.org/bot$(TELEGRAM_BOT_TOKEN)/setWebhook" \
		-d url=$(PUBLIC_BASE_URL)/telegram/webhook -d secret_token=$(TELEGRAM_WEBHOOK_SECRET)

diagrams:         ## Render docs/documentation/technical/diagrams/*.mmd to SVG + 300-dpi PNG (needs Node, Chrome)
	./docs/documentation/technical/diagrams/render.sh
