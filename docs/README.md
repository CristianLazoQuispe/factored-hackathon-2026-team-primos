# Documentation

This folder holds two kinds of documents:

- **Problem understanding and strategy:** what the challenge asks for and how we plan to win. This is internal context for the team.
- **Solution documentation:** how our system works, how it was evaluated, and how to run it. Judges read this part.

## Layout

```
docs/
├── README.md                     ← this index
├── problem/                      ← understanding the challenge (from the official sources)
│   ├── 01_challenge_overview.md  ← problem statement, deliverables, dates, rules
│   ├── 02_evaluation_criteria.md ← judging criteria and required metrics
│   ├── 03_dataset.md             ← LATAM Bank dataset map
│   └── 04_mentor_faq.md          ← official clarifications from mentors (Slack)
├── strategy_analysis_01/         ← strategy analysis by Cristian (each teammate adds strategy_analysis_NN/)
│   ├── README.md                 ← index: start at 10_proposal.md
│   ├── 01_winning_strategy.md    ← thesis, workflow selection, learned component, eval plan
│   ├── 02_team_plan.md           ← roles, timeline, open decisions, pitch outline
│   ├── 03_risks.md               ← risks and mitigations
│   ├── 04_creative_directions_debate.md ← how judging works, stakeholder debate (concept superseded)
│   ├── 05_market_research.md     ← international market scan (Asia, West, LATAM) with sources
│   ├── 06_disruptive_concepts_debate.md ← critic + strategist verdicts; architecture thesis
│   ├── 07_demo_experience.md     ← video, live demo, UI: what to show and how
│   ├── 08_forced_divergence_ideas.md ← 3 forced lenses → RASTRO: "the bank investigates itself first"
│   ├── 09_adversarial_direction.md ← red-team/evals/monitoring market + RASTRO with earned autonomy as proof
│   ├── 10_proposal.md            ← ★ CURRENT PROPOSAL: RASTRO (after stakeholder / delivery / judge debate)
│   └── 11_data_model.md          ← Postgres schema for the agent, mini-set, fixtures, tool → table map
├── documentation/                ← solution docs (filled in as we build)
│   ├── README.md                 ← index: technical vs user documentation
│   ├── technical/                ← for engineers
│   │   ├── architecture.md       ← component diagram, agent graph, skills + MCP, identity
│   │   ├── mcp/                  ← the agent's tools: one page per MCP server
│   │   ├── data/                 ← model.md (core schema), pipeline.md (ETL), quality report of the full load
│   │   ├── deploy.md             ← Cloud Run + Cloud SQL
│   │   ├── diagrams/             ← hand-drawn architecture SVG, Mermaid sources + SVG / 300-dpi PNG (`make diagrams`)
│   │   └── adr/                  ← architecture decision records
│   └── user/                     ← for testers and judges
│       └── README.md             ← what the assistant can do and how to try it
└── meetings/                     ← meeting notes
    └── 2026-09-25_kickoff.md
```

## Conventions

- All repository content is written in **English**.
- File names use `snake_case` with a numeric prefix when the reading order matters.
- Every claim about the challenge must cite its source (the problem statement, the kickoff deck, the data dictionary, or a mentor answer).
- **Never** paste credentials into these docs. The S3 keys live only in a local `.env`.
- **Each teammate owns one `strategy_analysis_NN/` folder**, in any format they prefer: `01` is Cristian, and `02`–`04` are for the other three members. Only the owner edits their folder. The team compares the folders and votes on one proposal. `problem/`, `documentation/` and `meetings/` are shared.
