# Tab2 增强 + Tab4 重设计 + 模块删除 — 设计文档

## 概述

对 Streamlit 应用进行三项调整：
1. **Tab2 增强**：在 F-003 目标毛利率反推区域，增加主原料配方拆解功能
2. **Tab4 重设计**：将原料价格模拟器改为选品→看 SKU 规格→配方明细+调价的完整流程
3. **删除** Tab6（产品组合评估）、Tab7（多场景对比）、Tab8（选品优化器）

## 1. 删除模块

### 删除的 UI Tab
- **Tab6**：「产品组合评估」标签页及其所有代码
- **Tab7**：「多场景对比」标签页及其所有代码
- **Tab8**：「选品优化器」标签页及其所有代码

### 删除的 calc 模块
- `src/mike_product_calc/calc/scenarios.py` — PortfolioScenario、SalesAssumptionScenario、evaluate_portfolio、compare_portfolios、evaluate_multi_scenario 等
- `src/mike_product_calc/calc/optimizer.py` — enumerate_portfolios、explain_recommendation、OptimizationConstraint 等
- `src/mike_product_calc/calc/capacity.py` — score_capacity_from_plan、capacity_to_dataframe 等（仅被已删除模块引用）

### 删除的导入
- `app.py` 中删除 scenarios、optimizer、capacity 相关 import
- `cli.py` 中删除对应命令处理函数和 import

### Tab 收缩
- 当前 8 个 Tab → 收缩为 5 个 Tab：概览/校验、SKU 毛利分析（双口径）、Sheet 浏览、原料价格模拟器、产销计划

## 2. Tab2 增强：主原料配方拆解

### 位置
现有 F-003 区域，在成本瀑布表下方新增交互。

### 交互流程
1. 用户在成本瀑布表中看到各原料/配料的成本行（bucket=main_material/ingredient/packaging）
2. 每个 main_material 行旁增加「展开配方」按钮
3. 点击后，展开该主原料的子配方表（从对应的半成品配方表中读取）
4. 子配方表列：项目 | 用量 | 成本 | 规格 | 门店价格 | 品牌成本 | 利润率
5. 门店价格为可编辑输入框，调整后自动重算成本并更新 SKU 总成本和毛利率
6. 品牌成本从总原料表读取，只读
7. 成本 = 门店价格 ÷ 规格 × 用量
8. 利润率 = (门店价格 − 品牌成本) ÷ 品牌成本

### 数据源
- 子配方数据来自 `产品配方表_*` 或 `半成品配方表_*` sheet
- 品牌成本来自 `总原料成本表` sheet
- 规格信息来自 `总原料成本表` 中的规格/单位量列

### 与 Tab4 共用
Tab2 的配方拆解逻辑、数据源、计算公式与 Tab4 第三层配方明细完全复用同一套底层函数。

## 3. Tab4 重设计：原料价格模拟器

### 三步递进架构

#### 第一步：选择产品
- 下拉框选择产品（品类|品名 级别，如草莓大福、芒果冰沙）
- 产品列表从 `sku_profit_table()` 的 product_key 中提取去重后的（品类|品名）部分
- 口径切换：[出厂口径 / 门店口径]

#### 第二步：SKU 规格列表
- 显示选中产品下的所有 SKU 规格（大杯、小杯等）
- 表格列：规格 | 定价 | 成本 | 毛利 | 毛利率 | [查看配方]
- 每行一个「查看配方」按钮，点击后展开第三步

#### 第三步：配方明细 + 调价面板

**左侧：配方明细表**
- 列序：项目 | 用量 | 成本 | 规格 | 门店价格 | 品牌成本 | 利润率
- **门店价格**列是可编辑输入框，用户在输入框中修改后，成本自动重算
- **品牌成本**从总原料表读取，只读显示
- **成本**计算：成本 = 门店价格 ÷ 规格 × 用量
- **利润率**计算：(门店价格 − 品牌成本) ÷ 品牌成本
- 自动汇总显示总成本行
- 半成品主原料以缩进层级展开其子配方（↳ 前缀），并累加子项成本

**右侧：定价 & 毛利看板**
- 门店售价：可编辑输入框
- 总成本：从左侧配方表汇总，自动更新
- 毛利 = 门店售价 − 总成本，自动计算
- 毛利率 = 毛利 ÷ 门店售价，自动计算
- 三个指标以卡片形式展示，颜色随正负变化

**方案管理（底部）**
- 输入方案名称 + 保存按钮
- 已保存方案列表展示（名称 + 关键指标标签）
- 对比按钮：展示已保存方案的对比表格

### 数据源
- 配方数据：`产品出品表_*` / `产品配方表_*` / `半成品配方表_*`
- 品牌成本 + 规格：`总原料成本表`
- SKU 定价：`产品毛利表_*`

### 状态管理
- 方案保存使用现有的 `ScenarioStore` / `MpcState` 机制
- 调价状态存储在 `st.session_state` 中，避免 widget 重绘丢失

## 4. CLI 调整

- 删除 `cmd_portfolio_eval`、`cmd_portfolio_compare`、`cmd_optimizer` 命令
- 删除对应的 argparse 注册
- `cmd_material_sim` 保留但增强：支持按产品/SKU 过滤的模拟查询

## 5. 测试调整

- 删除 `tests/test_tab6_e2e.py`、`tests/test_tab7_e2e.py`、`tests/test_tab8_9_10_11_e2e.py` 中的对应测试
- 删除 `tests/test_cli_smoke.py` 中对应的 CLI 测试
- 新增 Tab2 配方拆解 + Tab4 重设计的 e2e 测试

## 6. 未纳入范围

- Tab5（产销计划）保持不变
- Tab1（概览/校验）保持不变
- Tab3（Sheet 浏览）保持不变
- 不修改数据加载层（loader.py、validator.py）
