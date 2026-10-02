# Team Plan

> **Superseded for scheduling by [10_proposal.md §8](10_proposal.md)** (Delivery Lead plan, gates, Definition of Done). The roles and model-role notes below still apply.

Team: 4 senior ML engineers, all with Claude Code (Max plan). Combined background: computer vision, robotics, GenAI/LLMs, mechanics, and finance.

## Roles

| Member | Role | Owns |
|---|---|---|
| A | **Data Engineering + Analytics** | S3 ingestion → Parquet/DuckDB (bronze/silver/gold), data contracts, dedup, late arrivals, lineage, incremental-update fixture, EDA and insights, ROI (slide 1) |
| B | **Machine Learning** | Labels, splits, baseline ladder vs. learned component, evaluation harness, judge validation, error analysis |
| C | **AI Engineering (backend)** | Orchestrator, tools with authorization, policy engine, handoff, tracing, retries and fallback |
| D | **Frontend / Deploy / Red team / Pitch** | Chat UI and human-agent console, deployment, adversarial ES/PT set, slides and video |

Each member owns one module with an interface contract agreed on day 1, so nobody blocks anyone else.

## Timeline (2026-09-26 → 2026-10-05)

| Day | Date | Goal |
|---|---|---|
| D1 | Fri 09-26 | Repo setup, data download, EDA, **workflow decision**, team name, module contracts |
| D2 | Sat 09-27 | Bronze/silver/gold pipeline + contracts · tools + auth skeleton · evaluation set design |
| D3 | Sun 09-28 | Baselines B0/B1 · policy engine · minimal UI · first labeled cases |
| D4 | Mon 09-29 | End-to-end orchestrator (normal case) · B2 / proposed component |
| D5 | Tue 09-30 | Ambiguous and human cases + handoff · adversarial set · tracing |
| D6 | Wed 10-01 | First full evaluation run · initial deployment |
| D7 | Thu 10-02 | Error analysis → iterate · retries and fallback · cost and latency metrics |
| D8 | Fri 10-03 | **Feature freeze** · final evaluation run · README, operations docs, "what's missing" |
| D9 | Sat 10-04 | Slides (4–6) + video · **SUBMIT** |
| — | Sun 10-05 | Buffer (official deadline) |

## Open decisions (to settle on day 1)

- [ ] **Final workflow** (proposal: disputes; plan B: cards), after the EDA
- [ ] **Concept:** vote on [RASTRO](08_forced_divergence_ideas.md) with [earned-autonomy proof](09_adversarial_direction.md) (earlier option: ["The AI never holds the keys"](06_disruptive_concepts_debate.md))
- [ ] **Day-1 signal census:** see [08 §4](08_forced_divergence_ideas.md) and [09 §8](09_adversarial_direction.md)
- [ ] **Team name**, which sets the repo name `factored-hackathon-2026-[team]`
- [ ] **LLM provider** and models, and who covers API costs (see "Model roles" below)
- [ ] **Stack:** backend (FastAPI), storage (DuckDB/Postgres), UI (Streamlit / Next.js), tracing (Langfuse)
- [ ] **Deployment:** free tier (Render / Fly / HF Spaces / Vercel) + `docker compose`
- [ ] **Role assignment** A/B/C/D
- [x] **Who reviews the Portuguese cases?** A teammate with basic Portuguese. Claude Opus screens every PT case first; the human reviews only the flagged cases plus a random sample, and we report their agreement.
- [ ] Rituals: 15-minute daily + end-of-day integration sync

## Model roles (to avoid circular evaluation)

| Role | Model | Why |
|---|---|---|
| Customer-facing agent | Fast, cheap model (e.g. Claude Sonnet / Haiku) | Latency and cost per case are reported metrics |
| LLM judge (tone, clarity, language only) | Heavy model (e.g. Claude Opus) | Validated against ~150 human-labeled conversations (Cohen's kappa) |
| PT screening, label audits, adversarial generation | Heavy model; ideally another family (GPT / Gemini) for part of the attack generation | Stronger generation; avoids a model monoculture |
| Anything checkable by code (transaction ID, permissions, amounts, session) | **No LLM** | Deterministic ground truth |

**Budget note:** the Max plan covers Claude Code, which we use for coding and one-off offline validation. The deployed agent and the repeatable eval harness run on the **API, billed separately**. The challenge also requires reporting cost per case, so we measure this cost either way.

## Pitch outline

### Slides (5)

1. **The problem, with data:** contact reasons, volume, FCR, escalations, cost → why this workflow
2. **The solution:** architecture, "LLM where it helps, code where it must be guaranteed"
3. **Controls:** auth, authorization, confirmations, handoff, injection defense
4. **Results:** baseline vs. proposed (safe resolution, unsafe outcomes, escalation quality, p50/p95, cost), broken down by language and segment
5. **Route to production:** capacity, monitoring, retention, risks, remaining work

### Video (3–4 min)

1. Normal case (ES)
2. Ambiguous case (PT)
3. Escalation with handoff
4. Blocked prompt injection
5. Results table
