# Demo Experience: Video, Live Demo, and UI

> **Current proposal:** [10_proposal.md](10_proposal.md). The demo principles, Decision Log, and "customer is the hero" guidance here apply to RASTRO.

> Date: 2026-09-26. Status: **draft**. The core concept is still being iterated (see the note below), but these demo principles apply whatever concept we choose.
> Inputs: a UI/UX designer review and a non-technical viewer review (as a bank customer, a Head of Customer Service, and a tired judge on their 60th video).

> **Open issue (team feedback):** "LLM at the edges, deterministic rules in the middle" is standard practice in banking. It is an entry ticket, not a differentiator. We are running a new round of forcibly different ideas, and the concept section will be updated. What follows is about *how to show* whatever we build.

## 1. Principles

1. **The customer is the hero, not the system.** The video opens with her fear and must close with her relief ("$800 restored", she exhales, calls her daughter). The system is the ally.
2. **Every technical property needs a visual form, or it stays out of the video** and goes to the repo and slides instead.
3. **Show one thing at a time.** A cockpit full of gauges reads as "UI showing off."
4. **Quiet competence beats action-movie theatrics.** No sirens or speedometers. A short "denied" beat is enough. Banks want *precise*, not *playful*.
5. **Everything the judge sees must be driven by live data.** Judges are engineers and will rephrase requests to catch hardcoding.
6. **Automatic ≠ unsupervised.** Clarify it everywhere: the "bank" that authorizes is code that runs in milliseconds. A human steps in only for exceptions.

## 2. Viewer feedback summary

| Viewer | Works | Doesn't work | Wants |
|---|---|---|---|
| Bank customer | The phone-call opening (a real fear) | The internal dashboard as the star; jargon ("autonomy dial", "promise receipt") | Calm updates on *my* phone: "card frozen", "we're checking", "money's back" |
| Head of Customer Service | Avoidable compensation, SLA tracking, audit trail | Attack scene too clean (looks like a strawman); an instant handoff hides operational reality | A queue of cases (volume), not one heroic rescue; a sourced ROI number |
| Tired judge | Cold open; the "try to break it" QR (falsifiable) | Eight ideas in 90 s; round numbers without sources; the map time-lapse feels like a stats slide | One sharp insight, proven; a real attack attempt failing |

**Tagline test.**
- "The AI never holds the keys" works for judges but makes ordinary viewers ask "keys to what?".
- Plain-language options:
  - "It can solve your problem. It can't break the rules." / "Puede resolver tu problema. No puede saltarse las reglas."
  - "It can warn you. It can't move your money on its own." / "Puede avisarte. No puede mover tu dinero por su cuenta."
- Avoid taglines implying a human approves everything. That contradicts our design, where protective actions are automatic.

## 3. Visual system

- **Two registers.**
  - Customer side: warm, light, minimal.
  - System side: dark slate, precise, a compliance control room rather than a game HUD.
- **Four color tokens, never reused for another meaning:**
  - violet = AI proposal
  - amber = policy evaluation
  - green = executed / verified
  - red = blocked / live danger (**only** that)
- **Motion:** 150–200 ms, snappy, one subtle glow on state change.
- **Captions always on.** Judges may not speak ES/PT, and captions are an accessibility win.

### Key screens (wireframes)

**Customer phone.** Warm, simple, with live captions:
```
┌─────────────────────────────┐
│  🏦  On call · 00:42          │
│         ((•))  voice orb     │
│  "I don't recognize an $800  │
│   charge on my card"         │
│  ┌─────────────────────────┐ │
│  │ ✅ Card frozen            │ │
│  │ Ref #A192 · 14:32        │ │
│  └─────────────────────────┘ │
└─────────────────────────────┘
```

**Decision Log.** The hero screen for technical viewers. Every turn shows propose → decide → execute/block:
```
│ 🗣 CUSTOMER SAID   "I don't recognize an $800 charge"   │
│ 🤖 AI PROPOSES     freeze_card(•1234)  conf 0.94        │
│ ⚖ POLICY ENGINE    ✔ ALLOWED — reversible, instant tier │
│ ✅ EXECUTED        verified · card_status=FROZEN · rcpt │
```
```
│ 🤖 AI PROPOSES     refund($5000, auth=NONE)  conf 0.31  │
│ ⚖ POLICY ENGINE    ✘ BLOCKED — irreversible, needs step-up │
│ 🔻 AUTONOMY L3 → L1   👤 Escalated — case attached      │
```

