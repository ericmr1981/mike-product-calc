# Tab1: 概览/校验 — 页面结构

## 布局

页面分为 3 个纵向区域，全部使用 `st.markdown` 渲染自定义 HTML（无 Streamlit 原生组件）：

### ① 风险区（Risk Zone）
- 3 个信息卡片，CSS grid 布局
- 缺货项：available_qty ≤ 0 的品项数
- 异常项：负库存或金额不匹配的品项数
- 快照时效：库存快照距现在是否超过 2 小时
- 颜色由 `_risk_level()` 控制（正常/中等/严重）

### ② 业务指标区（Business Metrics Zone）
- 4 个信息卡片
- 原料总数 → `get_raw_materials()`
- 产品总数 → `get_products()`
- 成品数 → 筛选 `is_final_product`
- 出品规格数 → `get_all_serving_specs()`

### ③ 建议操作区（Action Hints Zone）
- 由 `_build_action_hints()` 生成的排序列表
- 根据风险状态输出指向其他 Tab 的操作链接
