# Creative Directions Debate: how do you win when "everyone builds a chatbot"?

> **Current proposal:** [10_proposal.md](10_proposal.md). Kept as history: how judging likely works and why "make rigor visible" matters.

> Status: **partially superseded** by [06_disruptive_concepts_debate.md](06_disruptive_concepts_debate.md).
> - Sections 1–3 (how judging works, making rigor visible, the stakeholder debate) still apply.
> - The concept in §5 ("the dispute desk that calls you back") was dropped: voice and photo are commodities, and outbound calls look like vishing.

## 1. The real game: who decides, and how

- **The judge is Factored**, a data/ML consultancy that *hires* engineers and *sells* projects to banks. The prize includes an interview. In practice, the winner is the team Factored would **want to show a banking client tomorrow**.
- **Likely funnel.** There are ~180 submissions and 10 days to pick finalists (10-05 → 10-15). Judges almost certainly screen first on **video + slides**, and only finalists get a deep repo review. That means two different exams:
  1. **Screening** (video, first 30–60 s): we must be *memorable and different*.
  2. **Final** (repo, evaluation, docs): we must *survive technical scrutiny*. Unverifiable "99% accuracy" claims fail here.
- **Conclusion:** we don't have to choose between "technical" and "visible". The move is to **make the rigor visible**, so the judge can *see and verify it*, not just read our claims about it.

## 2. "Anyone can claim 99% accuracy"

Anyone can *claim* it; very few let the judge *verify* it. What earns credibility:

