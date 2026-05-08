"""Excel -> Supabase sync engine.

Maps the 3 relevant Excel sheets to Supabase tables with diff preview
and conflict resolution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from mike_product_calc.data.supabase_client import MpcSupabaseClient


@dataclass
class SyncResult:
    inserts: int = 0
    updates: int = 0
    deletes: int = 0
    conflicts: int = 0


_SHEET_RAW = "总原料成本表"
_SHEET_RECIPE = "产品配方表"
_SHEET_SERVING = "产品出品表"
_RAW_COMPARE_FIELDS = (
    "code",
    "category",
    "item_type",
    "unit",
    "unit_amount",
    "base_price",
    "final_price",
    "status",
    "item_spec",
    "item_brand",
    "item_management_type",
    "item_shelf_life_unit",
    "item_shelf_life",
    "item_storage_method",
    "item_purchase_unit",
    "item_purchase_unit_qty",
    "item_purchase_to_inventory",
    "item_order_unit",
    "item_order_unit_qty",
    "item_order_to_inventory",
    "item_consume_unit",
    "item_consume_unit_qty",
    "item_consume_to_inventory",
    "item_volume_cm3",
    "item_weight_kg",
    "item_inventory_check_types",
    "item_enabled",
    "item_mall_sort_order",
    "item_material_type",
    "item_is_weighing",
    "item_tax_category",
    "item_tax_rate_extra",
    "item_replenish_strategy",
    "item_attr_name",
    "markup_template_id",
    "markup_item_identifier",
    "markup_mode",
    "markup_value",
)
_RAW_NUMERIC_FIELDS = {"unit_amount", "base_price", "final_price"}


def _find_sheet(sheets: dict[str, pd.DataFrame], *names: str) -> Optional[str]:
    """Find the first matching sheet name (fuzzy).

    Matches by exact normalized key first, then by prefix match to handle
    workbook-specific suffixes such as ``_Gelato``, ``_饮品``.
    """
    norm = {k.replace(" ", "").replace("_", "").lower(): k for k in sheets}
    for name in names:
        key = name.replace(" ", "").replace("_", "").lower()
        if key in norm:
            return norm[key]
        # Prefix fallback: "产品配方表" matches "产品配方表gelato"
        for nk, orig in norm.items():
            if nk.startswith(key):
                return orig
    return None


def _find_sheet_by_columns(
    sheets: dict[str, pd.DataFrame],
    required_cols: tuple[str, ...],
    *,
    min_match: int,
) -> Optional[str]:
    """Find sheet by matching column names when sheet title is unknown."""
    req = {c.strip() for c in required_cols if c.strip()}
    for sheet_name, df in sheets.items():
        cols = {str(c).strip() for c in df.columns}
        if len(req & cols) >= min_match:
            return sheet_name
    return None


def _map_status(excel_status: str) -> str:
    """Map Excel status values to Supabase status values."""
    mapping = {
        "已生效": "上线",
        "已失效": "下线",
    }
    return mapping.get(excel_status, excel_status)


def _to_num(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f):
            return None
        return round(f, 4)
    except (ValueError, TypeError):
        return None


def _norm_text(val: Any) -> str:
    if val is None:
        return ""
    # Treat pandas NaN as empty so empty/NaN comparisons are stable.
    if isinstance(val, float) and math.isnan(val):
        return ""
    return str(val).strip()


def _raw_field_value(record: dict[str, Any], field: str) -> Any:
    val = record.get(field)
    if field in _RAW_NUMERIC_FIELDS:
        return _to_num(val)
    return _norm_text(val)


def _record_key(code: Any, name: Any) -> str:
    code_key = _norm_text(code)
    if code_key:
        return f"code:{code_key}"
    name_key = _norm_text(name)
    return f"name:{name_key}"


def _clean_row_dict(row: pd.Series) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.to_dict().items():
        key = _norm_text(k)
        if not key:
            continue
        if v is None:
            out[key] = None
            continue
        if isinstance(v, float) and math.isnan(v):
            out[key] = None
            continue
        out[key] = v
    return out


def _to_bool_cn(val: Any) -> Optional[bool]:
    raw = _norm_text(val)
    if raw in ("是", "Y", "y", "true", "True", "1"):
        return True
    if raw in ("否", "N", "n", "false", "False", "0"):
        return False
    return None


def _status_from_item_enabled(val: Any) -> str:
    raw = _norm_text(val)
    if raw in ("是", "启用", "已启用", "Y", "y", "true", "True", "1"):
        return "上线"
    if raw in ("否", "停用", "已停用", "N", "n", "false", "False", "0"):
        return "下线"
    return ""


# ---------------------------------------------------------------------------
# Raw Materials Sync
# ---------------------------------------------------------------------------


def _parse_raw_materials(sheets: dict[str, pd.DataFrame]) -> list[dict]:
    sheet_name = _find_sheet(sheets, _SHEET_RAW)
    if not sheet_name:
        # Fallback for exports such as "模板加价规则导出" where sheet title differs.
        sheet_name = _find_sheet_by_columns(
            sheets,
            (
                "品项编码",
                "品项名称",
                "品项类别",
                "订货单位",
                "生效状态",
                "加价前单价",
                "加价后单价",
            ),
            min_match=5,
        )
    if not sheet_name:
        return []
    df = sheets[sheet_name]
    records = []
    for _, row in df.iterrows():
        name = str(row.get("品项名称", "")).strip()
        if not name:
            continue
        records.append(
            {
                "code": str(row.get("品项编码", "")).strip(),
                "name": name,
                "category": str(row.get("品项类别", "")).strip(),
                "item_type": str(row.get("品项类型", "普通")).strip(),
                "unit": str(row.get("订货单位", "")).strip(),
                "unit_amount": _to_num(row.get("单位量")),
                "base_price": _to_num(row.get("加价前单价")),
                "final_price": _to_num(row.get("加价后单价")),
                "status": _map_status(str(row.get("生效状态", "已生效")).strip()),
                "synced_from_excel": True,
            }
        )
    return records


def _parse_item_export_materials(sheets: dict[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    sheet_name = _find_sheet(sheets, "品项导出", "品项导出(导入模版格式)")
    if not sheet_name:
        sheet_name = _find_sheet_by_columns(
            sheets,
            ("品项编码", "品项名称", "库存单位", "消耗单位数量值"),
            min_match=3,
        )
    if not sheet_name:
        return {}

    df = sheets[sheet_name]
    out: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        code = _norm_text(row.get("品项编码"))
        if not code:
            continue
        name = _norm_text(row.get("品项名称")) or _norm_text(row.get("*品项名称"))
        if not name:
            continue
        unit = _norm_text(row.get("库存单位")) or _norm_text(row.get("*库存单位"))
        unit_amount = _to_num(row.get("消耗单位数量值"))
        if unit_amount is None:
            unit_amount = _to_num(row.get("*消耗单位换算值"))
        if unit_amount is None:
            unit_amount = _to_num(row.get("消耗单位换算库存单位"))
        out[code] = {
            "code": code,
            "name": name,
            "category": _norm_text(row.get("品项类别")) or _norm_text(row.get("*品项分类编号")),
            "unit": unit,
            # 按需求：单位量 = 消耗单位值
            "unit_amount": unit_amount,
            "status": _status_from_item_enabled(row.get("是否启用")),
            "item_main_image": _norm_text(row.get("品项主图")),
            "item_identifier": _norm_text(row.get("品项标识")),
            "item_spec": _norm_text(row.get("规格")),
            "item_brand": _norm_text(row.get("品牌")),
            "item_mnemonic_code": _norm_text(row.get("助记码")),
            "item_stat_subject": _norm_text(row.get("统计科目")),
            "item_barcode": _norm_text(row.get("条形码")),
            "item_order_barcode": _norm_text(row.get("订货条形码")),
            "item_management_type": _norm_text(row.get("管理类型")),
            "item_shelf_life_unit": _norm_text(row.get("保质期单位")),
            "item_shelf_life": _to_num(row.get("保质期")),
            "item_origin": _norm_text(row.get("产地")),
            "item_storage_method": _norm_text(row.get("存储方式")),
            "item_thaw_duration": _norm_text(row.get("解冻时长")),
            "item_tax_rate": _norm_text(row.get("税率")),
            "item_purchase_unit": _norm_text(row.get("采购单位")),
            "item_purchase_unit_qty": _to_num(row.get("采购单位数量值")),
            "item_purchase_to_inventory": _to_num(row.get("采购单位换算库存单位")),
            "item_order_unit": _norm_text(row.get("订货单位")),
            "item_order_unit_qty": _to_num(row.get("订货单位数量值")),
            "item_order_to_inventory": _to_num(row.get("订货单位换算库存单位")),
            "item_consume_unit": _norm_text(row.get("消耗单位")),
            "item_consume_unit_qty": _to_num(row.get("消耗单位数量值")),
            "item_consume_to_inventory": _to_num(row.get("消耗单位换算库存单位")),
            "item_volume_cm3": _to_num(row.get("品项体积cm³")),
            "item_weight_kg": _to_num(row.get("品项重量Kg")),
            "item_inventory_check_types": _norm_text(row.get("盘点类型")),
            "item_enabled": _to_bool_cn(row.get("是否启用")),
            "item_mall_sort_order": _to_num(row.get("商城下单排序")),
            "item_material_type": _norm_text(row.get("物料类型")),
            "item_is_weighing": _to_bool_cn(row.get("是否称重")),
            "item_tax_category": _norm_text(row.get("税收分类")),
            "item_tax_rate_extra": _norm_text(row.get("税率.1")),
            "item_replenish_strategy": _norm_text(row.get("补货策略")),
            "item_attr_name": _norm_text(row.get("品项属性名")),
            "item_raw_payload": _clean_row_dict(row),
        }
    return out


def _parse_markup_rule_materials(sheets: dict[str, pd.DataFrame]) -> dict[str, dict[str, Any]]:
    sheet_name = _find_sheet(sheets, "模板加价规则导出", _SHEET_RAW)
    if not sheet_name:
        sheet_name = _find_sheet_by_columns(
            sheets,
            ("品项编码", "品项名称", "加价前单价", "加价后单价"),
            min_match=3,
        )
    if not sheet_name:
        return {}

    df = sheets[sheet_name]
    out: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        code = _norm_text(row.get("品项编码"))
        if not code:
            continue
        out[code] = {
            "code": code,
            "name": _norm_text(row.get("品项名称")),
            "category": _norm_text(row.get("品项类别")),
            "item_type": _norm_text(row.get("品项类型")),
            "unit": _norm_text(row.get("订货单位")),
            "base_price": _to_num(row.get("加价前单价")),
            "final_price": _to_num(row.get("加价后单价")),
            "status": _map_status(_norm_text(row.get("生效状态")) or "已生效"),
            "markup_template_id": _norm_text(row.get("模板编号")),
            "markup_item_identifier": _norm_text(row.get("品项标识")),
            "markup_mode": _norm_text(row.get("加价方式")),
            "markup_value": _to_num(row.get("加价值")),
            "markup_raw_payload": _clean_row_dict(row),
        }
    return out


def _merge_two_part_materials(
    item_sheets: dict[str, pd.DataFrame],
    markup_sheets: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    items_map = _parse_item_export_materials(item_sheets)
    rules_map = _parse_markup_rule_materials(markup_sheets)

    records: list[dict[str, Any]] = []
    # 以品项表为主：只遍历品项表中的编码；加价规则按同编码补充。
    for code, item in items_map.items():
        rule = rules_map.get(code, {})
        name = _norm_text(item.get("name")) or _norm_text(rule.get("name"))
        if not name:
            continue
        # 按需求映射：
        # - 单位量 = 消耗单位值（来自品项）
        # - 单位 = 库存单位（来自品项）
        # - 成本 = 加价前单价（来自加价规则）
        # - 单价 = 加价后单价（来自加价规则）
        record = {
            "code": code,
            "name": name,
            "category": _norm_text(item.get("category")) or _norm_text(rule.get("category")),
            "item_type": _norm_text(rule.get("item_type")) or "普通",
            "unit": _norm_text(item.get("unit")) or _norm_text(rule.get("unit")),
            "unit_amount": _to_num(item.get("unit_amount")),
            # 允许没有价格：规则缺失或空值时不阻塞同步
            "base_price": _to_num(rule.get("base_price")),
            "final_price": _to_num(rule.get("final_price")),
            "status": _norm_text(rule.get("status")) or _norm_text(item.get("status")) or "上线",
            "item_main_image": item.get("item_main_image"),
            "item_identifier": item.get("item_identifier"),
            "item_spec": item.get("item_spec"),
            "item_brand": item.get("item_brand"),
            "item_mnemonic_code": item.get("item_mnemonic_code"),
            "item_stat_subject": item.get("item_stat_subject"),
            "item_barcode": item.get("item_barcode"),
            "item_order_barcode": item.get("item_order_barcode"),
            "item_management_type": item.get("item_management_type"),
            "item_shelf_life_unit": item.get("item_shelf_life_unit"),
            "item_shelf_life": item.get("item_shelf_life"),
            "item_origin": item.get("item_origin"),
            "item_storage_method": item.get("item_storage_method"),
            "item_thaw_duration": item.get("item_thaw_duration"),
            "item_tax_rate": item.get("item_tax_rate"),
            "item_purchase_unit": item.get("item_purchase_unit"),
            "item_purchase_unit_qty": item.get("item_purchase_unit_qty"),
            "item_purchase_to_inventory": item.get("item_purchase_to_inventory"),
            "item_order_unit": item.get("item_order_unit"),
            "item_order_unit_qty": item.get("item_order_unit_qty"),
            "item_order_to_inventory": item.get("item_order_to_inventory"),
            "item_consume_unit": item.get("item_consume_unit"),
            "item_consume_unit_qty": item.get("item_consume_unit_qty"),
            "item_consume_to_inventory": item.get("item_consume_to_inventory"),
            "item_volume_cm3": item.get("item_volume_cm3"),
            "item_weight_kg": item.get("item_weight_kg"),
            "item_inventory_check_types": item.get("item_inventory_check_types"),
            "item_enabled": item.get("item_enabled"),
            "item_mall_sort_order": item.get("item_mall_sort_order"),
            "item_material_type": item.get("item_material_type"),
            "item_is_weighing": item.get("item_is_weighing"),
            "item_tax_category": item.get("item_tax_category"),
            "item_tax_rate_extra": item.get("item_tax_rate_extra"),
            "item_replenish_strategy": item.get("item_replenish_strategy"),
            "item_attr_name": item.get("item_attr_name"),
            "item_raw_payload": item.get("item_raw_payload"),
            "markup_template_id": rule.get("markup_template_id"),
            "markup_item_identifier": rule.get("markup_item_identifier"),
            "markup_mode": rule.get("markup_mode"),
            "markup_value": rule.get("markup_value"),
            "markup_raw_payload": rule.get("markup_raw_payload"),
            "synced_from_excel": True,
        }
        records.append(record)
    return records


def preview_sync_raw_materials(
    sheets: dict[str, pd.DataFrame],
    client: MpcSupabaseClient,
) -> list[dict[str, Any]]:
    excel_records = _merge_two_part_materials(sheets, sheets)
    if not excel_records:
        excel_records = _parse_raw_materials(sheets)
    existing = client.list_raw_materials()
    existing_code_map = {_norm_text(r.get("code")): r for r in existing if _norm_text(r.get("code"))}
    existing_name_map = {_norm_text(r.get("name")): r for r in existing if _norm_text(r.get("name"))}
    diffs = []
    for rec in excel_records:
        name = rec["name"]
        code_key = _norm_text(rec.get("code"))
        old = existing_code_map.get(code_key) if code_key else None
        if old is None:
            old = existing_name_map.get(_norm_text(name))
        if old is None:
            diffs.append({"name": name, "action": "insert", "fields_changed": list(rec.keys())})
            continue
        changed = [k for k in _RAW_COMPARE_FIELDS if _raw_field_value(rec, k) != _raw_field_value(old, k)]
        if changed:
            diffs.append({"name": name, "action": "update", "fields_changed": changed})
        else:
            diffs.append({"name": name, "action": "skip", "fields_changed": []})
    return diffs


def execute_sync_raw_materials(
    sheets: dict[str, pd.DataFrame],
    client: MpcSupabaseClient,
    resolve_conflicts: str = "skip",
) -> SyncResult:
    diffs = preview_sync_raw_materials(sheets, client)
    excel_records = _merge_two_part_materials(sheets, sheets)
    if not excel_records:
        excel_records = _parse_raw_materials(sheets)
    records_by_name = {r["name"]: r for r in excel_records}
    result = SyncResult()
    to_upsert = []
    for d in diffs:
        if d["action"] in ("insert", "update"):
            rec = records_by_name[d["name"]]
            to_upsert.append(rec)
    if to_upsert:
        client.upsert_raw_materials(to_upsert)
    result.inserts = sum(1 for d in diffs if d["action"] == "insert")
    result.updates = sum(1 for d in diffs if d["action"] == "update")
    return result


def preview_sync_raw_materials_two_files(
    item_sheets: dict[str, pd.DataFrame],
    markup_sheets: dict[str, pd.DataFrame],
    client: MpcSupabaseClient,
) -> list[dict[str, Any]]:
    excel_records = _merge_two_part_materials(item_sheets, markup_sheets)
    existing = client.list_raw_materials()
    existing_code_map = {_norm_text(r.get("code")): r for r in existing if _norm_text(r.get("code"))}
    diffs = []
    for rec in excel_records:
        name = rec["name"]
        code_key = _norm_text(rec.get("code"))
        old = existing_code_map.get(code_key) if code_key else None
        if old is None:
            diffs.append(
                {"code": code_key, "name": name, "action": "insert", "fields_changed": list(rec.keys())}
            )
            continue
        changed = [k for k in _RAW_COMPARE_FIELDS if _raw_field_value(rec, k) != _raw_field_value(old, k)]
        if changed:
            diffs.append({"code": code_key, "name": name, "action": "update", "fields_changed": changed})
        else:
            diffs.append({"code": code_key, "name": name, "action": "skip", "fields_changed": []})
    return diffs


def execute_sync_raw_materials_two_files(
    item_sheets: dict[str, pd.DataFrame],
    markup_sheets: dict[str, pd.DataFrame],
    client: MpcSupabaseClient,
    resolve_conflicts: str = "skip",
) -> SyncResult:
    diffs = preview_sync_raw_materials_two_files(item_sheets, markup_sheets, client)
    excel_records = _merge_two_part_materials(item_sheets, markup_sheets)
    records_by_code = {_norm_text(r.get("code")): r for r in excel_records if _norm_text(r.get("code"))}
    result = SyncResult()
    to_upsert = []
    for d in diffs:
        if d["action"] in ("insert", "update"):
            rec = records_by_code[d["code"]]
            to_upsert.append(rec)
    if to_upsert:
        client.upsert_raw_materials(to_upsert)
    result.inserts = sum(1 for d in diffs if d["action"] == "insert")
    result.updates = sum(1 for d in diffs if d["action"] == "update")
    return result


# ---------------------------------------------------------------------------
# Products & Recipes Sync
# ---------------------------------------------------------------------------


def _parse_products_recipes(sheets: dict[str, pd.DataFrame]) -> list[dict]:
    sheet_name = _find_sheet(sheets, _SHEET_RECIPE)
    if not sheet_name:
        return []
    df = sheets[sheet_name]
    products: dict[str, dict] = {}
    for _, row in df.iterrows():
        prod_name = str(row.get("品名", "")).strip()
        if not prod_name:
            continue
        if prod_name not in products:
            products[prod_name] = {
                "product_name": prod_name,
                "category": str(row.get("品类", "")).strip(),
                "ingredients": [],
            }
        ingredient_name = str(row.get("配料", "")).strip()
        if ingredient_name:
            products[prod_name]["ingredients"].append(
                {
                    "name": ingredient_name,
                    "quantity": _to_num(row.get("用量")),
                    "unit_cost": _to_num(row.get("单位成本")),
                    "store_unit_cost": _to_num(row.get("门店单位成本")),
                }
            )
    return list(products.values())


def preview_sync_products_recipes(
    sheets: dict[str, pd.DataFrame],
    client: MpcSupabaseClient,
) -> list[dict[str, Any]]:
    excel_products = _parse_products_recipes(sheets)
    existing = client.list_products()
    existing_names = {p["name"] for p in existing if p.get("name")}
    diffs = []
    for prod in excel_products:
        name = prod["product_name"]
        if name not in existing_names:
            diffs.append({"name": name, "action": "insert", "type": "product"})
        else:
            diffs.append({"name": name, "action": "skip", "type": "product"})
    return diffs


def execute_sync_products_recipes(
    sheets: dict[str, pd.DataFrame],
    client: MpcSupabaseClient,
    resolve_conflicts: str = "skip",
) -> SyncResult:
    diffs = preview_sync_products_recipes(sheets, client)
    result = SyncResult()
    excel_products = _parse_products_recipes(sheets)
    for d in diffs:
        if d["action"] != "insert":
            continue
        prod_data = next(p for p in excel_products if p["product_name"] == d["name"])
        new_prod = client.create_product(
            {
                "name": prod_data["product_name"],
                "category": prod_data.get("category"),
                "is_final_product": True,
            }
        )
        result.inserts += 1
        recipes_data = []
        for i, ing in enumerate(prod_data.get("ingredients", [])):
            recipes_data.append(
                {
                    "product_id": new_prod["id"],
                    "ingredient_source": "raw",
                    "raw_material_id": None,
                    "quantity": ing["quantity"] or 0,
                    "unit_cost": ing["unit_cost"],
                    "store_unit_cost": ing["store_unit_cost"],
                    "sort_order": i,
                }
            )
        if recipes_data:
            client.set_recipes(new_prod["id"], recipes_data)
    return result


# ---------------------------------------------------------------------------
# Serving Specs Sync (stub)
# ---------------------------------------------------------------------------


def preview_sync_serving_specs(
    sheets: dict[str, pd.DataFrame],
    client: MpcSupabaseClient,
) -> list[dict]:
    return []


def execute_sync_serving_specs(
    sheets: dict[str, pd.DataFrame],
    client: MpcSupabaseClient,
    resolve_conflicts: str = "skip",
) -> SyncResult:
    return SyncResult()
