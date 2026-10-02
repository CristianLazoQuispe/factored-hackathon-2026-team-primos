---
name: designing-algorithms
description: Use before writing any loop, matching, dedupe, aggregation, sort, or data-structure choice, and when reviewing code that runs over rows, files, records, pages or API results — anything where N grows.
---

# Designing Algorithms

## Overview

Think in invariants, worst cases and complexity **before** the first line. Then pick the **simplest
solution that is correct** — not the cleverest. An O(n²) that is fine for n<1000 is the right answer;
say so and move on.

## The contract: declare N and the target, in one line

```python
# N ≤ 500 pages × 200 rows = 100k rows; one O(n) pass with a dict keyed by amount; O(u) memory.
```

If you cannot write that line, you do not yet know what you are about to write. If the declared
complexity is worse than the table below for that operation, justify it or change the structure.

## Reduce to a known problem before inventing one

Bipartite matching, two pointers, sequence alignment / edit distance, interval merge, prefix sums,
top-k with a heap, union-find, hashing. Most "messy business logic" is one of these wearing a
domain costume. Name it, and the complexity and edge cases come for free.

## Structure per operation

| Operation | Structure | Complexity |
|---|---|---|
| membership / dedupe by value | `set`, or a grouping `dict` | O(n) — never `x in list` inside a loop (O(n²)) |
| lookup by id | `dict` built **once** outside the loop | O(1) per access |
| multiset match (e.g. amounts vs rows) | `Counter` value→count, greedy | O(n+m); fuzzy only over the unmatched rest |
| building a string in a loop | `list.append` + `"".join` | O(n) — never `s += ...` (O(n²)) |
| top-k | `heapq.nlargest` | O(n log k), not a full sort |
| repeated range queries | `sorted` once + `bisect` | O(log n) per query |
| grouping | `defaultdict(list)` | O(n) |
| max / min / count / any | one pass | O(n) — sort only if ORDER is part of the output |

## Budget by N

| N | Acceptable | Note |
|---|---|---|
| ≤ 1000 | O(n²) | **Say it's enough and don't optimize.** |
| ≤ 100k | O(n log n) | The nested loop is the bug here. |
| ≥ 1M | O(n), streaming | Nothing may be materialized whole. |

The worst case that matters is the domain's real one (500 pages, 40 emails in a batch, 8 concurrent
LLM calls), not a theoretical one nobody will hit.

## Memory

- Lazy over materialized: generators and comprehensions, one page/file at a time.
- Never accumulate blobs (PNGs, PDFs, response bodies) in a list that grows with N.
- `lru_cache` always with a bounded `maxsize` — 18 documents fit in RAM, 500 do not.
- Don't duplicate a whole table to transform it; project it.

## I/O dominates, and that's where the real bug is

A DB query or HTTP call **inside** the loop is the actual defect, whatever the CPU complexity says.
One call per document against a quota-limited API is how this pipeline earned its Sheets 429 storms:
the fix was memoizing the read, not tightening the loop. Batch, or hoist and cache.

## Edge cases, enumerated with concrete values

Empty, one element, all equal, duplicates, ties, unsorted input, N at the declared maximum. Say what
your algorithm does in each. **To reject a design, build the explicit counterexample that breaks it** —
"this feels fragile" is not an argument.

## Red flags

- A nested loop over the same collection and no complexity line above it.
- `x in list` / `list.index` inside a loop.
- `sorted()` on a hot path "to keep it tidy".
- A query, HTTP call, or file open inside the loop.
- Recomputing inside the loop what is constant outside it.
- `s += ...` accumulation; an unbounded cache.
- "It's fast enough" without having stated N.
