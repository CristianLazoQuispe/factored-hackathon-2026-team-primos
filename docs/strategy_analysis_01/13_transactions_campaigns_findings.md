# Transactions and Campaigns: Findings and Proposals

> Date: 2026-10-04. Measured on the **full** raw dataset: `transactions` (4,425,008 rows), `campaign_sends` (1,746,801),
> `marketing_campaigns` (200), 2023-06-17 → 2026-06-18. `customers`, `products`, `call_center_interactions` and
> `complaints` were used for lookups only.
> Follows [12_full_data_findings.md](12_full_data_findings.md). Part of the team EDA split (transactions + campaigns).

**Question:** how do customers behave financially, and do campaigns change that behaviour?

**Answer:** customers behave almost identically whatever their segment, channel or hour, and campaigns produce no
measurable change. What carries business weight is the volume of money that does not go through, the share of contacts
that are about a transaction, and the weight of transfers in the money moved.

Where everything is:

| What | Where |
|---|---|
| Notebook, executed, with all charts | [`notebooks/EDA/02.EDA_Transactions_campaign_sends.ipynb`](../../notebooks/EDA/02.EDA_Transactions_campaign_sends.ipynb) |
| Exploratory scripts, metric tables (CSV) and figures | `notebooks/EDA/eda02/` (`out/`, `figures/`) |
| Slide-ready charts (16:9 PNG) | `notebooks/EDA/eda02/slides/` |
| Proposal to let the agent move money | [ADR 0004](../documentation/technical/adr/0004-khipear-money-movement.md) |

To reproduce: `uv run python notebooks/EDA/eda02/00_prepare.py` (builds a Parquet cache in `data/interim/eda02/`), then
run the notebook or any script in `eda02/`.

## 1. Headline KPIs

| KPI | Value |
|---|---|
| Approved value, 3 years | USD 6,820M, about USD 190M a month, flat |
| Transactions that did not complete | 8.0% of 4.43M, worth USD 593M |
| Customers with at least one declined transaction | 99,318 of 150,000 (66%) |
| Contacts about a transaction | 240,056, 35% of all contacts, 12,663 agent hours |
| Transfers | 20% of operations, 61% of the value moved |
| Complaints for an unrecognised charge | 12,297, USD 10.4M claimed |
| Campaign funnel | 94.0% delivered, 27.9% opened, 5.6% clicked, 0.56% converted |
| Campaigns below their own conversion target | 160 of 161 |
| Change in 30-day spend after a delivered send, against control | +USD 6.94 on a USD 1,245 base (95% CI −16 to +29) |

## 2. How customers behave financially

1. **Flat activity.** About 122 thousand transactions, 75 thousand active customers (half the base) and USD 190M
   approved every month. No growth, no seasonality.
2. **Only the transaction type sets the amount.** Each type has a round ceiling: USD 500 for purchases and withdrawals,
   1,000 adjustments, 2,000 payments, 5,000 deposits, 10,000 transfers.
3. **Segments are identical.** Student, Basic, Plus and Premium all move USD 1,433 to 1,454 a month with the same ticket
   distribution and the same 5% decline rate.
4. **No peak hour and no problem channel.** About 184 thousand transactions in each of the 24 hours; the decline rate is
   between 4.96% and 5.12% on all six channels.
5. **Friction.** Declined: 221,234 operations, USD 370M. Pending: 88,343, USD 148M, 97% of them older than 30 days.
   Reversed: 44,750, USD 74M. 60,027 customers were declined two or more times.
6. **Low frequency, mild concentration.** The median customer makes 29 transactions in three years. The top 10% hold
   25.5% of the value.
7. **Dormant customers.** 15,485 customers never transacted; 13,185 of them are still marked `Active`.

## 3. Campaigns

8. **The funnel loses people at the open.** 1.75M sends, 9,799 conversions. Only 6.3% of customers ever converted, on a
   median of 11 messages each.
9. **Far below plan.** 9,078 conversions against 123,024 planned (7.4%). At the average recorded conversion value
   (USD 2,547) the gap is about USD 290M. This assumes `expected_conversion_rate` is a percentage of sends.
10. **Budget is not recovered.** The 146 campaigns with a budget total USD 39.1M and record USD 19.5M of conversion
    value; 101 return less than their budget.
11. **Two channels are not measured.** WhatsApp and Voice have no open data on any delivered send and record no clicks
    or conversions, while taking 37.7% of the send cost.
12. **Cost and volume do not line up.** SMS is 24.7% of sends and 57.5% of the cost. Push is 16.6% of sends and 0.2% of
    the cost, with a similar conversion rate (0.77% against 0.94%).
13. **Wrong audience.** 874,417 sends (50.06%) went to customers who do not accept marketing, 763,550 to a segment
    other than the campaign's target, 34,762 to customers whose account is closed.
