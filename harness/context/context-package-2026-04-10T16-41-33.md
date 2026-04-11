# Context Package
> Built by ContextAssembler | 2026-04-10T16-41-33 | task: 项目 mike-product-calc：实现 PRD 的所有内容，并确保 E2E 测试通过。最终验收以 PRD 功能闭环 + E2E 全绿为准。

## 📋 Git State
- **Branch**: `main`
- **Status**: ⚠️ dirty
```
?? .DS_Store
?? .skill-staging/
?? CliX/
?? "Coder \351\205\215\347\275\256.md"
?? "Coder+Codex \345\215\217\344\275\234\346\265\201\347\250\213.md"
?? FireRed-OpenStoryline/
?? "GitHub+VPS\350\207\252\345\212\250\351\203\250\347\275\262\351\205\215\347\275\256\346\214\207\345\215\227.md"
?? LTX-Desktop/
?? MC-Gen/
?? Nexus/
?? Obsidian/
?? "Pencil Desgin/"
?? Pipi-go/
?? README.md
?? XianyuAutoAgent/
?? _archive/
?? _tmp/
?? a2a-ws-hub/
?? agent-harness-trinity/
?? agents/
?? app-Home-Portal/
?? app-host-portal/
?? app-minesweeper/
?? app-portal/
?? app-snake/
?? autonomous-dev-harness/
?? bit-office-demo/
?? chinese-learning-kids/
?? collab/
?? debate-orchestra/
?? demo-agent-teams/
?? docker-compose.local.yml
?? edict/
?? explore-universe-kids/
?? kids-chinese-storybook/
?? local-portal/
?? mike-product-calc/ACTIVE.md
?? n8n-orchestration/
?? new-project/
?? obsidian-llm-knowledge-base/
?? openclaw-agent-monitor-demo/
?? openclaw-mission-control-oc/
?? openclaw-notebooklm-ui-design/
?? openclaw-session-page-oa-style-demo/
?? openclaw-to-ltx/
?? openstoryline/
?? retail-finance-system/
?? software-registry/
?? solar-system-animator/
?? team-kanban/
?? templates/
?? wdg-data-foundation/
?? wdg-supabase-migration/
?? whatscode/
?? xxxxx-check/
?? "\346\250\241\345\236\213\351\205\215\347\275\256.md"
```

## 📜 Recent Commits (last 5)
```
  6abfe34 docs: add V1 ADR-0001 tech stack decision
  e7371be kickoff V2: 产品经营决策台 PRD+ARCH+features+goal
```

## 🎯 Features (0/12 passing)
### Unfinished:
- [ ] **F-001: Excel 数据解析与校验（V2）** (priority=1 | size=n/a | acceptance=0)
- [ ] **F-002: SKU 毛利分析（双口径）** (priority=2 | size=n/a | acceptance=0)
- [ ] **F-003: 目标毛利率反推原料定价** (priority=3 | size=n/a | acceptance=0)
- [ ] **F-004: 原料价格模拟器** (priority=4 | size=n/a | acceptance=0)
- [ ] **F-005: 生产计划录入** (priority=5 | size=n/a | acceptance=0)
- [ ] **F-006: 备料计划引擎（BOM展开+规则）** (priority=6 | size=n/a | acceptance=0)
- [ ] **F-007: 采购建议页** (priority=7 | size=n/a | acceptance=0)
- [ ] **F-008: 产品组合评估（实时联动）** (priority=8 | size=n/a | acceptance=0)
- [ ] **F-009: 数据健康与可信度提示** (priority=9 | size=n/a | acceptance=0)
- [ ] **F-010: 多场景对比** (priority=10 | size=n/a | acceptance=0)

## ▶️  ACTIVE.md
# Active — 蜜可诗产品经营决策台

> Last updated: 2026-04-11

## 当前目标
完成 M1：数据层 + SKU 毛利展示（Streamlit Web UI）

## 下一行动
搭建项目脚手架（M1）：
1. `data/loader.py` — 解析 13 个 Excel sheet，构建内存数据模型
2. `data/validator.py` — 识别 103 处计算错误，输出 `data_validation_report.csv`
3. `data/material_index.py` — 原料主数据，含 CostAdjustability 枚举
4. `calc/profit.py` — 双口径利润计算，与 Excel 交叉验证误差 < 0.01
5. `pages/1_SKU_毛利调价台.py` — Streamlit 页面

## Oracle（验收命令）
```bash
cd /Users/ericmr/Documents/GitHub/mike-product-calc
python -c "from data.loader im

## ✂️  Relevant Snippets (extracted; large docs are NOT inlined)
> If more context is needed, request specific files/sections; do not ask for “the whole doc”.

### `docs/kickoff/PRD.md`
#### lines 1-21
```
# PRD V2 — mike-product-calc（蜜可诗产品经营决策台）

