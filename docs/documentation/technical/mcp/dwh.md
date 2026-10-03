# `dwh` server

Skill `data_lookup`. Code: `app/adapters/inbound/mcp/dwh.py`, SQL in `app/adapters/outbound/postgres/spending.py`, use cases in `app/application/{spending,run_sql}.py`. Common rules: [README.md](README.md).

The skill tries the four reviewed tools first. Only when none fits does the model write SQL.

## `get_movements(...)`

The customer's movements on their accounts and cards, newest first.

| Argument | Values |
|---|---|
| `days` | 1 to 365, default 30, counted back from the customer's latest transaction |
| `product_type`, `last4` | Narrow to one account or card |
| `transaction_type` | `Purchase`, `Payment`, `Transfer`, `Deposit`, `Withdrawal`, `Adjustment` |
| `status` | `Approved`, `Declined`, `Pending`, `Reversed` |
| `category` | `Food`, `Transport`, `Services`, `Entertainment`, `Health`, `Other` |
| `merchant` | Case-insensitive substring (`"uber"`) |
| `min_amount`, `max_amount` | In the movement's own currency |
| `order` | `newest` (default) or `largest` |
| `limit` | 1 to 50, default 20 |

Returns `count`, `truncated` (there are more than `limit`) and `movements`: date, type, amount, currency, merchant, category, channel, status, country, city, and the product's type and last 4 digits. No internal ids.

## `get_spending_summary(days)`

What the customer spent (Approved purchases) in the last `days` (1 to 365, default 30), against the same number of days before. One block per currency in `currencies`:

| Field | Meaning |
|---|---|
| `spend`, `previous_spend`, `change_pct` | This period, the one before, and the change (only when there was previous spending) |
| `transactions`, `tx_per_week`, `avg_ticket`, `max_ticket` | Count and ticket sizes |
| `by_category` | Amount and count per category |
| `top_merchants` | The five merchants with the most spending |
| `monthly` | Amount and count per month |
| `foreign` | Purchases outside the customer's country |

Five lookups run at once. One that fails is listed in `unavailable` and its fields are left out; the others still answer.

## `get_complaints()`

`count`, `open` (Open, In Process or Escalated), `by_status`, and the `latest` ten with type, category, subcategory, channel, priority, status, claimed amount and dates. The template `description` and `resolution` texts are not returned.

## `get_exchange_rate(source, target, on?)`

The reference rate between `USD`, `MXN`, `COP` and `ARS`: 1 `source` = `exchange_rate` `target`, with `buy_rate` and `sell_rate`. `on` gives the rate of that day or the closest earlier one. `found: false` when there is none.

## `describe_schema()` and `run_sql(sql)`: the fallback

For questions no tool covers. `describe_schema` returns the catalog of tables the model may query (`dwh_catalog.md`). `run_sql` takes one `SELECT` written by the model:

1. `app/domain/sql_scope.py` parses it and refuses anything but a single read-only SELECT over the allowlisted `core` tables, and any function it does not know.
2. Every customer-owned table is rewritten into a subquery filtered to the session customer, and the regenerated SQL is what runs.
3. The database is a second wall: role `dwh_reader` (SELECT on `core` only), read-only transaction, 3 s timeout.
4. At most 100 rows and 300 characters per cell come back. An error is returned as data (`error`, `blocked`) so the model can correct the query.

The reference questions and their expected answers are in `tests/dwh_questions.py`.
