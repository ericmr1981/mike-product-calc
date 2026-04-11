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

## MVP 里程碑（M1~M4）

| 阶段 | 目标 | 核心交付物 |
|------|------|----------|
| **M1** | 数据层 + SKU 毛利展示 | `data/loader.py`, `data/validator.py`, `data/material_index.py`, `calc/profit.py`, `pages/1_SKU_毛利调价台.py` |
| **M2** | 目标毛利率反推 + 原料价格模拟 | `calc/margin_target.py`, `calc/material_sim.py`, `pages/2_原料价格模拟器.py`, `model/scenario.py` |
| **M3** | 生产计划 + 备料计划 + 采购建议 | `model/production.py`, `calc/prep_engine.py`, `calc/purchase_suggestion.py`, `pages/3_生产计划.py`, `pages/4_备料计划.py`, `pages/5_采购建议.py` |
| **M4** | 组合评估 + 场景对比 + 数据健康 | `calc/scenarios.py`, `pages/6_组合评估.py`, `pages/7_数据健康.py`, README.md |

---

## 优先级排序（MVP）

### P0 — 核心闭环（必须交付）
1. Excel 解析 + 数据校验
2. SKU 毛利分析（双口径）
3. 目标毛利率反推原料定价
4. 原料价格模拟（版本管理）
5. 生产计划录入
6. 备料计划引擎（BOM 展开）
7. 采购建议
8. 产品组合评估（实时联动）
9. 数据健康提示

### P1 — 增强体验
- 方案 A/B/C 保存与对比
- CSV 导出（备料计划、采购建议、利润表）

### P2 — 拉开差距
- 多场景对比（不同销量假设）
- 选品优化器（枚举法 + 次优方案）

### P3 — 锦上添花
- 产能工时换算
- scipy 优化算法
- 库存字段扩展

---

## 关键业务规则（开发必须知道）

### 成本可调性分类
```
FIXED      = 包材、标配耗材（杯/碗/勺/卡/贴/袋）
ADJUSTABLE = 奶浆、果酱、坚果、巧克力、糖浆、油脂、基底乳
MANAGED    = 糖类、部分半成品（可调但需谨慎）
```

### 定价反推公式
```
目标允许门店成本 = 售价 × (1 - 目标门店毛利率)
成本调整空间     = 目标允许门店成本 - 当前门店成本
某原料建议单价   = (当前单价 × 理论总量 + 分配调整额) / 理论总量
```

### 备料规则默认值
```
损耗率:          5%（可在 UI 层覆盖）
安全库存率:      10%（可在 UI 层覆盖）
提前期:          0 天（V1 由用户手动配置）
最小采购单位:    按原料实际包装单位
批次取整:        向上取整到最小单位倍数
```

---

## 与 V1 的主要差异

| 项目 | V1 | V2 |
|------|----|----|
| 核心链路 | 组合→原料需求 | 毛利分析→定价反推→调价模拟→生产备料 |
| 页面数 | ~4 | ~8 |
| 新增计算 | — | margin_target, material_sim, prep_engine, purchase_suggestion |
| 数据校验 | 有 | 更完善，影响范围更清晰 |
| 场景管理 | 多场景对比 | 方案A/B/C + 价格版本管理 |
| 运营语言 | 模块名 | 备料计划、采购建议、瓶颈分析 |
