# Deploy: GitHub Actions → Cloud Run

Every push to `main` runs lint and tests, then the [eval gate](#the-eval-gate), then deploys the two
Cloud Run services that the team already uses, with the same build and deploy as `make deploy-api` and
`make deploy-web`, plus the feature flags and mail settings, which only the workflow sets (a deploy by
hand with `make deploy-api` leaves them at the code's defaults, so khipear would be on):

| Service | Image | What it is |
|---|---|---|
| `factored-api` | `factored/api:<git sha>` | FastAPI + agent. Talks to Cloud SQL, Gemini on Vertex AI |
| `factored-web` | `factored/web:<git sha>` | Next.js static export served by nginx. The API URL is baked in at build time |

Pull requests run lint and tests only. Workflow: `.github/workflows/deploy.yml`.

GitHub authenticates to GCP with **Workload Identity Federation**: there is no service-account key
anywhere. Settings live in repository *variables*; there are no GitHub secrets.

## What already exists in `factored-510201` (reused, not recreated)

- Region `us-central1`; Artifact Registry repo `factored`.
- Cloud SQL `factored-510201:us-central1:factored-db` (Postgres 16), database and user `agent`.
  It holds `core`, `ops` and the `dwh_reader` role. `core` is loaded by `make etl-cloud`
  (see [data/pipeline.md](data/pipeline.md)): it **replaces** `core`, so coordinate before running it.
- Runtime account `factored-api@…` with `cloudsql.client`, `secretmanager.secretAccessor` and
  `aiplatform.user` (so it can read every secret and call Gemini through Vertex AI: no API key).
- Secrets `factored-database-url`, `factored-db-password`, `jwt-secret` (signs the bearer tokens) and
  `operator-key` (opens the operator console; read it with
  `gcloud secrets versions access latest --secret operator-key`). The deploy also mounts
  `langfuse-public-key`, `langfuse-secret-key` and `factored-smtp-password`: they must exist, even
  while mail is simulated.
- Secrets `langfuse-public-key` and `langfuse-secret-key`: the API keys of the team's project in
  Langfuse Cloud (US region, `https://us.cloud.langfuse.com`), where the agent's traces go. To use
  another Langfuse project, add a new version to both secrets and redeploy.

## One-time setup (done on 2026-09-30; kept for the next repository)

Run with `gcloud` logged in as an owner of the project. Confirm the project first:
`gcloud config get-value project` must print `factored-510201`.

```bash
export PROJECT_ID=factored-510201   REGION=us-central1
export GH_REPO=CristianLazoQuispe/factored-hackathon-2026-team-primos   # the repo allowed to deploy
export DEPLOYER_SA=gh-deployer@$PROJECT_ID.iam.gserviceaccount.com
export API_SA=factored-api@$PROJECT_ID.iam.gserviceaccount.com
export WEB_SA=531756916664-compute@developer.gserviceaccount.com   # factored-web's current account
gcloud config set project $PROJECT_ID
gcloud services enable sts.googleapis.com cloudresourcemanager.googleapis.com
```

**1. The key that signs the API's bearer tokens, and the key of the operator console.** The API
refuses to start without either.

```bash
for secret in jwt-secret operator-key; do
  gcloud secrets describe $secret >/dev/null 2>&1 \
    && echo "$secret already exists" \
    || (openssl rand -hex 32 | tr -d '\n' | gcloud secrets create $secret --data-file=-)
done
```

**2. The account GitHub deploys as.**

```bash
gcloud iam service-accounts create gh-deployer --display-name="GitHub deployer"
gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$DEPLOYER_SA --role=roles/run.admin
gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$DEPLOYER_SA --role=roles/artifactregistry.writer
gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$DEPLOYER_SA --role=roles/aiplatform.user
for sa in $API_SA $WEB_SA; do
  gcloud iam service-accounts add-iam-policy-binding $sa \
    --member=serviceAccount:$DEPLOYER_SA --role=roles/iam.serviceAccountUser
done
```

The `aiplatform.user` binding is for the eval gate, which calls Gemini as this account.

**3. Let GitHub (only this repository) become that account.**

```bash
gcloud iam workload-identity-pools create github --location=global --display-name="GitHub"
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location=global --workload-identity-pool=github \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='$GH_REPO'"
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
gcloud iam service-accounts add-iam-policy-binding $DEPLOYER_SA \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$GH_REPO"
echo "GCP_WIF_PROVIDER=projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-provider"
```

The pool was created for the working repository (`CristianLazoQuispe/Factored2026`). To move the deploy
to another repository, repeat the last `add-iam-policy-binding` with the new `GH_REPO`, and update the
provider condition with `gcloud iam workload-identity-pools providers update-oidc github-provider
--location=global --workload-identity-pool=github --attribute-condition="assertion.repository=='NEW/REPO'"`.

**4. GitHub variables.** Six are required; six more are optional (`ACTIONS_ENABLED`, `KHIPU_ENABLED`,
`MAIL_MODE`, `MAIL_FROM`, `SMTP_USER`, `DEMO_INBOXES`), each off or empty when unset. With the GitHub CLI (needs `brew install gh` and `gh auth login`;
repository admin rights):

```bash
R=CristianLazoQuispe/factored-hackathon-2026-team-primos
gh variable set GCP_PROJECT_ID     --repo $R --body "factored-510201"
gh variable set GCP_REGION         --repo $R --body "us-central1"
gh variable set CLOUD_SQL_INSTANCE --repo $R --body "factored-db"
gh variable set GCP_DEPLOYER_SA    --repo $R --body "gh-deployer@factored-510201.iam.gserviceaccount.com"
gh variable set GCP_WIF_PROVIDER   --repo $R --body "projects/531756916664/locations/global/workloadIdentityPools/github/providers/github-provider"
gh variable set DEMO_CUSTOMER_IDS  --repo $R --body "DEMO-MX-DUPLICATE,DEMO-CO-PENDING,DEMO-MX-FX,DEMO-BR-PORTUGUESE,DEMO-AR-FRAUD,CLI-J0N40EZVP1P6,CLI-XKD238N6EUVH,CLI-AGDPF9SUW2Q4,DEMO-MX-KHIPU"
gh variable list --repo $R
```

`DEMO_CUSTOMER_IDS` is the list `GET /api/demo-customers` returns and the IDs that can sign in (the password is the same ID); the eight demo emails in the root README sign in too. `DEMO-MX-KHIPU` is the customer with two accounts, a card and a loan for khipear, and it only signs in by ID. Add `*` to the list and the ID of any customer in the database signs in too; `GET /api/demo-customers` still returns only the IDs written in it.

## Day to day

1. Work on your `dev-<name>` branch (only its owner can push to it), open a PR to `dev` (lint + tests
   run), then a PR from `dev` to `main`. Repository rulesets reject direct pushes to `dev` and `main`
   and require a green `test`.
2. Merging into `main` deploys: `test` → `eval-gate` → `deploy-api` → `deploy-web`, about 13 minutes (the
   gate adds about 8). Follow it with
   `gh run watch --repo CristianLazoQuispe/factored-hackathon-2026-team-primos`; re-run it without a commit with
   `gh workflow run "CI and deploy to Cloud Run" --ref main`.
3. Do not run `make deploy`, `deploy-api` or `deploy-web` by hand: the last deploy wins and can bring
   back an old image.

What a deploy does **not** do:

- It does not touch the database. A change in `schema.sql` reaches Cloud SQL only with
  `make etl-cloud CONFIRM=yes`, which rebuilds and replaces `core`. New code reads the new columns,
  so run it **before** merging the change to `main`, and coordinate first.
  Khipear is such a change: it needs `core.products.account_number` and `ops.transfers`. The
  workflow deploys with `KHIPU_ENABLED=false` unless the repository variable `KHIPU_ENABLED` is
  `true`: off, the skill is not offered and a transfer is refused as before. Set the variable
  only after the reload; on without it, a transfer fails (the tool errors on the missing table and column) and the
  customer gets no proposal.
- It does not create secrets such as `jwt-secret` or `operator-key`.
- It **replaces** every environment variable of `factored-api`. A variable added by hand in the console
  is lost on the next deploy: add it to `.github/workflows/deploy.yml`.
- It deploys on every push to `main`, even a docs-only one, and `deploy-web` adds one more API revision
  (it refreshes `CORS_ORIGINS`).
- If `deploy-api` succeeds and `deploy-web` fails, the API is new and the web old until it is fixed.

Roll back (both services together; run `--to-latest` on each once it is fixed):

```bash
gcloud run revisions list --service factored-api --region us-central1 --limit 5
gcloud run services update-traffic factored-api --region us-central1 --to-revisions=<previous>=100
gcloud run services update-traffic factored-web --region us-central1 --to-revisions=<previous>=100
```

Still to do (not applied yet):

- **Let only `main` deploy:** add `&& assertion.ref=='refs/heads/main'` to the provider condition with
  `gcloud iam workload-identity-pools providers update-oidc github-provider --location=global
  --workload-identity-pool=github --attribute-condition="assertion.repository=='<repo>' &&
  assertion.ref=='refs/heads/main'"`.
- **Trying the gate from a branch stops working** once only `main` can authenticate: that run uses the
  same provider. Tick `skip_eval_gate` or try it from `main`.
- **A budget alert** in Billing: the public endpoints can call Gemini on Vertex AI.

## The eval gate

Between `test` and `deploy-api`, the `eval-gate` job asks Gemini the regression questions of
`evals/text_to_sql/` and compares the answers with the floor in `evals/text_to_sql/baseline.json`. If
the agent got worse, nothing is deployed: `deploy-web` waits for `deploy-api`, which waits for the gate.
What it measures, and what it does not, is in [evaluation.md](evaluation.md).

- **It does not run on pull requests**, only on a push to `main` and on a manual run.
- **It needs Gemini capacity.** It runs the 31 regression questions three times on the `global` Vertex endpoint
  (93 to 125 calls; the job takes about 8 minutes with its setup) and judges them together. A run that proves nothing because the provider refused too many
  calls is tried once more after 90 seconds; if it still proves nothing, the deploy stops. Run the
  workflow again a few minutes later.
- **It authenticates as `gh-deployer`**, which therefore needs `roles/aiplatform.user` (see the setup).

Try the gate from a branch (Actions, *Run workflow*, or the command below). Only the gate runs: a
branch never deploys.

```bash
gh workflow run deploy.yml --ref <branch>
```

Emergency: deploy `main` without the gate, to ship a fix. The run shows a warning; afterwards, find out
why the gate failed.

```bash
gh workflow run deploy.yml --ref main -f skip_eval_gate=true
```

The summary of the job shows the table of the floor and, when the provider refused calls, its first
error. The `eval-report` artifact has every query the model wrote.

## First deploy, by hand, with a canary (how it was done the first time)

Build the API image, deploy it **without traffic** under a tag, test it on its own URL, and only then
move traffic. Nobody is affected until the last step.

```bash
export PROJECT=factored-510201 REGION=us-central1 TAG=$(git rev-parse --short HEAD)
export REGISTRY=$REGION-docker.pkg.dev/$PROJECT/factored
gcloud builds submit --project $PROJECT --region $REGION --tag $REGISTRY/api:$TAG .
gcloud run deploy factored-api ... --no-traffic --tag canary      # same flags as `make deploy-api`
curl -s https://canary---factored-api-<hash>-uc.a.run.app/health
```

Then build the web against the API URL, deploy it with `--no-traffic --tag canary`, and switch both
services in a row: `update-traffic --to-revisions=<new>=100` (API) and `--to-tags canary=100` (web),
followed by `--to-latest` and `--remove-tags canary` so later deploys go live on their own.
Roll back with `update-traffic --to-revisions=<previous revision>=100` on **both** services.

## Gotchas we hit

- **zsh and colons:** write `"${PROJECT}:${REGION}:factored-db"` with braces. `$REGION:factored-db`
  is read as a path modifier and produces a malformed Cloud SQL instance.
- **Define the variables in the same terminal** before running a block; an empty `$PROJECT` produces
  misleading errors (`argument --project: expected one argument`).
- **New service accounts take a few seconds to propagate:** if `add-iam-policy-binding` says the
  account does not exist right after creating it, run the command again.
- **Do not paste trailing `# comments` in zsh:** the shell passes them as arguments.
- **A wrong provider condition fails silently:** verify it with
  `gcloud iam workload-identity-pools providers describe github-provider --location=global
  --workload-identity-pool=github --format="value(attributeCondition)"`.
- **`make etl-cloud` replaces `core` on the shared database.** It refuses to run without
  `CONFIRM=yes`, builds the new schema aside and swaps it in at the end, so a failed load changes
  nothing; a successful one changes what every teammate's deployed agent reads.

## Using the deployed API

Every protected call needs `Authorization: Bearer <jwt>`. The token lives 15 minutes.

```bash
API=$(gcloud run services describe factored-api --region us-central1 --format='value(status.url)')
TOKEN=$(curl -s $API/api/auth/token -H 'content-type: application/json' \
  -d '{"email":"demo-mx-duplicate@demo.bank","password":"demo-mx-duplicate@demo.bank"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s $API/api/chat -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"message":"no reconozco un cargo de Uber"}'
```

Without a token `/api/chat` answers `401`; a wrong email or password gets `401` from `/api/auth/token`, and the ninth try in a minute gets `429`. In Swagger (`$API/docs`) paste the token in **Authorize**.

## Known limits (state them in the submission)

- **Khipear writes to the stand-in core.** A confirmed transfer changes balances and adds
  movements in `core`, the team's copy of the bank's data, not in a core banking system, and
  `make etl-cloud` undoes them (`ops.transfers` keeps the record). The limits to another customer
  (USD 1,000 per operation, USD 3,000 per day) are a team assumption, set with
  `KHIPU_LIMIT_PER_OPERATION_USD` and `KHIPU_LIMIT_PER_DAY_USD`.

- **`--max-instances 1`.** Conversation memory is an in-process `InMemorySaver`: with two instances a
  customer's thread would vanish between requests. Real fix: a Postgres checkpointer.
- **The operator console forgets.** `/consola` on the web shows a mirror of the chats that lives in the
  same process: chats and the handoff queue are lost when the instance stops (idle, or any deploy).
  It also needs the single instance. Real fix: write them to `ops.conversations`, `ops.messages` and
  `ops.handoff_cases`, which `schema.sql` already defines.
- **Voice makes `factored-api` bigger and spoken turns slower.** The image carries faster-whisper
  `small` and Kokoro (0.8 GB) and the service runs with `--memory 4Gi --cpu 4`: with both models
  loaded the local container used 1.3 GiB, and 2.5 GiB while generating 73 s of audio in one
  request. Measured locally (Ollama), the agent's answer to a spoken question is ready 20-28 s
  after the microphone is released (about 4 s of transcription, the rest is the agent); with the
  voice on, text and voice then start together about 2 s later. Both models are loaded while the
  container starts (5-10 s), so that no spoken message waits for them.
- **One shared operator key.** Whoever has `OPERATOR_KEY` reads every chat; there are no operator
  accounts. Telegram chats do not reach the console.
- **The token endpoint checks a demo password.** Eight synthetic emails and the IDs in `DEMO_CUSTOMER_IDS`; the password is that same text. Three wrong passwords lock that account for 15 minutes. Eight tries per minute per client, then `429`. The lock lives in the API process, not in the database. In production the bank's identity provider replaces it; the rest stays. The Telegram webhook has its own secret.
- **Conversations are keyed by customer**, so nobody can continue another customer's thread.
- **`/docs` (Swagger) is public.**
- **Cloud SQL has a public IP** (`ipv4Enabled`); the app reaches it through the Cloud SQL socket.
- **Cold start.** With no minimum instances, the first request after idle is slow.
- **A deploy now waits for Gemini.** The eval gate needs the model to answer: if Vertex AI is saturated for
  a while the gate proves nothing and the deploy stops. The emergency switch is in
  [The eval gate](#the-eval-gate).

## Troubleshooting

- *`unauthorized_client` in Actions*: wrong `GH_REPO` in the provider condition, or wrong
  `GCP_WIF_PROVIDER`.
- *Permission denied on deploy*: the deployer lacks `serviceAccountUser` on the account the service runs
  as, or (Cloud SQL) `roles/cloudsql.client` / `roles/cloudsql.viewer`.
- *Revision fails to start*: read its logs. A `ValueError` mentioning `JWT_SECRET` or `OPERATOR_KEY`
  means that secret is missing or shorter than 32 characters; one mentioning `DATABASE_URL` means the
  secret points to a local host.
- *The browser shows a CORS error*: `CORS_ORIGINS` on `factored-api` must list the URLs of
  `factored-web` (the workflow updates it after deploying the web), and the API must allow the
  `Authorization` header.
- *`/health/ready` says `db: error`*: the Cloud SQL instance is not attached to the service.
- *`eval-gate` says `INCONCLUSIVE`*: the provider refused too many calls. Read `the first refusal was:`
  in the summary: `403` means `gh-deployer` lacks `roles/aiplatform.user`; `429` is shared Gemini
  capacity, so run the workflow again in a few minutes.
- *`eval-gate` fails with `gold SQL of <case> fails`*: the data model changed under a case of the eval; fix
  the gold query in `evals/text_to_sql/cases.py`.
- *`eval-gate` fails while loading the data*: it downloads a DuckDB extension, so a network hiccup of the
  runner can fail it; run it again.
