# Tab2: 原数据 — 数据清单

## Supabase 表

| 表名 | 查询方式 | limit | 字段 |
|------|---------|-------|------|
| raw_materials | query_table("raw_materials", 200) | 200 | id, name, category, base_price, final_price, ... |
| products | query_table("products", 200) | 200 | id, name, version, is_final_product, ... |
| recipes | query_table("recipes", 200) | 200 | id, product_id, raw_material_id, quantity, ... |
| serving_specs | query_table("serving_specs", 200) | 200 | id, product_id, spec_name, price, ... |
| serving_spec_toppings | query_table("serving_spec_toppings", 200) | 200 | id, serving_spec_id, material_id, qty, ... |

## 计算逻辑

无计算逻辑。纯展示原始数据。
