# 页面功能结构

## 总览：9 个 Tab 的数据流

```
DataService (统一数据入口)
  ├─ get_raw_materials()     → Tab 1, 5, 6, 7
  ├─ get_products()          → Tab 1, 6, 7
  ├─ get_all_recipes()       → Tab 6
  ├─ get_all_serving_specs() → Tab 1, 7
  ├─ get_sheets()            → Tab 3, 4, 9
  ├─ get_latest_inventory_rows() → Tab 1, 4, 8, 9
  └─ query_table()           → Tab 2
```

---

## Tab 1: 概览/校验

**功能**：运营驾驶舱，风险预警 + 经营指标

**数据源**：DataService (raw_materials, products, serving_specs, inventory)

**结构**：
- 风险区：缺货项 / 异常项 / 快照时效（3 张 CSS 卡片）
- 经营区：原料总数 / 产品数 / 最终成品 / 出品规格（4 张 CSS 卡片）
- 建议动作：条件生成的操作指引列表

**用户交互**：无（纯展示）

---

## Tab 2: 原数据

**功能**：浏览 Supabase 原始表数据

**数据源**：DataService.query_table()

**结构**：
- 下拉选择表名（raw_materials / products / recipes / serving_specs / serving_spec_toppings）
- 数据表格展示（最多 200 行）

**用户交互**：选表 → 看数据

---

## Tab 3: 原料价格模拟器

**功能**：三步递进调价 → 看毛利变化 → 保存/应用方案

**数据源**：DataService.get_sheets() → sku_profit_table / build_recipe_table

**结构**：
- Step 1：选择产品 + 口径（出厂/门店）
- Step 2：SKU 规格毛利表 → 选 SKU 看配方
- Step 3：配方明细 → 逐原料调价 → 成本拆解图 → 方案管理
- 方案管理：保存方案 / 应用到原料库 / 回滚 / 方案对比
- 价格变更记录：批次列表 + 查看详情 + 回滚

**用户交互**：
- 选产品 → 选 SKU → 调价格 → 实时看成本毛利变化 → 保存方案 → 应用到数据库 → 查看历史 → 回滚

**写操作**：apply_scenario() / rollback_batch()

---

## Tab 4: 产销计划

**功能**：销售计划 → 生产计划 → BOM展开 → 成本核算

**数据源**：DataService.get_sheets() + get_latest_inventory_rows()

**结构**：
- Step 1：销售计划录入（data_editor + CSV 导入）
- Step 2：从销售生成生产计划 + 联动仓库 + 缺货预警
- Step 3：BOM 展开（参数设置 + 日期过滤）→ 原料需求 / 缺口预警 / 统计概览 三个子 Tab
- Step 4：成本核算概览

**用户交互**：
- 录入销售 → 生成生产 → 展开 BOM → 看缺口 → 看成本

**写操作**：无（纯会话状态）

---

## Tab 5: 原料管理

**功能**：原料 CRUD + Excel 同步

**数据源**：DataService.get_raw_materials() + create/update/delete

**结构**：
- 统计行（4 个指标）
- Excel 同步（双文件上传 → 预览 diff → 确认执行）
- 筛选条件（类别 / 状态 / 搜索）
- 原料列表表格
- CRUD：新增模式 / 修改模式 + 删除确认流

**用户交互**：
- 看列表 → 筛选 → 新增 / 编辑 / 删除原料
- 上传 Excel → 预览差异 → 确认同步

**写操作**：create / update / delete / upsert raw_material

---

## Tab 6: 配方管理

**功能**：产品 CRUD + 配方 BOM 编辑

**数据源**：DataService.get_products() + get_raw_materials() + get_all_recipes() + create/update/set_recipes

**结构**：
- 左栏：产品列表 + 新建产品
- 右栏：产品信息编辑 + 配方明细 + 添加/删除配料

**用户交互**：
- 选产品 → 编辑产品信息 → 看配方列表 → 添加/删除配料 → 保存
- 新建产品 → 自动跳转

**写操作**：create/update product / set_recipes

---

## Tab 7: 出品规格

**功能**：最终产品规格管理（小杯/标准杯等）

**数据源**：DataService.get_products() + get_raw_materials() + get_all_serving_specs() + set_serving_specs

**结构**：
- 左栏：最终产品列表
- 右栏：已有规格列表（编辑/删除）+ 新增规格表单
- 每个规格：规格名 / 主原料 / 包材 / 定价 / 附加配料

**用户交互**：
- 选产品 → 看规格 → 编辑/删除某规格 → 新增规格 → 保存

**写操作**：set_serving_specs（批量替换）

---

## Tab 8: 门店库存

**功能**：库存状态驾驶舱

**数据源**：DataService.client → list_latest_inventory_rows()

**结构**：
- 快照时效提示
- 安全库存设置（data_editor）
- 筛选条件（仓库 / 品类 / 安全状态 / 关键字）
- KPI 指标（总品项 / 缺货 / 低库存 / 异常 + 金额统计）
- 库存表格（条件着色：红=零库存 / 黄=低于安全库存）

**用户交互**：
- 设置安全库存 → 筛选 → 浏览库存状态

**写操作**：无（安全库存仅 session state）

---

## Tab 9: 覆盖天数分析

**功能**：基于销量 + BOM + 库存计算覆盖天数

**数据源**：DataService.get_sheets() + client.list_latest_inventory_rows() + calc/coverage_analysis

**结构**：
- Step 1：周销量录入（data_editor）
- Step 2：选择仓库
- 计算按钮 → BOM 展开 → 覆盖矩阵 → SKU/原料覆盖天数
- SKU 覆盖表：条件着色（充足/一般/不足/紧急）
- 原料覆盖表：同上

**用户交互**：
- 录入销量 → 选仓库 → 计算 → 看覆盖结果

**写操作**：保存销量到 JSON 文件（非数据库）
