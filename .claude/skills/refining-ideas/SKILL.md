---
name: refining-ideas
description: Use when a feature, fix, plan, or task list is being proposed, expanded or estimated, before writing code — and whenever tempted to add a fallback, a retry, a config flag, a callback, an abstraction, or a test for a library.
---

# Refining Ideas

## Overview

The deliverable is the smallest change that makes the asked-for behavior true and leaves it
verifiable. **Complexity is paid for by a case that exists now and can be named** — a real input, a
real caller, a real observed failure. A roadmap is not a case. "Robustness" is not a case.

## The refined idea has four parts, in this order

1. **The behavior change**, one sentence.
2. **The files it touches.**
3. **What stays out, and why** — name the tempting additions you are declining.
4. **The verification** — the command to run or the observable that proves it works.

Nothing else. No restated brief, no options survey, no phase plan for a two-file change.

```
Add the CSV branch to the attachment parser so .csv attachments produce rows like .xlsx does.
  Touches: src/services/parsers/canonical_parser.py, tests/test_canonical_parser.py
  Out: no format registry (two formats, an if is enough); no encoding fallback chain
       (the retailer sends UTF-8; if that changes we want the failure, not a guess).
  Verify: uv run pytest tests/test_canonical_parser.py -k csv
```

## What gets cut

| Proposal | Why it's cut | Instead |
|---|---|---|
| Fallback when a secret or env var is missing | The config is ours and set at deploy. A fallback turns a broken deploy into a silently wrong run | Fail loudly at boot |
| Default value for a config knob "just in case" | Same: it hides the real error and nobody notices for weeks | Require it |
| Retry or timeout wrapping an SDK call | `azure-core` and `googleapiclient` already retry. Layers **multiply**, they don't add — and a retry longer than the deadline is a silent drop | Read what the SDK already does, first |
| `try/except` added "for robustness" | Turns a bug into false data, which is worse than a crash | The concrete exception, only at a declared edge |
| Test asserting the library/SDK behaves | You are testing a third party's code | Test ours; mock at the boundary |
| Test for a case no caller can produce | Fake coverage that must be maintained forever | Name the caller. No caller, no test |
| Callback / event / plugin seam with one call site | Indirection with no payoff | Call the function |
| ABC / Protocol / interface with one implementation | — | The concrete class |
| Config flag nobody turns | — | Hard-code it; add the knob when someone needs to turn it |
| "It will also handle XML and CSV later" | Roadmap, not requirement | Build the one that was asked for |
| Compatibility shim with no other consumer | — | Delete the old path |
| Refactoring the neighbours while you're in there | Different idea, different review | Its own commit — see `writing-atomic-commits` |

**One idea = one branch = one PR.** If the plan contains two ideas, it is two branches, unless the
request explicitly asked for one big change.

## Red flags — go back to the four parts

- "in the future", "eventually", "probably need", "just in case", "to be safe", "defensive".
- A plan step with no observable outcome.
- A test whose failure would mean the library broke, not that we broke.
- A guard whose trigger you cannot produce on demand.
- Any file in the plan that the request never mentioned.
