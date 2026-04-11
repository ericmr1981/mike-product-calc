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
| 1 | 团队熟悉度（Python > Node.js） |
| 2 | 数据处理能力（pandas 在 Excel 场景无可替代） |
| 3 | 零依赖部署（仅 pip install pandas + scipy） |
| 4 | 快速原型（Streamlit 5分钟出 UI） |
| 5 | 优化算法支持（scipy.optimize） |

---

## Options Considered

### Option A — Python 原生 CLI（纯标准库 + pandas）
**描述**：全部用 Python 标准库，数据处理用 pandas，优化用纯 Python 枚举或 scipy

| 维度 | 评分 |
|------|------|
| 开发速度 | ⭐⭐⭐⭐⭐ |
| 数据处理 | ⭐⭐⭐⭐⭐ |
| 可维护性 | ⭐⭐⭐⭐ |
| 依赖量 | ⭐⭐⭐⭐⭐（仅 pandas + scipy） |
| 非技术用户友好 | ⭐⭐ |

**代表项目**：[MC-Gen](https://github.com/ericmr1981/MC-Gen)

---

### Option B — Python + Streamlit Web UI
**描述**：后端 Python 模块 + Streamlit 前端，本地 `streamlit run`

| 维度 | 评分 |
|------|------|
| 开发速度 | ⭐⭐⭐⭐ |
| 数据处理 | ⭐⭐⭐⭐⭐ |
| 可维护性 | ⭐⭐⭐ |
| 依赖量 | ⭐⭐⭐（+ streamlit） |
| 非技术用户友好 | ⭐⭐⭐⭐⭐ |

**代表项目**：MC-Gen Streamlit 版本

---

### Option C — Node.js / TypeScript
**描述**：Node.js 后端 + React/Tailwind Web UI

| 维度 | 评分 |
|------|------|
| 开发速度 | ⭐⭐⭐ |
| 数据处理 | ⭐⭐⭐（xlsx 库远不如 pandas） |
| 可维护性 | ⭐⭐⭐⭐ |
| 依赖量 | ⭐⭐⭐ |
| 非技术用户友好 | ⭐⭐⭐ |

---

## Decision

**选择：Option B（Python + Streamlit Web UI）作为 MVP**

决策变更（2026-04-10）：
- 原计划 CLI，但用户明确需要"可操控的UI界面"，多选产品+填数量，实时输出毛利/利润/原料需求
- Streamlit 在数据应用场景的开发速度无可替代，Eric 对其熟悉度高
- Web UI 大幅降低非技术用户门槛，与 CLI 相比体验更优

**依赖清单（V1）**：
```
pandas        # Excel 解析
streamlit     # Web UI（核心依赖，用户界面）
scipy         # 优化算法（选品组合，V1 用 scipy.optimize）
numpy         # 数值计算
```

**启动方式**：`streamlit run app.py`

**不引入**：
- FastAPI / Flask（Streamlit 自带服务端）
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
