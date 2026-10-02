"""Speech for the web chat: faster-whisper hears the customer, Kokoro reads the agent's reply.
Both run on CPU from the files in `models/` (`make models`; the image downloads them at build)."""

import logging
import re
import wave
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from time import perf_counter

import numpy as np
from faster_whisper import WhisperModel
from kokoro_onnx import Kokoro

MODELS = Path(__file__).parents[3] / "models"
# Kokoro voice and espeak language of each reply language. The agent answers in Spanish or
# Portuguese, so any language other than Portuguese is read in Spanish.
VOICES = {"es": ("ef_dora", "es"), "pt": ("pf_dora", "pt-br")}
MARKDOWN = re.compile(r"[*#`]")  # Kokoro reads these symbols aloud, by name

log = logging.getLogger(__name__)  # sizes and times only: what was said stays out of the logs


@lru_cache
def whisper() -> WhisperModel:
    started = perf_counter()
    model = WhisperModel(str(MODELS / "whisper-small"), device="cpu", compute_type="int8")
    log.info("loaded whisper in %.1f s", perf_counter() - started)
    return model


@lru_cache
def kokoro() -> Kokoro:
    started = perf_counter()
    model = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    log.info("loaded kokoro in %.1f s", perf_counter() - started)
    return model


def transcribe(audio: bytes) -> tuple[str, str]:
    """What a recording says and the language Whisper heard it in (`es`, `pt`, ...)."""
    # The filter drops silence first: without it, a silent recording keeps Whisper busy for
    # most of a minute before it answers with no text.
    model, started = whisper(), perf_counter()
    segments, info = model.transcribe(BytesIO(audio), vad_filter=True)
    text = " ".join(segment.text.strip() for segment in segments)
    log.info(
        "transcribed %.1f s of audio in %.1f s: %d characters, language %s",
        info.duration,
        perf_counter() - started,
        len(text),
        info.language,
    )
    return text, info.language


def synthesize(text: str, language: str) -> bytes:
    """`text` read aloud, as a WAV file."""
    voice, lang = VOICES.get(language, VOICES["es"])
    model, started = kokoro(), perf_counter()
    samples, rate = model.create(MARKDOWN.sub("", text), voice=voice, lang=lang)
    log.info(
        "synthesized %d characters into %.1f s of audio in %.1f s, voice %s",
        len(text),
        len(samples) / rate,
        perf_counter() - started,
        voice,
    )
    out = BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return out.getvalue()
