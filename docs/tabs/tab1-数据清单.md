# Tab1: 概览/校验 — 数据清单

## Supabase 表

| 表/视图 | 查询方式 | 字段 | 用途 |
|---------|---------|------|------|
| raw_materials | get_raw_materials() | id, name, category, status | 原料总数/活跃数 |
| products | get_products() | id, name, is_final_product | 产品总数/成品数 |
| serving_specs | get_all_serving_specs() | id, product_id, spec | 出品规格数 |
| v_inventory_latest_item_by_warehouse | list_latest_inventory_rows() | available_qty, is_negative_stock, has_amount_mismatch | 缺货/异常统计 |

## 计算逻辑

- **缺货数**：inventory_rows 中 available_qty ≤ 0 的条数
- **异常数**：is_negative_stock = true 或 has_amount_mismatch = true 的条数
- **快照时效**：get_latest_inventory_snapshot_at() 距 now() 是否 > 2 小时
- **建议操作**：根据风险组合生成文本提示