- **The judge tests it:** a public link where they can try to break the system (prompt injection, asking for another customer's data) and watch it get blocked.
- **We publish our failures:** "It fails on 7% of Portuguese cases; here are the 12 cases." This builds more trust than a clean 99%.
- **One command reproduces everything:** `make eval` regenerates the exact table shown in the slides.
- **Every reply is a glass box:** the UI shows which policy rule applied, which tool was called, and which action was verified ✔.

## 3. Stakeholder debate

**Customer (LATAM bank client).** "I don't want to chat. I want to **call** or send a **WhatsApp photo** of the weird charge, be understood with my accent, and not repeat my story to 5 people."
→ Voice and photo evidence matter more than a web chat UI.

**Head of Customer Service (the buyer).** "Most of my cost is phone calls. I care about **how much I contain safely**, and that when a case reaches a human agent, the agent **doesn't start from zero**. Show me cost per resolved case."
→ Human-agent console with the handoff, plus an ROI model grounded in `call_center_interactions`.

**CISO / Compliance.** "I don't care about avatars. Prove the system **cannot** leak another customer's data or act without confirmation, and give me an audit trail."
→ Live red-team arena and auditable traces.

**Factored judge (engineer).** "I will open the repo. If the evaluation isn't reproducible or there is leakage, a beautiful video won't save you."
→ Rigor is the entry ticket, not the screening differentiator.

**Delivery lead.** "We have 9 days. Every extra is a risk. Build one shared workflow **engine** with channels as thin adapters. No VR. Feature freeze on 10-03."
→ Prioritize by (visibility × justification) / effort.

**Devil's advocate.** "The statement says more workflows earn no bonus. Add avatars and the judges will think you missed *'Don't build a chatbot'*. Every 'wow' must be **justified by the data** or move a required metric."
→ Filter applied to every idea: *does the data justify it, and does it move a required metric?*

## 4. Ideas evaluated

| Idea | Justified by data / statement? | Visibility | Effort (9 days) | Verdict |
|---|---|---|---|---|
| **Voice (phone) channel, ES/PT, accent-aware** | ✅ The data *is* call-center data: 800k interactions, transcripts, MX/CO/AR accents, audio_quality | ⭐⭐⭐ | Medium (STT + TTS, latency) | **YES: main differentiator** |
| **Receipt/screenshot photo (CV/OCR) → match to the transaction** as dispute evidence | ✅ Disputes need evidence; uses the team's CV background | ⭐⭐⭐ | Low–medium (VLM + deterministic matching) | **YES** |
| **Glass-box human-agent console** (handoff, verified facts ✔, rules, trace) | ✅ Required by the statement (handoff, audit) | ⭐⭐⭐ | Low | **YES (de facto mandatory)** |
| **Public red-team arena** ("try to break it") + blocked-attack counter | ✅ The statement asks for injection, unauthorized-access, and unsafe-outcome evidence | ⭐⭐⭐ | Low (reuses the adversarial set) | **YES** |
| **Contact-center simulator:** thousands of synthetic customers (LLM personas built from real dataset profiles, accents, ES/PT) calling the system | ✅ It *is* evaluation at scale, plus the capacity and ROI projection | ⭐⭐⭐ ("2,000 simulated calls" in the video) | Medium | **YES: this is the eval** |
| **Proactive outreach:** the bank detects a suspicious charge (`is_fraud` / `fraud_score`) and *calls or messages first*: "Do you recognize this purchase?" | ✅ Uses the fraud data; turns reactive service into proactive service | ⭐⭐⭐ | Low (another scenario on the same engine) | **YES, as a video scenario** |
| Real WhatsApp (Twilio/Meta sandbox) | ✅ Dominant channel in LATAM | ⭐⭐ | Low–medium | Optional (stretch) |
| Talking video avatar | ❌ No data supports it | ⭐⭐ | Medium | NO (at most in the pitch intro) |
| VR / AR | ❌ No bank customer uses it | ⭐ | High | NO |
| Robotics / mechanics | ❌ | — | — | NO (that background goes into systems thinking: state machines, failure modes, control) |
| Voice emotion/stress → earlier escalation | ⚠️ `sentiment` exists but is synthetic text; ethical and fairness risk | ⭐⭐ | Medium | Only as a text signal, never biometric |

## 5. Proposed concept: "The dispute desk that calls you back"

> **Not a chatbot.** An **omnichannel dispute and fraud desk** for LATAM banks. The customer calls or sends a photo by WhatsApp or web. The system:
> 1. understands accented Spanish and Portuguese;
> 2. identifies the transaction;
> 3. verifies the facts and asks for confirmation;
> 4. acts, then checks the action actually happened;
> 5. when needed, hands the case to a human *already assembled*.
>
> And when the bank detects a suspicious charge, **it calls first**.

### Video storyline (90-second hook)

1. A phone rings: the *bank* calls an Argentine customer about a suspicious charge. The customer doesn't recognize it. The system asks for confirmation, blocks the card, and shows the block as verified ✔.
2. A Brazilian customer sends a receipt photo. The system finds two candidate transactions and asks which one she means.
3. A high-amount case from a repeat complainer is escalated. The console shows the case already assembled.
4. A "customer" attempts prompt injection → blocked, with the counter going up on screen.
5. Results table: baseline vs. system over 2,000 simulated calls and 300 labeled cases, with the failures shown.

### Why it wins

- **Memorable at screening:** voice, photo evidence, and "the bank calls you".
- **Every extra is justified by the data:** call-center volume, fraud flags, the need for dispute evidence.
- **Rigor is visible:** the arena, the glass-box console, and `make eval`.
- **It matches what Factored would sell to a bank.**

## 6. Prioritization (delivery lead): the core is non-negotiable

| Priority | Piece | Note |
|---|---|---|
| P0 | Dispute workflow engine + authorized tools + policy engine + handoff | Every channel is an adapter over this engine |
| P0 | Data pipeline + EDA + held-out evaluation + baselines | Entry ticket for the final round |
| P0 | Glass-box human-agent console (web) | Also serves as the demo UI |
| P1 | Voice channel ES/PT | The differentiator; if latency is too high, fall back to push-to-talk |
| P1 | Receipt photo → transaction match | Uses the team's CV strength |
| P1 | Synthetic-customer simulator | Evaluation at scale |
| P1 | Red-team arena | Reuses the adversarial set |
| P2 | Proactive fraud outreach | A scenario, not a new system |
| P3 | Real WhatsApp | Only if time allows |

**Cut rule:** if P0 does not run end to end by **2026-10-01**, freeze every P1 item except the console.

## 7. Working assumptions

- **Finalists present live** on 10-16, so the demo must run reliably in front of an audience.
- **Judges will try the deployed tool**, so it must be stable, and the red-team arena must be publicly reachable.
- **Voice and image are UI/UX choices within a single workflow**, which is ours to define. They are not extra workflows.
