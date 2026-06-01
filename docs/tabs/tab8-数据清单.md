# Tab 8: 门店库存 — 数据清单

## Supabase 表结构

### inventory_check_batches

盘点批次表。每次上传盘点 Excel 文件生成一条记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | PK |
| source_filename | text | 上传的原始文件名 |
| check_at | timestamptz | 盘点时间（从文件名解析 yyyy年MM月dd日） |
| row_count | integer | 导入行数 |
| status | text | imported / partial / failed |
| error_count | integer | 错误行数 |
| error_summary | jsonb | 错误分类统计 |
| created_at | timestamptz | 创建时间 |

API：
- `client.create_check_batch(data)` → POST
- `client.find_check_batch(source_filename)` → GET（防重复上传）
- `client.update_check_batch(id, data)` → PATCH
- `client.list_check_batches()` → GET（按 check_at 降序，limit 100）

### inventory_check_items

盘点明细表。每条记录一个品项。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | PK |
| batch_id | uuid | FK → inventory_check_batches.id |
| item_code | text | 品项编码 |
| item_name | text | 品项名称 |
| spec | text | 品项规格 |
| category | text | 品项类别 |
| unit | text | 库存单位 |
| system_qty | numeric | 系统库存 |
| first_check_qty | numeric | 初盘数量 |
| second_check_qty | numeric | 复盘数量 |
| diff_qty | numeric | 盘点差异（system - check） |
| avg_price | numeric | 库存均价 |
| diff_amount | numeric | 差异金额 |
| data_warnings | jsonb | 数据警告（negative_stock, amount_mismatch） |

API：
- `client.insert_check_items(rows)` → POST（批量，每次 500 条 chunked）
- `client.list_latest_check_items()` → 取最新批次的 items（GET batch_id=latest）

### inventory_delivery_batches

到货批次表。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | PK |
| source_filename | text | 文件名 |
| delivery_at | timestamptz | 到货时间 |
| row_count | integer | 行数 |
| status | text | 状态 |
| error_count | integer | 错误数 |
| error_summary | jsonb | 错误摘要 |

API 同 check_batches 模式。

### inventory_delivery_items

到货明细表。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | PK |
| batch_id | uuid | FK → inventory_delivery_batches.id |
| item_code | text | 品项编码 |
| item_name | text | 品项名称 |
| spec | text | 品项规格 |
| category | text | 品项类别 |
| unit | text | 库存单位 |
| delivery_qty | numeric | 到货数量 |

### inventory_snapshot_batches

库存快照批次表（旧数据源，如 Kingdee 导出）。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | PK |
| snapshot_at | timestamptz | 快照时间 |
| source_filename | text | 文件名 |
| source_file_sha256 | text | 文件哈希（防重） |
| status | text | imported / partial / error |
| row_count | integer | 行数 |
| error_count | integer | 错误数 |

### inventory_snapshot_items

库存快照明细表。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | PK |
| batch_id | uuid | FK → inventory_snapshot_batches.id |
| warehouse_code | text | 仓库编码 |
| warehouse_name | text | 仓库名称 |
| item_code | text | 品项编码 |
| item_name | text | 品项名称 |
| category_lv1 | text | 一级分类 |
| category_lv2 | text | 二级分类 |
| unit | text | 单位 |
| stock_qty | numeric | 库存数量 |
| available_qty | numeric | 可用数量 |
| occupied_qty | numeric | 占用数量 |
| expected_out_qty | numeric | 预计出库 |
| expected_in_qty | numeric | 预计入库 |
| current_amount | numeric | 当前金额（stock_qty × unit_price） |
| stock_unit_price | numeric | 单价 |
| item_attribute_name | text | 属性名 |

### v_inventory_latest_item_by_warehouse

视图，按 warehouse + item_code 去重取最新快照的数据。API 数据源：

```
client.list_latest_inventory_rows(limit=5000)
→ GET /rest/v1/v_inventory_latest_item_by_warehouse?limit=5000&order=warehouse_code.asc,item_code.asc

client.list_latest_inventory_rows_by_warehouse(code, limit=5000)
→ GET /rest/v1/v_inventory_latest_item_by_warehouse?warehouse_code=eq.{code}&limit=5000
```

## 计算逻辑

### 消耗计算（client._compute_consumption）

消耗分析的数学公式：

```
consumption_qty = max(0, start_qty + delivery_qty - end_qty)
consumption_amount = consumption_qty × avg_price
```

前提条件（来自 `query_consumption`）：

1. 在日期范围内找到至少 2 个盘点批次 → 最早 = start_batch，最晚 = end_batch
2. 获取 start_batch 和 end_batch 的 check_items（按 item_code 索引）
3. 获取日期范围内所有分发批次，按 item_code 聚合 `delivery_qty`
4. 对每个出现在 start 或 end 的 item_code 计算消耗
5. 仅在 start 和 end 都存在的品项标记为 `item_type = "matched"`，仅有 end 的标记为 `"new"`
6. `days = max(1, date_diff_days(start_date, end_date))`

### 消耗 KPI（build_consumption_kpis）

| KPI | 计算方式 |
|-----|----------|
| total_consumption_amount | 所有 consumed_items（consumption_qty > 0）的 consumption_amount 之和 |
| daily_avg_amount | total_consumption_amount / days |
| consumption_item_count | consumption_qty > 0 的品项数 |
| total_matched_items | item_type == "matched" 的品项数 |
| total_new_items | item_type == "new" 的品项数 |
| fastest_item_name | consumption_qty 最大的品项 |
| fastest_item_daily | 最大 consumption_qty / days |
| top_category_name | 按 category 聚合 consumption_amount 最大的分类 |

### 库存状态分类（classify_inventory_row）

| 状态 | 条件 |
|------|------|
| 异常 | `is_negative_stock == True` 或 `has_amount_mismatch == True` |
| 缺货 | `available_qty <= 0` |
| 低库存 | `0 < available_qty <= reorder_point(5.0)` |
| 正常 | 其他 |

### 安全库存状态（classify_safety_status）

| 状态 | 条件 |
|------|------|
| zero_stock | available_qty <= 0 |
| below_safety | 0 < available_qty < safety_stock |
| normal | available_qty >= safety_stock 或 safety_stock 为 None/0 |

### 耗尽紧迫度（classify_depletion_urgency）

| 等级 | 条件 |
|------|------|
| urgent | 预计耗尽 < 3 天（背景色 #FFDDDD） |
| warning | 3-7 天（背景色 #FFF3CD） |
| normal | > 7 天或充足 |

### 快照过期检测（is_snapshot_stale）

- 快照时间距当前 UTC 时间超过 `stale_hours=2` 小时视为过期
- 过期时显示 `st.warning("库存快照已超过 2 小时未更新")`

## 数据优先级

```
盘点数据（check_items） → 最优
  └─ 不可用时回退到 ...
库存快照视图（v_inventory_latest_item_by_warehouse） → 次优
  └─ 404 错误 → 显示提示信息
```

## 导出规范

### 盘点文件格式

文件名匹配正则：`盘点.+?\d{4}年\d{2}月\d{2}日?(\d{2}时\d{2}分\d{2}秒)?`

Excel 列（必须包含）：品项编码、品项名称、品项规格、品项类别、库存单位、初盘数量、复盘数量、系统库存、盘点差异、库存均价、差异金额、明细状态

### 到货文件格式

文件名匹配正则：`\d{8}`（如 到货记录20250529.xlsx）

Excel 列（必须包含）：品项编码、品项名称、品项规格、品项类别、库存单位、数量
