"""The only chat-model factory. Provider and model come from settings (APP_ENV, LLM_*)."""

from functools import lru_cache

import httpx
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from app.config import Role, get_settings

MAX_RETRIES = 2
REQUEST_TIMEOUT_S = 30


@lru_cache
def chat_model(role: Role = "fast") -> BaseChatModel:
    settings = get_settings()
    kwargs = {}
    if settings.provider == "ollama":
        # Thinking mode adds latency with little gain for NLU; 8k context keeps RAM under ~8 GB.
        kwargs = {"base_url": settings.ollama_base_url, "reasoning": False, "num_ctx": 8192}
    else:  # bounded retries: the library default (6 tries, no timeout) can hang a customer turn
        kwargs = {"max_retries": MAX_RETRIES, "timeout": REQUEST_TIMEOUT_S}
    return init_chat_model(settings.model(role), model_provider=settings.provider, **kwargs)


def ping() -> str:
    """Check the configured LLM can serve requests, without spending tokens."""
    settings = get_settings()
    model = settings.model("fast")
    if settings.provider == "ollama":
        try:
            tags = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=2).json()
        except httpx.ConnectError as error:
            url = settings.ollama_base_url
            raise RuntimeError(f"Ollama not reachable at {url}: run `make llm`") from error
        if model not in {m["name"] for m in tags["models"]}:
            raise RuntimeError(f"{model} is not pulled: run `make llm`")
    elif not settings.llm_configured:
        raise RuntimeError("no Gemini credentials (GOOGLE_API_KEY): the agent only echoes")
    return f"ok ({settings.provider} {model})"
