-- Operational store for the customer-service agent.
--   core: read-mostly mirror of the bank, reloaded from silver by `python -m pipeline.load`.
--   ops:  written only by the agent's tools; append-only or audited. Never reloaded.
-- Rows seeded by the team (demo scenarios) carry is_synthetic_fixture = true.

DROP SCHEMA IF EXISTS core CASCADE;
CREATE SCHEMA core;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE core.customers (
    customer_id            text PRIMARY KEY,
    document_type          text,
    document_number        text,
    first_name             text,
    last_name              text,
    date_of_birth          date,
    email                  text,
    mobile_phone           text,
    city                   text,
    country                text NOT NULL,
    detected_accent        text,
    preferred_language     text NOT NULL DEFAULT 'es',
    segment                text,
    customer_status        text,
    is_synthetic_fixture   boolean NOT NULL DEFAULT false
);

CREATE TABLE core.products (
    product_id             text PRIMARY KEY,
    customer_id            text NOT NULL REFERENCES core.customers,
    product_type           text NOT NULL,
    product_number_last4   text,
    currency               text,
    current_balance        numeric(15, 2),
    credit_limit           numeric(15, 2),
    product_status         text,
    is_synthetic_fixture   boolean NOT NULL DEFAULT false
);
CREATE INDEX ON core.products (customer_id);

CREATE TABLE core.transactions (
    transaction_id         text PRIMARY KEY,
    customer_id            text NOT NULL REFERENCES core.customers,
    product_id             text,
    transaction_date       timestamp NOT NULL,
    transaction_type       text,
    transaction_category   text,
    amount                 numeric(15, 2) NOT NULL,
    currency               text NOT NULL,
    amount_usd             numeric(15, 2),
    channel                text,
    merchant_name          text,
    merchant_category      text,
    transaction_country    text,
    transaction_city       text,
    transaction_status     text NOT NULL,
    response_code          text,
    is_fraud               boolean,
    fraud_score            numeric(5, 2),
    is_synthetic_fixture   boolean NOT NULL DEFAULT false
);
CREATE INDEX ON core.transactions (customer_id, transaction_date DESC);

CREATE TABLE core.fx_rates (
    date                   date NOT NULL,
    source_currency        text NOT NULL,
    target_currency        text NOT NULL,
    exchange_rate          numeric(14, 6) NOT NULL,
    buy_rate               numeric(14, 6),
    sell_rate              numeric(14, 6),
    PRIMARY KEY (date, source_currency, target_currency)
);

-- Derived from digital_events: one row per app/web session (evidence for "was it you?").
CREATE TABLE core.app_sessions (
    session_id             text PRIMARY KEY,
    customer_id            text NOT NULL REFERENCES core.customers,
    started_at             timestamp NOT NULL,
    ended_at               timestamp NOT NULL,
    channel                text,
    platform               text,
    ip_country             text,
    ip_city                text,
    had_login              boolean NOT NULL,
    events                 integer NOT NULL,
    is_synthetic_fixture   boolean NOT NULL DEFAULT false
);
CREATE INDEX ON core.app_sessions (customer_id, started_at DESC);

-- Derived from interactions, complaints and surveys: context for escalation rules and the case file.
CREATE TABLE core.customer_service_summary (
    customer_id               text PRIMARY KEY REFERENCES core.customers,
    contacts_in_window        integer NOT NULL,
    escalated_contacts        integer NOT NULL,
    last_contact_at           timestamp,
    last_contact_reason       text,
    open_complaints           integer NOT NULL,
    unrecognized_charge_complaints integer NOT NULL,
    is_repeat_complainer      boolean NOT NULL,
    last_csat                 integer
);

-- Customer-service history (organizer data). Only the columns the agent may talk about.
CREATE TABLE core.complaints (
    complaint_id           text PRIMARY KEY,
    customer_id            text NOT NULL REFERENCES core.customers,
    creation_date          timestamp NOT NULL,
    case_type              text,
    category               text,
    subcategory            text,
    reception_channel      text,
    affected_product_id    text,
    description            text,
    claimed_amount         numeric(15, 2),
    currency               text,
    priority               text,
    status                 text NOT NULL,
    first_response_date    timestamp,
    resolution_date        timestamp,
    closing_date           timestamp,
    sla_breached           boolean,
    resolution_days        integer,
    resolution             text,
    compensation_granted   numeric(15, 2),
    resolution_satisfaction integer,
    is_repeat_complainer   boolean
);
CREATE INDEX ON core.complaints (customer_id, creation_date DESC);

CREATE TABLE core.call_center_interactions (
    interaction_id         text PRIMARY KEY,
    customer_id            text NOT NULL REFERENCES core.customers,
    interaction_date       timestamp NOT NULL,
    interaction_type       text,
    channel                text,
    contact_reason         text,
    duration_seconds       integer,
    wait_time_seconds      integer,
    was_resolved           boolean,
    requires_followup      boolean,
    detected_sentiment     text,
    sentiment_score        numeric(4, 2),
    was_escalated          boolean,
    mentioned_products     text,
    has_transcript         boolean
);
CREATE INDEX ON core.call_center_interactions (customer_id, interaction_date DESC);

