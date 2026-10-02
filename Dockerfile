# API image: FastAPI + agent. The web has its own image (web/Dockerfile) and Cloud Run service.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app/ app/
COPY data_pipeline/ data_pipeline/
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.adapters.inbound.http:app --host 0.0.0.0 --port ${PORT}"]
