# 0001. Stack and single-container deployment

- Status: accepted; deployment superseded by [0003](0003-split-web-and-api.md)
- Date: 2026-09-26

## Context
Four people build in parallel for nine days. The submission needs a public repo, a deployed link and a credible route to production. The dataset lives in a read-only AWS S3 bucket; the rules allow any cloud.

## Decision
- **Monorepo**, one Python project managed with **uv** (layout superseded by [ADR 0002](0002-hexagonal-layout.md)), plus a **Next.js (TypeScript)** app in `web/`.
- **Backend:** FastAPI serves the API, the Telegram webhook and the static web build.
- **Agent:** LangGraph + LangChain (`init_chat_model`). **Gemini** by default (AI Studio key or Vertex AI via `GOOGLE_GENAI_USE_VERTEXAI`).
- **Tools:** FastMCP server; the agent consumes it through `langchain-mcp-adapters`.
- **Data:** boto3 download to `data/raw` → DuckDB → Parquet (bronze/silver/gold), pandera contracts.
- **UI:** Next.js static export + Tailwind + shadcn/ui + Motion.
- **Channel:** Telegram as the WhatsApp stand-in (text, voice notes, photos).
- **Deploy:** one multi-stage Docker image → **one Cloud Run service on GCP**. `docker compose` for local.
- **Tracing:** Langfuse.

AWS is only the data source. Nothing we run is deployed there.

## Alternatives considered
- **Separate UI and API services:** more flexible, but two deploys, CORS and more cost for no demo benefit.
- **Streamlit:** faster, but it looks generic and does not suit a product-grade chat and agent console.
- **uv workspace with several packages:** cleaner boundaries, but too much ceremony for a nine-day build.

## Consequences
- One URL, one image, one set of logs: simple to operate and to explain.
- The image is ~1.9 GB (data libraries included). If cold starts hurt, move the data dependencies to a separate dependency group.
- Raw data never reaches Cloud Run. Only small gold artifacts do (baked into the image or pulled from GCS, to be decided).
- UI and API scale together. That is acceptable at demo scale and noted as future work.
