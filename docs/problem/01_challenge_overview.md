# Challenge Overview

> Sources: *Factored AI & Data Hackathon 2026: Problem Statement* and the *Kickoff deck* (2026-09-25).

## TL;DR

- Build a **working prototype** of an AI-first banking **customer-service system** for **one** focused workflow. The prototype must come with **measured evidence** that it works and that it knows when *not* to act.
- Deliver a **public GitHub repo**, a **deployed link**, **4–6 slides**, and a **mandatory video pitch**.
- **Submissions close 2026-10-05.** Our internal target is 2026-10-04.
- **The data is synthetic, not real.** It is a generated LATAM bank dataset (Mexico, Colombia, Argentina; Spanish only; ~19M rows). It contains no real customers and has data-quality problems added on purpose. See [dataset](03_dataset.md).

> *"Don't build a chatbot, build a customer-service system."*
> *"Build something that works, prove that it works, and know when it should not act. And show us what it would take to make it real."*

## Timeline

| Date | Milestone |
|---|---|
| 2026-09-01 | Registration opens |
| 2026-09-25 | Challenge launch; the 10-day build starts |
| **2026-10-05** | **Submissions close** |
| 2026-10-15 | Finalists announced |
| 2026-10-16 | Award ceremony |

- **Competition:** ~750 participants, ~180 teams.
- **Prizes:** 1st USD 6,000 · 2nd USD 3,000 · 3rd USD 1,000. Winners also get an interview with Factored's engineering and talent team.

## Deliverables

Send everything to **hackathon.admin@factored.ai**:

1. Link to a **public GitHub repository** named `factored-hackathon-2026-[team-name]`
2. Link to where the **tool is deployed** (cloud is not strictly required; see [mentor FAQ](04_mentor_faq.md))
3. A **4–6 slide presentation** about the tool
4. A **short, mandatory video pitch** that shows the working solution and explains the core architectural decisions

Any language or toolset is allowed. The organizers also say: *"Submit your tool no matter what!"*

## Problem statement

Build a working AI-first customer-service system for a real-world banking environment. The system should:

- understand complex customer interactions;
- use data and tools securely;
- complete appropriate service workflows;
- involve human agents when needed.

Choose **one focused problem** and demonstrate it end to end. Use the supplied data to explain why the problem matters, to establish a **baseline**, and to measure whether the approach improves **service quality** and **operational efficiency**.

Design for **privacy, explainability, fairness, reliability, and scalability**. Make the trade-offs explicit across **autonomy, accuracy, latency, cost, and human oversight**. Justify where AI is appropriate and where deterministic logic is preferable.

### Scope

- The deliverable is a working prototype with evidence of production readiness and an honest account of the work that remains. It is not a live banking service.
- Example workflows (these are examples, **not tracks**):
  1. Account / payment inquiries
  2. Card-service support
  3. Transaction-dispute intake
  4. Credit-product information and eligibility support
- ⚠️ **Implementing more workflows earns no automatic bonus.** The score depends on depth, demonstrated behavior, and engineering judgment.

### Mandatory scenarios

| Scenario | Expected behavior |
|---|---|
| **Normal case** | Automated resolution that complies with policy: verified account queries and authorized self-service actions |
| **Ambiguous / unsupported** | Clarifying questions, or safe abstention when parameters are missing or the request is not supported |
| **Human required** | Structured handoff that carries verified facts and open questions, **not a raw transcript dump** |

- **Languages:** demonstrate interactions in **Spanish and Portuguese**, and report limitations in the data and in language coverage.
- **Expected loop:** Understand → Decide → Act → Verify → Escalate. *"AI should not be autonomous just because it can be."*

### Minimum system behaviors (kickoff)

- Maintain conversational context
- Clarify ambiguous requests
- Retrieve trusted information
- Use tools securely
- Execute appropriate workflows
- Verify that actions actually happened
- Know when **not** to act
- Hand off to a human when needed

