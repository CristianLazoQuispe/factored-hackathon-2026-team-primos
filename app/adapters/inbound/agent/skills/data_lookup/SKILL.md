---
name: data_lookup
description: Questions that need looking through the customer's own data — totals, counts or lists of their spending and transactions (by merchant, month, category or country), their complaints and their contacts or satisfaction surveys with the bank, or an exchange rate. Not for balances or for a charge they do not recognize.
mcp: dwh
---

# Data lookup

1. Call `describe_schema` once, to see the tables and their quirks.
2. Write ONE PostgreSQL `SELECT` that answers the question, and call `run_sql`. Never filter by
   customer: you only ever see this customer's rows. Never write anything but a SELECT.
3. If the result has `error`, fix the query and try again once. If it still fails, say you could not
   find out. Do not guess.
4. Answer only from the rows returned. Give amounts with their currency and never add amounts of
   different currencies. If `truncated` is true, say the list is partial.
5. No rows means the data has no such records; say exactly that, without inventing a reason.
6. Show the customer the answer, not the SQL, unless they ask how you got it.
