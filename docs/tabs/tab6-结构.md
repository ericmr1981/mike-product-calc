# Tab 6: 配方管理 — 界面结构

## 概览

配方管理 Tab 提供产品配方的 BOM 管理，支持选择产品、查看/编辑配方明细、添加/删除配料。采用左右两栏布局，左栏为产品列表，右栏为产品详情和配方编辑器。

**位置**: `app.py` 第 1931-2144 行。

---

## 顶部标题

**标题**: "配方管理 (BOM)"（带帮助提示悬浮卡）

**帮助文本**: "功能说明：管理产品的配方明细。支持引用采购原料和半成品作为配料。使用方式：选择产品 → 编辑配方明细 → 保存。"

---

## 两栏布局

**组件**: `st.columns([1, 2])`，左列占 1/3，右列占 2/3。

---

## 左栏：产品列表

**位置**: 第 1950-1985 行。

### 产品选择

**数据源**: `DataService.get_products()`（全量产品列表）。

**Widgets**:
- 子标题: "产品列表"。
- 产品下拉: `st.selectbox("选择产品")` — 选项为 `{product_name: product_id}` 映射。
- 如果 `get_products()` 返回空列表，显示 "暂无产品。" 并停止渲染 (`st.stop()`)。

### 新建产品

**组件**: `st.expander("➕ 新建产品", expanded=False)`。

**表单**: `st.form("new_product_form")`

| 字段 | Widget | 说明 |
|------|--------|------|
| 品名 * | `st.text_input` | 如"木姜子甜橙 2.0"，版本号自动拆分 |
| 品类 | `st.text_input` | 自由文本 |
| 制作类型 | `st.selectbox` | 选项: "门店调配" / "工厂调配" |
| 最终成品 | `st.checkbox` | 默认勾选 (value=True) |

**提交处理**:
1. 校验品名不能为空。
2. 调用 `_split_version(name)` 解析品名和版本号（正则匹配 `数字.数字` 后缀）。
3. 调用 `DataService.create_product()`。
4. 显示"已创建: {品名}"并刷新。

### 数据来源提示

**文本**: "数据来源: Supabase"

---

## 右栏：产品详情与配方编辑器

**位置**: 第 1987-2144 行。

### 产品信息表单

**组件**: `st.form("edit_product_form")`

| 列 | 字段 | Widget | 说明 |
|----|------|--------|------|
| 列 0 | 品名 | `st.text_input` | 预填充当前值 |
| 列 1 | 版本 | `st.text_input` | 预填充当前值 |
| 列 2 | 品类 | `st.text_input` | 预填充当前值 |
| 列 0 | 制作类型 | `st.selectbox` | 选项: "门店调配" / "工厂调配" |
| 列 1 | 状态 | `st.selectbox` | 选项: "上线" / "下线" |
| 列 2 | 最终成品 | `st.checkbox` | 预填充当前值 |

**提交按钮**: "保存产品信息" — 调用 `DataService.update_product(selected_id, {...})`。

---

### 配方明细 (BOM)

**标题**: "配方明细 (BOM)"

**数据源**: `DataService.get_all_recipes()` 按 `product_id` 过滤。

**配方行渲染**: 遍历当前产品的配方 `recipes`，构造每行包含：
- "来源": "原料" 或 "半成品"（根据 `ingredient_source` 字段）。
- "配料": 展开后的原料名称或半成品名称。
- "用量": `quantity` 值。

**显示**: `st.dataframe()` 隐藏索引。

#### 导出按钮

`st.download_button("📥 导出 CSV")` — 将配方数据编码为 CSV 下载。

#### 清空配方按钮

`st.button("🗑️ 清空全部配方")` — 调用 `DataService.set_recipes(selected_id, [])` 并刷新。

---

### 删除单条配料

**组件**: `st.expander("🗑️ 删除单条配料", expanded=False)`

**Widgets**:
- **配料下拉**: `st.selectbox("选择要删除的配料")` — 选项格式 `"{配料名} (用量: {N})"`。
- **确认删除按钮**: `st.button("确认删除")` —
  1. 找到选中配料的索引。
  2. 构造新配方列表（排除该索引）。
  3. 对每条剩余配方调用 `_extract_id()` 展开 `raw_material_id` / `ref_product_id`。
  4. 调用 `DataService.set_recipes()` 批量写入。
  5. 显示"配料已删除"并刷新。

---

### 添加配料

**组件**: `st.expander("➕ 添加配料", expanded=False)`

**表单**: `st.form("add_ingredient_form")`

#### 配料来源选择

`st.radio("配料来源", options=["原料", "半成品"], horizontal=True)`

#### 根据来源显示不同下拉

**来源 = "原料"**:
- 数据池: `DataService.get_raw_materials()` — 所有原料。
- 选项: `"{name} ({category})"` 映射到原料 ID。
- 选择器: `st.selectbox("选择原料")`。

**来源 = "半成品"**:
- 数据池: `DataService.get_products()` — 排除当前产品。
- 选项: `"{name} v{version}"` 映射到产品 ID。
- 选择器: `st.selectbox("选择半成品")`。

#### 用量输入

`st.number_input("用量", min_value=0.0, format="%.2f")`

#### 提交逻辑

1. 构造新配方记录，包含 `product_id`, `ingredient_source`, `quantity`。
2. 如来源为"原料"，设置 `raw_material_id`；如为"半成品"，设置 `ref_product_id`。
3. 展开现有配方调用 `_extract_id()` 处理嵌套对象。
4. 合并后调用 `DataService.set_recipes()`。
5. 显示"配料已添加"并刷新。

---

## 辅助函数

### `_split_version(name: str) -> tuple[str, str]`

- 路径: `app.py` 第 1938-1943 行。
- 功能: 将 `"木姜子甜橙 2.0"` 拆分为 `("木姜子甜橙", "2.0")`。
- 实现: 正则 `r'^(.+?)\s*(\d+\.\d+)$'`。

### `_extract_id(val)`

- 路径: `app.py` 第 73-77 行。
- 功能: 从嵌套字典（Supabase 展开的外键）或普通字符串中提取 UUID。
- 实现: 若 `val` 为 `dict`，返回 `val.get("id")`，否则返回 `val` 本身。
