# 覆盖天数分析 (Coverage Days Analysis)

## 概述

基于库存状态和配方BOM，结合用户输入的每周SKU销售预估，计算：
1. **每个SKU的可售卖天数**（取其所需所有原料覆盖天数的最小值）
2. **每种原料的可消耗天数**（基于所有SKU的总消耗速率）

帮助用户理解当前库存能支撑销售计划多久，从而指导补货决策。

## 架构

```
bom_expand_multi(qty=1) ──→ BOM模板 (per-SKU per-unit material req)
         +                          +
  周销量输入 (手动)           库存快照 (Supabase)
         │                          │
         └──────────┬───────────────┘
                    ▼
      coverage_analysis.py
         │
         ├──→ SKU覆盖天数表
         └──→ 原料覆盖天数表
```

### 数据流

1. **BOM模板生成**：复用 `prep_engine.bom_expand_multi()`，传入每SKU qty=1，得到每生产1单位SKU所需每种原料的用量。BOM支持三级展开（成品→半成品→原料），包括损耗率、安全库存。
2. **日消耗率计算**：周销量 ÷ 7 × BOM模板中的单位消耗量，按原料聚合求和。
3. **覆盖天数计算**：（库存可用量 − 安全库存）÷ 每日总消耗量。
4. **SKU聚合**：每个SKU的覆盖天数 = 其所有原料覆盖天数的最小值。

### 数据来源说明

- **BOM模板**：从Workbook（Excel）通过 `bom_expand_multi()` 生成
- **库存快照**：从 Supabase `list_latest_inventory_rows()` 获取，按原料名称跨仓库聚合 `available_qty` 求和
- **安全库存**：
  - UI 模式：从 `st.session_state.safety_stock_map` 读取（用户已在库存Tab配置）
  - CLI 模式：默认为 0，可通过 `--safety-stock-json` 选项传入 `{"原料名": 数量}`

### 精度约定

- 日消耗量：保留 4 位小数
- 覆盖天数：保留 1 位小数
- 库存量：保留 2 位小数

## 计算逻辑

### 核心公式

```
material_daily_consumption = Σ(all SKUs) (sku_weekly_sales / 7 × material_qty_per_sku_unit)
material_coverage_days = (available_qty - safety_stock) / material_daily_consumption
sku_coverage_days = min(material_coverage_days for all materials used by sku)
```

### 状态阈值

| 状态 | 覆盖天数 | 颜色 |
|------|---------|------|
| 充足 | ≥ 30天 | 绿色 |
| 一般 | 14-29天 | 蓝色 |
| 不足 | 7-13天 | 黄色 |
| 紧急 | < 7天 | 红色 |

### 边界情况

- **无库存记录的原料**：覆盖天数为 0，状态"紧急"，标记"无库存数据"
- **周销量为 0 的 SKU**：不参与计算，覆盖天数显示 "-"
- **未被任何 SKU 消耗的原料**：覆盖天数显示 "∞"
- **BOM 中存在 gap 的原料**：标记 `is_gap=true` 并显示 gap_reason，不参与天数计算

## UI 设计（Streamlit 新Tab）

### 布局

三个区域自上而下：

**区域1：每周销量输入表**
- 列出 Workbook 中所有可销售 SKU（从产品出品表读取）
- 每行：SKU名称 | 当前周销量输入框（默认0）
- "计算覆盖天数"按钮

**区域2：SKU覆盖天数结果表**
| SKU | 品类 | 周销量 | 限制原料 | 覆盖天数 | 状态 |
|---|---|---|---|---|---|

**区域3：原料覆盖天数结果表**
| 原料 | 现有库存 | 安全库存 | 日消耗 | 覆盖天数 | 状态 |
|---|---|---|---|---|---|

### 交互流程
1. 页面加载 → 读取Workbook，识别所有SKU，初始化销量输入表
2. 用户输入各SKU周销量
3. 点击"计算覆盖天数"
4. 调用 `coverage_analysis.py` 计算
5. 渲染结果表（含颜色标记）

## CLI 接口

### 命令

```bash
mpc coverage-estimate --sku "key=qty" [--sku ...] [--selections-json JSON] [--safety-stock-json JSON] [--out FILE]
```

### 参数

| 参数 | 说明 |
|------|------|
| `--sku "key=qty"` | 可重复，指定SKU及周销量 |
| `--selections-json JSON` | 替代 `--sku`，一次性传入 JSON |
| `--safety-stock-json JSON` | 可选，传入 `{"原料名": 数量}` 安全库存 |
| `--out FILE` | 输出到文件（JSON或CSV） |

### 输出格式

```json
{
  "sku_coverage": [
    {
      "sku_key": "Gelato|榛子巧克力|小杯",
      "category": "Gelato",
      "weekly_sales": 140,
      "limiting_material": "牛奶",
      "coverage_days": 12.3,
      "status": "不足"
    }
  ],
  "material_coverage": [
    {
      "material": "牛奶",
      "available_qty": 200.0,
      "safety_stock": 20.0,
      "daily_consumption": 15.0,
      "coverage_days": 12.0,
      "status": "不足"
    }
  ]
}
```

CLI输出遵循项目惯例：stdout纯JSON，--format text可选人性化输出，--out 可写文件。

## 文件清单

### 新增文件

| 文件 | 说明 |
|------|------|
| `src/mike_product_calc/calc/coverage_analysis.py` | 核心计算逻辑 |
| `src/mike_product_calc/ui/coverage_tab.py` | Streamlit UI Tab |
| `tests/test_coverage_analysis.py` | 单元测试 |

### 修改文件

| 文件 | 说明 |
|------|------|
| `app.py` | 注册新Tab |
| `cli.py` | 新增 `coverage-estimate` 命令 |

## 错误处理

- Workbook 未加载：提示用户上传 Excel
- 库存快照为空：提示"无库存数据，覆盖天数无法计算"，仅显示BOM模板
- BOM展开存在 gap：标记 gap 原料，不影响其他原料/SKU的计算
- 销量全为0：提示"请输入至少一个SKU的周销量"

## 测试策略

| 测试场景 | 说明 |
|---------|------|
| 正常计算 | 多个SKU共享原料，验证聚合消耗和最低覆盖天数 |
| 边界：销量0 | 周销量0的SKU不参与消耗计算 |
| 边界：无库存 | 原料无库存记录 → 天数为0 |
| 边界：不缺货 | 库存充足 → 覆盖天数大 |
| 多SKU聚合 | 2个SKU共用1种原料，验证消耗叠加 |
| SKU最小值 | SKU用5种原料，验证覆盖天数为最小值 |
| 安全库存 | 安全库存从可用量中扣除 |
| gap原料 | BOM gap标记不影响正常原料计算 |
