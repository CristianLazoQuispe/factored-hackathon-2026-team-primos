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
| [data_pipeline.md](technical/data_pipeline.md) | Living | raw → bronze → sample → silver → Postgres, contracts, freshness, GCP scale-out |
| [diagrams/](technical/diagrams/) | Living | Mermaid sources (`.mmd`) + rendered SVG / 300-dpi PNG (`make diagrams`) |
| [adr/](technical/adr/) | Ongoing | Architecture decision records (`NNNN-title.md`) |
| `evaluation.md` | Planned | Held-out set, metrics, repeated runs, judge validation, results, failures |
| `security.md` | Planned | Auth, authorization, prompt-injection defense, data handling and retention |
| `operations.md` | Planned | Deployment, tracing, monitoring, capacity limits, remaining production work |
| `limitations.md` | Planned | Data, language coverage, known risks |

## User documentation

| Document | Status | Covers |
|---|---|---|
| [user/README.md](user/README.md) | Living | What you can ask, test customers, languages, human handoff, current limits |
