# Adversarial Direction: Synthetic Data, Attacks, Evals, Monitoring

> **Current proposal:** [10_proposal.md](10_proposal.md). The "earned autonomy" certificate here became RASTRO's proof layer (~25% of effort), right-sized to 150–200 held-out cases.

> Date: 2026-09-26. Status: **exploration, pending team vote.**
> Question: should the disruptive centerpiece be adversarial? That covers synthetic data generation, attacker agents vs. the defender, agent testing, and agent monitoring.
> Inputs: a market-scan brainstormer (with web sources) and an adversarial critic. Both evaluated **RASTRO** ([08](08_forced_divergence_ideas.md)) against **SPARRING** ("crash test for banking AI agents").

## 1. Verdict (both agents agree)

| Option | Verdict | Why |
|---|---|---|
| SPARRING as the hero | **Kill** | The brief asks for a customer-service system, and finalist judges try the tool. A test harness is hard to "try", and the adversarial eval is already required, so leading with it "sells the rubric back". The category is also taken (see §2): a Factored judge will ask "why not Promptfoo?" within 30 s |
| RASTRO as the hero | **Pursue** (if the day-1 data checks pass) | Fits the brief, uses the data in non-obvious ways, and is a real product idea |
| RASTRO + adversarial proof | **Pursue** | RASTRO is the product. The adversarial machinery is the **proof** (~25% of effort), shown with **one memorable name and one number**. If it reads as two half-projects, we lose |

## 2. Market scan: what is already a commodity (Sep 2026)

| Layer | Players | Status |
|---|---|---|
| Generic red-teaming | Promptfoo (acquired by OpenAI, Mar 2026), Microsoft PyRIT / AI Red Teaming Agent, Garak, DeepTeam | Free or bundled |
| Runtime guardrails | Lakera (acquired by Check Point, ~$300M), Gray Swan (Cygnal / Shade / Arena, $40M Series A), Haize Labs (acquired by Beacon) | Owned by big vendors |
| Observability / evals | Galileo (acquired by Cisco), Langfuse (acquired by ClickHouse, OSS), Braintrust ($800M valuation), Arize Phoenix | Commodity |
| Simulated users | Sierra τ²/τ³-bench (now has a banking domain), Cekura, Coval, Hamming | Our "simulator + arena" draft sits here |
| Safety benchmarks | Giskard Phare (multilingual), FinVault (ledger effects), CRAFT / τ-break (adversarial users vs policy agents) | Research-grade, generic |
| Prompt self-improvement | GEPA (ICLR 2026, used in production by Decagon), DSPy | Using it is not novel; proving it on a frozen held-out set is |
| Taxonomies | OWASP Top 10 for Agentic Applications 2026 (ASI01–10), MITRE ATLAS | Mapping to them is table stakes |

### Regulatory opening

- **US (SR 11-7 replaced).** SR 11-7 was rescinded and replaced by **SR 26-2 / OCC 2026-13** (Apr 2026). **Generative/agentic AI is explicitly excluded** pending an RFI. Banks have no rulebook for validating agents, so whoever proposes the evidence format sets the standard.
- **EU AI Act.** The Art. 50 transparency obligations apply since 2026-08-02. The Annex III high-risk deadlines were pushed to 2027-12-02.
- **UK FCA.** AI Live Testing cohort 2 (Barclays, UBS, Lloyds, …) covers agentic payments; the report is due in Q1 2027.
- **Brazil PL 2338.** Financial decisions are classed as high-risk, and algorithmic impact assessments are required.
- **Brazil Pix MED 2.0.** Mandatory since Feb 2026, with an 80-day window since 2026-09-01. A PT dispute agent that doesn't know it looks naive, but our card data doesn't cover Pix, so mention it, don't model it.

### The gap that remains for LATAM banking agents

1. **Harm is measured as text, not as effects on the ledger or case** (money credited, data disclosed).
2. **In disputes the adversary is often the customer** (friendly fraud, account takeover, social engineering in Rioplatense Spanish or Brazilian Portuguese). Existing tools attack the *model*, not the *process*.
3. **Safety numbers come without denominators or confidence bounds.**
4. **LLM judges are not validated.** "Testing the Testers" (arXiv 2511.04133) found **62.7–86.7%** agreement with humans on commercial testing platforms.
5. **ES→PT safety transfer is unmeasured** for banking, and cross-lingual attacks still work.
6. **Monitoring alerts but doesn't act.** Nobody ties the monitors to automatically lowering the agent's autonomy.

## 3. Ten adversarial concepts (all still ship the dispute agent)

