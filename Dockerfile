# API image: FastAPI + agent. The web has its own image (web/Dockerfile) and Cloud Run service.

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
# Speech models (app/adapters/outbound/speech.py; `make models` gets the same files). They come
# before the code so that a code change does not download them again.
ADD https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx \
    https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin \
    models/
RUN .venv/bin/python -c "from faster_whisper import download_model; download_model('small', output_dir='models/whisper-small')"
COPY app/ app/
COPY data_pipeline/ data_pipeline/
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH" PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.adapters.inbound.http:app --host 0.0.0.0 --port ${PORT}"]
