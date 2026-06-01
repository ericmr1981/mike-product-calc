# Tab 9: 覆盖天数分析 — 页面结构

## 入口

```
app.py line 2476-2478:
    with tab9:
        render_coverage_tab()
```

实现在 `src/mike_product_calc/ui/coverage_tab.py:render_coverage_tab()`。

## 布局

### 0. 标题与描述

```
st.header("📊 覆盖天数分析")
st.caption("基于输入每周销量、BOM配方和库存快照，预估SKU和原料的覆盖天数。")
```

顶部还有诊断栏（始终展示）：

```
诊断: sheets=✅ | SKUs=23 | 有销量=5 | 已计算=✅ | cov=5条
```

### 1. 每周销量输入（Section 1）

`st.subheader("📥 每周销量输入")`

- 从 Excel `产品出品表` sheets 中 `_discover_sku_keys()` 发现所有 SKU
- SKU key 格式：`{品类}|{品名}|{规格}`
- `st.data_editor` 展示表格：

| 列 | 控件 | 说明 |
|----|------|------|
| 品类 | TextColumn(disabled) | 只读 |
| 品名 | TextColumn(disabled) | 只读 |
| 规格 | TextColumn(disabled) | 只读 |
| SKU Key | TextColumn(disabled) | 只读 |
| 周销量(份) | NumberColumn(editable, min=0) | 唯一可编辑列 |

- `height = min(400, 40 * (len + 1))` 自适应高度
- 编辑后自动同步回 `st.session_state.coverage_sales`

**保存/加载按钮**（两列）：

| 按钮 | 行为 |
|------|------|
| 💾 保存销量 | 调用 `_save_sales()` 写入 `state/coverage_sales.json` |
| 📂 加载已保存销量 | 从 `_load_saved_sales()` 读取并填充表格，`st.rerun()` |

### 2. 仓库选择（Section 2，仅 Supabase 模式）

`st.subheader("🏭 选择仓库")`

- `st.multiselect`，从 `client.list_latest_inventory_rows(5000)` 提取仓库列表
- 选项标签格式：`"{warehouse_name}({warehouse_code})"`
- 默认全选

### 3. 计算触发按钮

`st.button("🔍 计算覆盖天数", type="primary", use_container_width=True)`

- 设置 `st.session_state.coverage_compute_requested = True`，触发表格下方计算流程。

### 4. 计算流程（state 驱动）

检测到 `coverage_compute_requested` 后：

1. **过滤有销量 SKU**：`weekly_sales > 0`
2. **BOM 展开**：对每个有销量的 SKU 调用 `bom_expand_multi(sheets, {sku: 1}, basis="store")`
3. **构建覆盖矩阵**：`build_coverage_matrix(sku_dfs)` → material × SKU 矩阵（每个 material 在每个 SKU 中的单位用量）
4. **加载库存**：从 `client.list_latest_inventory_rows(5000)` 获取，按选中仓库过滤，聚合到 `{item_name: total_available_qty}`
5. **单位转换**：从 Excel `总原料成本表` 提取 `{material: {order_unit, unit_qty}}`，调用 `_convert_inventory_unit()` 转换库存量与 BOM 用量单位一致
6. **安全库存**：从 `st.session_state.get("safety_stock_map", {})` 读取
7. **计算覆盖**：`compute_coverage(matrix, weekly_sales, inventory, safety_stock, gap_materials)`
8. 结果存入 `st.session_state.cov_sku_dicts` 和 `st.session_state.cov_mat_dicts`，`cov_computed = True`

### 5. BOM 展开明细（debug 折叠区）

`st.expander("🔍 BOM 展开明细")`

- 每个 SKU 的 DataFrame：material, level, total_gross_qty, purchase_unit, total_purchase_qty, unit_price, is_semi_finished, is_gap, gap_reason
- 覆盖矩阵 material × SKU 的 pivot table
- 原料目录单位信息（来自 总原料成本表）

### 6. 单位转换记录（debug 折叠区）

`st.expander("📐 单位转换记录")`

- 列出所有发生单位转换的原料和转换计算过程
- 如：`牛奶: 100 箱 → 1200.00 L (×12.0)`

### 7. SKU 覆盖天数结果

`st.subheader("🏷️ SKU 覆盖天数")`

DataFrame 列：

| 列 | 说明 |
|----|------|
| SKU | sku_key 格式 "品类|品名|规格" |
| 周销量 | 用户输入的周销量 |
| 限制原料 | 覆盖天数最少的原料名 |
| 覆盖天数 | 数值（单位：天），或 "-" |
| 状态 | 带表情符号前缀：🟢 充足 / 🔵 一般 / 🟡 不足 / 🔴 紧急 |

状态阈值：充足 >= 30d, 一般 >= 14d, 不足 >= 7d, 紧急 < 7d

### 8. 原料覆盖天数结果

`st.subheader("🧪 原料覆盖天数")`

DataFrame 列：

| 列 | 说明 |
|----|------|
| 原料 | 原料名 |
| 库存可用量 | `available_qty` |
| 安全库存 | `safety_stock` |
| 有效可用量 | `max(0, available_qty - safety_stock)` |
| 日消耗量 | `daily_consumption`（所有 SKU 合计） |
| 覆盖天数 | `effective_qty / daily_consumption` |
| 状态 | 同上带表情前缀 |

## 模块调用链

```
render_coverage_tab()
  ├─ Excel / Supabase: _discover_sku_keys(sheets)  ← 产品出品表
  │
  ├─ Section 1: data_editor for weekly sales
  │   └─ _load_saved_sales() / _save_sales()     ← state/coverage_sales.json
  │
  ├─ Section 2: warehouse multiselect
  │   └─ client.list_latest_inventory_rows(5000)  ← Supabase 视图
  │
  ├─ Computation (on "计算覆盖天数"):
  │   ├─ prep_engine.bom_expand_multi(sheets, {skus}, basis)
  │   ├─ coverage_analysis.build_coverage_matrix(sku_dfs)
  │   ├─ _build_material_catalog_map(sheets)      ← 总原料成本表
  │   ├─ _convert_inventory_unit(inventory, units, catalog)
  │   └─ coverage_analysis.compute_coverage(matrix, sales, inv, ss, gaps)
  │
  └─ Results (from session_state):
      ├─ SKU coverage DataFrame
      └─ Material coverage DataFrame
```
