import pytest

from app.adapters.inbound.agent import skills
from app.adapters.outbound import speech
from app.config import get_settings


@pytest.fixture(autouse=True)
def no_speech_models(monkeypatch, tmp_path):
    """Tests never load the real speech models, even on a machine that has them (`make models`)."""
    monkeypatch.setattr(speech, "MODELS", tmp_path / "models")


@pytest.fixture(autouse=True)
def actions_start_off(monkeypatch):
    """Actions are off and mail is simulated at the start of every test, whatever the developer's
    `.env` says (it may turn actions on to try them, or send real mail). A test that needs them
    on says so itself. The caches that depend on the setting are cleared on both sides."""
    monkeypatch.setenv("ACTIONS_ENABLED", "false")
    monkeypatch.setenv("MAIL_MODE", "simulated")

    def forget() -> None:
        get_settings.cache_clear()
        skills.load_skills.cache_clear()
        skills.agent_prompt.cache_clear()

    forget()
    yield
    forget()
