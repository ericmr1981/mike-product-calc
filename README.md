# mike-product-calc

蜜可诗产品经营决策台 — 基于真实业务数据（蜜可诗产品库.xlsx）的 Python + Streamlit Web 应用。

## 功能一览

| # | Tab | 功能 | 数据源 |
|---|-----|------|--------|
| F-001 | Tab1 概览/校验 | Supabase 数据概览（原料/产品/规格统计）| Supabase |
| F-002 | Tab2 原数据 | Supabase 表数据浏览（原料/产品/配方/规格）| Supabase |
| F-003 | Tab3 原料价格模拟器 | SKU 毛利分析 + 配方明细调价 + 方案管理对比 | Supabase |
| F-004 | Tab4 产销计划 | 销售计划录入 → 生产计划生成 → BOM 展开 → 成本核算 | Supabase |
| F-005 | Tab5 原料管理 | 原料 CRUD（新增/修改/删除）+ Excel 批量同步 | Supabase |
| F-006 | Tab6 配方管理 | 产品配方 BOM 编辑（引用原料/半成品）| Supabase |
| F-007 | Tab7 出品规格 | 出品规格配置（多规格/包材/附加配料）| Supabase |
| F-008 | 门店库存驾驶舱 | 双端自适应库存看板（缺货/低库存/异常）+ 仓库库存快照同步 | Supabase |

## 环境要求

- Python 3.9+
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

# 3. 安装依赖（用于 Streamlit UI）
pip install -U pip
pip install -r requirements.txt

# 4. 安装 CLI（用于命令行，无需 PYTHONPATH）
pip install -e .

# 5. 启动（自动加载真实数据，需设置环境变量指向 xlsx）
MIKE_DEFAULT_XLSX=/path/to/蜜可诗产品库.xlsx streamlit run app.py
# 或不上传文件，每次手动上传：
streamlit run app.py
```

> 真实业务数据 `蜜可诗产品库.xlsx` 不在仓库里，需自行准备并在 UI 中上传。

## Supabase 配置

原料管理、配方管理、出品规格管理使用 Supabase (PostgreSQL) 存储。需要配置凭据：

```bash
# 方案 A：secrets 文件
mkdir -p .streamlit
# 在 .streamlit/secrets.toml 中写入：
# [supabase]
# url = "https://xxx.supabase.co"
# service_key = "sb_secret_xxx"

# 方案 B：环境变量
export SUPABASE_URL="https://xxx.supabase.co"
export SUPABASE_SERVICE_KEY="sb_secret_xxx"
```

首次启用库存快照同步前，请先在 Supabase SQL Editor 执行：

```sql
-- 将 docs/superpowers/specs/supabase_schema.sql 内容复制到 SQL Editor 后执行
```

## Agent CLI（原料/配方/规格/库存快照）

安装后可直接在终端使用，输出纯 JSON，适合 AI Agent 调用：

```bash
# 原料管理
mpc material list                    # 列出所有原料
mpc material list --category 乳制品   # 按类别过滤
mpc material list --status 上线       # 按状态过滤
mpc material get <uuid>              # 查看单个原料
mpc material create '{"name":"燕麦奶","category":"乳制品",...}'  # 新增（JSON 字符串）
mpc material create /path/to/file.json                              # 新增（JSON 文件）
mpc material update <uuid> '{"base_price":12.0}'                   # 修改
mpc material delete <uuid>           # 删除

# 产品查询
mpc product list                     # 列出所有产品
mpc product list --final-only        # 只列最终成品
mpc product get <uuid>               # 查看单个产品
mpc product compute-costs <uuid>     # 从配方重新计算产品成本（新增/修改配方后执行）

# 配方管理
mpc recipe list <product-uuid>       # 查看配方明细
mpc recipe set <product-uuid> recipes.json  # 替换配方

# 出品规格管理
mpc spec list <product-uuid>         # 查看出品规格
mpc spec set <product-uuid> specs.json     # 替换出品规格

# 库存快照同步（单文件）
mpc inventory sync "/path/to/仓库库存导出2026年05月06日20时20分44秒.xlsx"

# 库存快照同步（目录批量）
mpc inventory sync /path/to/dir --pattern "仓库库存导出*.xlsx"

