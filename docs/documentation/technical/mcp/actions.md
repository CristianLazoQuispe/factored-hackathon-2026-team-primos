# `actions` server

Skill `account_actions`, only when `ACTIONS_ENABLED=true` and only for a customer the token proved. Code: `app/adapters/inbound/mcp/actions.py`; the gateway it calls: `app/application/actions.py`; the policy: `app/domain/actions.py`. How it all fits: [../actions.md](../actions.md). Common rules: [README.md](README.md).

**There is no tool here that changes anything.** The model can look at the customer's cards and charges and *propose* actions. A proposal is stored and waits; it only runs when the customer confirms it in the app, through a route the model cannot call.

## `my_cards()`

The customer's cards: `product_id` (what an action needs), `product_type`, `last4`, `currency`, `balance` and `status` as it is now (Active, Blocked, Cancelled, Closed or Suspended; a card the customer blocked or cancelled shows it, laid over the bank's status).

## `recent_charges(merchant?, days?, limit?)`

Recent purchases, newest first: `transaction_id` (what an inquiry needs), `transaction_date`, `merchant`, `amount`, `currency`, `status`.

| Argument | Values |
|---|---|
| `merchant` (optional) | Part of the name, cut to 60 characters |
| `days` | 1 to 365, default 30, counted back from the dataset's last day |
| `limit` | 1 to 20, default 8 |

The skill needs this because a skill's tool results are not kept between turns: when the customer says "open an inquiry about that Uber charge" a turn after the investigation, the agent finds the id again.

## `propose_actions(actions)`

At most 6 requested (the gateway keeps the first 3 and refuses the rest). Each is `{action, params}`:

| `action` | `params` |
|---|---|
| `block_card`, `cancel_card` | `product_id` |
| `open_payment_inquiry` | `transaction_id`, `note?` (the customer's words, up to 300 characters) |
| `request_callback` | `window`: `morning`, `afternoon` or `evening` |
| `set_alert` | `kind`: `duplicate_charge` or `payment_due`; `enabled` |
| `send_summary_email` | `topic`: `balances`, `payment_status` or `case_receipt` (only with an inquiry in the same call) |
| `transfer_money`, `make_payment`, `refund`, `reissue_card`, `raise_limit`, `change_phone`, `change_email`, … | none: refused or sent to a person, never done |

Returns the batch as the app draws it: `batch_id`, `language`, `needs_confirmation`, `strong`, `items` (each with `status`: `awaiting_confirmation`, `refused` or `escalated`, and the `text` to show), `expires_at`, `escalate`. Nothing has happened yet, and the description the model reads says so.

## What the session sets, and the model cannot

| In the MCP request `meta` | Used for |
|---|---|
| `customer_id` | whose cards, charges and actions |
| `signed_in` | `"1"` only if the token proved the customer. Without it every tool here is an error |
| `language` | `es` or `pt`, detected from the customer's message by code; anything else is stored as `es` |
| `thread_id` | the chat the proposal belongs to, so a person who picks the chat up sees what was proposed |
