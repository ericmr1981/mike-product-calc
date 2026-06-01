# Tab 5: 原料管理 — 界面结构

## 概览

原料管理 Tab 提供对采购原料的完整 CRUD 操作，并支持从 Excel 文件批量同步数据。所有数据基于 Supabase 的 `raw_materials` 表。

**位置**: `app.py` 第 1684-1929 行。

---

## 顶部标题

**标题**: "原料管理"（带帮助提示悬浮卡）

**帮助文本**: "功能说明：管理所有采购原料的信息。支持 CRUD 操作，并可从 Excel 同步。字段说明：编码=品项编码（自动生成）；名称=品项名称；类别=调味酱/包材/乳制品等；单价=加价后有效采购价。"

---

## 统计指标行 (4 列)

**数据源**: `DataService.get_raw_materials()` 缓存

| 列 | 指标 | 说明 |
|----|------|------|
| col_s1 | 原料总数 | `len(_rm_cache)` |
| col_s2 | 已上线 | status 为"上线"或"已生效"的数量 |
| col_s3 | 已下线 | 总数减去已上线数 |
| col_s4 | 类别数 | 去重 category 的数量 |

---

## Excel 上传区

**组件**: `st.expander("📤 上传原料表（Excel）", expanded=False)`

**子标题**: "按两部分上传：品项导出 + 加价规则导出。系统将按品项编码合并后同步。"

**Widgets**:
- 文件上传器 1: "上传品项导出文件" (xlsx)。
- 文件上传器 2: "上传加价规则文件" (xlsx)。
- 数据预览（需两个文件都上传后）:
  - 使用 `_preview_sync_raw_materials_compat()` 预览差异。
  - 将差异渲染为 DataFrame。
- 确认按钮: "确认执行同步" — 调用 `_execute_sync_raw_materials_compat()`。
- 成功消息: "同步完成: 新增 N, 更新 N, 跳过 N"。
- 完成后: 调用 `invalidate_all()` 清空缓存并 `st.rerun()`。

**交互提示**: 若只上传了一个文件，显示"请同时上传「品项导出」和「加价规则导出」两个文件后再预览同步。"

---

## 筛选表单

**组件**: `st.form("tab5_filter_form")` — 提交时更新 session state 筛选条件。

**Widgets**:
- 类别下拉 (`_categories`): 从全部原料去重得到，包含"全部"占位选项和"新增类别..."选项。
- 状态下拉: "全部"、"上线"、"已生效"、"下线"。
- 搜索输入: 文本输入框，placeholder "输入原料名称..."。
- 提交按钮: "应用筛选"。

**筛选逻辑**（表单外部，第 1769-1783 行）:
- 从缓存 `_rm_cache` 开始。
- 若类别不是"全部"，按 `m["category"]` 过滤。
- 若搜索词非空，按 `m["name"]` 大小写不敏感匹配。
- 若状态指定：
  - "上线" → status in ("上线", "已生效")。
  - 其他值 → 精确匹配该状态。

---

## 原料数据表

**数据源**: 按过滤条件过滤后的 `DataService.get_raw_materials()` 结果。

**显示列**: 编码、名称、类别、成本、单价、单位量、单位、状态。

**Widget**: `st.dataframe()` 高度 360px、隐藏索引。

**空状态**: "暂无原料数据。请先上传 Excel 导入。"

---

## 分隔线

---

## 操作切换（新增 vs 修改）

**组件**: `st.radio("操作", options=["➕ 新增原料", "✏️ 修改原料"], horizontal=True)`

### 新增原料 (tab5_action == "➕ 新增原料")

**组件**: `st.form("new_material_form", clear_on_submit=True)`

**Widgets**:
- 编码（自动生成、禁用）: 格式 `RM` + 4 位数字序列（如 `RM0001`），使用 `_next_material_code()`。
- 必填指示: "**必填字段**"。
- 左列:
  - 名称 * — 文本输入。
  - 类别 * — 下拉（含"新增类别..."选项）。
  - 单位 * — 文本输入。
  - 单位量 * — 数字输入 (min=0, 4 位小数)。
- 右列:
  - 加价前单价 * — 数字输入 (min=0, 4 位小数)。
  - 加价后单价 * — 数字输入 (min=0.0001, 4 位小数)。
  - 品项类型 * — 下拉 (普通/特殊)。
  - 状态 * — 下拉 (上线/下线)。
- 备注（可选）— 多行文本。
- 提交按钮: "保存" (type=primary) — 校验必填字段，调用 `DataService.create_raw_material()`。

### 修改原料

**组件**: `st.selectbox("选择要修改的原料")` + `st.form("edit_material_form")`

**与新增相同的字段布局**，但数据预填充：编码禁用显示、名称、类别、单位、单位量、加价前单价、加价后单价、品项类型、状态、备注均从选中的原料数据加载。

**提交按钮**: "保存修改" (type=primary) — 调用 `DataService.update_raw_material(id, {...})`。

**删除功能**:
- 分隔线下方的"🗑️ 删除此原料"按钮。
- 二次确认流程：
  1. 点击 → 设置 `confirm_delete_material` session state。
  2. 显示 "确认删除「名称」？此操作不可撤销。"
  3. "确认删除"按钮 → 调用 `delete_raw_material(id)` + rerun。
  4. "取消"按钮 → 清除 `confirm_delete_material` + rerun。

---

## 状态变量

| Key | 类型 | 用途 |
|-----|------|------|
| tab5_filter_cat_applied | str | 当前应用的类别筛选 |
| tab5_filter_status_applied | str | 当前应用的状态筛选 |
| tab5_filter_search_applied | str | 当前应用的搜索词 |
| confirm_delete_material | str or None | 确认删除模式下的原料 ID |

---

## 常量

| 常量 | 值 | 用途 |
|------|-----|------|
| STATUS_ACTIVE | "上线" | 原料上线状态 |
| STATUS_INACTIVE | "下线" | 原料下线状态 |
