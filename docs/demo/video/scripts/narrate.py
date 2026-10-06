"""Narration for the demo video, one WAV per scene, with Kokoro (the repo's local TTS).

Run from the repo root:  uv run python docs/demo/video/scripts/narrate.py [voice]
"""
import sys
from pathlib import Path

import wave

import numpy as np
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parents[1] / "public" / "vo"
VOICE = sys.argv[1] if len(sys.argv) > 1 else "af_heart"

LINES = {
    "01-intro": "It's Sunday, eleven p.m. Somewhere, someone sees a charge they don't recognize. Today, thirty-nine percent of them never get an answer. The rest wait thirty-eight hours.",
    "02-numbers": "Three point eight million dollars sit open in complaints. Three hundred seventy million in declined transactions over three years, and each one is a question nobody answers at night. Sixty-five percent of complaints arrive outside office hours. So we built Quipu: the agent that answers at eleven p.m., checks the bank's own data, and acts, with every decision verified.",
    "03-phone": "Two identical charges, four seconds apart. Lucía opens Quipu.",
    "04-voice": "She attaches the screenshot and sends a voice note. Voice, text, or a photo of the statement. Spanish or Portuguese. Quipu transcribes it with Whisper, reads the image, and checks the bank's own data.",
    "05-resolved": "Same charge twice, four seconds apart. Quipu proposes: open the inquiry, block the card. One tap to confirm. Done, verified, and the receipt is already in her inbox. Eleven oh four p.m.",
    "06a-tour": "And it's not only disputes. Talk to Quipu, and it talks back, with a real answer from the bank's data. Balances, debts, your spending. Transfers and bill payments with khipear, where only the customer's Confirm button moves money.",
    "06b-tour": "It also speaks Portuguese and remembers your past chats. When a person is needed, the operator console gets the case file, not a transcript. And management sees who resolved what, and how fast.",
    "07-architecture": "Under the hood: a LangGraph agent behind FastAPI, skills as MCP servers, Postgres with audit, deployed on Cloud Run with Gemini on Vertex, and Ollama locally. Three rules. Identity comes from the JWT, never from the model. SQL is read-only and scoped to one customer. And nothing is reported as done until the system reads it back.",
    "07b-engineering": "And we shipped it like a product. Feature branches merge into dev, and dev into main. Every pull request runs lint and nine hundred ninety tests. A push to main runs the text-to-SQL evaluation as a gate: below the quality floor, nothing deploys. Above it, GitHub Actions builds both images and deploys to Cloud Run.",
    "08-evidence": "We measured it blind, against the same agent without actions. Correct end state went from twenty-seven to one hundred percent. Zero unsafe outcomes. Thirty-eight hours became six seconds, and eight dollars became one cent. The failures are in the repo.",
    "09-close": "Quipu, by team primos. Answers in seconds. Verified decisions. People where they matter. The repo and the live app are on screen.",
}

model = Kokoro(str(ROOT / "models" / "kokoro-v1.0.onnx"), str(ROOT / "models" / "voices-v1.0.bin"))
OUT.mkdir(parents=True, exist_ok=True)
for name, text in LINES.items():
    samples, rate = model.create(text, voice=VOICE, lang="en-us", speed=1.08)
    path = OUT / f"{name}.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())
    print(f"{name}: {len(samples) / rate:.1f}s")
