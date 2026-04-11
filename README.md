# mike-product-calc

蜜可诗产品经营决策台 — 基于真实业务数据（蜜可诗产品库.xlsx）的 Python + Streamlit Web 应用。

## 功能一览（12 Features）

| # | 功能 | Tab |
|---|------|-----|
| F-001 | Excel 数据解析与校验 V2（健壮 sheet 匹配、自动表头检测）| Tab1 |
| F-002 | SKU 毛利分析（出厂/门店双口径，含成本瀑布图）| Tab2 |
| F-003 | 目标毛利率反推原料定价 | Tab2 |
| F-004 | 原料价格模拟器（版本管理 + 任意两版对比）| Tab4 |
| F-005 | 生产计划录入（data_editor + CSV 模板导入/导出）| Tab5 |
| F-006 | 备料计划引擎（BOM 三级展开 + 缺口预警）| Tab6 |
| F-007 | 采购建议页（按原料汇总 + 紧急项标红）| Tab7 |
| F-008 | 产品组合评估（实时 KPI + 方案 A/B/C 保存对比）| Tab8 |
| F-009 | 数据健康与可信度提示（issues 关联 SKU/原料）| Tab1 |
| F-010 | 多场景对比（多组销量假设 + 差异表）| Tab9 |
| F-011 | 产能需求估算（评分可视化 + 高压 SKU 标红）| Tab11 |
| F-012 | 选品组合优化器（枚举 Top-3 + 可解释推荐）| Tab10 |

## 环境要求

- Python 3.10+
- pip

## 安装

```bash
# 1. 克隆仓库
git clone https://github.com/ericmr1981/mike-product-calc.git
cd mike-product-calc

# 2. 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows

# 3. 安装依赖
pip install -U pip
pip install -r requirements.txt

# 4. 启动（自动加载真实数据，需设置环境变量指向 xlsx）
MIKE_DEFAULT_XLSX=/path/to/蜜可诗产品库.xlsx streamlit run app.py
# 或不上传文件，每次手动上传：
streamlit run app.py
```

> 真实业务数据 `蜜可诗产品库.xlsx` 不在仓库里，需自行准备并在 UI 中上传。

## 验证

```bash
# 编译检查
python -m py_compile src/mike_product_calc/**/*.py
python -m py_compile app.py

# 自动化测试（22 个测试，全部通过）
pytest tests/ -v

# CLI 校验
PYTHONPATH=src python3 -m mike_product_calc validate --help
# 或用脚本（需传入 xlsx 路径）
bash scripts/validate.sh /path/to/蜜可诗产品库.xlsx
```

## 项目结构

```
mike-product-calc/
├── app.py                        # Streamlit Web UI（11 个 Tab）
├── src/mike_product_calc/
│   ├── data/
│   │   ├── loader.py             # Excel 加载 + sheet 匹配
│   │   ├── validator.py          # 校验规则 + ValidationReport
│   │   └── shared.py             # 共享工具函数
│   ├── calc/
│   │   ├── profit.py             # 毛利计算（F-002）
│   │   ├── margin_target.py      # 目标成本反推（F-003）
│   │   ├── material_sim.py       # 原料价格模拟（F-004）
│   │   ├── prep_engine.py        # BOM 展开 + 缺口（F-006）
│   │   ├── purchase_suggestion.py # 采购建议（F-007）
│   │   ├── scenarios.py          # 组合评估 + 多场景（F-008/F-010）
│   │   ├── optimizer.py          # 枚举优化器（F-012）
│   │   └── capacity.py           # 产能估算（F-011）
│   └── model/
│       └── production.py         # 生产计划数据模型（F-005）
├── tests/                        # pytest 测试（22 tests）
├── data/                         # 放置蜜可诗产品库.xlsx
├── docs/
│   └── E2E_TEST_PLAN.md         # 端到端测试计划
└── requirements.txt
```

## 技术栈

- **Python 3.10+**
- **Streamlit** — Web UI
- **pandas** — 数据处理
- **numpy** — 向量计算
- **scipy** — 优化算法（V2 扩展）
- **openpyxl** — Excel 读取

## 依赖列表

```
streamlit>=1.40.0
pandas>=2.0.0
numpy>=1.24.0
openpyxl>=3.1.0
scipy>=1.11.0
pytest>=7.4.0
```