# 仅校验不写入
mpc inventory sync /path/to/dir --pattern "仓库库存导出*.xlsx" --dry-run
```

可选参数：
- `--archive-dir <dir>` 成功后移动文件到归档目录
- `--max-files <n>` 限制本次处理文件数
- `--sheet <name>` 指定 sheet（默认 `仓库库存导出`）
- `--timezone <tz>` 文件名时间解析时区（默认 `Asia/Shanghai`）

## 门店库存驾驶舱（Tab8）

- 入口：`门店库存`（Tab8）
- 数据源：`v_inventory_latest_item_by_warehouse`
- 默认规则：
  - 缺货：`available_qty <= 0`
  - 低库存：`0 < available_qty <= 5`（阈值可在页面调节）
  - 异常：`is_negative_stock = true` 或 `has_amount_mismatch = true`
- 支持筛选：仓库、状态、关键字（编码/名称）
  - 仓库下拉显示中文仓库名（内部按仓库编码精确过滤）
  - 筛选采用“应用筛选”触发，避免切换时频繁整页刷新
- 快照时效：超过 2 小时未更新会告警

## 产销计划 × 门店库存联动（Tab4）

- Step 2 新增“联动仓库”选择器（中文仓库名展示，内部按仓库编码匹配）。
- 生成生产计划后，系统会立刻按当前仓库计算“即时缺货提示”。
- Step 3 新增“补货计划（当前联动仓库）”区块。
- 关键公式：
  - `缺口量 = max(0, BOM需求量 - 当前可用量)`
  - `建议补货量 = 缺口量`
- 物料匹配规则：
  - 优先全名精确匹配（`material == item_name`）
  - 若未命中，尝试“唯一前缀匹配”（如 `原味奶浆` → `原味奶浆JYX001`）

## 概览页驾驶舱（Tab1）

- 风险优先、经营次级的信息布局：
  - 风险区：缺货项、异常项、快照时效
  - 经营区：原料总数、产品数、最终成品、出品规格
- 建议动作区会根据风险状态动态给出下一步操作建议（Tab8 / Tab4）。
- 降级容错：当库存风险数据不可用时，仍展示经营区并给出可读提示。

## 验证

```bash
# 编译检查
python -m py_compile src/mike_product_calc/cli.py src/mike_product_calc/state.py src/mike_product_calc/__main__.py

# 自动化测试（84+ 个测试，全部通过）
pytest tests/ -q

# CLI 校验（安装后直接使用）
mpc --help
mpc material --help
mpc product --help
mpc recipe --help
mpc spec --help
mpc inventory --help
```

## 项目结构

```
mike-product-calc/
├── app.py                        # Streamlit Web UI（8 个 Tab）
├── src/mike_product_calc/
│   ├── cli.py                    # CLI 入口（mpc 命令）
│   ├── state.py                  # Session state 管理
│   ├── data/
│   │   ├── supabase_client.py    # Supabase REST API 客户端
│   │   ├── cli_supabase.py       # CLI Supabase 连接（env → secrets）
│   │   ├── inventory_upload.py   # 仓库库存快照导入与校验
│   │   ├── supabase_adapter.py   # Supabase → DataFrame 适配
│   │   ├── loader.py             # Excel 加载 + sheet 匹配
│   │   ├── validator.py          # 校验规则 + ValidationReport
│   │   ├── upload.py             # 文件上传注册
│   │   └── shared.py             # 共享工具函数
│   ├── calc/
│   │   ├── profit.py             # 毛利计算（F-002）
│   │   ├── profit_oracle.py      # 一致性校验 oracle
│   │   ├── margin_target.py      # 目标成本反推（F-003）
│   │   ├── material_sim.py       # 原料价格模拟（F-004）
│   │   ├── prep_engine.py        # BOM 展开 + 缺口（F-006）
│   │   ├── purchase_suggestion.py # 采购建议（F-007）
│   │   ├── inventory_linkage.py  # 产销与库存联动补货计算
│   │   ├── material_mgmt.py      # 原料管理逻辑（Tab5）
│   │   ├── recipe_mgmt.py        # 配方管理逻辑（Tab6）
│   │   ├── serving_mgmt.py       # 出品规格逻辑（Tab7）
│   │   ├── scenarios.py          # 组合评估
│   │   ├── optimizer.py          # 枚举优化器
│   │   └── capacity.py           # 产能估算
│   ├── model/
│   │   └── production.py         # 生产计划数据模型
│   └── sync/
│       └── excel_sync.py         # Excel → Supabase 同步
├── tests/                        # pytest 测试（84+ tests）
├── data/                         # 放置蜜可诗产品库.xlsx
├── docs/
│   └── E2E_TEST_PLAN.md          # 端到端测试计划
└── requirements.txt
```

## 技术栈

- **Python 3.9+**
- **Streamlit** — Web UI
- **Supabase (PostgreSQL)** — 数据存储（原料/配方/规格）
- **pandas** — 数据处理
- **numpy** — 向量计算
- **scipy** — 优化算法
- **openpyxl** — Excel 读取
- **requests** — Supabase REST API

## 依赖列表

```
streamlit>=1.40.0
pandas>=2.0.0
numpy>=1.24.0
openpyxl>=3.1.0
scipy>=1.11.0
pytest>=7.4.0
```
