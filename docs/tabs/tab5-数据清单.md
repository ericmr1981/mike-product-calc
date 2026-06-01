# Tab 5: 原料管理 — 数据清单

## 数据源总览

| 数据源 | 方法 | 用途 |
|--------|------|------|
| Supabase raw_materials | `DataService.get_raw_materials()` | 所有原料的读取、过滤、显示 |
| Supabase raw_materials | `DataService.create_raw_material()` | 新增原料 |
| Supabase raw_materials | `DataService.update_raw_material()` | 修改原料 |
| Supabase raw_materials | `DataService.delete_raw_material()` | 删除原料 |
| Supabase raw_materials | `DataService.upsert_raw_materials()` | Excel 同步用批量写入 |
| Excel 文件 | 品项导出 + 加价规则导出 | 批量同步 (preview + execute) |

---

## DataService 方法

### `get_raw_materials(category=None, search=None) -> list[dict]`

**路径**: `DataService.get_raw_materials()` → `MpcSupabaseClient.list_raw_materials()`

**缓存**: 会话级（`_caches["raw_materials"]`），写入后失效。

**返回字段**: code, name, category, base_price, final_price, unit_amount, unit, status, item_type, notes, id 等。

**Tab 5 使用方式**:
- 首次调用获取全量缓存 `_rm_cache`。
- 后续在 UI 层做 JavaScript 风格的数组过滤（category、search、status）。
- 不在 DataService 层面做 status 过滤（因为 status 过滤逻辑涉及"上线"和"已生效"的 OR 条件，DataService 不支持）。

### 写方法

| 方法 | 签名 | 副作用 |
|------|------|--------|
| `create_raw_material` | `(data: dict) -> dict` | 自动 code 生成在 UI 层（`RM` + 4 位序号），调用后缓存失效 |
| `update_raw_material` | `(id: str, data: dict) -> dict` | 调用后缓存失效 |
| `delete_raw_material` | `(id: str) -> bool` | 调用后缓存失效 |
| `upsert_raw_materials` | `(records: list[dict]) -> list[dict]` | 用于 Excel 批量同步，调用后缓存失效 |

所有写方法在完成后调用 `_invalidate()` 清空 `_caches`。

---

## Excel 同步流程

### 入口

用户在 expander 中上传两个 Excel 文件：
1. **品项导出文件** — 包含品项编码、名称、类别等。
2. **加价规则文件** — 包含每个品项的加价后单价等。

### 预览

```python
_diffs = _preview_sync_raw_materials_compat(items_wb.sheets, markup_wb.sheets, _ds_t5.client)
```

此函数支持两种模式：
- **新模式**: `preview_sync_raw_materials_two_files()` (双文件分别处理)。
- **旧模式（回退）**: 合并 sheets 后调用 `preview_sync_raw_materials()`。

差异 `diffs` 包含每项的 action（insert/update/skip）等信息，渲染为 DataFrame 供用户预览。

### 执行

```python
_result = _execute_sync_raw_materials_compat(items_wb.sheets, markup_wb.sheets, _ds_t5.client)
```

`SyncResult` 包含 `inserts` 和 `updates` 计数。

执行后：
1. `_ds_t5.invalidate_all()` 清空缓存。
2. `st.rerun()` 刷新 UI。

---

## 数据模型 (raw_materials)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 (Supabase auto) |
| code | str | 编码 (RM + 4 位数字，如 RM0001) |
| name | str | 品项名称 |
| category | str | 类别（调味酱、包材、乳制品等） |
| base_price | float | 加价前单价 |
| final_price | float | 加价后有效单价 |
| unit_amount | float | 单位量 |
| unit | str | 单位（克、个、盒等） |
| item_type | str | 品项类型（普通、特殊） |
| status | str | 状态（上线、下线、已生效） |
| notes | str | 备注（可选） |

---

## 数据流关键点

1. **编码自动生成**: `_next_material_code()` 扫描所有现有原料，找到最大 `RM` 序号后 +1。例如现有 RM0003，下一个为 RM0004。
2. **过滤在 UI 层**: DataService 返回全量缓存，过滤由 Streamlit 端的列表推导完成（category 过滤、名称搜索、status 的 OR 条件）。
3. **缓存失效**: 所有写操作（create/update/delete/upsert）都会清空整个 `_caches` 字典，下次读取时重新从 Supabase 拉取。
4. **Excel 同步的双文件合并**: 品项导出提供基础信息，加价规则提供价格信息，按品项编码匹配合并后写入数据库。
