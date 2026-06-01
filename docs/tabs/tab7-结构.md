# Tab 7: 出品规格管理 — 页面结构

## 布局

两栏布局：

- **左侧 1/3**：产品列表（`st.selectbox`）。数据来源 `DataService.get_products()`，过滤 `is_final_product == True`。选中产品后，右侧联动显示其所有出品规格。
- **右侧 2/3**：规格编辑器。显示选中产品的所有出品规格，每个规格以 `st.container(border=True)` 包裹。

## 规格显示（只读视图）

每个规格容器内从上到下排列：

1. **名称行**：`spec_name` 加粗 + 定价（`product_price`，格式 `¥XX.XX`）
2. **主原料行**：`main_material_id`（通过关联查询 name） × `quantity` 克
3. **包材行**：`packaging_id`（name）+ 附加配料中 `category == "包材"` 的项（`name × quantity`）
4. **附加配料行**：附加配料中 `category != "包材"` 的项（`name × quantity`，逗号拼接）
5. **操作按钮**：右侧对齐的 ✏️ 编辑（`st.button`）和 🗑️ 删除（`st.button`）

### 编辑态

点击 ✏️ 按钮后，`st.session_state["_editing_spec"]` 设为当前 spec id，触发表单渲染。

编辑表单（`st.form`）：

| 字段 | 控件 | 数据来源 |
|------|------|----------|
| 规格名 | `st.text_input` | 当前 spec.spec_name |
| 主原料 | `st.selectbox` | `main_prod_options`（所有产品，含版本号） |
| 主原料用量 | `st.number_input`（克） | 当前 spec.quantity |
| 包材 | `st.multiselect` | `pkg_options`（category=包材 的原料） |
| 定价 | `st.number_input`（元） | 当前 spec.product_price |
| 附加配料 | `st.data_editor`（动态行） | `_ing_mat_options`（调味酱/配料/乳制品等） |

保存按钮 **保存修改**：

1. 收集包材项（第一项设 `packaging_id`，其余转为 `_toppings`）
2. 收集配料 data_editor 非空行
3. 构建完整 payload（保留当前产品所有规格，只替换编辑的规格）
4. 调用 `DataService.set_serving_specs(product_id, payload)`
5. `invalidate_all()` 清除缓存
6. `st.rerun()`

## 新增规格

`st.expander("➕ 新增出品规格", expanded=False)` 内嵌表单：

| 字段 | 控件 | 备注 |
|------|------|------|
| 规格名 | `st.selectbox` 可选 小杯/标准杯/华夫蛋筒/华夫碗, 或选"自定义..."后显示 text_input |
| 主原料 | `st.selectbox` | 默认选中当前产品名 |
| 主原料用量 | `st.number_input`（克） | 默认 120.0 |
| 包材 | `st.multiselect` | category=包材 |
| 定价 | `st.number_input`（元） | 默认 0.0 |
| 附加配料 | `st.data_editor`（动态行） | 下方显示单位提示 |

保存按钮 **保存规格**：

1. 收集包材和配料数据
2. 保留现有全部规格（`_normalize_spec_payload`）
3. 追加新规格 payload，含 `product_id`, `spec_name`, `quantity`, `main_material_id`, `packaging_id`, `product_price`, 可选 `_toppings`
4. 调用 `DataService.set_serving_specs(product_id, payload)`

## 数据流

```
前端 UI (app.py tab7)
  │
  ├─ DataService.get_products(is_final=True)        ← 产品列表
  ├─ DataService.get_raw_materials()                ← 原料池（包材 + 配料）
  ├─ DataService.get_all_serving_specs()            ← 全部规格（含关联 toppings）
  │     └─ client.list_all_serving_specs()
  │           └─ SELECT * FROM serving_specs
  │               + serving_spec_toppings(*, material_id(*))
  │               + packaging_id(*), main_material_id(*)
  │
  └─ DataService.set_serving_specs(product_id, specs_data)
        └─ client.set_serving_specs(product_id, specs_data)
              ├─ DELETE serving_spec_toppings (for each existing spec)
              ├─ DELETE serving_specs WHERE product_id = ?
              ├─ POST new specs
              └─ POST serving_spec_toppings (for each new spec's _toppings)
```

## 样式说明

- 规格容器：`st.container(border=True)`
- 操作按钮：`st.container(horizontal=True, horizontal_alignment="right")`
- 包材分类常量：`CATEGORY_PACKAGING = "包材"`
- 配料分类池：`{"调味酱", "配料", "乳制品", "风味奶浆", "辅料", "成品", "水果"}`
- 主原料来源：所有产品（含非最终品），标签格式 `"{name} v{version}"`

## 删除规格

点击 🗑️ 按钮：

1. 过滤掉当前 spec
2. 剩余 specs 经 `_normalize_spec_payload()` 标准化
3. 调用 `set_serving_specs(product_id, remaining)`
4. `invalidate_all()` + `st.rerun()`

## 关键约束

- `set_serving_specs` 是全量替换：删除旧规格和旧 toppings，再插入新数据。这意味并发编辑会有覆盖风险。
- 包材（`packaging_id`）仅存第一个选中项，其余包材转入 `_toppings`。
- 主原料必须是产品（`products` 表），不能是原料（`raw_materials`）。
