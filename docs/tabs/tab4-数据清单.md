# Tab 4: 产销计划 — 数据清单

## 数据源总览

| 数据源类型 | 路径 | 用途 |
|-----------|------|------|
| Supabase 库存快照 | `get_latest_inventory_rows()` | 仓库列表、补货计算 |
| Supabase 按仓库库存快照 | `get_latest_inventory_rows_by_warehouse()` | 指定仓库补货计划 |
| DataService 工作表 | `get_sheets()` | profit / recipe / serving 数据 |
| session state | `production_plans["销售计划_当前"]` | 销售计划存储 |
| session state | `production_plans["生产计划_当前"]` | 生产计划存储 |
| session state | `_bom_result` | BOM 展开结果 DataFrame |

---

## 数据流向

```
用户录入/上传 CSV → 销售计划 (session state)
                        ↓
        sales_to_production()  ←  sheets (配方表 + 出品表)
                        ↓
                    生产计划 (session state)
                        ↓
        bom_expand_multi()  ←  sheets (完整配方链)
                        ↓
                BOM 展开结果 DataFrame
                        ↓
        build_replenishment_plan()  ←  库存快照
                        ↓
                    补货计划 + 成本汇总
```

---

## DataService 方法

### `get_sheets()`
- 路径: `DataService.get_sheets()` → `build_sheets(client)` → `MpcSupabaseClient`
- 返回: `dict[str, pd.DataFrame]` — 多张工作表，供 calc 模块消费。
- 缓存: 会话级缓存（`_caches["sheets"]`），写入操作后失效。

### `get_latest_inventory_rows(limit=5000)`
- 路径: `DataService.get_latest_inventory_rows()` → `MpcSupabaseClient.list_latest_inventory_rows()`
- 返回: `list[dict]` — 最新库存快照的全部行。
- 用途: 构建仓库标签映射 `_build_warehouse_label_map_from_rows()`、仓库选择下拉。

### `get_latest_inventory_rows_by_warehouse(code, limit=5000)`
- 路径: `DataService.get_latest_inventory_rows_by_warehouse()`
- 返回: `list[dict]` — 指定仓库的库存行。
- 用途: Step 3 的补货计划计算。

---

## Calc 函数

### `sales_to_production(sales_rows, sheets, lead_days=1)`

**路径**: `mike_product_calc.calc.prep_engine.sales_to_production()`

**逻辑**: 将销售计划行转换为生产计划行。每行销售计划 → 根据产品出品表匹配配方 → 按比例计算出每个配料用量。

**公式**: 配料用量 = 销售数量 x 出品表.主原料用量 x 配方表.该配料用量 / denom

其中 denom = 产品成本计算表.规格（批次总重量, g）。

**输入**: `List[ProductionRow]` + `Dict[str, pd.DataFrame]`
**输出**: `List[ProductionRow]` (plan_type="production")

### `bom_expand_multi(sheets, sku_plan, basis="store", ...)`

**路径**: `mike_product_calc.calc.prep_engine.bom_expand_multi()`

**逻辑**: 对多个 SKU 执行三级 BOM 展开（SKU → 主原料/配料 → 原料），按物料聚合，合并结果。

**参数**:
- `sheets` — 所有工作表 DataFrame。
- `sku_plan` — 映射 `{sku_key: planned_qty}`。
- `basis` — 单价口径：`"store"`（加价后）或 `"factory"`（加价前）。
- `order_date`, `default_lead_days`, `default_loss_rate`, `default_safety_stock` — 回退值。

**输出列**: material, level, unit, purchase_unit, lead_days, total_plan_qty, total_gross_qty, total_safety_stock, total_purchase_qty, unit_price, total_cost, is_gap, gap_reason, is_semi_finished, sku_keys, latest_order_date。

### `gaps_only(df)`

**路径**: `mike_product_calc.calc.prep_engine.gaps_only()`

返回 `is_gap=True` 的行子集。

### `build_replenishment_plan(bom_df, inv_df)`

**路径**: `mike_product_calc.calc.inventory_linkage.build_replenishment_plan()`

将 BOM 展开结果与库存快照关联，计算每项物料的缺口量和建议补货量。

### `summarize_shortage_alert(plan_df)`

**路径**: `mike_product_calc.calc.inventory_linkage.summarize_shortage_alert()`

返回 `dict` 包含总缺口物料数、总缺口量等摘要指标。

---

## 模型

### `ProductionRow` (`mike_product_calc.model.production`)

| 字段 | 类型 | 说明 |
|------|------|------|
| date | str | 日期 YYYY-MM-DD |
| sku_key | str | SKU 或生产项名称 |
| spec | str | 规格（可选） |
| qty | float | 数量 |
| plan_type | str | "sales" 或 "production" |

---

## 数据流关键点

1. **销售计划 SKU** 来自产品毛利表 (`sku_profit_table().product_key`)。
2. **生产项下拉** 从 Excel 工作表 `"产品配方表_Gelato"` 和 `"产品出品表_Gelato"` 的"品名"和"配料"列提取。
3. **采购成本** 在 Step 4 汇总为按类型（半成品/原料）的分组统计。
4. **即时缺货检查** 在生成生产计划后立即执行，不存储结果；Step 3 的补货计划是完整的、可导出的。