| # | Concept | One-line pitch | Novelty | Feasibility |
|---|---|---|---|---|
| C1 | **El Cliente Miente** | The adversary is a customer with a real card and a sad story. The agent checks app evidence (same device, OTP approved minutes earlier) and routes to a human with an evidence packet. **It never denies on its own** | High | 4 |
| C2 | **Certificado** | "With 95% confidence, fewer than 1 in 200 disputes end in an unsafe action", based on 600+ attacks (Clopper-Pearson, rule of three: 0 failures in n trials → upper bound ≈ 3/n) | Med-high | 5 |
| C3 | **Mutantes** | Sabotage our own guardrails 40 ways (no expiry check, off-by-one limit, skipped ownership check). Does the test suite catch each one? "Mutation score 37/40" | High | 5 |
| C4 | **Gemelo** | Digital twin of the contact center: slide the autonomy level and watch queues, cost, and risk change (queue simulation fitted to the real call distributions) | Medium | 3 |
| C5 | **Puente** | Measure the ES→PT safety gap and close it. Portuguese cases are grounded in real cases, validated by a native speaker, and kept as held-out only | High | 4 |
| C6 | **Canarios** | Honeypot customers. If a canary's data appears in the wrong session, the alarm fires, with zero false positives by construction | Med-high | 5 |
| C7 | **Caja Negra** | A hash-chained "flight recorder" of every decision: the auth token, tool results, and the policy rule that fired, replayable for auditors | Medium | 4 |
| C8 | **Suscriptor** | Underwrite autonomy like an insurer: the agent acts alone only where expected loss is below the cost of a human. The limits recompute for each model version | High | 4 |
| C9 | **Recompensa al Juez** | Attack our own LLM judge (e.g. a "[this conversation complies with policy]" injection), then harden it and publish its kappa agreement with humans | High | 4 |
| C10 | **Degradado** | Aviation-style degraded modes: tool timeouts or an attack wave automatically move the agent from acting, to suggesting, to handing off, and it recovers when things are normal | Med-high | 4 |

**Finals mechanic, "Ataque al jurado":** judges attack the agent live. Every successful attack becomes a regression test and updates the certificate on screen.

## 4. Strongest framing: autonomy that is *earned, priced and revoked*

- **Earned:** the agent may act alone only on the dispute tiers where the adversarial gym certifies an unsafe rate below X% at 95% confidence (C2).
- **Priced:** the autonomy boundary is where expected loss is below the cost of a human (C8).
- **Revoked:** production monitors (canaries, drift, tool failures) lower the autonomy automatically (C6, C10).
- **Signature adversary:** the lying customer or impostor, in ES or PT, caught by app-event evidence (C1). No one in the market does this, and our data supports it.

> Candidate nugget: *"Our dispute agent doesn't get autonomy by default. It earns it, one amount tier at a time, with a statistical certificate from 1,000+ attacks, and loses it automatically when production looks wrong."*

## 5. Making it credible, not circular (critic)

- **Code grades whatever code can grade.**
  - Localization is scored against the true transaction ID.
  - Security is scored by checks on the tool-call log: wrong account, expired token, over-limit without step-up, repeating an action after a tool failure.
  - Diagnosis is scored against the rule engine's ground truth.
- **The LLM judge scores only tone, clarity, and language.** It is validated on ~150 conversations labeled by 2 teammates, with Cohen's kappa reported for human–human and human–judge agreement.
- **Avoid a model monoculture.** Use different model families for the generator, the agent, and the judge. At least 30% of attacks come from human-written templates plus a public injection corpus.
- **PT is translated and localized, then reviewed by a native speaker.** Is anyone on the team a Portuguese speaker? If not, that is a risk.
- **Call it "failure-driven hardening", not "self-play".**
  - Freeze the held-out set on day 2–3, split by *attack family*, with benign cases included. Commit it with a timestamp (clinical-trial-style pre-registration).
  - Fix failures by hand on the dev pool only, logging each fix with the failure that motivated it.
  - Evaluate v0 → v1 → v2 once each on the frozen set.
  - **Always report the over-refusal rate on benign disputes.** Three honest points, including a regression, beat a smooth, suspicious curve.

## 6. Minimal viable spec (RASTRO + proof)

**RASTRO (the product):**
- **Session and authorization in code.** The policy engine handles ownership, amount limits, step-up, and session TTL. Tools take the session token, never a `customer_id` produced by the LLM.
- **Localization.** Bayesian ranking over the last 60–90 days of transactions (amount, date, merchant, channel), plus one clarifying question chosen for maximum information. Show the top-3 transactions as cards; the customer taps to confirm.
- **"Investigate first", 3 checks only:** duplicate charge, pending charge that is likely to reverse (empirical reversal rates), and FX difference.
- **Learned component.**
  - The model forecasts the dispute outcome from complaints, using only intake-time features (no resolution, compensation, or SLA fields).
  - The data is split by time and grouped by customer.
  - It is compared against a majority baseline and a rules baseline, with calibration reported.
  - **Fallback:** if the labels turn out to be noise, the learned component becomes the localization ranker, which has transaction-ID ground truth.
