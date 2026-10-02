# Risks and Mitigations

> **Current proposal:** [10_proposal.md](10_proposal.md). Its §9 lists the RASTRO-specific open risks; the general risks below still apply.

| Risk | Impact | Mitigation |
|---|---|---|
| **AWS credentials in the data dictionary PDF leak into the public repo** | Disqualification or credential abuse | Keep keys only in a local `.env` (already git-ignored); never commit the kickoff PDFs; add `gitleaks` as a pre-commit hook |
| No Portuguese data in the dataset | PT requirement looks weak | Team-generated PT evaluation set, reviewed by a person, labeled as team-generated, and reported as a limitation |
| Synthetic labels are trivial or noisy | Learned-component results are misleading | Audit labels in the EDA, hand-review a sample, and document label quality |
| Over-building (multi-agent, dashboards, streaming) | Lost time, no extra score | One workflow; add a component only if it moves a reported metric |
| Claiming "production improvements" | Credibility loss with judges | Label every result as offline or simulated |
| "Zero failures" on a small test set | Overclaiming safety | Report n and confidence intervals |
| Deadline slip | Missing or weak submission | Feature freeze on 10-03, submit on 10-04, keep 10-05 as buffer |
| LLM and cloud costs | Budget | Small model for NLU, caching, free-tier deployment, cost reported per case |
| Integration friction between 4 people | Late breakage | Interface contracts on day 1, daily integration, end-to-end smoke test in CI |
