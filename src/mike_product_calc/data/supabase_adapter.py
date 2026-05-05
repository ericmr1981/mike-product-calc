"""Build pandas DataFrames from Supabase data, matching Excel sheet formats.

Allows existing calc modules (profit, recipe) to work with Supabase data
without modification.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from mike_product_calc.data.supabase_client import MpcSupabaseClient


def build_sheets(client: MpcSupabaseClient) -> dict[str, pd.DataFrame]:
    """Build a dict of DataFrames matching Excel sheet names and columns.

    Returns: {sheet_name: DataFrame} compatible with calc modules.
    """
    sheets: dict[str, pd.DataFrame] = {}

    # ── 总原料成本表 ──
    raw_materials = client.list_raw_materials()
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

    # ── 产品配方表_Gelato ──
    products = client.list_products()
    recipe_rows = []
    for prod in products:
        recipes = client.list_recipes(prod["id"])
        # recipes returns raw_material_id as expanded dict or id string
        for r in recipes:
            ing_name = ""
            ing_source = r.get("ingredient_source", "raw")
            if ing_source == "raw":
                rm = r.get("raw_material_id")
                if isinstance(rm, dict):
                    ing_name = rm.get("name", "")
                elif isinstance(rm, str):
                    ing_name = str(rm)
            else:
                rp = r.get("ref_product_id")
                if isinstance(rp, dict):
                    ing_name = rp.get("name", "")
                elif isinstance(rp, str):
                    ing_name = str(rp)
            if not ing_name:
                continue
            recipe_rows.append({
                "品类": prod.get("category", ""),
                "品名": f"{prod['name']} {prod.get('version','')}".strip(),
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
        specs = client.list_serving_specs(prod["id"])
        for sp in specs:
            # Main material row
            mm = sp.get("main_material_id")
            mm_name = ""
            if isinstance(mm, dict):
                v = mm.get("version", "")
                mm_name = f"{mm['name']} {v}".strip() if v else mm["name"]
            elif isinstance(mm, str):
                mm_name = str(mm)
            if mm_name:
                serving_rows.append({
                    "品类": prod.get("category", ""),
                    "品名": prod["name"],
                    "规格": sp["spec_name"],
                    "主原料": mm_name,
                    "配料": "",
                    "用量": sp.get("quantity", 0),
                })
            # Topping rows
            for t in sp.get("serving_spec_toppings", []):
                t_mat = t.get("material_id")
                t_name = ""
                if isinstance(t_mat, dict):
                    t_name = t_mat.get("name", "")
                elif isinstance(t_mat, str):
                    t_name = str(t_mat)
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

    # ── 产品毛利表_Gelato (computed from serving + raw material prices) ──
    # Build a basic version with serving specs and their costs
    profit_rows = []
    for prod in products:
        if not prod.get("is_final_product", False):
            continue
        specs = client.list_serving_specs(prod["id"])
        for sp in specs:
            mm = sp.get("main_material_id")
            cost = 0
            if isinstance(mm, dict):
                cost = float(mm.get("final_price") or 0) * float(sp.get("quantity", 0))
            profit_rows.append({
                "品类": prod.get("category", ""),
                "品名": prod["name"],
                "规格": sp["spec_name"],
                "状态": prod.get("status", "上线"),
                "成本": _f(cost),
                "定价": 0,
                "毛利率": "",
            })
    if profit_rows:
        sheets["产品毛利表_Gelato"] = pd.DataFrame(profit_rows)

    return sheets


def _f(val: Any) -> float | None:
    """Convert value to float or None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
