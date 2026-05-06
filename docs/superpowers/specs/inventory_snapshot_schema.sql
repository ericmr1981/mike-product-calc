-- Supabase schema for 仓库库存快照上传
-- Source file sample: 仓库库存导出YYYY年MM月DD日HH时MM分SS秒.xlsx
-- Snapshot granularity: one full export file = one batch

-- 批次头表：记录每次导入任务
CREATE TABLE IF NOT EXISTS inventory_snapshot_batches (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_filename       TEXT NOT NULL,
  source_sheet_name     TEXT NOT NULL DEFAULT '仓库库存导出',
  source_file_sha256    TEXT,
  snapshot_at           TIMESTAMPTZ NOT NULL,
  imported_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  row_count             INTEGER NOT NULL DEFAULT 0,
  status                TEXT NOT NULL DEFAULT 'imported' CHECK (status IN ('imported', 'partial', 'failed')),
  warning_count         INTEGER NOT NULL DEFAULT 0,
  error_count           INTEGER NOT NULL DEFAULT 0,
  warning_summary       JSONB NOT NULL DEFAULT '[]'::jsonb,
  error_summary         JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT uq_inventory_snapshot_batches_file UNIQUE (source_filename),
  CONSTRAINT uq_inventory_snapshot_batches_sha UNIQUE (source_file_sha256)
);

CREATE INDEX IF NOT EXISTS idx_inventory_batches_snapshot_at
  ON inventory_snapshot_batches(snapshot_at DESC);

CREATE INDEX IF NOT EXISTS idx_inventory_batches_status
  ON inventory_snapshot_batches(status);

-- 明细表：每个批次中的库存行
CREATE TABLE IF NOT EXISTS inventory_snapshot_items (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id              UUID NOT NULL REFERENCES inventory_snapshot_batches(id) ON DELETE CASCADE,

  -- 原始字段
  item_code             TEXT NOT NULL,          -- 品项编码
  item_name             TEXT NOT NULL,          -- 品项名称
  spec                  TEXT,                   -- 规格
  unit                  TEXT NOT NULL,          -- 单位
  category_lv2          TEXT NOT NULL,          -- 二级品项类别
  category_lv1          TEXT,                   -- 一级品项类别
  item_attribute_name   TEXT,                   -- 品项属性名
  warehouse_name        TEXT NOT NULL,          -- 仓库名称
  warehouse_code        TEXT NOT NULL,          -- 仓库编码

  stock_qty             NUMERIC(18,6) NOT NULL, -- 库存量
  available_qty         NUMERIC(18,6) NOT NULL, -- 可用量
  occupied_qty          NUMERIC(18,6) NOT NULL, -- 占用量
  expected_out_qty      NUMERIC(18,6) NOT NULL, -- 预计出库量
  expected_in_qty       NUMERIC(18,6) NOT NULL, -- 预计入库量
  current_amount        NUMERIC(18,6) NOT NULL, -- 现存金额
  stock_unit_price      NUMERIC(18,6) NOT NULL, -- 库存单价

  -- 质量标记（不阻断导入）
  is_negative_stock     BOOLEAN NOT NULL DEFAULT FALSE,
  has_amount_mismatch   BOOLEAN NOT NULL DEFAULT FALSE,
  data_warnings         JSONB NOT NULL DEFAULT '[]'::jsonb,

  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- 同一批次内防重
  CONSTRAINT uq_inventory_items_batch_item_wh UNIQUE (batch_id, item_code, warehouse_code)
);

CREATE INDEX IF NOT EXISTS idx_inventory_items_batch
  ON inventory_snapshot_items(batch_id);

CREATE INDEX IF NOT EXISTS idx_inventory_items_item_code
  ON inventory_snapshot_items(item_code);

CREATE INDEX IF NOT EXISTS idx_inventory_items_warehouse_code
  ON inventory_snapshot_items(warehouse_code);

CREATE INDEX IF NOT EXISTS idx_inventory_items_negative_stock
  ON inventory_snapshot_items(is_negative_stock)
  WHERE is_negative_stock = TRUE;

-- 常用查询视图：每个仓库每个品项取最新快照
CREATE OR REPLACE VIEW v_inventory_latest_item_by_warehouse AS
WITH ranked AS (
  SELECT
    b.snapshot_at,
    i.*,
    ROW_NUMBER() OVER (
      PARTITION BY i.item_code, i.warehouse_code
      ORDER BY b.snapshot_at DESC, b.imported_at DESC
    ) AS rn
  FROM inventory_snapshot_items i
  JOIN inventory_snapshot_batches b ON b.id = i.batch_id
  WHERE b.status IN ('imported', 'partial')
)
SELECT *
FROM ranked
WHERE rn = 1;
