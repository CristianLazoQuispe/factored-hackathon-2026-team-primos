# LATAM Bank Dataset

> Sources: *LATAM Bank Dataset Summary* and *LATAM Bank Complete Data Dictionary* (v1.0.0).

## Key facts

| Attribute | Value |
|---|---|
| Nature | **Fully synthetic**, generated for Factored Datathon 2026 |
| Size | ~19M rows across 13 tables |
| Countries | Mexico, Colombia, Argentina |
| Date range | 2023-06-17 → 2026-06-17 |
| Currencies | MXN, COP, ARS, USD |
| Text language | **Spanish only** (Mexican, Colombian, and Argentine variants). **No Portuguese, no Brazil** |
| Storage | Amazon S3, `us-east-2`, read-only. Large fact tables are partitioned by `process_date` (year/month/day) |
| Access | Credentials are in the data dictionary PDF. **Keep them in a local `.env` only and never commit them** |

## Download size (measured 2026-09-26)

Everything is CSV under `s3://<bucket>/data/`, with fact tables split into daily hive partitions (`year=/month=/day=`, ~1.1k files each). `data_backup_20260831/` is an older copy and is ignored.

| Table | Size |
|---|---|
| digital_events | 3.76 GB |
| transactions | 808 MB |
| campaign_sends | 326 MB |
| call_center_interactions | 140 MB |
| call_transcripts | 137 MB |
| products | 68 MB |
| customers | 47 MB |
| satisfaction_surveys | 46 MB |
| complaints | 18 MB |
| others | < 1 MB each |
| **Total** | **~5.4 GB** (~1.6 GB without digital_events) |

It fits comfortably on a laptop. Parquet (zstd) is ~4-5x smaller: customers + branches + complaints go from 65 MB to 14 MB. Note: `complaints` has **67,095** raw rows, not the ~80k in the summary PDF.

## Intentional data-quality challenges

| Challenge | Rate |
|---|---|
| Duplicate records | ~2% |
| Null values (nullable fields) | ~5% |
| Late-arriving partitions | yes |
| Schema evolution | yes |
| Orphaned foreign keys | small % |

These are an opportunity: judges score how the data engineering handles them (contracts, dedup, late-arrival policy, lineage).

## Tables

### Dimensions

| Table | Rows | Columns most relevant to us |
|---|---|---|
| `customers` | 150k | customer_id, document_type/number, segment (Premium/Plus/Basic/Student), credit_score, estimated_monthly_income, customer_status, detected_accent, country |
| `products` | 400k | product_type (accounts, cards, loans, mortgage, investment), product_status (Active/Blocked/Closed/Suspended), credit_limit, interest_rate, days_past_due, has_linked_app |
| `branches` | 350 | location, type, hours |
| `service_agents` | 1.2k | experience_level, specialty, languages, native_accent, avg_csat, work_shift |
| `marketing_campaigns` | 200 | low relevance for customer service |

### Facts

| Table | Rows | Columns most relevant to us |
|---|---|---|
| `transactions` | 5M | transaction_type, amount, currency, amount_usd, merchant_name, merchant_category, channel, transaction_status (Approved/Declined/Pending/Reversed), response_code, **is_fraud, fraud_score**, country/city, lat/long |
| `call_center_interactions` | 800k | **contact_reason, reason_category** (Transactional/Product/Technical/Commercial/Complaint), channel, duration_seconds, wait_time_seconds, **was_resolved** (FCR), requires_followup, **was_escalated**, detected_sentiment, mentioned_products |
| `call_transcripts` | 200k | **full_text, customer_text, agent_text**, detected_language, detected_accent, detected_keywords, mentioned_entities (JSON), **detected_intents**, main_topics, audio_quality |
| `complaints` (PQR) | 80k | case_type, **category, subcategory, description**, **claimed_amount**, priority, status, **sla_breached**, resolution_days, **resolution**, compensation_granted, is_repeat_complainer, origin_interaction_id |
| `satisfaction_surveys` | 250k | survey_type (CSAT/NPS/CES), main_score, open_comments, comment_sentiment |
| `digital_events` | 10M | app/web events, errors, logins, sessions, ip_country |
| `campaign_sends` | 2M | low relevance for customer service |

### Reference

| Table | Rows | Notes |
|---|---|---|
| `daily_exchange_rates` | 3k | currency conversion |

## Key relationships

- `products`, `transactions`, `call_center_interactions`, `call_transcripts`, `satisfaction_surveys`, `digital_events`, `complaints`, `campaign_sends` → `customers.customer_id`
- `call_transcripts.interaction_id` → `call_center_interactions.interaction_id`
- `satisfaction_surveys.interaction_id` → `call_center_interactions.interaction_id`
- `complaints.origin_interaction_id` → `call_center_interactions.interaction_id`
- `transactions.product_id`, `complaints.affected_product_id`, `digital_events.product_id` → `products.product_id`
- `*.agent_id` → `service_agents.agent_id`; `*.branch_id` → `branches.branch_id`

## Candidate labels

| Target | Candidate source | Must check in EDA |
|---|---|---|
| Intent / routing | `contact_reason`, `detected_intents`, `complaints.category` | cardinality, class balance, whether it is trivially recoverable from keywords |
| Needs a human | `was_escalated`, `complaints.priority`, `sla_breached` | how it correlates with the text and whether it is consistent |
| Resolution | `was_resolved`, `complaints.status` | noise, share of nulls |
| Fraud | `is_fraud`, `fraud_score` | leakage between `fraud_score` and `is_fraud` |

Because the data is synthetic, these labels may be trivial or noisy. We **audit them and report what we find** rather than assuming they are valid.

## Known limitations to report

- No Portuguese text: the PT evaluation set will be team-generated and labeled as such.
- No real policy documents: the policy knowledge base will be synthetic and labeled as such.
- Transcripts are synthetic Spanish text, not real speech. Audio fields are metadata only.
