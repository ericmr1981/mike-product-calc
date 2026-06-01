# Tab3: 原料价格模拟器 — 页面结构

## 布局

三步向导式布局：

### Step 1 — 产品选择
- `st.selectbox("Select Product")` — 从 sku_profit_table() 提取唯一产品键
- `st.radio("Basis")` — 工厂价/门店价切换

### Step 2 — SKU 规格列表
- `st.dataframe`：所选产品的所有 SKU 行（名称/价格/成本/毛利率）
- `st.selectbox("Select SKU to view recipe")` — 默认为"小杯"

### Step 3 — 配方详情与定价
- SKU 标签标题
- 每个配料的 st.number_input("Store price for {item}") + 成本/利润说明
- KPI 行：售价输入 / 总成本 / 品牌成本 / 毛利率
- 成本分解图（Plotly 圆环图 × 2）
- 场景管理：场景名称输入 + 保存/预览/应用
- 价格变更历史：最近 10 批 + 查看/回滚按钮
- 场景对比：两个 selectbox + Compare 按钮
