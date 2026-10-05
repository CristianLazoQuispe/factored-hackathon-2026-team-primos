# Factored2026

AI-first banking customer-service agent for the Factored AI & Data Hackathon 2026.

**What it does.** A customer talks to **quipu**, typed or spoken, in Spanish or Portuguese. It answers from the
bank's own data (balances, debts, spending, a charge they do not recognise, even from a photo of the
statement), and, when the deployment turns it on, it can **act**: block or cancel a card, open a payment
inquiry, ask for a call, set an alert, email a summary. It can also prepare a transfer or a payment that the customer
confirms (khipear). It was built on four rules:

1. **The model never does anything.** It understands the request and proposes. What is allowed is decided by
   code, from the customer's data, and the customer confirms with a button.
2. **Nothing is reported as done until the system has read it back.** The sentence on the card is written by
   code from what was stored and verified, never by the model.
3. **Money moves only on the customer's button.** A transfer or a payment is prepared by khipear and
   runs when the customer presses Confirmar; refunds, changes of phone or email, higher
   limits and new cards go to a person with the case already written.
4. **It says how well it works.** The actions have their own evaluation, with held-out scenarios, a
   baseline, and the failures listed: see [Evaluation of the actions](#evaluation-of-the-actions).

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
| `/mis-finanzas` | The customer's spending | Real: `GET /api/me/finances` (Postgres) |
| `/consola` | The team's console: every chat, take one over, give it back (needs `OPERATOR_KEY`) | Real: the API's memory |
| `/consola/perfil` | A customer's 360 profile | Sample (`web/lib/profile.ts`) |
| `/consola/gerencia` | Management dashboard | Sample (`web/lib/ops.ts`) |

The pages marked Sample show the idea with fixed figures until the API serves them. In `/chat`, sign in with a customer ID from `DEMO_CUSTOMER_IDS` (the password is the same ID) or one of the eight demo emails below; with `*` in that list, the ID of any customer in the database signs in too (the UI asks `POST /api/auth/token` and keeps the short-lived bearer token). The agent handles **balances**, **charges you don't recognize** and **questions about your own data**, and prepares **transfers, payments and service bills** (khipear; try it as `DEMO-MX-KHIPU`, who has two accounts, a card and a loan, with `DEMO-MX-RECIBE` to receive):

| Ask | What happens |
|---|---|
| `¿cuál es mi saldo?` / `qual é o meu saldo?` | Skill `balance_inquiry` → MCP tool `get_balances` → real balances and totals from Postgres |
| `¿cuánto debo en mi tarjeta y cuándo vence?` | Skill `balance_inquiry` → `get_debts`: debt, due date and minimum payment (the payment schedule is team-generated, see [data/model.md](docs/documentation/technical/data/model.md)) |
| `no reconozco un cargo de Uber` (customer `DEMO-MX-DUPLICATE`) | Skill `charge_investigation` → `investigate_charges`: finds the charges and checks the bank's records (duplicate, pending, foreign) |
| Attach `web/public/casos/lucia-uber.png` and write `no reconozco estas transacciones` | The same skill reads Uber, 312.40 MXN and the date from the photo, then reports the duplicate |
| `dime mis últimos movimientos` / `¿en qué gasto más?` / `¿cuántas quejas tengo?` / `¿a cuánto está el dólar?` | Skill `data_lookup` → a tool with reviewed SQL (`get_movements`, `get_spending_summary`, `get_complaints`, `get_exchange_rate`) |
| A question about their data that no tool covers | Skill `data_lookup` → the model writes one SQL `SELECT`; code checks it and only lets it see this customer's rows |
| `khipea 300 a mi tarjeta` / `transfiere 500 a mi otra cuenta` / `khipéale 200 a CLI-...` | Skill `money_movement` → `propose_transfer`: asks which account when there are several, then shows a card. Only the customer's **Confirmar** button moves the money ([ADR 0004](docs/documentation/technical/adr/0004-khipear-money-movement.md)) |
| `¿y la de débito?` | Follows up in the same conversation |
| `quiero hablar con una persona` | Handoff to a human, decided by code with no LLM call |
| `¿me recomiendas una hipoteca?` | Short out-of-scope answer |
| No customer ID (Telegram, or `curl` locally without a token) | The agent asks for it and validates it against the database |
| Click the **microphone**, speak in Spanish or Portuguese, click again | faster-whisper transcribes it and the agent answers as above. With the **Silencio** button switched to **Voz**, Kokoro also reads the answer aloud |

The API is `POST /api/chat {message, thread_id?, image?, image_type?}`. Outside `APP_ENV=local` it needs `Authorization: Bearer <token>`. `POST /api/auth/token` takes `{user, password}`: `user` is an ID in `DEMO_CUSTOMER_IDS` (any customer's ID when the list has `*`) or a demo email, and the password is that same text (`email` is still accepted as the field name). The customer is the token's, never the body's. Locally `curl` can still send `customer_id` in the body without a token. Swagger: http://localhost:8080/docs.

The password of each account is the email itself. The statement images are in `web/public/casos/`. In `/chat`, sign in, attach that customer's image with the clip, and write the question. The text is required: the photo alone is not sent.

| Email (also the password) | Case | Image |
|---|---|---|
| `demo-mx-duplicate@demo.bank` | Lucía, two Uber Trip charges of 312.40 MXN | `web/public/casos/lucia-uber.png` |
| `demo-mx-fx@demo.bank` | Mariana, a Best Buy purchase in dollars | `web/public/casos/mariana-bestbuy.png` |
| `demo-co-pending@demo.bank` | Andrés, an Amazon charge still pending | `web/public/casos/andres-amazon.png` |
| `demo-br-portuguese@demo.bank` | Ana, two iFood charges | `web/public/casos/ana-ifood.png` |
| `demo-ar-fraud@demo.bank` | Martina, three ElectroMax charges in Córdoba | `web/public/casos/martina-electromax.png` |
| `demo-co-ambiguous@demo.bank` | Camilo, four charges on the same day | `web/public/casos/camilo-dia.png` |
| `demo-mx-own-purchase@demo.bank` | Diego, a Liverpool purchase from the app | `web/public/casos/diego-liverpool.png` |
| `demo-ar-reversed@demo.bank` | Sofía, a Mercado Libre charge already reversed | `web/public/casos/sofia-mercadolibre.png` |

Example, Lucía's duplicate Uber charge:

1. Sign in as `demo-mx-duplicate@demo.bank` with that same text as the password.
2. Attach `web/public/casos/lucia-uber.png`.
3. Write `no reconozco estas transacciones` and send.

The assistant should name the two Uber Trip charges of 312.40 MXN on 11 Jun 2026, at 09:00:00 and 09:00:04, and say they are 4 seconds apart. The same question works for the other seven images. For Ana, write `não reconheço estas transações`.

### Customers to try

The deployed demo has `*` in `DEMO_CUSTOMER_IDS`: the ID of any customer in the database signs in, with that same ID as the password. Many of the organizer's 150,000 customers are thin (no account with a balance, no recent purchase, or closed), and with those a screen comes back empty. These 25 were checked against the full dataset in Cloud SQL on 2026-10-05, and the chat field offers them:

| Customer ID (also the password) | Who | What to try |
|---|---|---|
| `DEMO-MX-KHIPU` | Valeria: two accounts, a credit card, a loan, three service bills | Khipear: `khipea 300 a mi tarjeta`, `pasa 500 de mi cuenta de ahorro a mi cuenta corriente`, `khipéale 200 a la cuenta 4000000033`, `paga la luz`. No purchases, so Mis finanzas is empty |
| `DEMO-MX-RECIBE` | Renata: one account in MXN (`4000000033`) and one in USD | The customer who receives. No card and no purchases |
| `DEMO-MX-DUPLICATE`, `DEMO-MX-FX`, `DEMO-CO-PENDING`, `DEMO-BR-PORTUGUESE`, `DEMO-AR-FRAUD`, `DEMO-CO-AMBIGUOUS`, `DEMO-MX-OWN-PURCHASE`, `DEMO-AR-REVERSED` | The eight customers of the table above (they also sign in by email): a credit card with about 30 purchases, a savings account, three service bills | Everything: the dispute of each case, Mis finanzas, paying the card or a bill |
| `CLI-35DQ8W3F31GF`, `CLI-T317OM6FPX6Q`, `CLI-VJ9MZ55A1TNX` | Organizer customers with the most to show: Carolina (Colombia, 5 accounts, 4 cards), Guadalupe Adriana (México, 2 accounts, 3 cards), Rosa (Argentina, 4 accounts, 1 card); 6 or 7 purchases in the last 90 days, in 4 or 5 categories | Everything, on the organizer's own data |
| `CLI-2HCAV5E4NFLH`, `CLI-714PN0OOE0WX`, `CLI-7LCAX6I6DX5F`, `CLI-9S264QYHP5E1`, `CLI-G3JO7K2GEVIF`, `CLI-MG4JR9V0OWYH`, `CLI-O4HNT6A74L3G`, `CLI-OHC9GVNM29TN`, `CLI-QAWTGLT3BESD`, `CLI-T2ZP6QXLFRLL`, `CLI-UJOW50WUBO63`, `CLI-XL20OA8V7GSM` | Organizer customers with an active account with a balance, a credit card with debt, 7 to 12 purchases in the last 90 days and three service bills | Everything |

Any other `CLI-...` ID signs in too, and money can be sent to any customer who has an active account in the same currency. What that customer sees depends on their data: without purchases in the last 90 days Mis finanzas says there is no spending, and without an account khipear answers that there is nothing to send from.

### If something fails

`make up` / `make smoke` print which piece failed:

| Message | Fix |
|---|---|
| `Ollama not found` | `brew install ollama` |
| `FAIL api` | Docker Desktop not running, or check `make logs` |
| `deps ... llm: error` | `make llm` |
| `deps ... db: error` | `make down && make up` |

## Actions

Off by default (`ACTIONS_ENABLED=false`): the agent, the routes and the screen are then exactly what they were
before. With them on, the agent **proposes** and the customer **confirms**:

| Action | Confirmation | Notes |
|---|---|---|
| Block a card | button | Refused if already blocked or closed; escalated if the bank suspended it |
| Cancel a card | button, with an irreversible warning | Escalated if it owes a balance or is past due |
| Open a payment inquiry | button | Refused for a reversed charge or a very recent pending one; priority from the fraud score and signals |
| Ask for a call | button | Morning, afternoon or evening |
| Set an alert | button | Duplicate charge, or a payment about to fall due |
| Email a summary | none | Balances, payment status or the receipt of an inquiry |
| Refund, change phone or email, raise a limit, new card | never automated | Sent to a person with the case |
| Transfer, pay | not one of these actions | Goes to khipear, which prepares it for the customer to confirm; refused only with `KHIPU_ENABLED=false` |

The cycle is propose, confirm, execute (retried up to three times), **verify** by reading the result back, and
audit. Three independent locks keep it to signed-in customers (the router, the skill, and the tools). A
stolen card is blocked **and** handed to a person.

To try it: put `ACTIONS_ENABLED=true` in `.env`, apply
`app/adapters/outbound/postgres/migrations/001_actions.sql`, restart, sign in at `/chat` as
`demo-mx-duplicate@demo.bank` and write `bloquea mi tarjeta` or `no reconozco el cargo de Uber, abre una consulta
y mándame el comprobante`. A card shows exactly what will be done; **Mensajes** lists what the system sent.

Mail is simulated unless `MAIL_MODE=smtp`; a real one goes only to the closed list `DEMO_INBOXES`, never to a
customer's synthetic address, and the screen says "accepted by the server", never "delivered". Details in
[actions.md](docs/documentation/technical/actions.md).

## Evaluation of the actions

The agent with actions was measured against the same agent without them (`--baseline`), on 65 scenarios (49
Spanish, 16 Portuguese) with a mechanical regression / held-out split fixed before any model answered. No
model judges anything: every verdict comes from the rows the actions left and from the replies. The 22
held-out scenarios were run once, blind, three times each:

| 66 attempts each | Without actions | With actions |
|---|---|---|
| Correct end state | 27% | 100% |
| Safe automated resolution | 0 of 18 | 18 of 18 |
| Needed a person: handed over correctly / missed / unnecessary | 8 / 10 / 12 | 18 / 0 / 0 |
| Unsafe outcomes confirmed | 0 | 0 |
| Latency p50 / p95 | 2.1 s / 6.6 s | 5.8 s / 12.3 s |
| Cost per attempt | 0.0010 USD | 0.0026 USD |

100% is **not** "perfect": 22 distinct scenarios (95% interval about 85-100%), and the same system scored **91%**
on the 43 regression scenarios it was tuned on, with four known, safe failures. What it shows, what it does
not, what was changed after seeing results and why: [evaluation_actions.md](docs/documentation/technical/evaluation_actions.md).
The raw reports, with every reply, are in
[evaluation_results/](docs/documentation/technical/evaluation_results/). The text-to-SQL skill has its own
evaluation and a quality floor that stops a deploy: [evaluation.md](docs/documentation/technical/evaluation.md).

```bash
uv run python -m evals.actions.run --repeats 1                         # regression, to study
uv run python -m evals.actions.run --baseline --repeats 1              # the agent without actions
uv run python -m evals.actions.run --split heldout --repeats 3         # held-out: once, blind
make eval-latency URL=http://localhost:8080 REPEATS=3                  # seconds per frequent question and khipear request
```

It needs the demo database, the actions migration and a model (Gemini with `LLM_PROVIDER=google_genai`, or Ollama); it builds
`DEMO-EVL-*` customers for each scenario and removes them. `make test` runs the 990 tests.

## Chat memory

Off by default (`CHAT_MEMORY_ENABLED=false`). With it on, the chat keeps what each customer said and was
answered, per customer: when they come back they see their earlier conversations (and can open or delete
them), and the agent is told, in a few lines the code writes, what the last eight were about. The agent is
never given the old messages, only that summary, with what the customer typed quoted as data and not as
instructions; a card number typed in the chat is kept by its last four digits. How it works, the safety
rules, how to turn it on in Cloud SQL and how to go back: [chat_memory.md](docs/documentation/technical/chat_memory.md).

## More

- **Use Gemini locally** (e.g. for evals): in `.env` set `LLM_PROVIDER=google_genai` and `GOOGLE_API_KEY`. In the cloud it's Gemini by default.
- **Code without Docker** (needs [uv](https://docs.astral.sh/uv/) and Node 24+): `make setup`, `make demo-data`, `make dev` (API :8080), `make web` (UI :3000), `make test`. For the microphone, `make models` downloads the speech models (about 0.8 GB) to `./models`; the Docker image has its own. `make setup` also enables a git pre-commit hook that runs the CI lint (`.githooks/pre-commit`).
- **Full dataset** (S3 keys from the data dictionary PDF): `make data-lite`, then `make bronze`, `make silver SOURCE=full` and `make db-load SOURCE=full` load it into the local Postgres (`make demo-data` goes back to the mini-set). See [data/pipeline.md](docs/documentation/technical/data/pipeline.md).
- **Telegram**: put a [@BotFather](https://t.me/BotFather) token in `TELEGRAM_BOT_TOKEN`, then `make telegram-local`.
- **Deploy** (GCP): two Cloud Run services, `factored-api` and `factored-web`, and Cloud SQL. See [Deploy to GCP](#deploy-to-gcp).
- **Architecture**: hexagonal. `app/domain` holds the rules, `app/application` the use cases, `app/adapters` HTTP/Telegram/MCP/LLM/Postgres. See [architecture.md](docs/documentation/technical/architecture.md) and the [ADRs](docs/documentation/technical/adr/).

## Add a skill

1. Create `app/adapters/inbound/agent/skills/<name>/SKILL.md` with frontmatter `name`, `description` (the router picks skills by it) and `mcp` (the server name), followed by the instructions. Optional: `sign_in: true` (only for a customer the token proved), `requires: actions` (only with `ACTIONS_ENABLED`; also needs sign-in) and `setting: <flag>` (the skill is left out when that setting is false).
2. Add the tools as a FastMCP server in `app/adapters/inbound/mcp/<server>.py`. Read the customer with `session_customer(ctx)` and **never take `customer_id` as a tool argument**.
3. Register the server in `SERVERS` (`app/adapters/inbound/agent/mcp_bridge.py`).
4. Add a route test in `tests/test_agent_graph.py`.

The graph doesn't change for a skill that only reads. Persona and scope live in `app/adapters/inbound/agent/AGENT.md`. Every tool that exists today is described in [docs/documentation/technical/mcp/](docs/documentation/technical/mcp/README.md).

## Let the SQL agent read a new table

`data_lookup` only sees the tables allowlisted in `app/domain/sql_scope.py`. To add one: create it in `schema.sql` (with `customer_id` if it holds customer data), list it in `OWNED` (has `customer_id`) or `REFERENCE`, load it in `data_pipeline/load.py`, and describe it in `app/adapters/inbound/mcp/dwh_catalog.md`. `tests/test_dwh.py` fails if a table in `schema.sql` is not classified.

## Deploy to GCP

`factored-api` (FastAPI + agent, root `Dockerfile`) and `factored-web` (static Next.js on nginx, `web/Dockerfile`) run on Cloud Run in `us-central1`; the API reads and writes Cloud SQL (Postgres 16, instance `CLOUD_SQL_INSTANCE`) through the Cloud SQL connector and calls Gemini on Vertex AI. Set `GCP_ACCOUNT`, `GCP_PROJECT_ID` and `CLOUD_SQL_INSTANCE` in `.env`.

One-time setup (project owner):

1. Enable `run`, `sqladmin`, `artifactregistry`, `cloudbuild`, `secretmanager` and `aiplatform`.
2. Create the Docker repository `factored` in Artifact Registry, and give the Compute default service account (Cloud Build) `artifactregistry.writer`, `logging.logWriter` and `storage.objectViewer`.
3. Create the Cloud SQL instance, the database `agent` and the user `agent`. Store the password in the secret `factored-db-password` and the URL `postgresql://agent:PASSWORD@/agent?host=/cloudsql/PROJECT:REGION:INSTANCE` in `factored-database-url`.
4. Create the service account `factored-api` with `cloudsql.client`, `aiplatform.user` and `secretmanager.secretAccessor`.
5. Create the secrets `jwt-secret` (signs the API's bearer tokens) and `operator-key` (opens the operator console), both with `openssl rand -hex 32`: the API does not start without them. The deploy also mounts `langfuse-public-key`, `langfuse-secret-key` and `factored-smtp-password`, so they must exist (the SMTP one may hold a placeholder while `MAIL_MODE=simulated`).
6. Load the data (this replaces `core`): in one terminal `make db-proxy` ([cloud-sql-proxy](https://cloud.google.com/sql/docs/postgres/sql-proxy)), in another `make etl-cloud CONFIRM=yes`. It runs the whole ETL on the dataset in `data/raw` and leaves its report in `docs/documentation/technical/data/quality_report_full.json`.

From there GitHub deploys: every push to `main` runs the tests and then deploys both services (`.github/workflows/deploy.yml`). Do not run `make deploy*` by hand (the last deploy wins) and never `make etl-cloud` on the shared database without telling the team: it replaces `core`. Setup, rollback and limits: [deploy.md](docs/documentation/technical/deploy.md). The API runs with `--max-instances 1` because conversation memory is in process.

## Repo map

```
app/adapters/inbound/agent/   agent graph (guard → router → skill_agent / refuse → handoff), AGENT.md, skills/
app/adapters/inbound/mcp/     FastMCP servers (one per skill; `actions.py` and `transfers.py` propose, never execute)
app/domain/                   the rules: actions policy, risk signals, routing, texts, claims
app/application/actions.py    the gateway: propose, confirm, execute, verify, audit
app/adapters/outbound/        Postgres queries + schema.sql, LLM factory
.github/workflows/           lint + tests on every PR; deploy of both services on push to main
evals/                        text_to_sql/ (quality floor of a deploy) and actions/ (safety of acting)
data_pipeline/                raw → bronze → sample → silver → Postgres
data/sample/                  committed mini-set of the organizer data + demo fixtures
web/                          Next.js chat (own image: web/Dockerfile)
docs/                         problem/, strategy_analysis_NN/ (one per teammate), documentation/
```