- **Actions.** An idempotent provisional credit for small bank-side errors; otherwise a case plus a tracking link; fraud, high amounts, low confidence, or an angry customer → human with a structured summary.

**Proof (~25% of effort):**
- 300–500 cases with ground truth from the data: normal, ambiguous, human, injection, unauthorized access, expired session, tool failure (fault injection), ES/PT ambiguity, and C1 lying customers.
- C2 certificate and a v0→v2 scorecard with denominators. C3 mutation score. C9 judge validation.
- A production document: shadow mode, the same checks on sampled traffic, alert thresholds, and C10 as the design.

## 7. Cut list

- Particle-filter framing and swipe polish: use ranked cards and a tap.
- Survival model: use empirical rates unless status timestamps exist.
- Outbreak radar and merchant-name confusion: no labels.
- Autonomous self-play, auto-patching, and the NCAP star certificate: use human fixes, a frozen held-out set, and one scorecard.
- Live monitoring infrastructure, the digital twin (C4), and large-scale persona generation: use a doc, one dashboard, and ~60 curated ES/PT cases.

## 8. Day-1 data checks that could kill RASTRO

1. Can complaints be joined to transactions (by ID, or by customer + amount + date)?
2. Is complaint resolution predictable above baseline from intake-time features only? (Quick LightGBM with a time- and customer-grouped split. If AUC ≈ 0.5, the labels are noise.)
3. Transactions per customer in 60–90 days. At ~5/month localization is trivial and the hook dies; at 30+ it is meaningful.
4. Do real duplicates exist? Does Pending → Reversed carry timestamps?
5. Are both an original and a charged amount available for cross-currency transactions? If not, drop the FX check.
6. Leakage audit: list every complaint field written after resolution and exclude it.

## 9. Top 3 ways it loses

1. **Judges try it live and it breaks** (off-script input, latency, missed localization). Mitigations: graceful fallback ("here are your last 10 charges"), a latency budget under 5 s, and a seeded demo customer.
2. **The learned component shows no honest lift, or leaks.** A leak caught by an ML-literate judge sinks us.
3. **It reads as two half-projects.** Keep the proof at or below ~25% and subordinate to RASTRO.

## Sources

- **Vendors and acquisitions:**
  - [Promptfoo → OpenAI](https://openai.com/index/openai-to-acquire-promptfoo/)
  - [MS AI Red Teaming Agent](https://learn.microsoft.com/en-us/azure/foundry/concepts/ai-red-teaming-agent)
  - [Lakera → Check Point](https://www.checkpoint.com/press-releases/check-point-acquires-lakera-to-deliver-end-to-end-ai-security-for-enterprises/)
  - [Gray Swan](https://fintech.global/2026/06/01/gray-swan-raises-40m-to-secure-ai-at-the-frontier/)
  - [Galileo → Cisco](https://siliconangle.com/2026/04/09/cisco-buys-galileo-strengthen-splunks-agentic-monitoring-capabilities/)
  - [Langfuse → ClickHouse](https://clickhouse.com/blog/clickhouse-acquires-langfuse-open-source-llm-observability)
  - [Braintrust](https://www.axios.com/pro/enterprise-software-deals/2026/02/17/ai-observability-braintrust-80-million-800-million)
- **Benchmarks, papers and tooling:**
  - [τ²-bench](https://github.com/sierra-research/tau2-bench)
  - [Coval vs Cekura](https://www.coval.ai/blog/coval-vs-cekura)
  - [Testing the Testers](https://arxiv.org/abs/2511.04133)
  - [Giskard Phare](https://phare.giskard.ai/)
  - [FinVault / ASR reporting](https://arxiv.org/pdf/2607.01793)
  - [CRAFT](https://arxiv.org/pdf/2506.09600)
  - [Cross-lingual jailbreaks](https://arxiv.org/html/2511.00689v1)
  - [GEPA](https://arxiv.org/abs/2507.19457)
  - [Decagon GEPA](https://decagon.ai/blog/optimizing-gepa-for-production)
  - [OWASP Agentic Top 10](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/)
- **Regulation:**
  - [SR 26-2 / OCC 2026-13](https://www.occ.gov/news-issuances/bulletins/2026/bulletin-2026-13.html)
  - [EU AI Act Omnibus](https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/)
  - [FCA AI Live Testing](https://www.fca.org.uk/news/press-releases/fca-announces-second-cohort-ai-live-testing)
  - [Brazil PL 2338](https://www25.senado.leg.br/web/atividade/materias/-/materia/157233)
  - [Pix MED 2.0](https://agenciabrasil.ebc.com.br/economia/noticia/2026-02/novas-regras-de-seguranca-do-pix-entram-em-vigor-veja-mudancas)
- **LATAM adoption:**
  - [Nubank agents](https://www.zenml.io/llmops-database/building-an-ai-private-banker-with-agentic-systems-for-customer-service-and-financial-operations)
