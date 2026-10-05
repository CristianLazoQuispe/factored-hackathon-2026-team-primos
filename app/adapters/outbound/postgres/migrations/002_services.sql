-- Khipear pays service bills: one more kind of transfer. Safe to run more than once.
-- Apply to a database that already has ops: psql "$DATABASE_URL" -f 002_services.sql
-- schema.sql holds the same statements between the BEGIN/END markers; a test keeps them equal.
-- The catalog and the bills live in core: `python -m data_pipeline.load` creates them.

ALTER TABLE ops.transfers DROP CONSTRAINT IF EXISTS transfers_kind_check;
ALTER TABLE ops.transfers ADD CONSTRAINT transfers_kind_check
    CHECK (kind IN ('own_accounts', 'pay_debt', 'third_party', 'pay_service'));