> 升级版 Kickoff：2026-04-11
> 数据源：`蜜可诗产品库.xlsx`（Gelato 84SKU + 雪花冰 10SKU + 饮品 1SKU）
> 产品定位：**目标毛利驱动的产品与原料定价决策台**

---

## 1. 背景与目标

### 业务背景
蜜可诗当前用 Excel 管理产品成本与定价，缺乏系统化的：
- 单品 / 组合毛利分析
- 目标毛利率反推原料定价
- 灵活调价模拟
- 按日期的生产计划与备料
- 选品决策支持

### 产品定位
**本地优先的产品经营决策工作台**——核心不是算数，而是让运营者能快速做出"卖什么、备多少、原料什么价、赚多少、卡在哪里"的判断。

```

#### lines 157-207
```

### 模块 6（贯穿）— 数据健康与可信度提示
**回答：这个结果能信多少**

原因：源数据有 103 处计算错误，必须诚实告知用户。

功能：
- 列出所有"计算错误"单元格及影响的 SKU / 原料
- 标记：哪些被置零、哪些是估算、哪些结果需谨慎解读
- 原料缺口预警：某原料无有效单价时，提示"该原料成本为 0，建议核实"

---

## 3. 页面结构设计

| 页面 | 路由 | 核心功能 |
|------|------|---------|
| 首页导航 | `/` | 5 个模块入口 + 数据健康状态卡片 |
| SKU 毛利调价台 | `/sku-margin` | 模块 1 + 模块 2 |
| 原料价格模拟器 | `/material-sim` | 模块 3 |
| 生产计划 | `/production-plan` | 模块 4a |
| 备料计划 | `/prep-plan` | 模块 4b~4d |
| 采购建议 | `/purchase` | 模块 4e |
| 组合评估 | `/portfolio` | 模块 5 |
| 数据健康 | `/data-health` | 模块 6 |

---

## 4. 核心数据对象

### Product
```
name, category, spec, status
price, cost_factory, cost_store
margin_factory, margin_store
recipe_items: list[RecipeItem]
is_adjustable: bool  # 是否参与定价反推
```

### RecipeItem
```
product_name, ingredient, quantity, unit_cost, total_cost
is_packaging: bool  # 是否为包材/固定成本
```

### Material
```
name, unit, cost, category
is_adjustable: bool
scenarios: dict[str, float]  # 各版本价格
```
```

### `harness/goal.md`
#### lines 1-35
```
# Goal Contract — mike-product-calc V2

**项目**：蜜可诗产品经营决策台
**Owner**：Eric / Polo
**启动日期**：2026-04-10，V2 升级：2026-04-11
**定位**：目标毛利驱动的产品与原料定价决策台（本地优先 Python + Streamlit）

---

## 成功标准（Done ✅）

- [ ] `data/loader.py` 完整解析 `蜜可诗产品库.xlsx` 全部 13 个 sheet，无报错
- [ ] `data/validator.py` 识别并记录 103 处计算错误，输出 `data_validation_report.csv`
- [ ] `calc/profit.py` 利润结果与 Excel 原始数据交叉验证误差 < 0.01 元
- [ ] `calc/margin_target.py` 给定 SKU + 目标毛利率，< 3 秒输出可调原料建议价
- [ ] `calc/material_sim.py` 原料调价后，组合毛利实时联动，< 3 秒刷新
- [ ] `calc/prep_engine.py` 输入 7 天生产计划，< 3 秒输出每日备料表
- [ ] `calc/purchase_suggestion.py` 备料计划 → 采购建议，字段完整（日期+原料+数量+单位）
- [ ] Streamlit UI 7 个页面全部可运行，交互流畅
- [ ] 方案 A/B/C 保存与对比功能正常
- [ ] 数据健康页诚实呈现所有异常及影响范围
- [ ] README.md：安装方法、使用示例、输入格式说明

---

## 当前约束（Constraints）

1. **数据约束**：复用现有 Excel，不做数据迁移；103 处"计算错误"需特殊处理并诚实呈现
2. **技术约束**：Python 3.10+，Streamlit + pandas + scipy + numpy（V1）
3. **范围约束**：Gelato（84SKU）+ 雪花冰（10SKU）+ 饮品（1SKU）；暂不接销售历史数据
4. **成本可调性约束**：包材/标配耗材不参与定价反推（由 CostAdjustability 枚举控制）
5. **时间约束**：无硬性 deadline，以质量优先

---

```

### `docs/kickoff/ARCHITECTURE_DRAFT.md`
#### lines 1-44
```
# ARCHITECTURE DRAFT V2 — mike-product-calc

> 基于蜜可诗产品库的本地产品经营决策工作台

---

## 1. 设计原则

- **本地优先**：数据不离开本地，双击运行或 `streamlit run`
- **可验证**：每步计算结果可与 Excel 原始数据交叉核对
- **诚实呈现**：脏数据不被隐藏，异常有明确提示
- **决策导向**：输出运营语言（"建议采购 6 瓶"），而非技术中间值