**Human-agent console.** A case already assembled: summary, timeline, verified facts, and actions (verify identity, mark fraud, take call).

**Attack arena.** Reframed so the headline cannot embarrass us:
```
│ Attempts: 132 · Players: 41                      │
│ 🟢 Contained, no change          118  89%        │
│ 🟡 Contained, autonomy lowered    11   8%        │
│ 🔴 Irreversible action executed    0   0%  ← headline │
```
The claim to say out loud is **"0 irreversible actions executed by an unverified attacker"**, not "47/47 blocked".

**Replay comparison.** Compact (8–10 s): a faint map in the background, with the numbers as the payload. "What the bank did → with the system": SLA met %, breaches, avoidable exposure. The numbers must come from a real computation with a stated source.

## 4. What must be real vs. what can be animation

| Must be REAL (live system state) | Can be polish |
|---|---|
| Decision Log (actual structured proposals and policy evaluations) | Voice orb / waveform |
| Autonomy level and its transitions | Map pans, dot pulses |
| Allow/block decisions (a server-side authorization service) | Row and step animations |
| Promise receipt (a record you can look up) | Ambient sound |
| Dispute clock (per-country config) | Glow on state change |
| Arena scoreboard (real submissions) | |
| Handoff summary (the live pipeline) | |

**Never fake:** pre-scripted LLM responses. TTS voices for personas are fine, but the inference and policy decision behind them must be live.

## 5. Live demo run-of-show (3 min) and fallback

1. **0:00–0:20** — *"This is not a chatbot. Watch what happens when the AI wants to touch someone's money."*
2. **0:20–1:00** — Live call in Spanish: the customer's phone is mirrored on screen next to the Decision Log.
3. **1:00–1:50** — A judge writes the attack themselves via the QR (Portuguese). The system blocks it, lowers autonomy, and hands off to a human.
4. **1:50–2:20** — A teammate plays the human agent and continues with full context.
5. **2:20–2:45** — The model behind it: tiers, levels, the ledger, per-country clocks.
6. **2:45–3:00** — "The arena stays open during judging."

**Fallback if live voice fails:** a "replay mode" in the real app. It feeds pre-recorded audio or a transcript into the *live* engine, so every downstream decision is still computed live. Never cut to an unrelated pre-rendered video.

## 6. UI build priority and stack

- **P0:**
  - Typed actions + policy engine, with one instant action (freeze) and one step-up action (refund).
  - Decision Log streaming from the backend (SSE).
  - Voice pipeline ES/PT for one workflow.
  - Handoff console.
  - Customer-facing receipt.
  - Public deployment.
- **P1:**
  - Autonomy downgrade logic.
  - Attack arena, with its headline metric and load testing for a burst of ~180 phones.
  - Per-country clock.
  - Compact replay screen.
- **P2:**
  - Cinematic map, rendered for the video only (Remotion / After Effects).
  - Extra dashboards.
  - Native push notifications.
- **Stack:**
  - Next.js + Tailwind + shadcn/ui + Framer Motion.
  - SSE for events.
  - Postgres (Supabase/Neon) for cases and the ledger.
  - A plain-code policy engine. **Not another LLM**: the answer to "who checks the policy check?" must be code.
- **Voice latency:** target under ~1.5 s per turn. Above ~2.5–3 s it feels like a chatbot with voice bolted on. Test Argentine Spanish and Brazilian Portuguese STT early, and budget a day for switching provider.

## 7. Name ideas (same spelling in ES/PT)

**Custodia/Custódia** (safekeeping; the designer's pick) · **Vigía/Vigia** (lookout) · **Compuerta/Comporta** (floodgate) · **Fiel** (a scale's needle, also "faithful") · **Represa** (dam)

Avoid "llave/chave" (key), which clashes with the tagline.
