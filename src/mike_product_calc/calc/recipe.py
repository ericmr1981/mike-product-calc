"""
Recipe breakdown module — shared by Tab2 (F-003) and Tab4 (原料价格模拟器).

Provides:
- get_brand_cost_map / get_brand_spec_map — from 总原料成本表
- get_semi_product_recipes — from 半成品配方表_*
- build_recipe_table — full hierarchical recipe table for a SKU
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class RecipeRow:
    item: str
    usage_qty: float
    usage_unit: str
    cost: float
    spec: str
    store_price: float
    brand_cost: float
    profit_rate: float
    level: int  # 0=direct ingredient, 1=semi-product, 2=sub-ingredient
    is_semi: bool


def _find_col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    for c in candidates:
        for col in df.columns:
            if c in col:
                return col
    return None


def get_brand_cost_map(sheets: Dict[str, pd.DataFrame]) -> Dict[str, float]:
    """Read brand cost from 总原料成本表. Returns {material_name: brand_cost}."""
    df = sheets.get("总原料成本表")
    if df is None:
        return {}
    name_col = _find_col(df, "品项名称")
    cost_col = _find_col(df, "原料价格", "单价", "品牌成本")
    if not name_col or not cost_col:
        return {}
    out = {}
    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip()
        if not name:
            continue
        try:
            out[name] = float(row[cost_col])
        except (TypeError, ValueError):
            pass
    return out


def get_brand_spec_map(sheets: Dict[str, pd.DataFrame]) -> Dict[str, str]:
    """Read spec/unit from 总原料成本表. Returns {material_name: spec_string}."""
    df = sheets.get("总原料成本表")
    if df is None:
        return {}
    name_col = _find_col(df, "品项名称")
    spec_col = _find_col(df, "规格", "单位量", "单位数量")
    if not name_col or not spec_col:
        return {}
    out = {}
    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip()
        if not name:
            continue
        spec = str(row.get(spec_col, "")).strip()
        if spec and spec != "nan":
            out[name] = spec
    return out


def get_semi_product_recipes(sheets: Dict[str, pd.DataFrame]) -> Dict[str, List[dict]]:
    """Read semi-product recipes from 半成品配方表_*.
    Returns {semi_product_name: [{item, usage_qty, usage_unit}, ...]}.
    """
    recipes: Dict[str, List[dict]] = {}
    for sheet_name in sheets:
        if "半成品配方表" not in sheet_name:
            continue
        df = sheets[sheet_name]
        # Try to find relevant columns
        semi_col = _find_col(df, "品名", "半成品")
        ing_col = _find_col(df, "配料", "原料")
        qty_col = _find_col(df, "用量")
        unit_col = _find_col(df, "单位")

        if not semi_col or not ing_col or not qty_col:
            continue

        for _, row in df.iterrows():
            semi = str(row.get(semi_col, "")).strip()
            ing = str(row.get(ing_col, "")).strip()
            if not semi or not ing:
                continue
            try:
                qty = float(row[qty_col])
            except (TypeError, ValueError):
                qty = 0.0
            unit = str(row.get(unit_col, "")).strip() if unit_col else ""
            if semi not in recipes:
                recipes[semi] = []
            recipes[semi].append({
                "item": ing,
                "usage_qty": qty,
                "usage_unit": unit,
            })
    return recipes


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_recipe_table(
    sheets: Dict[str, pd.DataFrame],
    *,
    product_key: str,
    basis: str = "store",
) -> pd.DataFrame:
    """Build hierarchical recipe table for a SKU.

    Columns: item | usage_qty | cost | spec | store_price | brand_cost | profit_rate
    """
    from mike_product_calc.calc.profit import sku_cost_breakdown

    # Get cost breakdown to find main materials
    breakdown = sku_cost_breakdown(sheets, product_key=product_key, basis=basis)
    if breakdown.empty:
        return pd.DataFrame()

    brand_cost_map = get_brand_cost_map(sheets)
    spec_map = get_brand_spec_map(sheets)
    semi_recipes = get_semi_product_recipes(sheets)

    rows: List[RecipeRow] = []
    for _, b_row in breakdown.iterrows():
        item = b_row["item"]
        bucket = b_row["bucket"]
        cost_val = _to_float(b_row["cost"]) or 0.0

        # Look up usage qty from 产品出品表
        usage_qty = 0.0
        usage_unit = ""
        for sname in sheets:
            if "产品出品表" in sname:
                df = sheets[sname]
                # Build product keys
                pk = df.apply(lambda r: "|".join(
                    str(r.get(c, "")).strip()
                    for c in ["品类", "品名", "规格"] if c in df.columns
                ), axis=1)
                mask = pk == product_key
                if mask.any():
                    match = df[mask].iloc[0]
                    # Determine if this row matches current item
                    main_mat = str(match.get("主原料", "")).strip()
                    ing = str(match.get("配料", "")).strip()
                    row_item = ing or main_mat
                    if row_item == item:
                        usage_qty = _to_float(match.get("用量")) or 0.0
                        usage_unit = str(match.get("单位", "")).strip() or ""
                    break

        brand_cost = brand_cost_map.get(item, 0.0)
        spec = spec_map.get(item, "")

        # Check if this item is a semi-product with sub-recipes
        is_semi = item in semi_recipes

        if not is_semi:
            # Direct ingredient
            store_price = brand_cost if brand_cost > 0 else cost_val
            spec_parsed = _parse_spec(spec)
            if spec_parsed and spec_parsed > 0 and usage_qty > 0:
                calculated_cost = usage_qty * (store_price / spec_parsed)
            else:
                calculated_cost = cost_val

            profit_rate = _calc_profit_rate(store_price, brand_cost)

            rows.append(RecipeRow(
                item=item,
                usage_qty=usage_qty,
                usage_unit=usage_unit,
                cost=round(calculated_cost, 4),
                spec=spec,
                store_price=store_price,
                brand_cost=round(brand_cost, 4),
                profit_rate=round(profit_rate, 4),
                level=0,
                is_semi=False,
            ))
        else:
            # Semi-product: show the semi row + sub-ingredients
            sub_items = semi_recipes[item]
            semi_cost = 0.0
            sub_rows: List[RecipeRow] = []

            for sub in sub_items:
                sub_name = sub["item"]
                sub_qty = sub["usage_qty"]
                sub_unit = sub.get("usage_unit", "")
                sub_brand_cost = brand_cost_map.get(sub_name, 0.0)
                sub_spec = spec_map.get(sub_name, "")

                sub_store_price = sub_brand_cost if sub_brand_cost > 0 else 0.0
                sub_spec_parsed = _parse_spec(sub_spec)
                sub_cost = 0.0
                if sub_spec_parsed and sub_spec_parsed > 0 and sub_qty > 0:
                    sub_cost = sub_qty * (sub_store_price / sub_spec_parsed)

                sub_profit_rate = _calc_profit_rate(sub_store_price, sub_brand_cost)
                semi_cost += sub_cost

                sub_rows.append(RecipeRow(
                    item=sub_name,
                    usage_qty=sub_qty,
                    usage_unit=sub_unit,
                    cost=round(sub_cost, 4),
                    spec=sub_spec,
                    store_price=sub_store_price,
                    brand_cost=round(sub_brand_cost, 4),
                    profit_rate=round(sub_profit_rate, 4),
                    level=2,
                    is_semi=False,
                ))

            # Main semi row
            rows.append(RecipeRow(
                item=item,
                usage_qty=0,
                usage_unit="",
                cost=round(semi_cost, 4),
                spec="",
                store_price=0,
                brand_cost=0,
                profit_rate=0,
                level=1,
                is_semi=True,
            ))
            rows.extend(sub_rows)

    # Build DataFrame
    data = []
    for r in rows:
        data.append({
            "item": r.item,
            "usage_qty": r.usage_qty,
            "usage_unit": r.usage_unit,
            "cost": r.cost,
            "spec": r.spec,
            "store_price": r.store_price,
            "brand_cost": r.brand_cost,
            "profit_rate": r.profit_rate,
            "level": r.level,
            "is_semi": r.is_semi,
        })
    df = pd.DataFrame(data)
    return df


def _parse_spec(spec_str: str) -> Optional[float]:
    """Parse spec like '1 kg', '0.5 L', '500 g' → numeric value in base unit."""
    if not spec_str or spec_str in ("—", "-", "nan"):
        return None
    import re
    m = re.match(r"([\d.]+)", spec_str.strip())
    return float(m.group(1)) if m else None


def _calc_profit_rate(store_price: float, brand_cost: float) -> float:
    """利润率 = (门店价格 - 品牌成本) / 品牌成本"""
    if brand_cost and brand_cost > 0:
        return (store_price - brand_cost) / brand_cost
    return 0.0