---

## 2. 系统边界

```
┌──────────────────────────────────────────────────────────────────┐
│                      mike-product-calc                             │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              Streamlit Web UI (app.py)                    │  │
│  │  /sku-margin  /material-sim  /production-plan             │  │
│  │  /prep-plan   /portfolio     /data-health                 │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                             ↓                                     │
│  ┌─────────────┐   ┌──────────────────┐   ┌──────────────────┐  │
│  │  Data       │ → │  Calc Engine     │ → │  Report          │  │
│  │  Loader     │   │  (pure func)     │   │  Exporter        │  │
│  └─────────────┘   └──────────────────┘   └──────────────────┘  │
│                            ↑                                      │
│              ┌─────────────┴─────────────┐                       │
│              │  Prep Rules Engine        │                       │
│              │  (BOM +损耗+安全库存+取整) │                       │
│              └───────────────────────────┘                       │
└──────────────────────────────────────────────────────────────────┘
        ↑                                        ↓
  蜜可诗产品库.xlsx                    CSV / Streamlit 表格 / 图表
```

---

## 3. 模块划分
```

### `docs/decisions/ADR-0001-tech-stack.md`
#### lines 1-21
```
# ADR-0001: Tech Stack Decision — mike-product-calc

- Status: **decided**
- Date: 2026-04-10

---

## Context

为蜜可诗产品分析工具选择技术栈，要求：
- 数据科学/分析为主（Python 优先）
- 零部署门槛，无需数据库
- 快速出 MVP，可交叉验证
- 未来可扩展 Web UI

---

## Decision Drivers

| 优先级 | 驱动因素 |
|--------|---------|
```

#### lines 96-135
```
- 数据库（数据源即 Excel）
- Docker（`pip install` 即可运行）

---

## Consequences

### Positive
- 开发速度最快，1-2天可出 MVP
- 所有计算逻辑可单元测试，与 Excel 数据交叉验证
- 可直接在 VS Code / Cursor 中调试
- 分发简单：`git clone + pip install`

### Negative
- 非技术用户需通过 CLI 交互（有学习门槛）
- 未来如果要 Web 化，需要一定重构
- Streamlit 扩展是额外工作

### Mitigation
- CLI 提供清晰的交互菜单，降低使用门槛
- 模块化设计（data/calc/report 分离），重构到 Web 成本可控

---

## Validation Plan

| 验证项 | 方法 |
|--------|------|
| Excel 解析完整性 | 加载后行数与原始文件一致（Gelato 84+10=94上线SKU） |
| 利润计算精度 | 抽检5个 SKU，误差 < 0.01元 |
| 原料测算正确性 | 用一个已知组合验证原料加总 = 成本计算表总成本 |
| 选品优化有效性 | 枚举 vs scipy.optimize 结果对比 |

---

## Next Step

按 M2~M8 里程碑逐步实现，模块顺序：
`data/loader.py` → `calc/profit.py` → `calc/material.py` → `calc/capacity.py` → `calc/optimizer.py` → `main.py`

```

### `ACTIVE.md`
#### lines 1-35
```
# Active — 蜜可诗产品经营决策台

> Last updated: 2026-04-11

## 当前目标
完成 M1：数据层 + SKU 毛利展示（Streamlit Web UI）

## 下一行动
搭建项目脚手架（M1）：
1. `data/loader.py` — 解析 13 个 Excel sheet，构建内存数据模型
2. `data/validator.py` — 识别 103 处计算错误，输出 `data_validation_report.csv`
3. `data/material_index.py` — 原料主数据，含 CostAdjustability 枚举
4. `calc/profit.py` — 双口径利润计算，与 Excel 交叉验证误差 < 0.01
5. `pages/1_SKU_毛利调价台.py` — Streamlit 页面

## Oracle（验收命令）
```bash
cd /Users/ericmr/Documents/GitHub/mike-product-calc
python -c "from data.loader import load; m=load(); print('sheets:', list(m.keys())); print('gelato_skus:', len(m['毛利表_Gelato']))"
pytest tests/ -v --tb=short
streamlit run app.py
```

## 最新提交
- `e7371be` kickoff V2: 产品经营决策台 PRD+ARCH+features+goal（2026-04-11）
- `6abfe34` docs: add V1 ADR-0001 tech stack decision（2026-04-11）

## 里程碑
| 阶段 | 目标 | 状态 |
|------|------|------|
| M1 | 数据层 + SKU 毛利展示 | pending |
| M2 | 目标毛利率反推 + 原料价格模拟 | pending |
| M3 | 生产计划 + 备料计划 + 采购建议 | pending |
| M4 | 组合评估 + 场景对比 + 数据健康 | pending |

```

---
*ContextAssembler v1 | 2026-04-10T16-41-33*