# Architecture Overview

## Data Sources

```
Excel (.xlsx)
  └─ load_workbook() ──→ wb.sheets (Dict[str, DataFrame])
       │                     │
       │               ┌─────┘
       │               ▼
       │          Supabase Sync (excel_sync.py)
       │               │
       │               ▼
       │          Supabase Database
       │               │
       │          build_sheets() (supabase_adapter.py)
       │               │
       │               ▼
       │          _cached_build_sheets() → _st_sheets
       │               │
       ▼               ▼
  ┌─────────────────────────────────────┐
  │         Streamlit App (app.py)       │
  └─────────────────────────────────────┘
```

## Tab Data Sources

| Tab | Name | Data Source | Key Tables/APIs |
|-----|------|-------------|-----------------|
| 1 | 概览/校验 | Supabase API | `client.list_raw_materials()`, `sku_profit_table(_st_sheets)` |
| 2 | 原数据 | `_st_sheets` | Raw DataFrames from Supabase |
| 3 | 原料价格模拟器 | `_st_sheets` → `build_recipe_table()` | 总原料成本表, 产品出品表, 产品成本计算表, 产品配方表 |
| 4 | 产销计划 | `_st_sheets` → `sku_profit_table()` | 产品出品表 |
| 5 | 原料管理 | Supabase API | `raw_materials` table (CRUD) |
| 6 | 配方管理 | Supabase API | `recipes`, `raw_materials`, `products` tables |
| 7 | 出品规格 | Supabase API | `serving_specs`, `serving_spec_toppings` tables |
| 8 | 门店库存 | Supabase API | `inventory_snapshot_*` tables |
| 9 | 覆盖天数分析 | `_st_sheets` + Supabase API | 产品出品表 + inventory data |

## Data Flow Detail

### Supabase Sync Path (CLI: `mpc supabase upload` / `mpc supabase sync`)
```
Excel 总原料成本表 ──→ raw_materials table (base_price, final_price, unit_amount, ...)
Excel 产品配方表*  ──→ recipes table
Excel 产品出品表*  ──→ serving_specs + serving_spec_toppings tables
Excel 产品成本计算表*→ (computed from recipes + raw_materials)
Excel 产品毛利表*    → (computed from serving_specs + costs)
```

### _st_sheets Build Path (Supabase → In-Memory DataFrames)
```
build_sheets() reads:
  raw_materials → 总原料成本表 (rebuilds with markup info from raw_payload)
  recipes → 产品配方表_Gelato/雪花冰/饮品
  serving_specs → 产品出品表_Gelato/雪花冰/饮品
  products + serving_specs → 产品成本计算表_Gelato/雪花冰/饮品
  products → 产品毛利表_Gelato/雪花冰/饮品
```

### Tab3 (原料价格模拟器) Calculation Chain
```
_st_sheets
  → build_recipe_table(sku, basis)
    → sku_cost_breakdown() - extracts SKU items from 产品出品表
    → get_store_price_map() - 加价后单价 from 总原料成本表
    → get_brand_cost_map() - 加价前单价 from 总原料成本表
    → get_brand_spec_map() - 单位量 from 总原料成本表
    → get_semi_product_recipes() - sub-ingredients from 产品配方表
    → Computes per-level costs:
        Level 0: cost = usage_qty × (price / spec)
        Level 1: cost from 产品成本计算表
        Level 2: cost from 产品配方表 (keyed by semi+ingredient)
  → recipe_df (DataFrame with store_price, brand_cost, spec, cost, level)
    → User edits store_price via number_input
    → calc_cost = orig_cost × (new_sp / orig_sp)  [proportional scaling]
    → semi-store cost = sum of Level 2 children costs, scaled to SKU qty
    → total_cost = Level 0 costs + scaled Level 1 cost
    → brand_cost = factory_cost_map values (from factory-basis recipe)
```

## Key Files

```
app.py                          - Streamlit UI (all tabs)
src/mike_product_calc/
  data/
    loader.py                   - Excel file loading
    supabase_client.py          - REST API client for Supabase
    supabase_adapter.py         - build_sheets() - rebuilds DataFrames from Supabase
    cli_supabase.py             - CLI commands for Supabase sync
    excel_sync.py               - Excel → Supabase sync engine
    upload.py                   - File upload handling
    shared.py                   - Shared utilities
    validator.py                - Excel validation
  calc/
    recipe.py                   - build_recipe_table(), spec parsing, profit rate calc
    profit.py                   - sku_profit_table(), margin calculations
    material_sim.py             - ScenarioStore, Scenario, MaterialPriceAdjustment
    material_mgmt.py            - Material search/categories
    serving_mgmt.py             - Serving management
    ...
```

## Current Issues

1. **Dual data sources**: Tab3/4/9 use `_st_sheets` (rebuilt from Supabase), while Tab5/6/7/8 query Supabase directly. Values can diverge.
2. **`unit_amount` mapping**: The `单位量` field in `_st_sheets` maps from `raw_materials.unit_amount`, which sometimes contains purchase unit qty (1) instead of actual spec (e.g., 2000). Already fixed for 123 materials via direct SQL update.
3. **Tab3 cost recalculation**: After dedup+unit_amount fixes, total_cost and brand_cost calculations now match the xlsx baseline.
