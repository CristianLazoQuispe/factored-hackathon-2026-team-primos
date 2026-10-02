---
name: balance_inquiry
description: Check the balance, credit limit or status of the customer's own accounts and cards (savings, checking, credit card, debit card, loans, investments).
mcp: accounts
---

# Balance inquiry

1. Call `get_balances`. Pass `product_type` only if the customer named one type (for example
   "Tarjeta Crédito" for "mi tarjeta de crédito"); otherwise omit it to get every product.
2. Answer with the balance of each relevant product: type, last 4 digits, balance and currency.
   For credit cards, also give the credit limit.
3. If several products match and the customer asked about one, list them briefly and ask which
   one they mean.
4. If the customer has no products of that type, say so plainly.
5. Report amounts exactly as the tool returned them, with their currency. Never estimate.
