# Winning Strategy

> **Current proposal:** [10_proposal.md](10_proposal.md) (RASTRO). This document keeps the original thesis and evaluation plan for reference.

> Status: **proposal**. The workflow choice is confirmed after the day-1 EDA.

## Thesis

1. **We win on rigor and honesty, not on features.** Most of the ~180 teams will ship a RAG chatbot. We stand out by answering the "Evaluation evidence" section to the letter: a metrics table with denominators, baseline vs. proposed, failures included, and explicit limitations.
2. **One workflow, in depth.** All three mandatory scenarios (normal, ambiguous, human) handled well and demonstrated in Spanish and Portuguese.
3. **"LLM where it helps, code where it must be guaranteed."** This is our one-line architecture pitch.
4. **Security that can be demonstrated:** session-based auth, authorization inside the tools, and a prompt-injection attempt blocked *live* in the video.
5. **Evaluation as a product:** a reproducible harness that anyone can run with one command.
6. **Honesty as a feature:** a clear "What it would take to go to production" section covering capacity, risks, language coverage, and pending work.
7. **Make the rigor visible.** Judges likely screen on the video first and review the repo only for finalists. We need to be memorable at screening *and* verifiable in the final. See [creative directions debate](04_creative_directions_debate.md).

## Proposed concept (pending team vote)

**"The AI never holds the keys."** A dispute-intake desk where the LLM only *proposes*. Deterministic code decides, runs the per-country legal clock, and keeps every promise. Autonomy per action is earned from evaluation evidence and is revoked live by a circuit breaker. The proof is a time-travel replay of historical complaints.

Full reasoning, verdicts, and the video script: [06_disruptive_concepts_debate.md](06_disruptive_concepts_debate.md). Research: [05_market_research.md](05_market_research.md).

The earlier voice/photo-centric concept ([04](04_creative_directions_debate.md)) is superseded. Voice and photo are now P2 input channels.

## Workflow selection

| Criterion | Transaction disputes / unrecognized charges | Card support | Account / payment inquiries | Credit info & eligibility |
|---|---|---|---|---|
| Data support | ⭐⭐⭐ transactions (is_fraud, Reversed/Declined), complaints (claimed_amount, resolution, SLA), transcripts | ⭐⭐⭐ products (Blocked), transactions (Declined), interactions | ⭐⭐ transactions, products | ⭐⭐ customers (credit_score, income), products (days_past_due); policy rules must be synthetic |
| Natural normal case | File a verified dispute on an identified transaction | Block/unblock a card, explain a decline | Balance, movements, payment status | Product info plus simulated eligibility |
| Natural ambiguous case | "I was charged something weird" and several transactions match | "My card doesn't work": which card? why? | "Where is my money?" | Missing income data |
| Natural human case | High amount, suspected fraud, repeat complainer, SLA risk | Active fraud, stolen card with charges | Accounting discrepancies | Borderline cases (required by the statement) |
| Actions needing confirmation | Create dispute, block card | Block, unblock, replace | Few | None (simulated only) |
| Execution risk | Medium | Low–medium | Low, but little differentiation | **High**: three separated layers (risk / policy / LLM) |
| Pitch value | **High** (money, fraud, regulation, SLA) | High | Medium | High if it works |

**Recommendation:** **transaction-dispute intake**, with card blocking as an action that needs confirmation. **Plan B:** card support.

**Decision gate (day 1):** we pick the workflow from the EDA, looking at:
- the distribution of `contact_reason` and `complaints.category`;
- volume;
- FCR and escalation rate;
- CSAT;
- SLA breaches by reason.

That evidence becomes slide 1 ("a problem supported by data").

## Architecture principles

The full design lives in [documentation/technical/architecture.md](../documentation/technical/architecture.md).

- A **deterministic state machine** drives the workflow.
- The LLM does NLU (intent, slots, language) and writes grounded replies. **It never decides permissions or policy.**
- A **policy engine in code** holds versioned rules.
- **Mock banking tools** sit on DuckDB/Postgres. `customer_id` always comes from the session token, never from the prompt.
- Sensitive actions require **explicit confirmation**, followed by a **read-back verification** before the customer is told the action is done.
- Handoffs use a structured JSON: request, verified facts, actions taken, evidence, open questions, priority, and escalation reason.
- Tracing on every step. Bounded retries and safe fallback.

## Learned component and baselines

Mentors confirmed that a prompted or fine-tuned LLM counts (see [mentor FAQ](../problem/04_mentor_faq.md)).

We compare a ladder of approaches on the **same held-out set**:

| Level | Approach | Role |
|---|---|---|
| B0 | Keyword rules | Deterministic floor |
| B1 | TF-IDF + Logistic Regression | Cheap classical baseline |
| B2 | Zero-shot LLM (small model) | Reference without domain data |
| **P** | Few-shot/RAG LLM, fine-tuned LLM, or a multilingual encoder + classifier | Proposed |

**Tasks:**
- (a) intent / routing classification;
- (b) the "needs a human" decision.

**Splits:** by `customer_id` **and** by time, so no customer or conversation appears in both train and test.

**Metrics:**
- macro-F1;
- recall of the "escalate" class, because a missed escalation is the costly error;
- cost and latency for each level.

## Evaluation plan

- A **held-out set of ~200–300 cases**, stratified by:
  - **Type:** normal / ambiguous / human / adversarial.
  - **Language:** ES (MX/CO/AR) / PT (team-generated and reviewed).
  - **Segment:** Premium / Plus / Basic / Student.
- **Adversarial cases:**
  - direct and indirect prompt injection (for example, text inside a merchant name or description);
  - expired sessions;
  - requests for another customer's data;
  - missing or wrong data;
  - tool timeouts or failures;
  - mixed ES/PT input.
- **Labels:** the expected outcome per case (resolve / clarify / abstain / escalate, plus the correct action), reviewed by two team members.
- **Repeated runs:** at least 3, with model and prompt versions pinned.
- **LLM-as-judge** only for response quality, with a published rubric and agreement measured against a hand-labeled sample.
- **Output:** a table of metric × system (baseline vs. proposed) × language × segment, with n, confidence intervals, and the failures listed.
