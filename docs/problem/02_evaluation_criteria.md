# Evaluation Criteria

> Sources: *Problem Statement* (section "Evaluation evidence") and the *Kickoff deck* (slides "Evaluation Criteria", "Prove It Works", "Think Beyond the Hackathon").

## Judging criteria (kickoff)

**First and foremost, the solution should work.** After that, judges assess:

| Area | What they look at |
|---|---|
| Overall rationale and documentation | Why the project is built this way and how well it is documented |
| AI Engineering | Backend, frontend, and deployment |
| Data Analytics | Data quality and relevant insights from the solution |
| Data Engineering | Extraction and transformation of the data |
| Machine Learning | Model selection, optimization, implementation, and tracking |

The kickoff says **no single skill is mandatory**. Its suggested split of tasks by discipline:

| Discipline | Suggested tasks |
|---|---|
| Artificial Intelligence | Production backend and structured JSON handoffs |
| Machine Learning | LLM/RAG orchestration and prompt-injection defense |
| Data Engineering | Strong ETL/ELT pipeline and customer record isolation |
| Data Analysis | Demand patterns and cost-per-resolution ROI |

## Technical rigor checklist (kickoff: "Prove It Works")

The kickoff frames the evaluation as **Baseline → Proposed System → Held-out Evaluation**.

- [ ] **Data quality and contracts:** strict input schema enforcement
- [ ] **Reproducible preparation:** deterministic pipeline execution
- [ ] **Valid labels:** grounded relevance judgments and ground truth
- [ ] **Leakage prevention:** strict train/eval isolation
- [ ] **Appropriate split:** realistic held-out test distributions
- [ ] **Learned component:** benchmarked against a baseline model

## Technical deliverables (kickoff)

| Deliverable | Meaning |
|---|---|
| Data-backed baseline | Justify the workflow choice with reproducible logs |
| Grounded AI core | Ground every response in verified records |
| Controlled automation | Enforce action permissions beyond model prompts |
| Data & ML discipline | Repeatable pipelines with strict schema contracts |
| Measured failures | Stress-test held-out cases, including injection |
| Route to operation | Deterministic setup with audited execution logs |

## "Think beyond the hackathon" (kickoff)

| Observability | Reliability | Security | Reproducibility |
|---|---|---|---|
| Tracing | Bounded retries | Authentication | Setup instructions |
| Execution records | Safe fallback | Access controls | Versioning |
| Monitoring | Tool-failure handling | Data retention | Repeatable evaluation |

**Be honest about what is missing:** capacity limits, data limitations, language coverage, deployment work, and remaining risks.

## Required evaluation evidence (problem statement)

- Compare the **baseline and the proposed system on the same held-out workload**.
- Report:
  - the number and mix of cases;
  - label quality;
  - model and prompt versions;
  - variability across repeated runs, where relevant.
- **Include failures in the results.**

### Outcomes to report separately

| Metric | Definition |
|---|---|
| **Safe automated resolution** | An eligible case reaches the correct, policy-compliant outcome without human intervention. Report the rate over **all in-scope test cases**, plus the share of cases where automation was attempted |
| **Containment** | A case ends without a transfer. Containment alone does **not** show that the problem was solved |
| **Escalation quality** | Cases that need escalation are transferred correctly with useful handoff context. Report **missed** and **unnecessary** transfers where labels allow |
| **Unsafe outcomes** | Unauthorized disclosures or actions, and materially incorrect outcomes, reported as counts with denominators. Zero observed failures in a small test set does not establish zero risk |
| **Operating efficiency** | End-to-end p50/p95 latency, and cost per attempted case and per successful automated resolution. State the workload, sample size, and cost assumptions. Use "not defined" when there are no successful resolutions |
| **Fairness / breakdowns** | Service outcomes by language and by authorized customer segment. State small-sample limitations and investigate disparities |

### Further rules

- If a model judges the answers, document its rubric and validate a sample against human or deterministic judgments.
- Label offline measurements, simulations, and projected business savings separately.
- **Do not describe an offline comparison as a measured production improvement.**
