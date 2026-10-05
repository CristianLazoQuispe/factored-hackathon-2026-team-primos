# Documentation

| Audience | Folder | Start with |
|---|---|---|
| **Users**: testers, judges trying the demo | [user/](user/) | [user/README.md](user/README.md): what the assistant can do and how to try it |
| **Engineers**: how it is built and run | [technical/](technical/) | [technical/architecture.md](technical/architecture.md): components diagram, agent, identity |

![Component architecture](technical/diagrams/architecture.svg)

## Technical documentation

| Document | Status | Covers |
|---|---|---|
| [architecture.md](technical/architecture.md) | Living | Component diagram, agent graph, skills and MCP, identity, tracing |
| [mcp/](technical/mcp/README.md) | Living | The tools the agent can call: which question each one answers, arguments, what it returns, the rules they all follow |
| [data/model.md](technical/data/model.md) | Living | The `core` schema: tables, diagram, provenance of each table, the team-generated billing and service-bills rules, design decisions |
| [data/pipeline.md](technical/data/pipeline.md) | Living | The ETL: raw → bronze → sample → silver → Postgres, contracts, quality report, local vs. Cloud SQL |
| [adr/0004](technical/adr/0004-khipear-money-movement.md) + [mcp/transfers.md](technical/mcp/transfers.md) | Living | Khipear, how the agent moves the customer's money: the three operations and the payment of a service bill, when it asks which account, the rules checked in code, the confirmation button, where the money is recorded |
| [actions.md](technical/actions.md) | Living | How the agent acts: the propose-confirm-execute-verify cycle, what each request gets, where it writes, what is simulated, how it is tested |
| [deploy.md](technical/deploy.md) | Living | Cloud Run and Cloud SQL: what exists, how a deploy runs, rollback, limits |
| [diagrams/](technical/diagrams/) | Living | Hand-drawn `architecture.svg`, Mermaid sources (`.mmd`) + rendered SVG / 300-dpi PNG (`make diagrams`) |
| [adr/](technical/adr/) | Ongoing | Architecture decision records (`NNNN-title.md`) |
| [evaluation.md](technical/evaluation.md) | Living | What the text-to-SQL eval measures and does not, the cases and the held-out split, the quality floor that stops a deploy, results, known failures, limits |
| [evaluation_actions.md](technical/evaluation_actions.md) | Living | What the action eval measures against the challenge's outcomes (safe automated resolution, containment, escalation, unsafe outcomes, efficiency), its 65 scenarios and held-out split, the baselines, how to run it, its limits |
| `security.md` | Planned | Auth, authorization, prompt-injection defense, data handling and retention |
| `operations.md` | Planned | Deployment, tracing, monitoring, capacity limits, remaining production work |
| `limitations.md` | Planned | Data, language coverage, known risks |

## User documentation

| Document | Status | Covers |
|---|---|---|
| [user/README.md](user/README.md) | Living | What you can ask, test customers, languages, human handoff, current limits |