14. **No fatigue.** The open rate goes from 40.6% on the first message to about 38% and stays there.

## 4. Do campaigns change behaviour?

Method: for each send, the customer's approved transactions 30 days before and 30 days after, with undelivered sends
as the control group, and a bootstrap 95% interval.

15. **No.** 0.74 transactions before and 0.74 after in every group. No group's interval excludes zero, including the
    customers recorded as converted.
16. **Recorded conversions leave no trace.** USD 23.6M of recorded conversion value against USD 0.23M of additional
    transactions. The promoted product is opened in 0.89% of cases after the send and 0.92% before.
17. **No effect on the contact centre.** About 29 interactions per 1,000 sends in the week before and in the week after.

## 5. Data quality

| Problem | Size | Effect |
|---|---|---|
| Type and channel that cannot go together (a purchase at an ATM, a transfer at a POS terminal) | 1,677,843 rows, 37.9% | Cross-tabulations cannot explain causes |
| Pending or reversed rows carrying a decline code | 126,391 of 133,093 | Response codes do not explain the status |
| Response codes split evenly (05, 14, 51, 54) | About 52 thousand declines each | "Why it failed" cannot be read from the data |
| Transactions before the product was opened or the customer registered | 18.7% | Tenure analysis is unreliable |
| `amount_usd` empty on USD rows; flat FX (350 ARS, 4,000 COP); no MXN | 57% of rows empty | Filled from the amount or the daily rate; 35 rows left without a value |
| `send_cost` empty | 15% of sends | Totals are scaled by the mean cost |
| Recorded send cost against campaign budget | USD 75K against USD 44.6M | The budget is not explained by sends |
| Duplicate charges (same customer, merchant and amount within 10 minutes) | 0 | The duplicate-charge demo case exists only in team fixtures |

Columns were generated independently, which matches what [12](12_full_data_findings.md) found for the service data.
Totals per column are usable. Relationships between columns are not.

## 6. What the agent covers today

| Case | Covered on `main` | Size in the data |
|---|---|---|
| Charge still pending | Yes | 88,343 operations, 60,720 customers |
| Charge reversed | Yes | 44,750 operations, 36,506 customers |
| Charge made abroad | Yes | 202,800 operations, 95,779 customers |
| Duplicate charge | Yes | 0 in the raw data |
| Payment declined | **No** | 221,234 operations, 99,318 customers |
| Moving money | **No** | Transfers and payments: 1.6M operations, USD 5,283M |

## 7. Proposals

### For the product

1. **Khipear: let the agent move money, with the customer confirming by a button.** Pay my card, between my accounts
   and to another customer. The model proposes, code decides, the customer confirms in the UI, code executes. Design in
   [ADR 0004](../documentation/technical/adr/0004-khipear-money-movement.md). Status: proposed, not implemented.
2. **Explain a declined payment.** The largest case and the one not covered. 95% of declines carry a response code, so
   the agent can translate it into a reason and a next step. It can ship alone or as the answer khipear gives when a
   proposal is blocked.
3. **Do not present the duplicate charge as the frequent problem.** It is a good demo, but the raw data has none.

### For the pitch

4. **Use these numbers:** USD 593M that did not complete, 66% of customers declined at least once, 240,056
   transactional contacts (12,663 agent hours, 3.7 minutes each, 91.5% resolved), transfers as 61% of the money, 12,297
   complaints for an unrecognised charge.
5. **Storyline:** the money is in transfers → a large share gets stuck → customers call about it and the calls are
   short and repetitive → the agent already explains three of the four big cases → next it operates.
6. **Six slide-ready charts** are in `notebooks/EDA/eda02/slides/`, one message each.
7. **Do not claim** that declines cause the calls (the contact rate after a failed transaction is the same as after an
   approved one: 12.5 against 12.6 per 1,000), nor that any segment, channel or hour behaves differently.
8. **To turn hours into dollars**, state the cost per agent hour as an assumption. The dataset has none.

### For the bank (from the campaign data)

9. Stop sending to customers who opted out of marketing: half of all sends.
10. Measure WhatsApp and Voice before spending more on them: 37.7% of the send cost with no outcome recorded.
11. Shift volume from SMS to Push: similar conversion at a fraction of the cost.

### For the team EDA

12. Join with the call-centre and complaints EDAs to size the contacts and complaints the agent could absorb, using
    the same `customer_id` and date range.
13. Reuse `eda02/00_prepare.py` for the USD value (`usd`) and the country normalisation instead of redoing them.

## 8. Limits

- Synthetic data: the null campaign effect describes this dataset, not a real bank.
- The control group (undelivered sends) is small (100,304 sends) but starts from the same level as the treated groups.
- Sends to the same customer are treated as independent in the bootstrap, which makes the intervals slightly narrow;
  they already include zero.
- The list of impossible type and channel pairs is conservative: app withdrawals and web deposits are not counted.
