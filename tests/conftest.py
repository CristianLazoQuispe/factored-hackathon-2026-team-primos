import pytest

from app.adapters.outbound import speech


@pytest.fixture(autouse=True)
def no_speech_models(monkeypatch, tmp_path):
    """Tests never load the real speech models, even on a machine that has them (`make models`)."""
    monkeypatch.setattr(speech, "MODELS", tmp_path / "models")
