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


# ---------------------------------------------------------------------------
# Raw Materials Sync
# ---------------------------------------------------------------------------


def _parse_raw_materials(sheets: dict[str, pd.DataFrame]) -> list[dict]:
    sheet_name = _find_sheet(sheets, _SHEET_RAW)
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
                "base_price": _to_num(row.get("加价前单价")),
                "final_price": _to_num(row.get("加价后单价")),
                "status": str(row.get("生效状态", "已生效")).strip(),
                "synced_from_excel": True,
            }
        )
    return records


def preview_sync_raw_materials(
    sheets: dict[str, pd.DataFrame],
    client: MpcSupabaseClient,
) -> list[dict[str, Any]]:
    excel_records = _parse_raw_materials(sheets)
    existing = client.list_raw_materials()
    existing_map = {r["name"]: r for r in existing if r.get("name")}
    diffs = []
    for rec in excel_records:
        name = rec["name"]
        if name not in existing_map:
            diffs.append({"name": name, "action": "insert", "fields_changed": list(rec.keys())})
        else:
            old = existing_map[name]
            changed = [
                k
                for k in ("final_price", "base_price", "category", "status")
                if rec.get(k) != old.get(k)
            ]
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
    result = SyncResult()
    to_upsert = []
    for d in diffs:
        if d["action"] in ("insert", "update"):
            rec = next(r for r in _parse_raw_materials(sheets) if r["name"] == d["name"])
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
