# Scenario Apply to Raw Materials + Price Change History

## Overview

Allow users to apply saved price scenarios from the Material Price Simulator
(Tab3) to actual raw material data in Supabase, with full history tracking
and rollback capability.

## Database: `price_change_log` table

```sql
CREATE TABLE price_change_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id UUID NOT NULL,
  material_name TEXT NOT NULL,
  material_code TEXT,
  old_final_price NUMERIC,
  new_final_price NUMERIC,
  scenario_name TEXT NOT NULL,
  applied_by TEXT DEFAULT 'streamlit',
  applied_at TIMESTAMPTZ DEFAULT now(),
  rolled_back_at TIMESTAMPTZ,
  rollback_reason TEXT
);
CREATE INDEX idx_pcl_batch ON price_change_log(batch_id);
CREATE INDEX idx_pcl_material ON price_change_log(material_name);
CREATE INDEX idx_pcl_time ON price_change_log(applied_at DESC);
```

## Backend: `supabase_client.py` additions

### `apply_scenario(scenario_name, adjustments) -> dict`

1. Generate `batch_id = str(uuid4())`
2. For each `MaterialPriceAdjustment` (item name + new final_price):
   - Look up `raw_material` by name via `list_raw_materials(search=name)`
   - If not found, skip with `status: "not_found"`
   - Record old `final_price`
   - `PATCH /raw_materials?id=eq.{id}` with `{"final_price": new_price}`
   - `POST /price_change_log` with batch_id, old/new prices, material info
3. Return `{batch_id, total, ok_count, changes[]}`

### `rollback_batch(batch_id, reason="") -> dict`

1. `GET /price_change_log?batch_id=eq.{batch_id}&rolled_back_at=is.null`
2. For each entry: `PATCH /raw_materials?id=eq.{id}` with `final_price = old_final_price`
3. `PATCH /price_change_log?batch_id=eq.{batch_id}` set `rolled_back_at = now()`, `rollback_reason`
4. Return `{batch_id, rolled_back_count}`

### `list_price_change_batches() -> list[dict]`

1. Query: `SELECT batch_id, scenario_name, MIN(applied_at) as applied_at,
   COUNT(*) as item_count, bool_and(rolled_back_at IS NOT NULL) as all_rolled_back
   FROM price_change_log GROUP BY batch_id, scenario_name ORDER BY applied_at DESC`

### `get_batch_details(batch_id) -> list[dict]`

1. `GET /price_change_log?batch_id=eq.{batch_id}&order=material_name`

## UI: Tab3 additions

### "应用到原料库" button per scenario

After the existing saved scenario display, add:

```
[方案名称]（X 项调价）
  [预览影响] [应用到原料库]
```

- **预览影响**: `st.popover` showing a table of item → new price
- **应用到原料库**: On click, show confirmation with expected changes,
  then call `apply_scenario`, show success/failure

### Price change history section

Below scenario list, add:

```
--- 价格变更记录 ---
[expander] 查看历史
  Batch table: time | scenario | items | actions
  [查看] button → expand batch detail
  [回滚] button → confirm + rollback (disabled if already rolled back)
```

## Data flow

```
Scenario (in-memory)
  → user clicks "应用到原料库"
  → supabase_client.apply_scenario()
  → PATCH raw_materials SET final_price = new_price
  → INSERT into price_change_log

price_change_log
  → user clicks "回滚"
  → supabase_client.rollback_batch()
  → PATCH raw_materials SET final_price = old_price
  → UPDATE price_change_log SET rolled_back_at = now()
```

## Files to modify

- `src/mike_product_calc/data/supabase_client.py` — new methods
- `app.py` — UI buttons and history display (Tab3 scenario section)

## Supabase migration

One-time: create `price_change_log` table via `apply_migration` MCP tool.
