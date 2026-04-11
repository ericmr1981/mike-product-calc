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

### `data/` — 数据层
| 文件 | 职责 |
|------|------|
| `loader.py` | 解析 Excel 所有 sheet，构建内存数据模型 |
| `validator.py` | 扫描"计算错误"等异常，输出校验报告 + 影响范围 |
| `material_index.py` | 原料主数据（名称、规格、单位、成本、分类、可调性） |

### `calc/` — 计算引擎（纯函数，无 UI 依赖）
| 文件 | 职责 |
|------|------|
| `profit.py` | 单品毛利、组合毛利、日度利润；双口径切换 |
| `margin_target.py` | 目标毛利率 → 反推允许成本 → 推荐原料定价 |
| `material_demand.py` | SKU 销量组合 → 原料需求（BOM 展开） |
| `prep_engine.py` | 备料规则引擎：损耗率、安全库存、取整、批次、提前期 |
| `purchase_suggestion.py` | 备料计划 → 采购建议（下单日/到货日/数量） |
| `material_sim.py` | 原料价格版本管理 + 组合影响计算 |
| `capacity.py` | 产能需求（V1 用量估算，配方工时留扩展） |
| `scenarios.py` | 场景管理：方案 A/B/C 保存与对比 |

### `model/` — 数据对象定义
| 文件 | 职责 |
|------|------|
| `product.py` | Product, RecipeItem, Material 数据类 |
| `production.py` | ProductionPlan, PrepRule, MaterialPrepPlan |
| `scenario.py` | MaterialPriceScenario, MarginTargetRule |

### `report/` — 报表输出
| 文件 | 职责 |
|------|------|
| `table.py` | Streamlit 表格渲染（含固定列、排序、筛选） |
| `chart.py` | 瀑布图（成本拆解）、进度条（约束占用） |
| `csv_exporter.py` | CSV 导出（备料计划、采购建议、利润表） |

### `app.py` — Streamlit Web UI 入口
| Tab | 功能 |
|-----|------|
| 首页导航 | 5 模块入口 + 数据健康状态卡 |
| SKU 毛利调价台 | 模块 1 + 模块 2 |
| 原料价格模拟器 | 模块 3 |
| 生产计划 | 模块 4a |
| 备料计划 | 模块 4b~4d |
| 采购建议 | 模块 4e |
| 组合评估 | 模块 5 |
| 数据健康 | 模块 6 |

---

## 4. 核心数据流

### 目标毛利率反推流程
```
Excel → loader.py → DataModel
                            ↓
              margin_target.py
              (输入: SKU + 目标毛利率)
                            ↓
              可调原料建议价
              (理想价/可接受价/红线价)
                            ↓
              → Streamlit 表格展示
```

### 原料价格模拟流程
```
Excel → loader.py → DataModel
                            ↓
              material_sim.py
              (原料价格版本 {name: scenario})
                            ↓
              recalculate(margin_target.py / profit.py)
                            ↓
              方案A vs 方案B 对比表
```

### 生产计划 → 备料计划流程
```
Excel → loader.py → DataModel
                            ↓
         production_plan.py (用户录入计划)
                            ↓
         prep_engine.py (BOM展开 + 备料规则)
                            ↓
         material_demand.py (按日期原料需求)
                            ↓
         purchase_suggestion.py (采购建议)
                            ↓
         → Streamlit 表格 / CSV导出
```

### 组合评估流程
```
Excel → loader.py → DataModel
                            ↓
         用户选择 SKU × 数量
                            ↓
         profit.py + material_demand.py
                            ↓
         利润表 + 原料需求 + 约束占用
                            ↓
         scenarios.py (保存/对比方案A/B)
```

---

## 5. 关键数据结构

### CostAdjustability（成本可调性）
```python
class CostAdjustability(Enum):
    FIXED    = "固定"   # 包材/标配耗材，不参与定价反推
    ADJUSTABLE = "可调"  # 奶浆/果酱/坚果等
    MANAGED  = "管理"   # 糖浆/半成品，可调但需谨慎
```

### MarginTargetResult
```python
class MarginTargetResult:
    sku: str
    target_margin: float
    allowed_cost: float   # 目标允许成本
    cost_gap: float      # 当前成本 vs 目标成本差额
    recommendations: list[IngredientRecommendation]
    locked_ingredients: list[str]
```

### PrepPlanResult
```python
class PrepPlanResult:
    date: date
    plans: list[MaterialPrepItem]
    # MaterialPrepItem:
    #   material, unit, theoretical_qty,
    #   adjusted_qty, suggested_qty,
    #   purchase_qty, gap, sources
```

---

## 6. 成本可调性识别规则

**固定成本（FIXED）** — 不参与定价反推：
- `产品出品表_*` 中，配料为以下类别：
  - 冰碗、杯子、勺、盖子
  - 卡片、贴纸、 logo 包
  - 糖粒、撒粉（小包装）
- `产品配方表_*` 中，配料名为以下关键词：
  - `杯`、`碗`、`勺`、`卡`、`袋`、`贴`、`印`

**可调成本（ADJUSTABLE）** — 参与定价反推：
- 奶浆、果酱、坚果、巧克力、糖浆
- 油脂、基底乳、粉类
- 半成品（雪花冰风味水等）

**管理成本（MANAGED）** — 可调但需提示：
-  дробильные 类
- 糖类（甜度可调但有下限）

---

## 7. 部署形态

- **Python + Streamlit Web UI**
- Python 3.10+，启动：`streamlit run app.py`
- 依赖：`pandas`, `streamlit`, `scipy`, `numpy`
- 可通过 `pip install -e .` 安装为本地包

---

## 8. 观测性

- `data/validator.py` 输出 `data_validation_report.csv`
- 所有计算模块写入 `logs/calc.log`
- Streamlit 内置页面刷新状态，无额外 metrics

---

## 9. Open Questions

| # | 问题 | 决策 |
|---|------|------|
| Q1 | 门店成本 vs 出厂成本在 UI 层如何区分？ | **分开 Tab**，同一 SKU 两套数字，切换全局联动 |
| Q2 | "计算错误"单元格在定价反推时如何处理？ | validator 标记；反推时该 SKU 提示"数据异常，跳过" |
| Q3 | 雪花冰的 Gelato 类半成品如何展开？ | 按 `半成品配方表_雪花冰` 展开到原料级，暂不做二次反推 |
| Q4 | 提前期如何配置？谁提供这个数据？ | V1 由用户在 UI 层手动填入 PrepRule；V2 接入供应商数据 |
| Q5 | 损耗率、安全库存率谁填？ | V1 用经验值（损耗 5%，安全库存 10%）；可在 UI 层覆盖 |
