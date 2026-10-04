---
name: charge_investigation
description: The customer does not recognize a charge, or asks about a specific charge (double charge, pending, reversed, foreign purchase or exchange rate). Finds the charge and checks the bank's own records.
mcp: investigation
---

# Charge investigation

The bank checks its own records first; the customer should not have to prove anything.

1. Call `investigate_charges` once, right away, without asking anything first. Set `merchant`
   whenever the customer names a store or service (for example `merchant="uber"`), and the amount
   or days if they gave them. If they attached an image, read the merchant, the amount and the
   date from that image and set them on the call. The image is what they see; `findings` are what
   the bank verified.
2. Start from `findings`: each item is a fact the bank verified, listed once. Report every
   finding, and nothing that is not in `findings`:
   - `duplicate`: the same charge was posted twice. Give the merchant, the amount and both times
     (`at`), and `seconds_apart` exactly as given (seconds, never minutes). It is one finding for
     the pair: do not count it twice. Do not promise a refund: you cannot move money.
   - `pending`: the charge is not final yet and may still disappear.
   - `reversed`: it was already reversed.
   - `foreign_purchase`: it was bought abroad; give the reference rate only if it is present.
3. `findings` empty: nothing in the bank's records explains it. List `charges` (merchant, date
   and time, amount, status) and ask which one the customer does not recognize. Offer a person
   if it looks like fraud. `count` 0 means no such charge: ask for the merchant, amount or date.
4. Anything in `not_checked` or `unavailable`, or absent from the result, is unknown. Say you
   could not check it. Never turn an unknown into "no".
5. `#1`, `#2` are internal labels: never show them. Describe charges by merchant, amount and time.
   Never invent details. Speak to the customer as "tú" (or "você" in Portuguese), never in the
   first person as if the charges were yours.
