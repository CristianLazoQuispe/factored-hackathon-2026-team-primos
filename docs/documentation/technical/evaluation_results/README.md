# Evidence of the action eval

The raw reports behind [evaluation_actions.md](../evaluation_actions.md). Each one lists every attempt:
what the customer wrote, every reply, the actions and their statuses, the verdict and the timings, so any
number in the page can be recomputed. The data is synthetic.

| File | What it is |
|---|---|
| `heldout_with_actions_20261005_034138.json` | The 22 held-out scenarios x 3 repeats on the agent with actions. Commit `9968b9e`, prompt `2ec7aafa9127` |
| `heldout_baseline_20261005_032438.json` | The same scenarios on the same code with actions off (`--baseline`). Commit `9968b9e`, prompt `f7fa934b3d74` |
| `regression_with_actions_20261005_025721.json` | The last of five regression runs (43 scenarios x 1) on the agent with actions, kept as development evidence. Commit `ade4f54` |

Each was produced by `uv run python -m evals.actions.run` (see the page for the exact flags), with
`gemini-2.5-flash` on Vertex AI (`global`), paced at 12 calls a minute. The held-out reports were
written blind: nobody opened them before both runs were complete.

Not included: the logs (tracebacks of refused calls, about 200 KB each) and the earlier regression
runs, which were made with detectors and a prompt that have since changed. The held-out run with
actions was started twice: the first launch was cut after 30 seconds with one scenario saved and was
discarded, and the whole run was repeated.
