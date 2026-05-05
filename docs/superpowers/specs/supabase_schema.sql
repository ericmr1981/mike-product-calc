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
  base_price      NUMERIC(12,4),
  final_price     NUMERIC(12,4),
  status          TEXT DEFAULT '已生效',
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
