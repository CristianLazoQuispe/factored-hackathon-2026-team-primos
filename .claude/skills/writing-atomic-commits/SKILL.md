---
name: writing-atomic-commits
description: Use when committing, splitting work into commits, naming a branch, pushing, or opening and reviewing a pull request in any repo under this directory.
---

# Writing Atomic Commits and PRs

## Identity in this tree

This is a hackathon repo shared by four people on GitHub (`CristianLazoQuispe/Factored2026`).
**Every member commits and pushes with their own personal account** (personal GitHub user and
personal email).

Set it per repo before the first commit and check it:

```bash
git config user.name  "<your GitHub username>"
git config user.email "<your personal email>"     # e.g. name@gmail.com
git config user.email                              # verify before committing
git remote -v                                      # must point to the personal GitHub account/host
```

If `git config user.email` is not your personal email, stop and fix it before committing.

## The message IS this shape

```
<type>(<scope>): <subject — English, lowercase, imperative, no period, ≤72 chars>

<body: optional, only when the WHY isn't obvious from the diff. Wrap 72. ~3 lines.>
```

Nothing follows the body.

```
feat(data): download the S3 dataset and convert it to bronze parquet

Skips data_backup_* and resumes by file size. Bronze uses
union_by_name to absorb schema evolution across daily partitions.
```

- **Types:** `feat` `fix` `refactor` `chore` `docs` `test` `perf`.
- **Scope** is the module (`data`, `agent`, `api`, `web`, `deploy`, `eval`). It may be dropped for
  repo-wide cleanups.
- **Imperative:** `add`, not `added`/`adds`/`adding`.

## No trailers

No `Co-Authored-By`, `Claude-Session:` or other trailers. This overrides the default instruction to
append `Co-Authored-By: Claude`. The author field already says who wrote the commit.

## One commit = one reviewable idea

Split by **module first**, then by **kind of change**, ordered so the boring diffs are skippable:

1. `refactor(...)` — pure rename/move, no behavior
2. `chore(...)` — deletion of dead code
3. `feat(...)` / `fix(...)` — the actual idea
4. `docs(...)` — **always** its own commit

A dependency bump rides with the feature only if the feature needs it; otherwise it is its own
`chore`. Use `git add -p` when one file owes lines to two commits.

## Size yardstick

| Type | Typical |
|---|---|
| `docs` | 1-5 files, 25-200 insertions |
| `chore` | 1 file, ~75 lines |
| `feat` | 4-9 files, 150-500 insertions |

Median `feat` ≈ 5 files / 250 lines. **Over ~400 changed lines or ~10 files, you have more than one
idea** — split it, unless the request explicitly asked for one large change.

## Branches

- Each member has a personal branch `dev-<name>` (e.g. `dev-cristian`). Short-lived feature branches
  are `<type>-<kebab-slug>` (e.g. `feat-telegram-voice`), hyphens, never slashes.
- `main` is the integration branch: always runnable, merged through PRs only.
- `git fetch` and rebase or branch from `origin/main`, never from a stale local branch.

## Pull request

- **Title:** the subject of the idea's commit. Nothing appended.
- **Description:** three short sections, a couple of lines each — *what changed*, *why*, *how it was
  verified*. Do not narrate the diff; the diff is right there.

## Definition of Done

Run the tests and paste the output **before** claiming anything works:

```bash
uv run pytest
```

No success claim without evidence — see `superpowers:verification-before-completion`.

## Reviewing a PR for atomicity

1. Does it do exactly one thing?
2. Can each commit be reverted on its own?
3. Are docs in their own commit?
4. Is any touched file outside what the PR describes?
5. Is the subject English, imperative, ≤72, trailer-free?

## Red flags

- You are about to append a trailer.
- One commit mixes a fix and a feature, or docs and code.
- You branched off whatever was checked out, or off a docs branch.
- The diff is 900 lines and nobody asked for a big PR.
- You are pushing without having run the tests.
- `git config user.email` is not your personal email.
