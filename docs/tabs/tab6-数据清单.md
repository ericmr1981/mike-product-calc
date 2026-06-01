# Tab 6: 配方管理 — 数据清单

## 数据源总览

| 数据源 | 方法 | 用途 |
|--------|------|------|
| Supabase products | `DataService.get_products()` | 产品列表（左栏选择 + 右栏详情） |
| Supabase products | `DataService.create_product()` | 新建产品 |
| Supabase products | `DataService.update_product()` | 更新产品信息 |
| Supabase raw_materials | `DataService.get_raw_materials()` | 原料池（添加配料时选择来源） |
| Supabase recipes | `DataService.get_all_recipes()` | 配方明细渲染 |
| Supabase recipes | `DataService.set_recipes()` | 批量设置配方（添加、删除、清空） |

---

## DataService 方法

### `get_products(is_final=None) -> list[dict]`

**路径**: `DataService.get_products()` → `MpcSupabaseClient.list_products()`

**缓存**: 会话级（`_caches["products"]`），写入后失效。

**返回字段**: id, name, version, category, production_type, is_final_product, status 等。

**Tab 6 使用方式**:
- 全量拉取 `_ds_t6.get_products()` → 填充产品下拉。
- 右栏通过 `{p["id"]: p}` 构建字典按 ID 查询产品详情。

### `get_raw_materials(category=None, search=None) -> list[dict]`

**路径**: `DataService.get_raw_materials()` → `MpcSupabaseClient.list_raw_materials()`

**缓存**: 会话级。

**用途**: 为添加配料时提供原料选择来源（`pool["raw_materials"]`）。

### `get_all_recipes() -> list[dict]`

**路径**: `DataService.get_all_recipes()` → `MpcSupabaseClient.list_all_recipes()`

**缓存**: 会话级（`_caches["all_recipes"]`）。

**返回字段（关键）**: product_id, ingredient_source, raw_material_id, ref_product_id, quantity, unit_cost, store_unit_cost, sort_order。

**注意**: `raw_material_id` 和 `ref_product_id` 可能是展开的嵌套字典（包含 `id`, `name` 等）或纯 UUID 字符串，取决于 Supabase API 响应格式。UI 使用 `_extract_id()` 统一处理。

### 写方法

| 方法 | 签名 | 副作用 |
|------|------|--------|
| `create_product` | `(data: dict) -> dict` | 写入后缓存失效 |
| `update_product` | `(id: str, data: dict) -> dict` | 写入后缓存失效 |
| `set_recipes` | `(product_id: str, recipes_data: list[dict]) -> list[dict]` | 批量替换产品的全部配方，写入后缓存失效 |

**`set_recipes` 写入格式**:

每条配方记录包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| product_id | str | 关联的产品 UUID |
| ingredient_source | str | `"raw"`（原料）或 `"product"`（半成品） |
| raw_material_id | str or None | 原料 UUID |
| ref_product_id | str or None | 半成品产品 UUID |
| quantity | float | 用量 |
| unit_cost | float or None | 单位成本 |
| store_unit_cost | float or None | 门店单位成本 |
| sort_order | int | 排序序号 |

---

## 数据模型

### Product

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | str | 品名（如 "木姜子甜橙"） |
| version | str | 版本（如 "2.0"） |
| category | str | 品类 |
| production_type | str | "门店调配" / "工厂调配" |
| is_final_product | bool | 是否最终成品 |
| status | str | "上线" / "下线" |

---

## 数据流关键点

1. **产品名/版本拆分**: `_split_version()` 分离 `name` 和 `version`。如用户输入"木姜子甜橙 2.0" → name="木姜子甜橙", version="2.0"。
2. **配方读写全量替换**: `set_recipes()` 是批量替换，不是增量追加。添加配料时 UI 先读取现有配方列表，追加新记录后全量写入。
3. **嵌套 ID 展开**: Supabase API 可能会以嵌套对象形式返回外键（如 `{"id": "uuid", "name": "原味奶浆"}`）。UI 使用 `_extract_id()` 在写入前统一提取 UUID 字符串。
4. **同层引用**: 添加半成品作为配料时，当前产品被自动排除（`p["id"] != selected_id`），防止自引用。
5. **数据源标签**: 界面底部标注"数据来源: Supabase"，确认所有数据存于远程数据库。
