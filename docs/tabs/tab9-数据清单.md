# Tab 9: 覆盖天数分析 — 数据清单

## Excel 数据来源

### 产品出品表（_discover_sku_keys）

SKU 发现逻辑：遍历所有 sheet_name 包含"产品出品表"的 DataFrame，提取 `品类`、`品名`、`规格` 三列组合。

```
SKU Key 格式: "{品类}|{品名}|{规格}"
```

必需列：品类、品名、规格

### 总原料成本表（_build_material_catalog_map）

用于单位转换：提取原料的`订货单位`和`单位量`。

| 列 | 用途 |
|----|------|
| 品项名称 | 原料名（索引 key） |
| 订货单位 | 库存中的采购单位（如"箱"） |
| 单位量 | 1 订货单位等于多少基础单位（如 1 箱 = 12 L） |

转换逻辑：当库存单位 `!=` 订货单位时，`qty = qty × unit_qty`。

## BOM 展开（prep_engine.bom_expand_multi）

输入参数：

- `sheets`: Excel workbook DataFrames
- `{sku_key: qty}`: SKU 与计划产量（此处固定为 1）
- `basis="store"`: 以门店成本为基础

输出 DataFrame 列：

| 列 | 说明 |
|----|------|
| material | 原料名 |
| level | BOM 层级（1=直接原料，2=半成品原料，3=半成品的原料） |
| total_gross_qty | 总毛量（含损耗率） |
| purchase_unit | 采购单位 |
| total_purchase_qty | 总采购量 |
| unit_price | 单价 |
| is_semi_finished | 是否为半成品 |
| is_gap | 是否为缺口（BOM 不全） |
| gap_reason | 缺口原因 |

## 覆盖矩阵（build_coverage_matrix）

从 `sku_bom_dfs`（每个 SKU 的 BOM DataFrame）构建 material × SKU 矩阵：

```
输入: {sku_key: DataFrame from bom_expand(sku, 1)}
过滤: is_semi_finished == False（仅原料）
值:   gross_qty / total_gross_qty（每个 SKU 对每个原料的单位用量）

输出: pd.DataFrame(index=material, columns=SKU_keys, values=qty_per_unit)
      空缺值补 0.0
```

## 覆盖天数计算（compute_coverage）

### 核心公式

```
daily_consumption[material] = Σ(SKU) weekly_sales[sku] / 7 × qty_per_unit[material, sku]

effective_qty[material] = max(0, available_qty[material] - safety_stock[material])

coverage_days[material] = effective_qty[material] / daily_consumption[material]

coverage_days[SKU] = min(coverage_days[material]) for all materials used by this SKU
```

### 状态分类

| 状态 | 条件 |
|------|------|
| 充足 | coverage_days >= 30 |
| 一般 | 14 <= coverage_days < 30 |
| 不足 | 7 <= coverage_days < 14 |
| 紧急 | coverage_days < 7 |
| ∞ | daily_consumption == 0（不消耗该原料的 SKU） |
| gap_reason | 原料在 BOM 中被标记为缺口 |

### 缺口原料（gap_material）

BOM 展开时 `is_gap == True` 的原料被视为缺口。缺口原料不参与 SKU 覆盖天数的限制计算（即 SKU 的 limiting_material 只会从非缺口原料中选择）。

### 零销量处理

- 所有 SKU 销量为 0：所有原料的 `daily_consumption = 0`，状态设为 "∞"
- 单个 SKU 销量为 0：该 SKU 不参与计算，结果中 `coverage_days = None, status = "-"`
- 仅新品项（仅期末有数据）：消耗字段显示 "-"

## Supabase 库存数据

### v_inventory_latest_item_by_warehouse

库存数据来源。从 `client.list_latest_inventory_rows(limit=5000)` 获取，按 `warehouse_code` 过滤。

关键字段：

| 字段 | 用途 |
|------|------|
| item_name | 与 BOM 展开的 `material` 列匹配（原料名） |
| available_qty | 聚合为各原料的库存可用量 |
| unit | 库存单位（用于单位转换判断） |

聚合逻辑：按 `item_name` 聚合 `available_qty`，跨仓库求和。

## 数据持久化

### coverage_sales.json

位置：`state/coverage_sales.json`

格式：
```json
{
  "水果茶|芒果奶昔|标准杯": 120,
  "水果茶|杨枝甘露|标准杯": 85
}
```

## 函数签名

```python
def build_coverage_matrix(
    sku_bom_dfs: Dict[str, pd.DataFrame],
) -> pd.DataFrame

def compute_coverage(
    bom_matrix: pd.DataFrame,           # material × SKU 矩阵
    weekly_sales: Dict[str, float],     # {sku_key: weekly_qty}
    inventory: Dict[str, float],        # {material_name: available_qty}
    safety_stock: Optional[Dict[str, float]] = None,  # {material: ss_qty}
    gap_materials: Optional[Dict[str, str]] = None,   # {material: reason}
) -> tuple[pd.DataFrame, pd.DataFrame]  # (sku_coverage_df, material_coverage_df)
```
