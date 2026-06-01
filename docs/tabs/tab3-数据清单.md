# Tab3: 原料价格模拟器 — 数据清单

## Excel Sheets（通过 get_sheets() 加载）

| Sheet 名称 | 关键字段 | 用途 |
|-----------|---------|------|
| Product Recipe Table_Gelato | product, ingredient, qty, unit | 配方 BOM |
| Product Output Table_Gelato | product, sku, price, cost | SKU 产出 |
| 总原料成本表 | material, base_price, final_price, unit | 原料价格 |

## Supabase 表

| 表 | 操作 | 用途 |
|----|------|------|
| raw_materials | apply_scenario() / rollback_batch() | 场景应用/回滚 |
| price_change_batches | list_price_change_batches() | 变更历史 |
| price_change_items | get_batch_details() | 变更明细 |

## 计算逻辑

- **SKU 利润**：sku_profit_table(sheets, basis) → 各 SKU 的售价/成本/毛利率
- **配方成本**：build_recipe_table(sheets, product, sku) → 用料明细 + 调整后价格
- **门店利润**：门店售价 - Σ(配料门店价 × 用量) = 门店毛利
- **工厂利润**：工厂售价 - Σ(配料工厂价 × 用量) = 工厂毛利
- **场景对比**：compare_scenarios(a, b) → 两场景差异 DataFrame
