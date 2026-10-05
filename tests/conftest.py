import warnings

import pytest

from app.adapters.inbound.agent import skills
from app.adapters.outbound import speech
from app.config import get_settings
from evals.actions.world import purge as purge_leftovers


@pytest.fixture(autouse=True)
def no_speech_models(monkeypatch, tmp_path):
    """Tests never load the real speech models, even on a machine that has them (`make models`)."""
    monkeypatch.setattr(speech, "MODELS", tmp_path / "models")


def clean() -> None:
    """Best effort: a failed clean-up warns and does not take every test of the project down."""
    try:
        purge_leftovers()
    except Exception as error:  # noqa: BLE001
        warnings.warn(f"could not remove what a stopped run left behind: {error}", stacklevel=2)


@pytest.fixture(scope="session", autouse=True)
def no_leftovers_of_the_action_tests():
    """What an interrupted run left in the developer's database is removed before this one starts
    and after it ends (see `purge_leftovers`)."""
    clean()
    yield
    clean()


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
