-- A customer can hide their earlier conversations: they stop seeing them and the agent stops being told
-- about them, but the rows stay in the database (the bank keeps the record). Adds one column and the index
-- of what is visible, and drops or changes nothing. Safe to run more than once.
-- Apply to a database that already has 003_chat_memory.sql: psql "$DATABASE_URL" -f 004_chat_memory_hidden.sql
-- schema.sql holds the same statements between the BEGIN/END markers; a test keeps them equal.

ALTER TABLE ops.conversations ADD COLUMN IF NOT EXISTS hidden_at timestamptz;
CREATE INDEX IF NOT EXISTS conversations_visible ON ops.conversations (customer_id, last_message_at DESC) WHERE hidden_at IS NULL;
