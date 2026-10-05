---
name: balance_inquiry
description: The customer's own products and what they owe — balances and totals, credit limit and credit available, product status, debt on credit cards and loans (amount owed, payment due date, minimum payment or installment, days past due, interest rate), and their own profile (name, segment, since when they are a customer, products held).
mcp: accounts
---

# Balances, debts and profile

Pick the one tool that answers the question and call it right away:

- `get_balances`: balances, limits, credit available, status. Pass `product_type` only if the
  customer named one type (for example "Tarjeta Crédito" for "mi tarjeta de crédito"); otherwise
  omit it. For "how much do I have in total" answer from `totals`, one figure per currency.
- `get_debts`: what they owe and when to pay (due date, minimum payment or installment, past
  due amount, interest rate).
- `get_profile`: their own data on record (segment, since when they are a customer, products).

Rules:

1. Answer with the figures of each relevant product: type, last 4 digits, amount and currency.
   For credit cards, also give the credit limit when asked about the balance.
2. If several products match and the customer asked about one, list them briefly and ask which
   one they mean. If they have no product of that type, say so plainly.
3. Report amounts and dates exactly as the tool returned them, with their currency. Never
   estimate, and never add amounts of different currencies.
4. Payment dates and amounts from `get_debts` are illustrative figures as of `as_of` (the data
   is a snapshot): give them with that date ("al 18 de junio de 2026"). You cannot move money
   from this skill: if they want to pay, tell them to ask for it ("paga mi tarjeta").
5. A field that is absent from the result is unknown: say you do not have it, never zero.
