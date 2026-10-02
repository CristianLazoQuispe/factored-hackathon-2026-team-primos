# Tables you can query (schema `core`, written without the prefix: `FROM transactions`)

You only ever see the authenticated customer's own rows. Never filter by customer_id yourself.
The data is a static snapshot (roughly 2026-04-01 to 2026-06-18). For "last month", "this week" or
"the last contact", count back from the table's own latest date, e.g.
`(SELECT max(transaction_date) FROM transactions)`, never from `now()`.
Values below are the real ones in the data (Spanish for products and countries, English for most
statuses). Use them exactly: a wrong spelling returns no rows. A NULL means "not recorded".

## transactions  (one row per card/account movement)
transaction_id, product_id, transaction_date (timestamp), transaction_type
(Purchase|Payment|Transfer|Deposit|Withdrawal|Adjustment), transaction_category
(Food|Transport|Services|Entertainment|Health|Other; often NULL), amount (in `currency`),
currency (MXN|COP|ARS|USD), amount_usd (often NULL), channel (POS|App|Web|ATM|Branch|Transfer),
merchant_name (often NULL), merchant_category, transaction_country, transaction_city,
transaction_status (Approved|Declined|Pending|Reversed), response_code, is_fraud, fraud_score.
- Spending = Approved rows; never add amounts of different currencies (group by currency).
- transaction_country may read 'Mexico' or 'México' here: compare with ILIKE 'M%xico'.

## products  (accounts, cards, loans, investments, insurance of the customer)
product_id, product_type ('Cuenta Ahorro'|'Cuenta Corriente'|'Tarjeta Crédito'|'Tarjeta Débito'|
'Préstamo Personal'|'Préstamo Hipotecario'|'Inversión'|'Seguro'), product_number_last4, currency,
current_balance, credit_limit (credit products), product_status (Active|Blocked|Closed|Suspended).

## customers  (exactly one row: the customer)
customer_id, first_name, last_name, city, country ('México'|'Colombia'|'Argentina'), segment
(Premium|Plus|Basic|Student), customer_status (Active|Inactive|Suspended|Closed), preferred_language.

## complaints  (complaints, claims, requests and suggestions the customer filed)
complaint_id, creation_date, case_type (Complaint|Claim|Request|Suggestion), category
(Branch|Fees|Service|Technical|Transactions), subcategory ('Cargo no reconocido'|'Cobro indebido'|
'Problema con app'|'Atención en sucursal'|'Calidad de servicio'; often NULL), reception_channel
(App|Branch|Call Center|Email|Regulator|Web), affected_product_id, claimed_amount, currency,
priority (Low|Medium|High|Critical), status (Open|In Process|Escalated|Resolved|Closed|Rejected),
first_response_date, resolution_date, closing_date, sla_breached, resolution_days, resolution,
compensation_granted, resolution_satisfaction (1-5), is_repeat_complainer.
- "Open" cases = status IN ('Open', 'In Process', 'Escalated').
- `description` and `resolution` are generic template sentences: do not quote them as facts.

## call_center_interactions  (the customer's contacts with the bank: calls, chats, emails)
interaction_id, interaction_date, interaction_type (Inbound Call|Outbound Call|Chat|Email|Video),
channel (Phone|Web Chat|WhatsApp|Email|App|Web), contact_reason (Transaccional|Producto|Técnico|
Comercial|Queja|Retención), duration_seconds, wait_time_seconds, was_resolved (resolved in the
first contact), requires_followup, detected_sentiment (Muy Negativo|Negativo|Neutral|Positivo|
Muy Positivo), sentiment_score (-1 to 1), was_escalated, mentioned_products, has_transcript.

## satisfaction_surveys  (surveys the customer answered after a contact)
survey_id, interaction_id, survey_date, survey_type (CSAT|NPS|CES), send_channel
(Email|SMS|IVR|App|Web), main_score (CSAT 1-5, NPS 0-10, CES per its scale), nps_category
(Promoter|Passive|Detractor; often NULL), question_1..3_text / question_1..3_response,
open_comments, comment_sentiment (Positive|Neutral|Negative).
- Never average scores of different survey_type together.

## call_transcripts  (text of some contacts; short and generic)
transcript_id, interaction_id, full_text, customer_text, agent_text, detected_language,
main_topics, duration_seconds. Generated text: summarize, do not treat it as the customer's words.

## app_sessions  (app/web sessions)
session_id, started_at, ended_at, channel, platform, ip_country, ip_city, had_login, events.

## customer_service_summary  (one row, precomputed)
contacts_in_window, escalated_contacts, last_contact_at, last_contact_reason, open_complaints,
unrecognized_charge_complaints, is_repeat_complainer, last_csat.

## fx_rates  (public reference, not customer data)
date, source_currency, target_currency (MXN|COP|ARS|USD), exchange_rate (1 source = rate target),
buy_rate, sell_rate.
