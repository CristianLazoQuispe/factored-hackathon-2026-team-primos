# Changelog

Notable changes to the agent, its data and its deploy, newest first. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Started on 2026-10-03; earlier work is in the git history and the merged PRs.

Add a line under **Unreleased** in the same PR as the change. When `main` is tagged, the section takes the tag's name and date.

## [Unreleased]

### Changed
- Silver keeps a 12-month history of transactions and digital events, counted back from the last transaction. The full load is now 1.48M transactions and 5.3M events, whatever part of the source was downloaded.
- Spending, movements and the charge search count "the last N days" back from the dataset's last day, the same for every customer, instead of from each customer's latest transaction.

### Fixed
- Open complaints older than 90 days are reported as stale (`stale_open`) instead of as being handled. Two thirds of the source's "open" cases are over a year old.
- Closed credit cards and loans no longer get a payment schedule in `core.billing`.
