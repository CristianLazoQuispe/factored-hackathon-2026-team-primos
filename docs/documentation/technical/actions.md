# Actions: what the agent may do, and who decides

The agent used to answer. This is how it **acts** without being trusted to: the model only
*proposes*, code decides, the customer confirms through a channel the model does not control, and
the result is reported only after the effect has been read back.

> **Status.** Done and tested: the policy, the gateway, the Postgres and mail adapters, the MCP
> server and skill that propose, the routes that confirm, the deploy settings, and the
> confirmation card and message tray in the web. Off by default: `ACTIONS_ENABLED=false`, and with
> it off the agent's prompt, skills, routes and screen are what they were before actions existed.
> Moving money is not one of these actions: khipear has its own skill, routes and flag
> (`KHIPU_ENABLED`, [ADR 0004](adr/0004-khipear-money-movement.md)).

## The cycle

```
model proposes  ──►  gateway checks  ──►  customer confirms  ──►  executes  ──►  reads it back
 (typed, by name)   facts + policy        (button, own endpoint)   (≤3 tries)    (only then: "done")
```

1. **Propose.** `ActionGateway.propose` takes up to three actions by name with typed parameters
   (extra fields are an error). Each one is checked against facts the code reads from the bank's
   data, and the policy gives a verdict. Nothing runs yet.
2. **Confirm.** If any action needs it, the whole batch waits for the customer. The confirmation
   arrives at its own endpoint, bound to the customer's token, and is **not** a chat message: a
   "yes" written by the model or injected in a text cannot confirm anything. It expires in 10
   minutes. Confirming twice runs the batch once (an atomic `UPDATE ... WHERE status =
   'awaiting_confirmation'`; five simultaneous confirmations are tested).
3. **Execute.** In order, after checking the policy **again** (the card may have been blocked by
   the bank in the meantime). Transient errors are retried up to three times with a growing pause;
   permanent errors are not retried.
4. **Verify.** Each action is read back (the card's effective status, the case, the preference,
   the stored message). If the read-back does not show the effect, the action is `failed` with
   `verification_failed`, the customer is not told it was done, and a person is asked to look.
5. **Audit.** Every proposal and every outcome is a row in `ops.decision_log`.

The customer-facing text (the card, the result, the emails) is written by code in Spanish or
Portuguese from the stored action and the verified result. **No model text reaches a confirmation
card or an outgoing message.**

## What each request gets

| Request | Verdict | Why |
|---|---|---|
| Send a summary, payment status or case receipt by email | allowed, no confirmation | goes only to the registered contact, from a template |
| Set a duplicate-charge alert or a payment reminder | confirm | |
| Request a call from a person (morning, afternoon, evening) | confirm | |
| Open a payment inquiry about a charge | confirm | refused if the charge was **reversed** or **declined**, or is **still pending** (under 3 days) |
| Block a card | confirm | refused if it is not a card, already blocked or closed; **escalated** if the bank suspended it |
| Cancel a card | confirm, **spelling out that it cannot be undone** | **escalated** if there is a balance owed or a payment is past due, or if the *bank* (not the customer) blocked it |
| Transfer, pay, schedule a payment | refused by this policy | moving money is not one of these actions. A transfer or a payment goes to khipear (`money_movement`, [ADR 0004](adr/0004-khipear-money-movement.md)), which the router picks before this policy is asked; scheduling is not offered |
| Refund, reverse a charge, compensate, provisional credit | goes to a person | |
| Change phone, email or address | goes to a person | account-takeover risk |
| Raise a limit, credit eligibility | goes to a person | credit policy is not the model's |
| Reissue a card, unblock a card | goes to a person | |
| Anything not in the catalog | goes to a person | the default is to escalate |

A card or charge that belongs to someone else is answered exactly like one that does not exist
(`not_found`), so the answer reveals nothing.

Case priority and the hours a person has to answer come from signals computed in code, never from
the model: `possible_fraud` (flag, or score of 70 or more) is High / 4 h; a duplicate or a foreign
charge is Medium / 24 h; anything else is Low / 72 h. The 70 comes from the sample: charges the
dataset flags as fraud average a score of 55.7 against 14.8 for the rest.

## Where it writes

The action gateway **never writes** the bank's own tables (`core`); the one writer of `core` is khipear. What the customer does through an action is laid over them:

| Effect | Where |
|---|---|
| Block or cancel a card | `ops.card_actions`, laid over `core.products.product_status` when read |
| Payment inquiry | `ops.disputes` + `ops.handoff_cases` (the case a person picks up) |
| Call request | `ops.handoff_cases` |
| Alerts | `ops.preferences` |
| Messages | `ops.outbox` |
| Every action and its state | `ops.actions` |

