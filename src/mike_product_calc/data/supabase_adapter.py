"""Build pandas DataFrames from Supabase data, matching Excel sheet formats.

All existing calc modules (profit, recipe, prep_engine) work with
`dict[str, pd.DataFrame]`. This adapter builds that dict from Supabase,
so calc modules work unchanged.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from mike_product_calc.data.supabase_client import MpcSupabaseClient


def build_sheets(client: MpcSupabaseClient) -> dict[str, pd.DataFrame]:
    """Build a dict of DataFrames matching Excel sheet names and columns.

    Returns: {sheet_name: DataFrame} compatible with calc modules.
    Empty dict if Supabase has no data.
    """
    sheets: dict[str, pd.DataFrame] = {}

    raw_materials = _safe_call(client.list_raw_materials) or []
    products = _safe_call(client.list_products) or []
    if not products:
        return sheets

    # ── 总原料成本表 ──
    if raw_materials:
        rows = []
        for m in raw_materials:
            rows.append({
                "品项编码": m.get("code", ""),
                "品项名称": m.get("name", ""),
                "品项类别": m.get("category", ""),
                "品项类型": m.get("item_type", "普通"),
                "订货单位": m.get("unit", ""),
                "加价前单价": _f(m.get("base_price")),
                "加价后单价": _f(m.get("final_price")),
                "生效状态": m.get("status", "已生效"),
                "单位量": _f(m.get("unit_amount")) if m.get("unit_amount") else None,
            })
        sheets["总原料成本表"] = pd.DataFrame(rows)

    # ── Batch fetch all recipes & specs (3 requests total instead of 50+) ──
    all_recipes = _safe_call(client.list_all_recipes) or []
    _recipes_by_product: dict[str, list[dict]] = {}
    for r in all_recipes:
        pid = r.get("product_id")
        if pid:
            _recipes_by_product.setdefault(pid, []).append(r)

    all_specs = _safe_call(client.list_all_serving_specs) or []
    _specs_by_product: dict[str, list[dict]] = {}
    for sp in all_specs:
        pid = sp.get("product_id")
        if pid:
            _specs_by_product.setdefault(pid, []).append(sp)

    # ── 产品配方表_Gelato ──
    recipe_rows = []
    for prod in products:
        for r in _recipes_by_product.get(prod["id"], []):
            ing_name = _get_ingredient_name(r)
            if not ing_name:
                continue
            recipe_rows.append({
                "品类": prod.get("category", ""),
                "品名": _full_name(prod),
                "配料": ing_name,
                "用量": r.get("quantity", 0),
            })
    if recipe_rows:
        sheets["产品配方表_Gelato"] = pd.DataFrame(recipe_rows)

    # ── 产品出品表_Gelato ──
    serving_rows = []
    for prod in products:
        if not prod.get("is_final_product", False):
            continue
        for sp in _specs_by_product.get(prod["id"], []):
            mm = sp.get("main_material_id")
            mm_name = _get_prod_name(mm) if isinstance(mm, dict) else str(mm or "")
            if mm_name:
                serving_rows.append({
                    "品类": prod.get("category", ""),
                    "品名": prod["name"],
                    "规格": sp["spec_name"],
                    "主原料": mm_name,
                    "配料": "",
                    "用量": sp.get("quantity", 0),
                })
            for t in sp.get("serving_spec_toppings", []):
                t_name = _get_mat_name(t.get("material_id"))
                if t_name:
                    serving_rows.append({
                        "品类": prod.get("category", ""),
                        "品名": prod["name"],
                        "规格": sp["spec_name"],
                        "主原料": "",
                        "配料": t_name,
                        "用量": t.get("quantity", 1),
                    })
    if serving_rows:
        sheets["产品出品表_Gelato"] = pd.DataFrame(serving_rows)

    # ── 产品毛利表_Gelato (computed) ──
    profit_rows = []
    for prod in products:
        if not prod.get("is_final_product", False):
            continue
        for sp in _specs_by_product.get(prod["id"], []):
            mm = sp.get("main_material_id")
            cost = 0.0
            if isinstance(mm, dict):
                cost = float(mm.get("final_price") or 0) * float(sp.get("quantity", 0))
            profit_rows.append({
                "品类": prod.get("category", ""),
                "品名": prod["name"],
                "规格": sp["spec_name"],
                "状态": prod.get("status", "上线"),
                "成本": _f(cost),
                "门店成本": _f(cost),
                "定价": 0.0,
                "门店定价": 0.0,
                "毛利率": "",
                "门店毛利率": "",
            })
    if profit_rows:
        sheets["产品毛利表_Gelato"] = pd.DataFrame(profit_rows)

    # ── 产品成本计算表_Gelato (computed) ──
    cost_rows = []
    for prod in products:
        full_name = _full_name(prod)
        serving_qty = 0
        for sp in _specs_by_product.get(prod["id"], []):
            mm = sp.get("main_material_id")
            if isinstance(mm, dict) and _full_name(mm) == full_name:
                serving_qty += float(sp.get("quantity", 0))
        cost_rows.append({
            "品类": prod.get("category", ""),
            "品名": full_name,
            "100克成本": "",
            "制作类型": prod.get("production_type", ""),
            "规格": str(int(serving_qty)) if serving_qty else "",
            "状态": prod.get("status", "上线"),
            "成本": "",
            "单位成本": "",
            "门店成本": "",
            "门店单位成本": "",
        })
    if cost_rows:
        sheets["产品成本计算表_Gelato"] = pd.DataFrame(cost_rows)

    return sheets


def _full_name(p: dict) -> str:
    """Return full name with version e.g. '木姜子甜橙 2.0'."""
    v = p.get("version", "")
    return f"{p['name']} {v}".strip() if v else p["name"]


def _get_ingredient_name(r: dict) -> str:
    """Extract ingredient name from a recipe record (may contain joined object)."""
    source = r.get("ingredient_source", "raw")
    if source == "raw":
        return _get_mat_name(r.get("raw_material_id"))
    return _get_prod_name(r.get("ref_product_id"))


def _get_mat_name(val: Any) -> str:
    """Extract material name from joined object or raw string."""
    if isinstance(val, dict):
        return val.get("name", "")
    return str(val or "")


def _get_prod_name(val: Any) -> str:
    """Extract product full name from joined object or raw string."""
    if isinstance(val, dict):
        v = val.get("version", "")
        return f"{val['name']} {v}".strip() if v else val["name"]
    return str(val or "")


def _f(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return round(float(val), 4)
    except (ValueError, TypeError):
        return None


def _safe_call(fn, default=None):
    """Call a function, return default on exception (connection issues)."""
    try:
        return fn()
    except Exception:
        return default
