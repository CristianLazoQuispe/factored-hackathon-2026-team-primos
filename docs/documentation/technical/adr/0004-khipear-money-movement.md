# 0004. Khipear: the agent moves money, the customer confirms

- Status: accepted, implemented
- Date: 2026-10-04 (scope revised and implemented on 2026-10-05)

## Context

Until now the agent only read: balances, debts, movements, and the investigation of a charge. The
team wants the agent to operate, not only to answer, and to give the operation a name of its own:
**khipear** ("khipéale 200 a Ana", "khipea 500 a mi tarjeta"), used as the verb for transferring
with the agent.

The data supports making this the next feature (see
[EDA 02](../../../../notebooks/EDA/02.EDA_Transactions_campaign_sends.ipynb), 3 years of the
organizer's dataset):

| Fact | Value |
|---|---|
| Transfers | 896,438 operations, USD 4,526M, about 61% of all value moved |
| Payments | 738,964 operations, USD 758M |
| Contact-centre contacts with reason "Transaccional" | 240,056, 35% of all contacts, 12,663 agent hours, 3.7 minutes on average, 91.5% resolved |
| Declined transactions | 221,234, USD 370M, 99,318 customers (60,027 with two or more) |

The dataset is synthetic and its columns were generated independently, so these figures size the
demand; they do not prove that a failed transfer causes a contact.

## Decision

A fourth skill, `money_movement`, lets the customer khipear in three ways.

| Operation (`kind`) | From | To |
|---|---|---|
| Between my accounts (`own_accounts`) | Own savings or checking account | Another own savings or checking account |
| Pay a debt (`pay_debt`) | Own savings or checking account | Own credit card or loan |
| To another customer (`third_party`) | Own savings or checking account | Another customer of the bank, named by **account number** or **customer ID** |

**The model proposes, code decides, the customer confirms with a button, code executes.** The model
never has a tool that moves money.

### The skill asks instead of guessing

A customer rarely says everything ("khipea 300 a mi tarjeta" does not say from which account). The
model passes only what the customer said, and code decides what is missing:

- One candidate: code takes it, no question.
- Several candidates, or last 4 digits that do not match exactly one: `propose_transfer` answers
  `needs_clarification` with the question and the options (type, last 4 digits, currency, balance
  or debt). The skill asks, the turn ends, and nothing is stored.
- The customer's answer ("la 2222") names no intent, so the router could not place it. The graph
  remembers which skill asked (`awaiting_skill`) and sends the next message back to it without a
  router call, unless that message is clearly another request ("mejor dime mi saldo").

The options come from the tool, never from the model's memory of the conversation.

### Flow

1. The customer writes or says "khipea 300 a mi tarjeta".
2. The router picks `money_movement` (with a regex fallback in `app/domain/routing.py`).
3. The skill calls `propose_transfer`. The result is `needs_clarification` (ask), `blocked` (say
   why, nothing stored) or `proposed` (a row in `ops.transfers` and a summary).
4. `POST /api/chat` returns the usual reply plus a `confirmation` object, taken from the tool's
   result and never from the model's text. The web shows a card: origin, destination, amount,
   currency, and **Confirmar** / **Cancelar**.
5. **Confirmar** calls `POST /api/khipu/confirm` with the transfer ID and the bearer token. No
   model runs. Code checks every rule again and executes in one database transaction.
6. The card shows the result: the new balance of the origin account, or why nothing moved.

### Components

| Layer | Piece | What it does |
|---|---|---|
| Domain | `app/domain/transfers.py` | Pure rules: which products can send, receive or be paid, how one is chosen, limits, the reason and response code of a block |
| Application | `app/application/transfers.py` | `propose`, `execute`, `cancel`, `transfer_options` over a `Ledger` port |
| Postgres | `app/adapters/outbound/postgres/transfers.py` | Reviewed SQL; `execute` is one transaction with row locks |
| MCP | `app/adapters/inbound/mcp/transfers.py` | Tools `list_transfer_options` and `propose_transfer`; no execute tool |
| Agent | `skills/money_movement/SKILL.md`, `graph.py` | The skill; `awaiting_skill` and `confirmation` in the graph state |
| HTTP | `POST /api/khipu/confirm`, `POST /api/khipu/cancel`, `confirmation` in `ChatResponse` | The only way to execute |
| Web | `web/components/khipu-card.tsx` | The card and its buttons |
| Schema | `ops.transfers`, `core.products.account_number` | The record of each operation; how a transfer names an account |

### Rules enforced in code

- The origin is an `Active` savings or checking account of the authenticated customer, who must be
  `Active` too. The customer comes from the session, never from the model or the request body.
- A product the model names (last 4 digits or type) that is not in the customer's own words is
  dropped before the rules run, so a guess becomes a question. After a clarifying question the
  model is trusted to map the answer ("la primera") to one of the options it was given.
- The destination decides the kind: money to the customer's own card or loan is a payment even
  if the model labelled it a transfer between accounts.
- A reply that speaks of confirming when no proposal was made is replaced by a fixed message:
  there would be no card on the screen.
- The amount is positive, with at most 2 decimals, and at most the origin's balance.
- Same currency on both sides. No currency conversion.
- Pay a debt: the destination is the customer's own credit card or loan that is not `Closed` and
  the amount is at most the debt. A blocked or past-due card can still be paid.
- To another customer by **account number**: the destination is exactly that account. Only savings
  and checking accounts have a number on record (`core.products.account_number`); a card's number
  is never loaded, so a card cannot be a destination.
- To another customer by **customer ID**: code picks that customer's oldest `Active` account in the
  origin's currency. The sender never sees or chooses among someone else's accounts.
- Of the recipient the customer sees only the first name and last initial, plus the last 4 digits
  when they typed the account number themselves. Never a balance.
- Limits for transfers to another customer: USD 1,000 per operation and USD 3,000 per day, or the
  equivalent at the latest rate in `core.fx_rates`. **These values are a team assumption** (the
  data has no limits); they are settings (`KHIPU_LIMIT_PER_OPERATION_USD`,
  `KHIPU_LIMIT_PER_DAY_USD`). Without a rate the transfer is refused.
- A proposal expires after 5 minutes and executes once. Confirming twice returns the same receipt
  and moves nothing the second time.
- At confirmation every rule runs again with the proposal and both products locked, because the
  balance or the day's total may have changed since the proposal.
- A block carries a plain reason and the response code a bank would give (51 insufficient funds,
  61 over the limit, 14 invalid account, 13 invalid amount, 57 not permitted), which also answers
  "why was my payment declined?".
- Every question, proposal, block, confirmation and cancellation is written to
  `ops.decision_log`.

### Where the money is recorded

`core` is the team's stand-in for the bank's core system. Executing updates
`core.products.current_balance` on both sides and inserts two movements in `core.transactions`
(`Transfer` on the origin; `Deposit` on a receiving account or `Payment` on a card or loan;
channel `App`, status `Approved`, response code `00`), so `get_balances` and `get_movements` show
it at once. The movements are dated at the dataset's last moment, not today: every "last N days"
in the agent counts back from `max(transaction_date)`, and a movement dated today would empty
those windows.

`ops.transfers` keeps the operation through its whole life (`proposed`, then `executed`,
`cancelled`, `expired` or `blocked`): who, from, to, amount, what the card showed, timestamps.
Reloading `core` with `python -m data_pipeline.load` resets the demo to the dataset's state;
`ops.transfers` remains as the trail. In a real deployment `execute` would call the bank's
transfer API instead.

## Alternatives considered

- **The model executes after the customer types "sí".** Rejected: a prompt injection or a model
  mistake could move money, and a typed or spoken "sí" is not attributable to a deliberate action.
- **Own accounts and card only.** Safer and smaller, since money never leaves the customer. The
  team chose to include transfers to another customer because it is the case people recognise.
- **Name the recipient by email.** Dropped: an account number or a customer ID is what a bank
  transfer uses, and an email would be one more way to probe who is a customer.
- **Let the sender pick among the recipient's accounts.** Rejected: it would show one customer the
  products of another.
- **Use `ops.pending_confirmations` for the proposal.** That table needs a row in `ops.sessions`,
  which the token login never writes. One table, `ops.transfers`, holds the proposal and its
  outcome instead.
- **A LangGraph interrupt for the clarifying question.** Not needed: the question is an ordinary
  reply, and one state field routes the answer back.
- **Ask for the password again at confirmation (step-up).** More convincing for a bank, deferred
  to keep the first version small. `ops.sessions.step_up_at` is there for it.

## Consequences

- **Autonomy:** the agent completes a transactional request end to end, with one click from the
  customer. It still cannot act alone.
- **Accuracy:** amounts and accounts come from code, not from the model's text. The card shows
  exactly what will be executed.
- **Risk:** this is the first write path. `core` stops being read-only for the application, and
  the database role of the API needs to update `core.products` and insert into
  `core.transactions`.
- **Latency and cost:** one tool call to propose; the answer to a clarifying question skips the
  router call; the confirmation makes no model call.
- **Human oversight:** every step is in `ops.decision_log` and `ops.transfers`; the operator
  console can show pending and executed operations later.
- **Channels:** Telegram has no confirmation card, so it answers that khipear is available in the
  web chat and the proposal expires. With the voice on, the web shows the same card; a spoken "sí"
  never confirms.
- **Demo data:** two team fixtures, `DEMO-MX-KHIPU` (two accounts, a credit card and a loan) and
  `DEMO-MX-RECIBE` (who receives), because the eight dispute scenarios have no accounts.

- **Next to the action gateway:** the actions of `account_actions` (block a card, open an inquiry;
  see [actions.md](../actions.md)) have their own policy, card and routes, and that policy refuses
  to move money. A transfer or a payment is sent to `money_movement` by code before the policy is
  asked, and khipear needs a signed-in customer like those actions do. `KHIPU_ENABLED=false`
  removes the skill and a transfer is refused as before; the action eval runs that way, because
  it measures the policy on its own. Folding khipear into the gateway (one card, one set of
  routes) is the natural next step.

## Open questions

- Spelling of the verb: the product is written **quipu**, the verb is **khipear**. The UI and the
  prompts use "khipear"; the routing fallback also accepts "quipea".
- Whether a later version converts currencies with `core.fx_rates`.
- Whether the chat should be told when a card is confirmed, so that "¿ya se hizo?" is answered
  from the conversation and not only from the balance.