Applying it to a database that already has `ops`:
`psql "$DATABASE_URL" -f app/adapters/outbound/postgres/migrations/001_actions.sql` (safe to run
twice; a test keeps it identical to the block in `schema.sql`). **A deploy does not apply it.**

## What is simulated, honestly

- **The bank's systems.** Blocking a card changes a row in `ops`, not a core banking system. The
  contract is documented here; a production system would call the bank's own card API behind the
  same `EffectsPort`.
- **Email.** `MAIL_MODE=simulated` (the default) sends nothing: the message is stored in
  `ops.outbox`. `MAIL_MODE=smtp` sends through a real server, **only** to the closed list in
  `DEMO_INBOXES` (the customers' own addresses are synthetic and never receive anything). The
  agent says the server **accepted** the message, never that it was delivered: the code cannot
  verify delivery.
  The summary of balances is made with the template of `app/adapters/outbound/email_template`: the
  message has a plain-text part (what the outbox keeps) and an HTML part with the logo attached to the
  message, built from the same content (`app/domain/email_content.py`), so both carry the same figures.
  The payment status and the case receipt are still plain text. If the HTML cannot be made, the
  message goes as plain text. The receipt of a transfer goes by the same mail: see `mcp/transfers.md`.
- **SMS** is not implemented.
- **Identity.** In the demo the password of a customer ID is the ID itself, so these actions are
  only as safe as that sign-in. A real deployment needs the bank's identity provider and, for the
  riskiest actions, a one-time code to a registered device.

## How it is tested

| What | Where | Needs |
|---|---|---|
| The policy, priority, payment state, language, texts and emails | `tests/test_actions_domain.py` | nothing |
| The state machine: confirmation once, expiry, re-check, retries, verification, audit | `tests/test_actions_gateway.py` | nothing (in-memory ports) |
| Mail: closed list of inboxes, TLS and login, which errors are retried | `tests/test_mailer.py` | nothing |
| The template connected: what the balances summary and the transfer receipt say, the HTML and the text carrying the same figures, a hostile name staying text, the message Gmail needs, the button | `tests/test_email_connected.py` | nothing |
| A receipt goes out once, also with two requests at the same time | `tests/test_email_connected_sql.py` | Postgres (skipped otherwise) |
| The same promises on real tables, ownership, five simultaneous confirmations, the full cycle | `tests/test_actions_sql.py` | Postgres (skipped otherwise) |

The store contract tests run against the in-memory store and the Postgres one, so the state machine
is tested without a database *and* the real store is held to the same promises. Twenty-six
deliberate breakages of the policy, the gateway, the mailer and the SQL were each caught by at
least one test. A test also checks that every reason the policy can give has text in both
languages.

## Who can ask for an action

Only a customer **the token proved**. A customer who only typed an ID in the chat (the Telegram
path, for example) is never offered the skill: the router's catalog leaves it out, the router and the
skill both refuse it in code, and every tool of the MCP server refuses it a third time. A customer
number alone does not prove identity.

## What a model's turn is not trusted with

The first runs against Gemini showed three things a model does that a bank cannot accept. Each is
now handled by code, and each has a test that reproduces it.

| What the model did | What the code does now |
|---|---|
| Told the customer to "review and confirm below" when its proposal had failed: it had sent `actions` as one object instead of a list, and the error was invisible | The tool forgives that shape (one action, or the list as JSON text). Every tool error is logged by the server. A turn of this skill that ends with **no proposal, no question and no person** is not repeated: the customer reads "I could not prepare that action" instead |
| Said it could "propose a transfer, confirm below" and called **no tool**, without consulting the policy | A request to move money, pay, refund, change phone, email or address, raise a limit or reissue a card is recognised by code before the model (narrow patterns: it has to be asked for, "quiero…", "necesito…", "hazme…"). The policy answers, through the same tool and the same audit. A question about the same things ("¿cuánto me cobran por transferir?") still goes to the model |
| Sent the `params` of an action as text (JSON, a Python-style dict, or only the value) instead of an object. The action eval found it: it made the first call of a turn fail, and sometimes the turn | The tool reads the text (only literals, nothing is evaluated, and a lone value only for an action with one required parameter). The gateway still checks it all against the customer's data, so a value that is not theirs is refused |
| Looked up the cards and wrote "review and confirm below" **without calling `propose_actions`**. The action eval saw it in 4 of 86 runs, and the guard answered "I could not prepare that action" even to "block my card" | The turn gets **one more chance**: the model is told, as a note that is not kept in the conversation, that nothing is proposed and what to do. It then proposes (and the policy answers in its own words, also for "already blocked"). If it still does not, the guard answers as before |
| Wrote a false claim and ended it with a question ("I blocked your card. ¿Algo más?"): any reply with a question mark used to count as a question | A reply that claims an action was done, points to a card that is not there, or promises to move money is not excused by a question mark (`app/domain/claims.py`, the same patterns the action eval counts as unsafe). A true statement ("your card is already blocked") or an offer in a question still goes through |
| Proposed twice in one chat | The newest proposal replaces any still waiting in that chat, so only one confirmation button is live |

A request for something the bank never does is also answered with no model turn at all, so it is
cheaper and the answer does not vary from one run to the next. Where a model is trusted is
understanding what the customer wants and finding the card or the charge; what is allowed, what is
said about it and what happened is never its to decide.

## The routes

| Route | What it does |
|---|---|
| `POST /api/actions/{batch}/confirm` | Runs the batch the customer confirmed. Body (all optional): `thread_id` (the chat, so a person who picks it up sees the outcome), `inbox` (a demo inbox the card offered). Asking again returns the same result |
| `POST /api/actions/{batch}/cancel` | The customer changes their mind |
| `GET /api/me/outbox` | What the system sent this customer: the simulated phone of the demo |

All three need the token, answer 404 for a batch that is not the token customer's, and answer 404
`actions_disabled` while actions are off. An outcome that failed verification or needs a person
turns the chat over to the operator console with the case file: what was proposed, what happened
and what is unresolved.

## On the screen

The chat draws what the agent proposes as a **card** (`web/components/action-card.tsx`): the title,
exactly what will be done, the irreversible warning for a cancellation, the demo inboxes to pick
from when an email is part of it, and **Confirmar** / **Cancelar**. Every sentence on it is written
by the API from what it stored, in the language of the conversation; the browser adds none. The
buttons are the confirmation: they call `POST /api/actions/{batch}/confirm` or `/cancel` with the
customer's token. While a request is on its way both buttons are locked, a failure is said inside
the card with the chance to try again, and once the API answers the same card shows what was
verified, or why nothing was done. An outcome that needs a person marks the message *agente de
soporte*.

**Mensajes** (`web/components/outbox-panel.tsx`) lists what the system sent the customer. It tells
the truth about each one: a simulated message says *simulado · no se envió*; one sent through a
real server says *aceptado por el servidor* and names the demo inbox; "delivered" is never said.
Asking for the tray uses the token as it is and never renews it or ends the session. With actions
off the API answers 404 and the button does not appear.

## What each demo customer can do

An action works for any signed-in customer who has what it needs: block and cancel need a card that is
not closed; an inquiry needs a charge that is not reversed and not pending for less than three days; the
email needs an address on file. Nothing in the code lists customers. `uv run python -m evals.actions.coverage`
asks the policy, with the data, what it would do for each one (a dry run: nothing is stored or executed);
point `DATABASE_URL` at the Cloud SQL proxy to check the customers that are really offered (it only
reads, eight customers at a time, and prints its progress). Do not run the tests in a shell with that
`DATABASE_URL`: they would skip, by design, but the habit is not worth having.

Measured on the eight `DEMO-*` customers of the sample data:

| Action | Result for all eight |
|---|---|
| Block a card | Proposed, with confirmation |
| Open an inquiry | 24 or 25 of their last 25 charges are eligible. The ones that are not are the cases built to be refused: the pending Amazon charge of `DEMO-CO-PENDING` and the reversed Mercado Libre charge of `DEMO-AR-REVERSED` |
| Email a summary | Sent directly |
| Ask for a call, set an alert | Proposed, with confirmation |
| **Cancel a card** | **Sent to a person** (`outstanding_balance`): their only card is a credit card with a balance |

So cancelling a card can only be shown with a customer who holds a card with no balance. The tool counts
every card of each customer ("1 of 2" is one card that can be cancelled out of two) and says why the
others cannot, so it tells which of the offered customers can in the deployed data. Run on the
deployed data it showed block, inquiry, email, call and alert working for every customer checked (32),
and only a few able to cancel.

## Not done yet, and things to know

- The SQL tests build customers of their own in `core` (`TEST-ACT-<8 hex>` and `TEST-OTH-<8 hex>`)
  and remove them. If a run is stopped (Ctrl+C) before that, they are removed when the next
  session starts and when it ends, by a pattern that cannot match a real customer, in one
  transaction. Their data also respects the billing rule other tests check over the whole table, so
  leftovers are harmless even before they are removed.
- The web has no test runner in the repository. The behaviour of the card and the tray (37 checks
  with jsdom, among them the earlier sign-in and finance screens) was run outside it; the types,
  the linter and the static build do run in the project.
- A stolen card goes through `account_actions` and not straight to a person (the skill proposes the
  block *and* asks for a person); with actions off the old rule stays.
- Balances should show a blocked card as blocked: today only the actions' own facts apply the overlay.
- No scheduler, so reminders are stored as preferences but nothing sends them.
- Capacity: every statement opens its own connection, which is fine for a demo, not for load.
