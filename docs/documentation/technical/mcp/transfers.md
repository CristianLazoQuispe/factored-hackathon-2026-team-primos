# `transfers` server

Skill `money_movement` (khipear). Code: `app/adapters/inbound/mcp/transfers.py`, use cases in `app/application/transfers.py`, SQL in `app/adapters/outbound/postgres/transfers.py`, rules in `app/domain/transfers.py`. Common rules: [README.md](README.md). Why it is built this way: [ADR 0004](../adr/0004-khipear-money-movement.md).

This server **proposes** and never executes. There is no tool that moves money: a proposal runs only when the customer presses Confirmar, which calls `POST /api/khipu/confirm` with their token.

## `list_transfer_options()`

Returns `accounts` (the customer's Active savings and checking accounts, with `balance`) and `debts` (their credit cards and loans with something owed, with `debt`). Each item has `product_type`, `last4` and `currency`.

## `propose_transfer(kind, amount, from_last4?, to_last4?, from_type?, to_type?, to_account_number?, to_customer_id?)`

| Argument | Values |
|---|---|
| `kind` | `"own_accounts"`, `"pay_debt"` or `"third_party"` |
| `amount` | Greater than 0, in the currency of the origin account |
| `from_last4` (optional) | Last 4 digits of the account the money leaves |
| `to_last4` (optional) | Last 4 digits of the customer's own account, card or loan that receives it |
| `from_type` / `to_type` (optional) | The product type the customer named instead of its digits ("mi tarjeta" is `"Tarjeta Crédito"`). It narrows the candidates, so one that fits needs no question |
| `to_account_number` / `to_customer_id` | For `third_party`, exactly one of them |

The model passes only what the customer said. The result has a `status`:

| `status` | Meaning | Other fields |
|---|---|---|
| `needs_clarification` | More than one candidate, or the digits match none or several. Nothing is stored | `missing` (`origin` or `destination`), `options`, `ask` |
| `blocked` | A rule refuses it. Nothing is stored | `reason`, `response_code`, `detail` |
| `proposed` | Stored in `ops.transfers`, waiting for the button for 5 minutes | `confirmation`: `transfer_id`, `kind`, `origin`, `destination`, `amount`, `currency`, `expires_at` |

With one candidate, code takes it without asking. By customer ID, code picks the recipient's oldest Active account in the origin's currency. Of another customer the result only carries the first name and last initial.

| `reason` | `response_code` |
|---|---|
| `insufficient_funds` | 51 |
| `over_operation_limit`, `over_daily_limit` (to another customer; USD 1,000 and USD 3,000, a team assumption) | 61 |
| `recipient_not_found`, `destination_unavailable`, `same_account`, `own_account`, `nothing_to_pay`, `no_other_account` | 14 |
| `invalid_amount`, `over_debt` | 13 |
| `currency_mismatch`, `origin_unavailable`, `no_source_account` | 57 |
| `limit_unknown` (no exchange rate to check the limit) | 96 |

## `list_service_bills()`

Returns `bills`: the customer's pending service bills, the one due first on top. Each has `service` (`luz`, `agua`, `teléfono`, `internet` or `cable`), `biller`, `reference`, `amount`, `currency` and `due_date`. The catalog (`core.service_billers`) is team-defined and the bills (`core.service_bills`) are team-generated: illustrative, not bank records.

## `propose_service_payment(service?, from_last4?, from_type?)`

Prepares the payment of one pending bill from one of the customer's accounts. There is no amount argument: a bill is paid whole, for the amount in `core.service_bills`. `service` is the one the customer named; with none named and one bill pending, code takes that one. Only accounts in the bill's currency can pay.

The `status` is the same as for `propose_transfer`: `needs_clarification` (`missing` is `bill` or `origin`), `blocked` or `proposed`. The `confirmation` has `kind: "pay_service"` and a `destination` with the biller's `name`, the `service` and the `reference`. Reasons: `nothing_to_pay` (14), `no_source_account`, `origin_unavailable`, `currency_mismatch` (57), `insufficient_funds` (51) and, at the button, `already_paid` (94).

In `ops.transfers` the proposal keeps the bill in `destination_product_id` and the biller in `destination_customer_id`.

## The button: `POST /api/khipu/confirm` and `/api/khipu/cancel`

Body: `{"transfer_id": "<uuid>"}`. The customer is the one the bearer token proves. No model runs.

`confirm` locks the proposal and both products, runs every rule again, changes the two balances, adds two movements to `core.transactions` and marks the proposal `executed`, all in one transaction. It answers `executed` (with a `receipt` and the origin's `new_balance`), `blocked` (with `reason`), `expired` or `cancelled`; a transfer that does not exist or belongs to someone else is 404. Confirming twice returns the same receipt. For a service payment it locks the account and the bill, checks them again, lowers the one balance, marks the bill `paid` and adds one movement (`Payment`, category `Services`, the biller as merchant).

Both the tools and the routes write to `ops.decision_log` (`propose_transfer` with `needs_confirmation` when it proposes, `confirm_transfer`, `cancel_transfer`).

Tests: `tests/test_transfers.py` (rules, proposal and tools with a fake ledger), `tests/test_khipu_flow.py` (the question and its answer through the graph, the routes) and `tests/test_transfers_sql.py` (the real demo data; customers `DEMO-MX-KHIPU` and `DEMO-MX-RECIBE`).