## What the solution must demonstrate

1. **A problem supported by data.** Analyze contact reasons, demand patterns, data quality, and operational constraints. Use the evidence to prioritize the workflow and to define the customer and business outcomes.
2. **A functioning AI system.**
   - Keep conversational context and clarify ambiguity.
   - Ground factual answers in permitted account, transaction, or policy data.
   - Use tools where they help, and **report only actions whose outcome was verified**.
3. **Controlled automation.**
   - Define what the system can answer, what needs confirmation, and when to abstain or transfer.
   - **Enforce permissions and policy outside the text the model generates.**
   - The human handoff includes the request, verified facts, actions taken, evidence, and unresolved questions.
4. **Sound data and ML practice.**
   - Repeatable data preparation with contracts, quality checks, lineage, and an update/freshness policy.
   - **At least one learned component evaluated against a baseline**, with valid labels, no leakage, and justified representations, metrics, thresholds, and splits.
5. **Measured quality and failure handling.**
   - Evaluate on held-out cases, including: incorrect or missing data, expired sessions, unauthorized access, **prompt injection**, tool failures, and multilingual ambiguity.
   - Report successes, unsafe outcomes, handoff behavior, latency, and cost, with sample sizes and limitations.
6. **A credible route to operation.**
   - Show tracing, bounded retries, safe fallback, and reproducible setup.
   - Explain capacity limits, monitoring, access control, data retention, and the remaining deployment work.
   - Explanations come from sources, policy rules, and execution records. **Hidden chain-of-thought is not an audit artifact.**

## Architecture freedom

Conventional ML, pretrained LLMs, retrieval, deterministic workflows, agents, or any justified combination are all allowed. **None of these is required:** training a new model, multiple agents, a tool-count target, streaming, demand forecasting, or a dashboard.

Every team is assessed on **data engineering and AI/ML rigor**. For pretrained or retrieval-based solutions, that rigor shows in component selection, relevance or intent labels, representations, leakage prevention, held-out evaluation, and error analysis.

Use batch, incremental, or streaming processing according to what the workflow needs. Incremental file delivery alone does not require streaming. If only static data is supplied, show update correctness with a clearly labeled test fixture.

## The supplied data

> Source: *LATAM Bank Dataset Summary* and *Complete Data Dictionary*: "a synthetically generated dataset created specifically for the Factored Datathon 2026… No real customer information is included."

- **Fully synthetic:** names, addresses, transactions, and call transcripts are generated.
- **Scope:** 13 tables, ~19M rows, Mexico / Colombia / Argentina, 2023-06 → 2026-06, MXN/COP/ARS/USD.
- **Language:** Spanish only, with regional accents. **There is no Portuguese data**, so our Portuguese cases will be team-generated and labeled as such.
- **Quality problems added on purpose:** ~2% duplicates, ~5% nulls, late-arriving partitions, schema evolution, and orphaned foreign keys.
- **Risk:** synthetic generators may not create the relationships we expect between tables. We verify the signals on real queries before building on them.
- In the submission we label every input: **organizer synthetic** (the dataset) or **team-generated** (Portuguese set, adversarial cases, synthetic policy rules).

## Data and execution boundaries

- Use only organizer-approved data and permitted external resources.
- Label every input as **real, de-identified, synthetic, or team-generated**.
- Do not put private customer records, credentials, or restricted data in public submissions or in requests to external models.
- Sandbox services and mock banking tools are acceptable if their contracts and limitations are documented.
- **Authentication:** use a trusted test session or identity service. A national ID or customer number alone does **not** prove identity.
- Enforce per-customer record access and action permissions in the **service/tool layer**.
- **Credit workflows:** keep conversation handling, predictive risk estimates, and eligibility policy separate. Use approved rules or a clearly labeled synthetic policy service. The LLM must not invent eligibility rules or approve credit on its own. Show explanations, uncertainty, and review paths for borderline cases.
- No live lending decisions and no money movement are required or authorized.
