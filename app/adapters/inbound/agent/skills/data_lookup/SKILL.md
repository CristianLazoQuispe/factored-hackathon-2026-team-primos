---
name: data_lookup
description: Questions that need looking through the customer's own data — their movements (by account or card, merchant, type or amount), totals and counts of their spending (by merchant, month, category or country, against the period before), their complaints, or an exchange rate. Not for balances or debts, or for a charge they do not recognize.
mcp: dwh
---

# Data lookup

1. If one of these tools answers the question, call it right away and answer from its result:
   - `get_movements`: a list of movements ("mis últimos movimientos", "mis compras en Uber",
     "mis compras más grandes", "los movimientos de mi tarjeta de crédito").
   - `get_spending_summary`: how much they spent, on what and where, and against the period
     before ("¿cuánto gasté?", "¿en qué gasto más?", "¿en qué comercios?", "en el extranjero").
     Set `days` to the period asked (30 for a month, 90 for a quarter, 365 for "en total").
   - `get_complaints`: how many complaints they have and in what state.
   - `get_exchange_rate`: the rate between two currencies.
2. Only when none of them fits: call `describe_schema` once, write ONE PostgreSQL `SELECT` that
   answers the question, and call `run_sql`. Never filter by customer: you only ever see this
   customer's rows. Never write anything but a SELECT. If the result has `error`, fix the query
   and try again once. If it still fails, say you could not find out. Do not guess.
3. Answer only from what the tool returned. Give amounts with their currency and never add
   amounts of different currencies. If `truncated` is true, say the list is partial.
4. An empty list or `count` 0 means the data has no such records; say exactly that, without
   inventing a reason. A figure that is absent or listed in `unavailable` is unknown, not zero.
5. Show the customer the answer, not the SQL or the tool, unless they ask how you got it.
