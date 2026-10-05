# 0003. Web and API as separate Cloud Run services, Postgres on Cloud SQL

- Status: accepted
- Date: 2026-09-30
- Supersedes the deployment part of [0001](0001-stack-and-deploy.md)

## Context
ADR 0001 shipped one image: FastAPI served the static Next.js build. The team wants to deploy and scale the web and the API independently, and the agent needs a real database in the cloud: `app/config.py` refuses a local `DATABASE_URL` when `APP_ENV` is not `local`.

## Decision
- **`factored-api`**: root `Dockerfile`, FastAPI + agent only. Reads Cloud SQL over the Cloud Run connector (`/cloudsql/...` socket), with `DATABASE_URL` from Secret Manager. Gemini through Vertex AI with the `factored-api` service account. CORS allows the origins in `CORS_ORIGINS`.
- **`factored-web`**: `web/Dockerfile`, Next.js static export on nginx. The API URL is baked in at build time (`NEXT_PUBLIC_API_URL`), so the web is built after the API is deployed.
- **Cloud SQL**: Postgres 16, `db-f1-micro`, public IP with no authorized networks; only the connector and the Cloud SQL Auth Proxy reach it. The sample is loaded from a laptop through the proxy (`make db-load-cloud`).
- `docker compose` mirrors it locally: `app` on :8080, `web` on :3000.

## Alternatives considered
- **Keep one service:** one URL and no CORS, but the web can't be released or scaled on its own.
- **Web on Firebase Hosting or a bucket + CDN:** cheaper for static files, but a second platform to operate; Cloud Run keeps both services on the same tooling.
- **Private IP + VPC connector for Cloud SQL:** stronger isolation, more setup and cost; the connector already authenticates and encrypts.

## Consequences
- Two deploys, and CORS must list the web URL (`make deploy-web` sets it).
- Conversation memory is in process (`InMemorySaver`), so the API runs with `--max-instances 1` until the checkpointer moves to Postgres.
- `/api/demo-customers` is local-only, so on the deployed web the customer ID is typed by hand.
  (Changed later: the route is served wherever `DEMO_CUSTOMER_IDS` is set, and the sign-in field
  offers that list.)
