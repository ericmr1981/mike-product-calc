# Tab 7: 出品规格管理 — 数据清单

## 核心表

### products

用于产品列表和主原料选择。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | PK |
| name | text | 产品名 |
| is_final_product | boolean | 是否最终成品（可售卖） |
| version | text | 版本号（用于标签） |
| factory_cost | numeric | 工厂成本 |
| store_cost | numeric | 门店成本 |
| batch_size | numeric | 批量 |
| computed_factory_cost | numeric | 自动计算的工厂成本 |
| computed_store_cost | numeric | 自动计算的门店成本 |
| computed_batch_size | numeric | 自动计算的批量 |

查询：`client.list_products(is_final=True)` → `GET /rest/v1/products?is_final_product=eq.true`

### raw_materials

用于包材选择（`category == "包材"`）和配料选择（category 在 `{调味酱, 配料, 乳制品, 风味奶浆, 辅料, 成品, 水果}` 中）。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | PK |
| name | text | 原料名 |
| category | text | 分类（用于区分包材/配料） |
| unit | text | 单位 |
| base_price | numeric | 基础价 |
| final_price | numeric | 最终价 |
| unit_amount | numeric | 单位量 |

查询：`client.list_raw_materials()` → `GET /rest/v1/raw_materials?order=name`

### serving_specs

出品规格主表。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | PK |
| product_id | uuid | FK → products.id |
| spec_name | text | 规格名（如"标准杯"、"小杯"） |
| quantity | numeric | 主原料用量（克） |
| main_material_id | uuid | FK → products.id（主原料必须是产品） |
| packaging_id | uuid | FK → raw_materials.id（包材，category=包材） |
| packaging_qty | numeric | 包材数量 |
| product_price | numeric | 定价（元） |
| created_at | timestamptz | 创建时间 |

### serving_spec_toppings

出品规格附加配料关联表。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | uuid | PK |
| serving_spec_id | uuid | FK → serving_specs.id |
| material_id | uuid | FK → raw_materials.id |
| quantity | numeric | 用量 |

查询（嵌套）：`client.list_all_serving_specs()` 通过 `select` 参数一次性获取：

```
GET /rest/v1/serving_specs?
  select=*,serving_spec_toppings(*,material_id(*)),
         packaging_id(*),main_material_id(*)
```

## 数据流

```
【读取】
  DataService.get_all_serving_specs()
    → client.list_all_serving_specs()
    → GET /rest/v1/serving_specs (含关联数据)

  DataService.get_products()
    → client.list_products()

  DataService.get_raw_materials()
    → client.list_raw_materials()

【写入】
  DataService.set_serving_specs(product_id, specs_data)
    → client.set_serving_specs(product_id, specs_data)
      → GET existing specs
      → DELETE serving_spec_toppings (每个旧 spec)
      → DELETE serving_specs WHERE product_id = ?
      → POST new specs (batch insert)
      → POST serving_spec_toppings (每个新 spec 的 _toppings)
```

## 缓存

- `DataService` 内部维护 `_caches` 字典
- `get_all_serving_specs()` 结果缓存在 `_caches["all_specs"]`
- `get_products()` 结果缓存在 `_caches["products"]`
- `get_raw_materials()` 结果缓存在 `_caches["raw_materials"]`
- 每次 `set_serving_specs` 调用后自动 `_invalidate()` 清空所有缓存
- UI 端也可调用 `invalidate_all()` 手动刷新

## 旧 UI 数据来源（Excel Fallback）

当 Supabase 不可用时，仅使用 `_discover_sku_keys(sheets)` 从 `产品出品表` 发现 SKU。出品规格的 CRUD 仅支持 Supabase 模式。Excel 模式下 tab 7 不可用。
