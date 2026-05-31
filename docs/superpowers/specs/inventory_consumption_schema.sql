-- inventory_consumption_schema.sql
-- Extends the inventory system with inventory check (盘点) and delivery (到货) tables.

-- ============================================================
-- 1. 盘点批次头
-- ============================================================
CREATE TABLE IF NOT EXISTS inventory_check_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_filename TEXT NOT NULL,
    check_at        TIMESTAMPTZ NOT NULL,
    row_count       INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'imported',
    error_count     INTEGER NOT NULL DEFAULT 0,
    error_summary   JSONB DEFAULT '[]'::jsonb,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT valid_check_status CHECK (status IN ('imported', 'partial', 'failed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_check_batches_filename
    ON inventory_check_batches (source_filename);

-- ============================================================
-- 2. 盘点明细
-- ============================================================
CREATE TABLE IF NOT EXISTS inventory_check_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id         UUID NOT NULL REFERENCES inventory_check_batches(id) ON DELETE CASCADE,
    item_code        TEXT NOT NULL,
    item_name        TEXT NOT NULL,
    spec             TEXT,
    unit             TEXT NOT NULL,
    category         TEXT,
    system_qty       NUMERIC(18,6) NOT NULL DEFAULT 0,
    first_check_qty  NUMERIC(18,6),
    second_check_qty NUMERIC(18,6),
    diff_qty         NUMERIC(18,6),
    avg_price        NUMERIC(18,6),
    diff_amount      NUMERIC(18,6),
    data_warnings    JSONB DEFAULT '[]'::jsonb,
    UNIQUE (batch_id, item_code)
);

CREATE INDEX IF NOT EXISTS idx_check_items_batch
    ON inventory_check_items (batch_id);

CREATE INDEX IF NOT EXISTS idx_check_items_code
    ON inventory_check_items (item_code);

-- ============================================================
-- 3. 到货批次头
-- ============================================================
CREATE TABLE IF NOT EXISTS inventory_delivery_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_filename TEXT NOT NULL,
    delivery_at     TIMESTAMPTZ NOT NULL,
    row_count       INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'imported',
    error_count     INTEGER NOT NULL DEFAULT 0,
    error_summary   JSONB DEFAULT '[]'::jsonb,
    imported_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT valid_delivery_status CHECK (status IN ('imported', 'partial', 'failed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_delivery_batches_filename
    ON inventory_delivery_batches (source_filename);

-- ============================================================
-- 4. 到货明细
-- ============================================================
CREATE TABLE IF NOT EXISTS inventory_delivery_items (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id        UUID NOT NULL REFERENCES inventory_delivery_batches(id) ON DELETE CASCADE,
    item_code       TEXT NOT NULL,
    item_name       TEXT,
    spec            TEXT,
    unit            TEXT,
    category        TEXT,
    delivery_qty    NUMERIC(18,6) NOT NULL DEFAULT 0,
    UNIQUE (batch_id, item_code)
);

CREATE INDEX IF NOT EXISTS idx_delivery_items_batch
    ON inventory_delivery_items (batch_id);

CREATE INDEX IF NOT EXISTS idx_delivery_items_code
    ON inventory_delivery_items (item_code);
