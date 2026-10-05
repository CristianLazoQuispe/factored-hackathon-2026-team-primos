-- Actions the agent proposes and the customer confirms. Safe to run more than once.
-- Apply to a database that already has ops: psql "$DATABASE_URL" -f 001_actions.sql
-- schema.sql holds the same statements between the BEGIN/END markers; a test keeps them equal.

ALTER TABLE ops.card_actions DROP CONSTRAINT IF EXISTS card_actions_action_check;
ALTER TABLE ops.card_actions
    ADD CONSTRAINT card_actions_action_check CHECK (action IN ('freeze', 'unfreeze', 'cancel'));
CREATE INDEX IF NOT EXISTS card_actions_product_idx ON ops.card_actions (product_id, requested_at DESC);

-- One row per proposed action, grouped in a batch the customer confirms once.
CREATE TABLE IF NOT EXISTS ops.actions (
    action_id              uuid PRIMARY KEY,
    batch_id               uuid NOT NULL,
    position               integer NOT NULL,
    customer_id            text NOT NULL,
    conversation_id        text,
    action                 text NOT NULL,
    params                 jsonb NOT NULL,
    view                   jsonb NOT NULL DEFAULT '{}',
    decision               text NOT NULL CHECK (decision IN ('allowed', 'needs_confirmation', 'blocked', 'escalated')),
    reason                 text,
    status                 text NOT NULL CHECK (status IN (
        'awaiting_confirmation', 'confirmed', 'executing', 'verified', 'failed',
        'cancelled', 'expired', 'refused', 'escalated', 'skipped')),
    language               text NOT NULL DEFAULT 'es',
    idempotency_key        text NOT NULL UNIQUE,
    attempts               integer NOT NULL DEFAULT 0,
    result                 jsonb,
    created_at             timestamptz NOT NULL DEFAULT now(),
    expires_at             timestamptz NOT NULL,
    confirmed_at           timestamptz,
    finished_at            timestamptz
);
CREATE INDEX IF NOT EXISTS actions_batch_idx ON ops.actions (batch_id, position);
CREATE INDEX IF NOT EXISTS actions_customer_idx ON ops.actions (customer_id, created_at DESC);

-- What the customer chose for alerts and reminders.
CREATE TABLE IF NOT EXISTS ops.preferences (
    customer_id            text NOT NULL,
    key                    text NOT NULL,
    value                  jsonb NOT NULL,
    updated_at             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, key)
);

-- Messages the system sent (or tried to). `accepted` means the mail server took the message,
-- not that it reached anyone; `destination` is the registered contact, masked, and
-- `delivered_to` the demo inbox it really went to.
CREATE TABLE IF NOT EXISTS ops.outbox (
    message_id             bigserial PRIMARY KEY,
    customer_id            text NOT NULL,
    action_id              uuid,
    channel                text NOT NULL CHECK (channel IN ('email', 'sms')),
    destination            text NOT NULL,
    delivered_to           text,
    template               text NOT NULL,
    language               text NOT NULL,
    subject                text NOT NULL,
    body                   text NOT NULL,
    mode                   text NOT NULL CHECK (mode IN ('simulated', 'smtp')),
    status                 text NOT NULL CHECK (status IN ('queued', 'accepted', 'failed')),
    provider_reply         text,
    attempts               integer NOT NULL DEFAULT 0,
    created_at             timestamptz NOT NULL DEFAULT now(),
    sent_at                timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS outbox_action_idx ON ops.outbox (action_id) WHERE action_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS outbox_customer_idx ON ops.outbox (customer_id, created_at DESC);
