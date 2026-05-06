# 库存定时上传 Agent 规则（基于当前导出模板）

## 1. 输入约束
- 文件名模式：`仓库库存导出YYYY年MM月DD日HH时MM分SS秒.xlsx`
- 目标 sheet：`仓库库存导出`
- 表头行：第 1 行（16 列）

## 2. 字段映射
- `品项编码` -> `item_code` (text, required)
- `品项名称` -> `item_name` (text, required)
- `规格` -> `spec` (text, nullable)
- `单位` -> `unit` (text, required)
- `二级品项类别` -> `category_lv2` (text, required)
- `一级品项类别` -> `category_lv1` (text, nullable)
- `品项属性名` -> `item_attribute_name` (text, nullable)
- `仓库名称` -> `warehouse_name` (text, required)
- `仓库编码` -> `warehouse_code` (text, required)
- `库存量` -> `stock_qty` (numeric, required)
- `可用量` -> `available_qty` (numeric, required)
- `占用量` -> `occupied_qty` (numeric, required)
- `预计出库量` -> `expected_out_qty` (numeric, required)
- `预计入库量` -> `expected_in_qty` (numeric, required)
- `现存金额` -> `current_amount` (numeric, required)
- `库存单价` -> `stock_unit_price` (numeric, required)

## 3. 批次逻辑（幂等）
1. 读取文件后计算 `sha256`。
2. 从文件名解析 `snapshot_at`（例如 `2026-05-06 20:20:44`，建议按 `Asia/Shanghai` 解析后转 UTC 入库）。
3. 写入 `inventory_snapshot_batches`：
   - `source_filename`, `source_file_sha256`, `source_sheet_name`, `snapshot_at`
4. 若 `source_filename` 或 `source_file_sha256` 已存在，视为重复批次，直接跳过并记录“duplicate_batch”。

## 4. 数据校验规则

### 4.1 阻断错误（整批失败）
- 找不到目标 sheet。
- 表头不匹配（16 列任一缺失）。
- 任意 required 字段列缺失。

### 4.2 行级阻断（该行丢弃，批次可继续）
- `item_code` / `warehouse_code` / `item_name` / `unit` / `category_lv2` 为空。
- 数值列无法转换为数字。
- 同批次出现重复键：`(item_code, warehouse_code)`。

### 4.3 行级告警（不阻断）
- `stock_qty < 0`：标记 `is_negative_stock = true`，warning=`negative_stock`。
- `abs(stock_qty * stock_unit_price - current_amount) > 0.05`：
  - 标记 `has_amount_mismatch = true`，warning=`amount_mismatch`。
- `spec` 为空：warning=`empty_spec`。

## 5. 写入顺序
1. 插入批次头（状态先设 `imported`，计数为 0）。
2. 逐行校验并写入 `inventory_snapshot_items`。
3. 回写批次统计：
   - `row_count`
   - `warning_count`
   - `error_count`
   - `warning_summary` / `error_summary`
   - `status`：
     - `imported`：无错误
     - `partial`：有行级错误但有成功行
     - `failed`：0 成功行或结构错误

## 6. 定时任务建议
- 执行频率：每 15 分钟或每小时。
- 文件发现策略：扫描固定目录（如下载目录或共享目录），按文件名时间降序处理。
- 处理成功后动作（二选一）：
  - 移动到 `archive/` 并附加处理时间；
  - 或重命名为 `.done.xlsx`。

## 7. 查询接口建议（给前端）
- 最新库存列表：`v_inventory_latest_item_by_warehouse`
- 低库存查询（示例）：
  - `available_qty <= 0`
  - 或结合阈值表做 `available_qty <= reorder_point`
- 异常库存查询：
  - `is_negative_stock = true` 或 `has_amount_mismatch = true`

## 8. 现阶段已知数据特征（基于样本）
- 单文件数据行：182
- 仓库数：3
- 品项编码去重数：121
- `一级品项类别` / `品项属性名` 全空
- 存在负库存与少量金额不一致（应告警不阻断）
