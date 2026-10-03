# Factored2026

AI-first banking customer-service agent for the Factored AI & Data Hackathon 2026.

![Component architecture](docs/documentation/technical/diagrams/architecture.svg)

Solid = built, dashed = planned. Details in [architecture.md](docs/documentation/technical/architecture.md).

## Run it locally

You need [Docker](https://www.docker.com/products/docker-desktop/) and [Ollama](https://ollama.com) (`brew install ollama`).

```bash
cp .env.example .env
make up
```

Open http://localhost:3000 for the landing page of **quipu**, the bank's voice agent, and **Hablar con Quipu** for the chat. That's it: `make up` starts the local LLM, Postgres with sample data, the API (:8080) and the web (:3000), then checks that everything answers.

```bash
make smoke   # check again that everything is healthy
make logs    # see what's going on
make down    # stop everything, Ollama included (make down V=1 also wipes the database)
```

No keys needed: it runs on Ollama (`qwen3.5:4b`) and a committed data sample.

### Try it

| Page | What it is | Data |
|---|---|---|
| `/` | Landing | Static |
| `/chat` | The customer's chat, typed or spoken | Real: the agent |
| `/mis-finanzas` | The customer's spending | Sample (`web/lib/profile.ts`) |
| `/consola` | The team's console: every chat, take one over, give it back (needs `OPERATOR_KEY`) | Real: the API's memory |
| `/consola/perfil` | A customer's 360 profile | Sample (`web/lib/profile.ts`) |
| `/consola/gerencia` | Management dashboard | Sample (`web/lib/ops.ts`) |

The sample pages show the idea with fixed figures until the API serves them. In `/chat`, the **Cliente** field lists the customers in `DEMO_CUSTOMER_IDS` (`.env`); choosing one logs you in (the UI asks `POST /api/auth/token` for a short-lived bearer token). The agent handles **balances**, **charges you don't recognize** and **questions about your own data**:

| Ask | What happens |
|---|---|
| `¿cuál es mi saldo?` / `qual é o meu saldo?` | Skill `balance_inquiry` → MCP tool `get_balances` → real balances from Postgres |
| `no reconozco un cargo de Uber` (customer `DEMO-MX-DUPLICATE`) | Skill `charge_investigation` → `investigate_charges`: finds the charges and checks the bank's records (duplicate, pending, foreign) |
| `¿cuántas quejas tengo?` / `¿cuánto he gastado?` | Skill `data_lookup` → the model writes one SQL `SELECT`; code checks it and only lets it see this customer's rows |
| `¿y la de débito?` | Follows up in the same conversation |
| `quiero hablar con una persona` | Handoff to a human, decided by code with no LLM call |
| `¿me recomiendas una hipoteca?` | Short out-of-scope answer |
| Empty Customer ID | The agent asks for it and validates it against the database |
| Click the **microphone**, speak in Spanish or Portuguese, click again | faster-whisper transcribes it and the agent answers as above. With the **Silencio** button switched to **Voz**, Kokoro also reads the answer aloud |

The API is `POST /api/chat {message, thread_id?}`. Outside `APP_ENV=local` it needs `Authorization: Bearer <token>` (from `POST /api/auth/token`, demo customers only) and the customer is the token's, never the body's. Locally it still accepts `customer_id` in the body, so `curl` works without a token. Swagger: http://localhost:8080/docs.

### If something fails

`make up` / `make smoke` print which piece failed:

| Message | Fix |
|---|---|
| `Ollama not found` | `brew install ollama` |
| `FAIL api` | Docker Desktop not running, or check `make logs` |
| `deps ... llm: error` | `make llm` |
| `deps ... db: error` | `make down && make up` |

## More

- **Use Gemini locally** (e.g. for evals): in `.env` set `LLM_PROVIDER=google_genai` and `GOOGLE_API_KEY`. In the cloud it's Gemini by default.
- **Code without Docker** (needs [uv](https://docs.astral.sh/uv/) and Node 24+): `make setup`, `make db-up db-load`, `make dev` (API :8080), `make web` (UI :3000), `make test`. For the microphone, `make models` downloads the speech models (about 0.8 GB) to `./models`; the Docker image has its own. `make setup` also enables a git pre-commit hook that runs the CI lint (`.githooks/pre-commit`).
- **Full dataset** (S3 keys from the data dictionary PDF): `make data-lite`, `make bronze`. See [data_pipeline.md](docs/documentation/technical/data_pipeline.md).
- **Telegram**: put a [@BotFather](https://t.me/BotFather) token in `TELEGRAM_BOT_TOKEN`, then `make telegram-local`.
- **Deploy** (GCP): two Cloud Run services, `factored-api` and `factored-web`, and Cloud SQL. See [Deploy to GCP](#deploy-to-gcp).
- **Architecture**: hexagonal. `app/domain` holds the rules, `app/application` the use cases, `app/adapters` HTTP/Telegram/MCP/LLM/Postgres. See [architecture.md](docs/documentation/technical/architecture.md) and the [ADRs](docs/documentation/technical/adr/).

## Add a skill

1. Create `app/adapters/inbound/agent/skills/<name>/SKILL.md` with frontmatter `name`, `description` (the router picks skills by it) and `mcp` (the server name), followed by the instructions.
2. Add the tools as a FastMCP server in `app/adapters/inbound/mcp/<server>.py`. Read the customer with `session_customer(ctx)` and **never take `customer_id` as a tool argument**.
3. Register the server in `SERVERS` (`app/adapters/inbound/agent/mcp_bridge.py`).
4. Add a route test in `tests/test_agent_graph.py`.

The graph doesn't change. Persona and scope live in `app/adapters/inbound/agent/AGENT.md`.

## Let the SQL agent read a new table

`data_lookup` only sees the tables allowlisted in `app/domain/sql_scope.py`. To add one: create it in `schema.sql` (with `customer_id` if it holds customer data), list it in `OWNED` (has `customer_id`) or `REFERENCE`, load it in `data_pipeline/load.py`, and describe it in `app/adapters/inbound/mcp/dwh_catalog.md`. `tests/test_dwh.py` fails if a table in `schema.sql` is not classified.

## Deploy to GCP

`factored-api` (FastAPI + agent, root `Dockerfile`) and `factored-web` (static Next.js on nginx, `web/Dockerfile`) run on Cloud Run in `us-central1`; the API reads Cloud SQL (Postgres 16, instance `CLOUD_SQL_INSTANCE`) through the Cloud SQL connector and calls Gemini on Vertex AI. Set `GCP_ACCOUNT`, `GCP_PROJECT_ID` and `CLOUD_SQL_INSTANCE` in `.env`.

One-time setup (project owner):

1. Enable `run`, `sqladmin`, `artifactregistry`, `cloudbuild`, `secretmanager` and `aiplatform`.
2. Create the Docker repository `factored` in Artifact Registry, and give the Compute default service account (Cloud Build) `artifactregistry.writer`, `logging.logWriter` and `storage.objectViewer`.
3. Create the Cloud SQL instance, the database `agent` and the user `agent`. Store the password in the secret `factored-db-password` and the URL `postgresql://agent:PASSWORD@/agent?host=/cloudsql/PROJECT:REGION:INSTANCE` in `factored-database-url`.
4. Create the service account `factored-api` with `cloudsql.client`, `aiplatform.user` and `secretmanager.secretAccessor`.
5. Create the secret `jwt-secret` (`openssl rand -hex 32`): the key that signs the API's bearer tokens. The API does not start without it.
6. (Only for an empty database: `make db-load-cloud` drops `core`.) In one terminal `make db-proxy` ([cloud-sql-proxy](https://cloud.google.com/sql/docs/postgres/sql-proxy)), in another `make db-load-cloud`.

From there GitHub deploys: every push to `main` runs the tests and then deploys both services (`.github/workflows/deploy.yml`). Do not run `make deploy*` by hand (the last deploy wins) and never `make db-load-cloud` on the shared database. Setup, rollback and limits: [deploy.md](docs/documentation/technical/deploy.md). The API runs with `--max-instances 1` because conversation memory is in process.

## Repo map

```
app/adapters/inbound/agent/   agent graph (guard → router → skill_agent → handoff), AGENT.md, skills/
app/adapters/inbound/mcp/     FastMCP servers (one per skill)
app/adapters/outbound/        Postgres queries + schema.sql, LLM factory
.github/workflows/           lint + tests on every PR; deploy of both services on push to main
data_pipeline/                raw → bronze → sample → silver → Postgres
data/sample/                  committed mini-set of the organizer data + demo fixtures
web/                          Next.js chat (own image: web/Dockerfile)
docs/                         problem/, strategy_analysis_NN/ (one per teammate), documentation/
```
