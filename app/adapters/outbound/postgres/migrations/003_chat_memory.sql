-- Chat memory: what each customer asked in earlier conversations, so the chat can show it when they come
-- back and the agent can be given a short summary of the last eight. It adds to the tables ops already has
-- (conversations, messages) and drops or changes nothing. Safe to run more than once.
-- Apply to a database that already has ops: psql "$DATABASE_URL" -f 003_chat_memory.sql
-- schema.sql holds the same statements between the BEGIN/END markers; a test keeps them equal.

ALTER TABLE ops.conversations ADD COLUMN IF NOT EXISTS customer_id text;
ALTER TABLE ops.conversations ADD COLUMN IF NOT EXISTS title text;
ALTER TABLE ops.conversations ADD COLUMN IF NOT EXISTS skill text;
ALTER TABLE ops.conversations ADD COLUMN IF NOT EXISTS outcome text;
ALTER TABLE ops.conversations ADD COLUMN IF NOT EXISTS last_message_at timestamptz;
ALTER TABLE ops.messages ADD COLUMN IF NOT EXISTS skill text;
CREATE INDEX IF NOT EXISTS conversations_by_customer ON ops.conversations (customer_id, last_message_at DESC);
CREATE INDEX IF NOT EXISTS messages_by_conversation ON ops.messages (conversation_id, message_id);
