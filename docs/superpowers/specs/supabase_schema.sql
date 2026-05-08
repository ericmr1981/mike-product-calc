-- Supabase schema for 原料与配方管理模块
-- Run this in the Supabase SQL Editor to create all tables.

-- 原料表
CREATE TABLE IF NOT EXISTS raw_materials (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code            TEXT,
  name            TEXT NOT NULL,
  category        TEXT,
  item_type       TEXT DEFAULT '普通',
  unit            TEXT,
  unit_amount     NUMERIC(12,4),
  base_price      NUMERIC(12,4),
  final_price     NUMERIC(12,4),
  status          TEXT DEFAULT '已生效',
  item_main_image TEXT,
  item_identifier TEXT,
  item_spec       TEXT,
  item_brand      TEXT,
  item_mnemonic_code TEXT,
  item_stat_subject TEXT,
  item_barcode    TEXT,
  item_order_barcode TEXT,
  item_management_type TEXT,
  item_shelf_life_unit TEXT,
  item_shelf_life NUMERIC(12,4),
  item_origin     TEXT,
  item_storage_method TEXT,
  item_thaw_duration TEXT,
  item_tax_rate   TEXT,
  item_purchase_unit TEXT,
  item_purchase_unit_qty NUMERIC(12,4),
  item_purchase_to_inventory NUMERIC(12,4),
  item_order_unit TEXT,
  item_order_unit_qty NUMERIC(12,4),
  item_order_to_inventory NUMERIC(12,4),
  item_consume_unit TEXT,
  item_consume_unit_qty NUMERIC(12,4),
  item_consume_to_inventory NUMERIC(12,4),
  item_volume_cm3 NUMERIC(12,4),
  item_weight_kg  NUMERIC(12,4),
  item_inventory_check_types TEXT,
  item_enabled    BOOLEAN,
  item_mall_sort_order NUMERIC(12,4),
  item_material_type TEXT,
  item_is_weighing BOOLEAN,
  item_tax_category TEXT,
  item_tax_rate_extra TEXT,
  item_replenish_strategy TEXT,
  item_attr_name  TEXT,
  item_raw_payload JSONB,
  markup_template_id TEXT,
  markup_item_identifier TEXT,
  markup_mode     TEXT,
  markup_value    NUMERIC(12,4),
  markup_raw_payload JSONB,
  notes           TEXT,
  synced_from_excel BOOLEAN DEFAULT FALSE,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_materials_category ON raw_materials(category);
CREATE INDEX IF NOT EXISTS idx_raw_materials_status ON raw_materials(status);

-- 产品/半成品主表
CREATE TABLE IF NOT EXISTS products (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name              TEXT NOT NULL,
  category          TEXT,
  version           TEXT,
  production_type   TEXT,
  status            TEXT DEFAULT '上线',
  is_final_product  BOOLEAN DEFAULT FALSE,
  notes             TEXT,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_products_final ON products(is_final_product);

-- 配方明细 BOM
CREATE TABLE IF NOT EXISTS recipes (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id        UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  ingredient_source TEXT NOT NULL CHECK (ingredient_source IN ('raw', 'product')),
  raw_material_id   UUID REFERENCES raw_materials(id) ON DELETE SET NULL,
  ref_product_id    UUID REFERENCES products(id) ON DELETE SET NULL,
  quantity          NUMERIC(12,4) NOT NULL,
  unit_cost         NUMERIC(12,4),
  store_unit_cost   NUMERIC(12,4),
  sort_order        INTEGER DEFAULT 0,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW(),

  CONSTRAINT chk_ingredient_ref CHECK (
    (ingredient_source = 'raw' AND raw_material_id IS NOT NULL AND ref_product_id IS NULL)
    OR
    (ingredient_source = 'product' AND ref_product_id IS NOT NULL AND raw_material_id IS NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_recipes_product ON recipes(product_id);

-- 出品规格
CREATE TABLE IF NOT EXISTS serving_specs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id        UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  spec_name         TEXT NOT NULL,
  main_material_id  UUID REFERENCES products(id) ON DELETE SET NULL,
  quantity          NUMERIC(12,4),
  packaging_id      UUID REFERENCES raw_materials(id) ON DELETE SET NULL,
  packaging_qty     NUMERIC(12,2) DEFAULT 1,
  product_price     NUMERIC(10,2) DEFAULT 0,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_serving_specs_product ON serving_specs(product_id);

-- 出品规格附加配料
CREATE TABLE IF NOT EXISTS serving_spec_toppings (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  serving_spec_id   UUID NOT NULL REFERENCES serving_specs(id) ON DELETE CASCADE,
  material_id       UUID NOT NULL REFERENCES raw_materials(id) ON DELETE SET NULL,
  quantity          NUMERIC(12,4) DEFAULT 1,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_toppings_spec ON serving_spec_toppings(serving_spec_id);

-- 同步日志
CREATE TABLE IF NOT EXISTS sync_log (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sync_type         TEXT NOT NULL,
  action            TEXT NOT NULL,
  source_sheet      TEXT,
  item_name         TEXT,
  details           JSONB,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- 库存快照导入：批次头表
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

-- 库存快照导入：明细表
CREATE TABLE IF NOT EXISTS inventory_snapshot_items (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id              UUID NOT NULL REFERENCES inventory_snapshot_batches(id) ON DELETE CASCADE,
  item_code             TEXT NOT NULL,
  item_name             TEXT NOT NULL,
  spec                  TEXT,
  unit                  TEXT NOT NULL,
  category_lv2          TEXT NOT NULL,
  category_lv1          TEXT,
  item_attribute_name   TEXT,
  warehouse_name        TEXT NOT NULL,
  warehouse_code        TEXT NOT NULL,
  stock_qty             NUMERIC(18,6) NOT NULL,
  available_qty         NUMERIC(18,6) NOT NULL,
  occupied_qty          NUMERIC(18,6) NOT NULL,
  expected_out_qty      NUMERIC(18,6) NOT NULL,
  expected_in_qty       NUMERIC(18,6) NOT NULL,
  current_amount        NUMERIC(18,6) NOT NULL,
  stock_unit_price      NUMERIC(18,6) NOT NULL,
  is_negative_stock     BOOLEAN NOT NULL DEFAULT FALSE,
  has_amount_mismatch   BOOLEAN NOT NULL DEFAULT FALSE,
  data_warnings         JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

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

-- 最新库存视图：每个仓库每个品项取最新快照
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
