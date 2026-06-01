# Tab 8: 门店库存 — 页面结构

## 入口

```
app.py line 2472-2474:
    with tab8:
        _render_inventory_fragment(st.session_state.data_service.client)

_fragment → src/mike_product_calc/ui/inventory_tab.py:render_inventory_tab(client)
```

页面使用 `_render_inventory_fragment(client)` 包装在 Streamlit fragment 中，避免筛选提交时触发全应用重渲染。

## 布局

### 1. 标题与数据源说明

```
st.title("库存状态")
st.caption("数据来源：最新盘点 ({check_at})")        # 优先显示盘点数据
st.warning("库存快照已超过 2 小时未更新")             # 快照过期警告
```

数据优先级：`client.list_latest_check_items()` > `client.list_latest_inventory_rows(limit=5000)`（快照回退）

### 2. 安全库存设置折叠区

`st.expander("安全库存设置", expanded=False)`

- 对所有品项生成 editable DataFrame：品项编码（禁用）、品项名称（禁用）、单位（禁用）、安全库存（可编辑 NumberColumn，min=0）
- 底部 **保存安全库存设置** 按钮
- 数据存储在 `st.session_state["inv_safety_stock_map"]`（`dict[item_code, float]`）

### 3. 筛选表单

`st.form("inventory_filter_form")` 四列布局：

| 列 | 控件 | 选项 |
|----|------|------|
| 仓库 | `st.selectbox` | "全部" + 从数据提取的 warehouse_code 列表 |
| 品类 | `st.selectbox` | "全部" + `category_lv2` 去重值 |
| 安全状态 | `st.selectbox` | 全部 / 正常 / 低于安全库存 / 零库存 |
| 关键字 | `st.text_input` | 匹配 品项编码 / 品项名称（子串匹配） |
| 按钮 | `st.form_submit_button("应用筛选")` | 点击后将筛选条件写入 session_state |

筛选条件存储在 `session_state`（`inv_filter_warehouse_applied`、`inv_filter_category_applied`、`inv_filter_safety_applied`、`inv_filter_keyword_applied`）。点击"应用筛选"后更新这些值。筛选通过 `apply_inventory_filters()` 函数应用。

### 4. KPI 行

#### Row1：状态指标（4 列）

| 指标 | 数据来源 |
|------|----------|
| 总品项 | `kpis["total"]` |
| 缺货 | `kpis["out_of_stock"]`（`available_qty <= 0`） |
| 低库存 | `kpis["low_stock"]`（`available_qty <= reorder_point(5.0)`） |
| 异常 | `kpis["abnormal"]`（`is_negative_stock` 或 `has_amount_mismatch`） |

#### Row2：金额指标（3 列）

| 指标 | 计算方式 |
|------|----------|
| 库存总额 | `current_amount` 总计 |
| 原料/包材 | 总额 - 工具金额 |
| 工具 | `category_lv1` 或 `category_lv2` 包含"工具"的 `current_amount` 合计 |

格式：`¥X,XXX.XX`（<1万）或 `¥X.XX万`（>=1万）

#### Row3：消耗指标（4 列，来自 `build_consumption_kpis`）

| 指标 | 说明 |
|------|------|
| 消耗总额 | `total_consumption_amount` |
| 日均消耗额 | `daily_avg_amount`（总额 ÷ 天数） |
| 消耗品项数 | `consumption_item_count / total_matched_items` |
| 消耗最快 | `fastest_item_name` + `fastest_item_daily /天` |

### 5. 库存数据表

处理后的 DataFrame 通过 `shape_inventory_table(df, reorder_point=5.0, safety_stock_map=map)`：

- 新增列：`inventory_status`（基于 `classify_inventory_row`）、`safety_stock`（映射）、`safety_status`（基于 `classify_safety_status`）、`_priority`（排序用）
- 按优先级排序：异常(0) → 缺货(1) → 低库存(2) → 正常(3)
- 样式：零库存行红色背景（`#FFDDDD`）、低于安全库存行黄色背景（`#FFF3CD`）
- 隐藏列：`_priority`, `safety_status`, `snapshot_at`, `id`, `batch_id`, `category_lv1`, `item_attribute_name`, `warehouse_code`, `is_negative_stock`, `created_at`, `rn`

### 6. 消耗分析折叠区

`st.expander("📊 消耗分析", expanded=False)` （`render_consumption_expander`）

- **日期选择**：两列 date_input（默认取盘点批次起止日期，回退为当月1日至今）
- **查询按钮**：调用 `client.query_consumption(start_iso, end_iso)`
- **统计信息**：`{days}天 | 匹配品项：{matched} 项 | 新品项：{new_items_count} 项`
- **筛选/排序**：
  - 排序：消耗量 / 消耗金额 / 日均消耗 / 品项名称
  - 品类筛选：全部 + 数据中的 category 列
- **消耗表**：品项编码、品项名称、单位、期初库存、到货量、期末库存、消耗量、消耗金额、日均消耗、预计耗尽
  - 新品项消耗字段显示 "-"
  - 耗尽紧迫着色：urgent（<3天，红色 `#FFDDDD`），warning（3-7天，黄色 `#FFF3CD`），normal（无样式）

## 模块调用链

```
render_inventory_tab(client)
  ├─ client.list_latest_check_items()       ← 尝试盘点数据
  │   └─ → inventory_view.check_items_to_inventory_rows()
  ├─ client.list_check_batches()
  ├─ [fallback] client.list_latest_inventory_rows(5000)
  │              & get_latest_inventory_snapshot_at()
  │
  ├─ inventory_view._init_safety_stock()    ← 初始化安全库存 map
  ├─ inventory_view.shape_inventory_table() ← 加状态列、优先级排序
  ├─ inventory_view.build_inventory_kpis()  ← KPI 计算
  ├─ inventory_view.apply_inventory_filters() ← 筛选
  │
  ├─ render_consumption_kpi_row()           ← 消耗 KPI 行
  │
  └─ render_consumption_expander()          ← 消耗分析面板
       ├─ client.list_check_batches()
       ├─ client.query_consumption(start, end)
       └─ inventory_consumption.build_consumption_table()
```
