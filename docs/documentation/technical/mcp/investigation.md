# `investigation` server

Skill `charge_investigation`: the bank checks its own records before asking the customer for anything. Code: `app/adapters/inbound/mcp/investigation.py`, SQL in `app/adapters/outbound/postgres/investigation.py`, use case in `app/application/investigate.py`, facts in `app/domain/evidence.py`. Common rules: [README.md](README.md).

## `investigate_charges(days, merchant?, min_amount?, max_amount?)`

The entry point. Finds the customer's charges that fit what they said (at most 3, newest first) and investigates each one.

| Argument | Values |
|---|---|
| `days` | 1 to 90, default 30, counted back from the dataset's last day |
| `merchant` | Case-insensitive substring (`"uber"`) |
| `min_amount`, `max_amount` | In the charge's own currency |

Returns:

- `findings`: each verified fact once.
  - `duplicate`: the same merchant, amount and currency posted again within 10 minutes, with `seconds_apart`. A pair is one finding.
  - `pending`: the charge is not final.
  - `reversed`: it was already reversed.
  - `foreign_purchase`: bought outside the customer's country, with the reference rate to USD when there is one.
- `charges`: the charges found, named `#1`, `#2`, `#3`. Internal transaction ids are never shown.
- `count` and `not_checked` (charges whose investigation failed: unknown, never "no").

## `investigate_charge(transaction_id)`

The same checks for one charge. A transaction that does not exist and one that belongs to another customer give the same answer: no such charge.

## `search_transactions(days, merchant?, min_amount?, max_amount?)`

The customer's charges that match, newest first, at most 20. Used when the customer has to pick one.

## Limits

- A duplicate needs the same `merchant_name`; a charge without a merchant never matches.
- Only Approved and Pending charges count as a possible double charge.
- The FX reference is the latest rate within 7 days before the charge.
- The organizer's data has no near-duplicate charges, so the duplicate scenarios are team fixtures (`DEMO-MX-DUPLICATE`, `DEMO-BR-PORTUGUESE`).
