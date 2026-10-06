---
workflow: general-video
flow: companion
storyboard: no
message: "Answers in seconds. Verified decisions. People where they matter."
destination: youtube
aspect: 1920x1080
language: en
audience: hackathon jury (Factored AI & Data Hackathon 2026)
length: 159s
angle: product + architecture + business evidence
---

## Intent

A professional sales demo of Quipu, the AI-first banking customer-service agent, for the hackathon jury.
It must sell three things other teams' videos don't: the product in motion (voice, text, photo, khipear,
finances, operator console), the technical architecture (LangGraph agent, MCP skills, Postgres audit,
"AI proposes, code decides, the customer confirms"), and the business case with blind-measured evidence.
Tone: confident, concrete, numbers-backed. Narration in English; the product UI stays in Spanish.

## Assets

- ../intro-final-night-maria.mov — cinematic AI intro; use 5.0–15.2 s as scene 1, 3.0–5.0 s (the knot) in the close.
- ../runway/ref_01..04.html + common.css + chat.css — the phone mock scenes (notifications, voice+photo chat, resolved card, endcard).
- ../presentation/Quipu Deck slides creation/uploads/quipu-design-system/{tokens.css,slides.css} — design tokens and slide components (Geist).
- ../presentation/slides/slide-1..6.png — approved copy and layout references.
- ../../documentation/technical/diagrams/architecture.png — real component diagram (ghost background in the architecture scene).
- ../../../app/adapters/outbound/email_template/preview/case_receipt.png — the receipt email.
- ../../../web/public/casos/lucia-uber.png — the statement photo attached in the chat.
- public/screens/ — Playwright captures of the real app (landing.mp4, corona.mp4 with a voice note through a fake mic, khipu.mp4 with the Confirmar card, finanzas.png, chat-pt.png, consola.png, gerencia.png), made by scripts/capture.py against `make up` with Gemini.

## Customizations

- Narration: Kokoro (local, models/ in the repo), English voice, one WAV per scene; scene durations follow the voice.
- Count-ups on the business and evidence numbers.
- Music bed ducked under the narration. No HeyGen credential: generated locally with MusicGen via media-use (assets/bgm/track.wav).
- Close uses the real animated web logo (web/components/logo.tsx + globals.css keyframes).

## Notes

- Never claim what the README does not back (eval numbers, rules, stack).
- The intro's phone close-up (15.25–17 s) has AI-garbled text: never show it.