CREATE TABLE core.satisfaction_surveys (
    survey_id              text PRIMARY KEY,
    customer_id            text NOT NULL REFERENCES core.customers,
    interaction_id         text,
    survey_date            timestamp NOT NULL,
    survey_type            text NOT NULL,
    send_channel           text,
    main_score             integer NOT NULL,
    nps_category           text,
    question_1_text        text,
    question_1_response    integer,
    question_2_text        text,
    question_2_response    integer,
    question_3_text        text,
    question_3_response    integer,
    open_comments          text,
    comment_sentiment      text
);
CREATE INDEX ON core.satisfaction_surveys (customer_id, survey_date DESC);

CREATE TABLE core.call_transcripts (
    transcript_id          text PRIMARY KEY,
    customer_id            text NOT NULL REFERENCES core.customers,
    interaction_id         text,
    full_text              text,
    customer_text          text,
    agent_text             text,
    detected_language      text,
    main_topics            text,
    duration_seconds       integer
);
CREATE INDEX ON core.call_transcripts (customer_id);

-- ---------- ops: written by the agent's tools ----------

CREATE TABLE IF NOT EXISTS ops.sessions (
    session_id             uuid PRIMARY KEY,
    customer_id            text NOT NULL,
    issued_at              timestamptz NOT NULL DEFAULT now(),
    expires_at             timestamptz NOT NULL,
    step_up_at             timestamptz
);

-- Two-phase confirmation: a tool proposes, the customer confirms in the UI (never the LLM).
CREATE TABLE IF NOT EXISTS ops.pending_confirmations (
    confirmation_id        uuid PRIMARY KEY,
    session_id             uuid NOT NULL REFERENCES ops.sessions,
    action                 text NOT NULL,
    payload                jsonb NOT NULL,
    created_at             timestamptz NOT NULL DEFAULT now(),
    expires_at             timestamptz NOT NULL,
    confirmed_at           timestamptz
);

CREATE TABLE IF NOT EXISTS ops.card_actions (
    action_id              uuid PRIMARY KEY,
    product_id             text NOT NULL,
    customer_id            text NOT NULL,
    action                 text NOT NULL CHECK (action IN ('freeze', 'unfreeze')),
    requested_at           timestamptz NOT NULL DEFAULT now(),
    verified_at            timestamptz
);

CREATE TABLE IF NOT EXISTS ops.provisional_credits (
    credit_id              uuid PRIMARY KEY,
    idempotency_key        text NOT NULL UNIQUE,
    customer_id            text NOT NULL,
    transaction_id         text NOT NULL,
    amount                 numeric(15, 2) NOT NULL,
    currency               text NOT NULL,
    reason                 text NOT NULL,
    status                 text NOT NULL,
    created_at             timestamptz NOT NULL DEFAULT now(),
    verified_at            timestamptz
);

CREATE TABLE IF NOT EXISTS ops.disputes (
    dispute_id             uuid PRIMARY KEY,
    customer_id            text NOT NULL,
    transaction_id         text NOT NULL,
    investigation_result   jsonb NOT NULL,
    status                 text NOT NULL,
    sla_due_at             timestamptz,
    tracking_token         text UNIQUE,
    created_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.handoff_cases (
    case_id                uuid PRIMARY KEY,
    customer_id            text NOT NULL,
    dispute_id             uuid REFERENCES ops.disputes,
    priority               text NOT NULL,
    reason_codes           text[] NOT NULL,
    case_file              jsonb NOT NULL,
    status                 text NOT NULL DEFAULT 'open',
    created_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.conversations (
    conversation_id        uuid PRIMARY KEY,
    session_id             uuid REFERENCES ops.sessions,
    channel                text NOT NULL,
    language               text,
    started_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.messages (
    message_id             bigserial PRIMARY KEY,
    conversation_id        uuid NOT NULL REFERENCES ops.conversations,
    role                   text NOT NULL,
    content                text NOT NULL,
    created_at             timestamptz NOT NULL DEFAULT now()
);

-- Audit trail: every proposal, policy decision and verified outcome.
CREATE TABLE IF NOT EXISTS ops.decision_log (
    log_id                 bigserial PRIMARY KEY,
    conversation_id        uuid,
    tool                   text NOT NULL,
    proposed               jsonb NOT NULL,
    policy_decision        text NOT NULL CHECK (policy_decision IN ('allowed', 'blocked', 'needs_confirmation', 'escalated')),
    policy_reason          text,
    executed               boolean NOT NULL DEFAULT false,
    verified               boolean NOT NULL DEFAULT false,
    created_at             timestamptz NOT NULL DEFAULT now()
);

-- ---------- read-only role for SQL written by the LLM (see app/domain/sql_scope.py) ----------
-- SELECT on core only: no ops, no writes. Whose rows a query sees is decided in code, not here.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dwh_reader') THEN
        CREATE ROLE dwh_reader NOLOGIN;
    END IF;
END
$$;
GRANT dwh_reader TO CURRENT_USER;  -- lets a non-superuser (Cloud SQL) run SET ROLE dwh_reader
GRANT USAGE ON SCHEMA core TO dwh_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA core TO dwh_reader;
