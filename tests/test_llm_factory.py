"""The chat-model factory: how many times the client retries on its own is the caller's choice."""

from types import SimpleNamespace

from app.adapters.outbound import llm


def capture(monkeypatch, provider: str) -> dict:
    seen = {}

    def fake_init(model, model_provider, **kwargs):
        seen.update(kwargs)
        return object()

    settings = SimpleNamespace(
        provider=provider, model=lambda role: "m", ollama_base_url="http://x"
    )
    monkeypatch.setattr(llm, "init_chat_model", fake_init)
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    return seen


def build(**kwargs):
    return llm.chat_model.__wrapped__("fast", **kwargs)  # the cache would hide the second call


def test_the_client_retries_as_the_app_always_did_unless_told_otherwise(monkeypatch):
    seen = capture(monkeypatch, "google_genai")
    build()
    assert seen["max_retries"] == llm.MAX_RETRIES


def test_a_caller_that_does_its_own_retries_can_turn_the_clients_off(monkeypatch):
    seen = capture(monkeypatch, "google_genai")
    build(max_retries=1)
    assert seen["max_retries"] == 1
