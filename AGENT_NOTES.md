# AGENT_NOTES.md — mike-product-calc

> 目的：让维护者/Agent 在 5 分钟内搞清楚应用边界、架构、运行方式、变更历史。
> 此文件由 Agent 在每次发版时维护（参见 skill: apply-agent-notes）。

---

## 0. 应用概览

| 字段 | 值 |
|------|-----|
| 应用名称 | mike-product-calc（蜜可诗产品经营决策台） |
| 类型 | Python Streamlit Web 应用 |
| 数据来源 | 蜜可诗产品库.xlsx |
| 面向用户 | internal（业务/运营/管理层） |
| 运行端口 | Streamlit 默认 8501（或通过 `--server.port` 自定义） |
| 进程管理 | 推荐 systemd 或 pm2 |
| 版本策略 | Tag + GitHub Releases（tar.gz） |
| Release 下载 | `https://github.com/ericmr1981/mike-product-calc/releases/download/<tag>/mike-product-calc-<tag>.tar.gz` |

---

## 1. 运行 / 部署

### 1.1 本地运行（开发）

```bash
cd /path/to/mike-product-calc
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### 1.2 生产部署

```bash
# systemd service 示例（/etc/systemd/system/mike-product-calc.service）
[Unit]
Description=mike-product-calc Streamlit app
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/mike-product-calc
ExecStart=/opt/mike-product-calc/.venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port 8501
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable mike-product-calc
sudo systemctl start mike-product-calc
```

### 1.3 快速健康检查

```bash
curl -sI http://localhost:8501/ | head -3
systemctl status mike-product-calc
```

---

## 2. 更新方式

### 2.1 远程安装 / 升级（推荐，**无 git 依赖**）

```bash
curl -fsSL https://raw.githubusercontent.com/ericmr1981/mike-product-calc/main/scripts/install.sh | bash
# 或指定版本：
TAG=v0.1.0 bash <(curl -fsSL https://raw.githubusercontent.com/ericmr1981/mike-product-calc/main/scripts/install.sh)
```

安装脚本会自动：
- 下载指定版本的 tar.gz
- 校验 SHA256
- 解压到 `/opt/mike-product-calc`（或 `APP_INSTALL_DIR` 环境变量指定路径）
- 写入 `VERSION.md`（版本号 / 安装时间 / checksum）

### 2.2 Git 升级（有 git 的服务器）

```bash
cd /opt/mike-product-calc
git fetch --tags
git checkout v0.X.Y
pip install -r requirements.txt   # 如有新增依赖
```

### 2.3 回滚

```bash
# 方法 1：checkout 旧 tag（git 方式）
git checkout v0.X.Y

# 方法 2：重新安装旧版本（install.sh 方式）
TAG=v0.X.Y bash <(curl -fsSL https://raw.githubusercontent.com/ericmr1981/mike-product-calc/main/scripts/install.sh)
```

**回滚安全性**：应用状态由 Excel 数据文件驱动，不写数据库。无状态，回滚即切换代码版本，安全无损。

---

## 3. 架构

### 3.1 目录结构

| 路径 | 用途 | 生产注意事项 |
|------|------|-------------|
| `app.py` | Streamlit 主入口，所有 Tab 页面 | — |
| `src/mike_product_calc/` | 核心业务逻辑（parser/calculator/validator） | — |
| `data/` | Excel 数据文件 + 校验报告 | 生产部署建议挂载到只读路径 |
| `scripts/validate.sh` | 数据校验脚本 | 部署后可定期跑 |
| `scripts/install.sh` | 安装/升级脚本（包含 VERSION.md 生成） | — |
| `tests/` | pytest 单元测试（profit / margin / material_sim / loader） | CI 必须通过 |
| `harness/` | 开发任务追踪文件（非生产内容） | tar.gz 会排除 |
| `docs/` | 设计文档 / 决策记录 / E2E 测试计划 | tar.gz 会排除 |

### 3.2 核心模块

```
Excel 数据文件 (蜜可诗产品库.xlsx)
    ↓
src/mike_product_calc/
    ├── loader.py        # sheet 检测 / 表头解析 / 数据加载
    ├── validator.py     # 数据校验（issue 关联 SKU/原料）
    ├── profit.py        # 毛利/利润计算（双口径：出厂/门店）
    ├── margin_target.py # 目标毛利率反推原料定价
    ├── material_sim.py  # 原料价格模拟器（版本管理 + 对比）
    ├── bom.py           # BOM 三级展开 + 缺口预警
    └── combinator.py    # 选品组合优化器（枚举 Top-3 + 推荐）
    ↓
app.py (Streamlit Tabs) → 用户浏览器
```

### 3.3 外部依赖

- `pandas` — 数据加载 / 清洗
- `numpy` — 数值计算
- `scipy` — 优化算法（选品组合器）
- `streamlit` — Web UI
- `openpyxl` — Excel 读取

**注意**：无数据库。数据来源唯一为 `data/蜜可诗产品库.xlsx`。

### 3.4 配置与密钥

- 无外部 API 密钥依赖
- 数据文件路径：`data/蜜可诗产品库.xlsx`（支持通过 Streamlit 上传覆盖）
- 生产环境建议：`data/` 目录挂载为只读，防止误改

---

## 4. 功能清单

| ID | 功能 | Tab | 核心模块 | 数据依赖 | 风险 |
|----|------|-----|---------|---------|------|
| F-001 | Excel 数据解析与校验 V2 | Tab1 | loader + validator | 蜜可诗产品库.xlsx | sheet 结构变化 |
| F-002 | SKU 毛利分析（双口径） | Tab2 | profit | 蜜可诗产品库.xlsx | 成本字段缺失 |
| F-003 | 目标毛利率反推原料定价 | Tab2 | margin_target | 蜜可诗产品库.xlsx | 反推无解情况 |
| F-004 | 原料价格模拟器（版本管理） | Tab4 | material_sim | 蜜可诗产品库.xlsx | — |
| F-005 | 生产计划录入（CSV 导入/导出） | Tab5 | bom | 蜜可诗产品库.xlsx | BOM 字段缺失 |
| F-006 | 备料计划引擎（BOM 三级展开） | Tab6 | bom | 蜜可诗产品库.xlsx | 级联缺口放大 |
| F-007 | 采购建议页（紧急项标红） | Tab7 | bom + material_sim | 蜜可诗产品库.xlsx | — |
| F-008 | 产品组合评估（方案 A/B/C） | Tab8 | profit + combinator | 蜜可诗产品库.xlsx | — |
| F-009 | 数据健康与可信度提示 | Tab1 | validator | 蜜可诗产品库.xlsx | — |
| F-010 | 多场景对比（多组销量假设） | Tab9 | profit | 蜜可诗产品库.xlsx | — |
| F-011 | 产能需求估算（高压 SKU 标红） | Tab11 | bom | 蜜可诗产品库.xlsx | — |
| F-012 | 选品组合优化器（可解释推荐） | Tab10 | combinator + scipy | 蜜可诗产品库.xlsx | — |

---

## 5. 运维 / 故障排查

### 5.1 常见问题

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| Streamlit 启动报错 "No module named" | 依赖未安装 | `pip install -r requirements.txt` |
| Tab 页面空白 / 报错 | Excel sheet 结构变化 | 运行 `python -m mike_product_calc.validator` 检查 |
| 毛利计算结果异常 | 成本字段为空或 0 | 检查 `data_validation_report.csv` 中的 issue |
| install.sh 下载失败 | 网络问题 / 指定 tag 不存在 | 确认 https://github.com/.../releases 存在该版本 |

### 5.2 日志位置

- Streamlit 日志：stdout（systemd/pm2 捕获）
- 数据校验报告：`data_validation_report.csv`（每次 app.py 启动时自动生成）

---

## 6. 更新记录

> 仅记录**维护者/Agent 需要知会**的重要变更：破坏性变更、迁移步骤、已知风险。

### v0.1.0 (2026-04-13)
- **Sprint-2 完成**，12/12 features 合入 main
- 新增 Tab：F-004 原料价格模拟器、F-005 生产计划录入、F-006 备料计划引擎等
- 修复：说明框显示异常、上传文件持久化失败、日历日期默认 today、SKU 池区分显示
- **Breaking**: 无
- **Rollback**: 安全（无状态，回滚代码即可）
- **风险**: Excel sheet 结构变化会导致 loader 失效，请关注 `data_validation_report.csv`

---

## 7. 部署检查清单（Deploy Checklist）

每次发版前确认：

- [ ] `tests/` 所有用例通过（`pytest`）
- [ ] `scripts/validate.sh` 对当前 Excel 数据无新增 issue
- [ ] `AGENT_NOTES.md` Changelog 已更新
- [ ] 新 tag 已 push：`git tag vX.Y.Z && git push origin vX.Y.Z`
- [ ] GitHub Release 已创建，tar.gz 已上传（如需第三方安装）
- [ ] `install.sh` 在干净环境测试通过
