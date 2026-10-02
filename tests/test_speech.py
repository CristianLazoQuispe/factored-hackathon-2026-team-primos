"""Voice in the chat: who may use the speech routes, and what goes to and comes from the models."""

import wave
from io import BytesIO

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.adapters.inbound import http
from app.adapters.inbound.auth import issue_token
from app.adapters.outbound import speech
from app.config import get_settings

RATE = 24_000


@pytest.fixture
def cloud(monkeypatch):
    """The deployed configuration: no local shortcut around the token."""
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "cloud")
    monkeypatch.setattr(settings, "jwt_secret", "s" * 40)


@pytest.fixture
def kokoro(monkeypatch):
    """Replace the voice model: records what it is asked to read and answers half a second."""
    asked = []

    class FakeKokoro:
        def create(self, text, voice, lang):
            asked.append({"text": text, "voice": voice, "lang": lang})
            return np.full(RATE // 2, 2.0, dtype=np.float32), RATE  # louder than a WAV can hold

    monkeypatch.setattr(speech, "kokoro", FakeKokoro)
    return asked


def test_both_models_are_loaded_before_the_first_request(monkeypatch, tmp_path):
    loaded = []
    monkeypatch.setattr(speech, "MODELS", tmp_path)
    monkeypatch.setattr(speech, "whisper", lambda: loaded.append("whisper"))
    monkeypatch.setattr(speech, "kokoro", lambda: loaded.append("kokoro"))

    with TestClient(http.app):
        assert sorted(loaded) == ["kokoro", "whisper"]


def bearer(customer_id: str) -> dict:
    return {"Authorization": f"Bearer {issue_token(customer_id)[0]}"}


def test_the_recording_reaches_whisper_and_its_text_comes_back(cloud, monkeypatch):
    heard = []
    monkeypatch.setattr(
        speech, "transcribe", lambda audio: heard.append(audio) or ("¿Cuál es mi saldo?", "es")
    )

    response = TestClient(http.app).post(
        "/api/speech/transcribe",
        content=b"webm-bytes",
        headers={"Content-Type": "audio/webm", **bearer("CLI-A")},
    )

    assert response.json() == {"text": "¿Cuál es mi saldo?", "language": "es"}
    assert heard == [b"webm-bytes"]


def test_the_reply_comes_back_as_audio(cloud, monkeypatch):
    monkeypatch.setattr(speech, "synthesize", lambda text, language: f"{language}:{text}".encode())

    response = TestClient(http.app).post(
        "/api/speech/synthesize", json={"text": "Olá", "language": "pt"}, headers=bearer("CLI-A")
    )

    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"pt:Ol\xc3\xa1"


@pytest.mark.parametrize(
    "call",
    [
        {"url": "/api/speech/transcribe", "content": b"webm-bytes"},
        {"url": "/api/speech/synthesize", "json": {"text": "Hola", "language": "es"}},
    ],
)
def test_speech_needs_a_token_outside_local(cloud, call):
    assert TestClient(http.app).post(**call).status_code == 401


@pytest.mark.parametrize(
    ("language", "voice", "lang"),
    [("es", "ef_dora", "es"), ("pt", "pf_dora", "pt-br"), ("en", "ef_dora", "es")],
)
def test_the_voice_follows_the_language_the_customer_spoke(kokoro, language, voice, lang):
    speech.synthesize("Hola", language)

    assert kokoro == [{"text": "Hola", "voice": voice, "lang": lang}]


def test_markdown_symbols_are_not_read_aloud(kokoro):
    speech.synthesize("## Saldo\nTienes **$1,234.56** en `ahorros`", "es")

    assert kokoro[0]["text"] == " Saldo\nTienes $1,234.56 en ahorros"


def test_the_audio_is_a_wav_the_browser_can_play(kokoro):
    with wave.open(BytesIO(speech.synthesize("Hola", "es"))) as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")

        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, RATE)
    assert len(samples) == RATE // 2
    assert set(samples) == {32767}  # clipped, not wrapped around into noise
