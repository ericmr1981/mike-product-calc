"""
Recipe breakdown module — shared by Tab2 (F-003) and Tab4 (原料价格模拟器).

Provides:
- get_brand_cost_map / get_brand_spec_map — from 总原料成本表
- get_semi_product_recipes — from 半成品配方表_*
- build_recipe_table — full hierarchical recipe table for a SKU
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

# Level constants for recipe hierarchy
LEVEL_DIRECT = 0  # direct ingredient
LEVEL_SEMI = 1    # semi-product (rolled-up parent row)
LEVEL_SUB = 2     # sub-ingredient of a semi-product


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
    """Read 加价前单价 (brand cost) from 总原料成本表.
    Returns {material_name: brand_cost}.
    """
    df = sheets.get("总原料成本表")
    if df is None:
        return {}
    name_col = _find_col(df, "品项名称")
    cost_col = _find_col(df, "加价前单价")
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


def get_store_price_map(sheets: Dict[str, pd.DataFrame]) -> Dict[str, float]:
    """Read 加价后单价 (store purchase price) from 总原料成本表.
    Returns {material_name: store_price}.
    """
    df = sheets.get("总原料成本表")
    if df is None:
        return {}
    name_col = _find_col(df, "品项名称")
    price_col = _find_col(df, "加价后单价")
    if not name_col or not price_col:
        return {}
    out = {}
    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip()
        if not name:
            continue
        try:
            out[name] = float(row[price_col])
        except (TypeError, ValueError):
            pass
    return out


def get_brand_spec_map(sheets: Dict[str, pd.DataFrame]) -> Dict[str, str]:
    """Read 单位量 (spec/unit qty) from 总原料成本表.
    Returns {material_name: spec_string}.
    """
    df = sheets.get("总原料成本表")
    if df is None:
        return {}
    name_col = _find_col(df, "品项名称")
    spec_col = _find_col(df, "单位量")
    if not name_col or not spec_col:
        return {}
    out = {}
    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip()
        if not name:
            continue
        spec = str(row.get(spec_col, ""))
        if spec and spec != "nan":
            out[name] = spec
    return out


def get_semi_product_recipes(sheets: Dict[str, pd.DataFrame]) -> Dict[str, List[dict]]:
    """Read semi-product recipes from 产品配方表_*.
    Returns {semi_product_name: [{item, usage_qty, usage_unit, unit_cost, total_cost}, ...]}.
    """
    recipes: Dict[str, List[dict]] = {}
    for sheet_name in sheets:
        if "产品配方表" not in sheet_name:
            continue
        df = sheets[sheet_name]
        semi_col = _find_col(df, "品名")
        ing_col = _find_col(df, "配料")
        qty_col = _find_col(df, "用量")
        unit_cost_col = _find_col(df, "单位成本")

        if not semi_col or not ing_col or not qty_col:
            continue

        for _, row in df.iterrows():
            semi = str(row.get(semi_col, "")).strip()
            ing = str(row.get(ing_col, "")).strip()
            if not semi or not ing or semi.lower() == "nan" or ing.lower() == "nan":
                continue
            try:
                qty = float(row[qty_col])
            except (TypeError, ValueError):
                qty = 0.0
            uc = _to_float(row.get(unit_cost_col)) if unit_cost_col else None
            if uc is None or math.isnan(uc):
                uc = 0.0
            tc = round(uc * qty, 4)
            if semi not in recipes:
                recipes[semi] = []
            recipes[semi].append({
                "item": ing,
                "usage_qty": qty,
                "usage_unit": "",
                "unit_cost": uc,
                "total_cost": tc,
            })
    return recipes


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _lookup_usage_map(
    sheets: Dict[str, pd.DataFrame],
    product_key: str,
) -> Dict[str, tuple[float, str]]:
    """Build {item_name: (usage_qty, usage_unit)} from ALL rows matching product_key in 产品出品表."""
    usage_map: Dict[str, tuple[float, str]] = {}
    for sname in sheets:
        if "产品出品表" not in sname:
            continue
        df = sheets[sname]
        pk = df.apply(lambda r: "|".join(
            str(r.get(c, "")).strip()
            for c in ["品类", "品名", "规格"] if c in df.columns
        ), axis=1)
        mask = pk == product_key
        if not mask.any():
            continue
        # Iterate ALL matching rows — products may have multiple ingredient rows
        for _, match in df[mask].iterrows():
            main_mat = str(match.get("主原料", "")).strip()
            ing = str(match.get("配料", "")).strip()
            item = ing or main_mat
            if not item:
                continue
            qty = _to_float(match.get("用量")) or 0.0
            unit = str(match.get("单位", "")).strip() or ""
            usage_map[item] = (qty, unit)
        break  # only process the first 产品出品表 sheet found
    return usage_map


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
    store_price_map = get_store_price_map(sheets)
    spec_map = get_brand_spec_map(sheets)
    semi_recipes = get_semi_product_recipes(sheets)

    usage_map = _lookup_usage_map(sheets, product_key)

    rows: List[RecipeRow] = []
    for _, b_row in breakdown.iterrows():
        item = b_row["item"]
        cost_val = _to_float(b_row["cost"]) or 0.0

        # Look up usage qty from 产品出品表 via the pre-built map
        usage_qty, usage_unit = usage_map.get(item, (0.0, ""))

        brand_cost = brand_cost_map.get(item, 0.0)
        spec = spec_map.get(item, "")

        # Check if this item is a semi-product with sub-recipes
        is_semi = item in semi_recipes

        if not is_semi:
            # Direct ingredient
            store_price = store_price_map.get(item, brand_cost or cost_val)
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
                level=LEVEL_DIRECT,
                is_semi=False,
            ))
        else:
            # Semi-product: show the semi row + sub-ingredients
            sub_items = semi_recipes[item]

            # Calculate original batch cost from recipe data
            _tc_list: list[float] = []
            for s in sub_items:
                v = s.get("total_cost")
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    _tc_list.append(0.0)
                else:
                    _tc_list.append(float(v))
            original_batch_cost = sum(_tc_list) or 0.0

            # For cost recalculation: store the scaling factor
            # scale = cost_val / original_batch_cost (SKU-level cost per unit of batch cost)
            scale_factor = cost_val / original_batch_cost if original_batch_cost > 0 else 0.0

            semi_cost = 0.0
            sub_rows: List[RecipeRow] = []

            for sub in sub_items:
                sub_name = sub["item"]
                sub_qty = sub["usage_qty"]
                sub_unit = sub.get("usage_unit", "")
                sub_brand_cost = brand_cost_map.get(sub_name, 0.0)
                sub_spec = spec_map.get(sub_name, "")

                # Default store_price = brand_cost
                sub_store_price = store_price_map.get(sub_name, sub_brand_cost or 0.0)
                sub_spec_parsed = _parse_spec(sub_spec)
                sub_sku_cost = 0.0

                if sub_spec_parsed and sub_spec_parsed > 0 and sub_qty > 0:
                    # Cost of this ingredient in one batch of the semi-product
                    sub_cost_in_batch = sub_qty * (sub_store_price / sub_spec_parsed)
                    # Scale to SKU level
                    sub_sku_cost = sub_cost_in_batch * scale_factor

                semi_cost += sub_sku_cost
                sub_profit_rate = _calc_profit_rate(sub_store_price, sub_brand_cost)

                sub_rows.append(RecipeRow(
                    item=sub_name,
                    usage_qty=sub_qty,
                    usage_unit=sub_unit,
                    cost=round(sub_sku_cost, 4),
                    spec=sub_spec,
                    store_price=sub_store_price,
                    brand_cost=round(sub_brand_cost, 4),
                    profit_rate=round(sub_profit_rate, 4),
                    level=LEVEL_SUB,
                    is_semi=False,
                ))

            # Main semi row (summary)
            rows.append(RecipeRow(
                item=item,
                usage_qty=0,
                usage_unit="",
                cost=round(semi_cost, 4),
                spec="",
                store_price=0,
                brand_cost=0,
                profit_rate=0,
                level=LEVEL_SEMI,
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


_UNIT_MAP = {
    "g": 0.001,
    "ml": 0.001,
    "kg": 1.0,
    "l": 1.0,
    "斤": 0.5,
    "个": 1.0,
    "只": 1.0,
}


def _parse_spec(spec_str: str) -> Optional[float]:
    """Parse spec like '1 kg', '0.5 L', '500 g' → numeric value in base unit (kg/L)."""
    if not spec_str or spec_str in ("—", "-", "nan"):
        return None
    m = re.match(r"([\d.]+)\s*(.*)", spec_str.strip())
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2).strip().lower()
    factor = _UNIT_MAP.get(unit, 1.0)
    return value * factor


def _calc_profit_rate(store_price: float, brand_cost: float) -> float:
    """利润率 = (门店价格 - 品牌成本) / 品牌成本"""
    if brand_cost and brand_cost > 0:
        return (store_price - brand_cost) / brand_cost
    return 0.0
