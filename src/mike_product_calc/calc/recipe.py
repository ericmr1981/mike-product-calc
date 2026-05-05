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
    Returns {semi_product_name: [{item, usage_qty, unit_cost, total_cost, store_total_cost}, ...]}.
    """
    recipes: Dict[str, List[dict]] = {}
    for sheet_name in sheets:
        if "产品配方表" not in sheet_name:
            continue
        df = sheets[sheet_name]
        semi_col = _find_col(df, "品名")
        ing_col = _find_col(df, "配料")
        qty_col = _find_col(df, "用量")
        factory_total_col = next((c for c in df.columns if c.strip() == "总成本"), None)
        store_total_col = next((c for c in df.columns if c.strip() == "门店总成本"), None)

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
            # Factory total cost (总成本)
            ftc = _to_float(row.get(factory_total_col)) if factory_total_col else None
            if ftc is None or math.isnan(ftc):
                ftc = 0.0
            # Store total cost (门店总成本)
            stc = _to_float(row.get(store_total_col)) if store_total_col else None
            if stc is None or math.isnan(stc):
                stc = 0.0
            if semi not in recipes:
                recipes[semi] = []
            recipes[semi].append({
                "item": ing,
                "usage_qty": qty,
                "usage_unit": "",
                "total_cost": round(ftc, 4),
                "store_total_cost": round(stc, 4),
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
            raw_ing = str(match.get("配料", "")).strip()
            ing = raw_ing if raw_ing and raw_ing.lower() != "nan" else ""
            item = ing or main_mat
            if not item or item.lower() == "nan":
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

    Calculation rules by type and basis:
    - 1级直接原料: store_price=总原料成本表.加价后单价, brand_cost=总原料成本表.加价前单价
      - 成本(store)=store_price×用量/规格, 成本(factory)=brand_cost×用量/规格
    - 1级半成品: store_price=产品成本计算表.门店成本, brand_cost=产品成本计算表.成本
      - 成本(store)=门店价格/规格×用量, 成本(factory)=品牌成本/规格×用量
    - 2级配料: store_price=总原料成本表.加价后单价, brand_cost=总原料成本表.加价前单价
      - 成本(store)=产品配方表.门店单位成本×用量
      - 成本(factory)=产品配方表.单位成本×用量
    """
    from mike_product_calc.calc.profit import sku_cost_breakdown

    # ── Extract category from product_key (e.g. "Gelato" from "Gelato|xxx|xxx") ──
    category = product_key.split("|")[0] if "|" in product_key else ""

    # ── Read semi-product data from 产品成本计算表 ──
    semi_store_price: dict[str, float] = {}
    semi_brand_cost: dict[str, float] = {}
    semi_spec: dict[str, str] = {}
    for sname in sheets:
        if "产品成本计算表" not in sname:
            continue
        if category and category.lower() not in sname.lower():
            continue
        df = sheets[sname]
        name_col = _find_col(df, "品名")
        # Use exact match for cost columns to avoid matching "100克成本"
        store_cost_col = next((c for c in df.columns if c.strip() == "门店成本"), None)
        factory_cost_col = next((c for c in df.columns if c.strip() == "成本"), None)
        spec_col = _find_col(df, "规格")
        if not name_col:
            continue
        for _, row in df.iterrows():
            nm = str(row.get(name_col, "")).strip()
            if not nm or nm == "nan":
                continue
            if store_cost_col:
                try:
                    semi_store_price[nm] = float(row[store_cost_col])
                except (TypeError, ValueError):
                    pass
            if factory_cost_col:
                try:
                    semi_brand_cost[nm] = float(row[factory_cost_col])
                except (TypeError, ValueError):
                    pass
            if spec_col:
                sp = str(row.get(spec_col, ""))
                if sp and sp != "nan":
                    semi_spec[nm] = sp

    # ── Read sub-ingredient total costs from 产品配方表 ──
    sub_factory_cost: dict[str, float] = {}  # factory total cost (总成本)
    sub_store_cost: dict[str, float] = {}    # store total cost (门店总成本)
    for sname in sheets:
        if "产品配方表" not in sname:
            continue
        df = sheets[sname]
        ing_col = _find_col(df, "配料")
        fc_col = _find_col(df, "总成本")
        sc_col = _find_col(df, "门店总成本")
        if not ing_col:
            continue
        for _, row in df.iterrows():
            ing = str(row.get(ing_col, "")).strip()
            if not ing or ing == "nan":
                continue
            if fc_col:
                try:
                    sub_factory_cost[ing] = float(row[fc_col])
                except (TypeError, ValueError):
                    pass
            if sc_col:
                try:
                    sub_store_cost[ing] = float(row[sc_col])
                except (TypeError, ValueError):
                    pass

    # ── Get cost breakdown (items + costs) ──
    breakdown = sku_cost_breakdown(sheets, product_key=product_key, basis=basis)
    if breakdown.empty:
        return pd.DataFrame()

    # ── Maps from 总原料成本表 ──
    brand_cost_map = get_brand_cost_map(sheets)
    store_price_map = get_store_price_map(sheets)
    spec_map = get_brand_spec_map(sheets)

    # ── Semi-product recipes from 产品配方表 ──
    semi_recipes = get_semi_product_recipes(sheets)

    # ── Usage map from 产品出品表 ──
    usage_map = _lookup_usage_map(sheets, product_key)

    rows: List[RecipeRow] = []
    for _, b_row in breakdown.iterrows():
        item = b_row["item"]
        usage_qty, usage_unit = usage_map.get(item, (0.0, ""))
        is_semi = item in semi_recipes

        if is_semi:
            # ── 1级半成品: data from 产品成本计算表 ──
            sp = semi_store_price.get(item, 0.0)
            bc = semi_brand_cost.get(item, 0.0)
            spec = semi_spec.get(item, "")

            spec_parsed = _parse_spec(spec)
            if spec_parsed and spec_parsed > 0 and usage_qty > 0:
                if basis == "store":
                    cost_val = usage_qty * (sp / spec_parsed)
                else:
                    cost_val = usage_qty * (bc / spec_parsed)
            else:
                cost_val = 0.0

            profit_rate = round(
                _calc_profit_rate(sp or bc or 0.0, bc or 0.0) * 100, 1
            )

            # ── 2级配料 (sub-ingredients) ──
            sub_items = semi_recipes.get(item, [])
            sub_rows: List[RecipeRow] = []
            for sub in sub_items:
                sub_name = sub["item"]
                sub_qty = sub["usage_qty"]
                sub_bc = brand_cost_map.get(sub_name, 0.0)
                sub_sp = store_price_map.get(sub_name, sub_bc or 0.0)
                sub_spec = spec_map.get(sub_name, "")

                # Cost = total cost from 产品配方表 (no scale_factor)
                if basis == "store":
                    sub_row_cost = sub_store_cost.get(sub_name, 0.0)
                else:
                    sub_row_cost = sub_factory_cost.get(sub_name, 0.0)

                sub_profit_rate = round(
                    _calc_profit_rate(sub_sp or sub_bc or 0.0, sub_bc or 0.0) * 100, 1
                )
                sub_rows.append(RecipeRow(
                    item=sub_name,
                    usage_qty=sub_qty,
                    usage_unit="",
                    cost=round(sub_row_cost, 4),
                    spec=sub_spec,
                    store_price=sub_sp,
                    brand_cost=round(sub_bc, 4),
                    profit_rate=sub_profit_rate,
                    level=LEVEL_SUB,
                    is_semi=False,
                ))

            rows.append(RecipeRow(
                item=item,
                usage_qty=usage_qty,
                usage_unit=usage_unit,
                cost=round(cost_val, 4),
                spec=spec,
                store_price=round(sp, 4) if sp else 0.0,
                brand_cost=round(bc, 4) if bc else 0.0,
                profit_rate=profit_rate,
                level=LEVEL_SEMI,
                is_semi=True,
            ))
            rows.extend(sub_rows)

        else:
            # ── 1级直接原料: data from 总原料成本表 ──
            bc = brand_cost_map.get(item, 0.0)
            sp = store_price_map.get(item, bc or _to_float(b_row["cost"]) or 0.0)
            spec = spec_map.get(item, "")

            spec_parsed = _parse_spec(spec)
            if spec_parsed and spec_parsed > 0 and usage_qty > 0:
                if basis == "store":
                    calc_cost = usage_qty * (sp / spec_parsed)
                else:
                    calc_cost = usage_qty * (bc / spec_parsed)
            else:
                calc_cost = _to_float(b_row["cost"]) or 0.0

            profit_rate = round(
                _calc_profit_rate(sp or bc or 0.0, bc or 0.0) * 100, 1
            )

            rows.append(RecipeRow(
                item=item,
                usage_qty=usage_qty,
                usage_unit=usage_unit,
                cost=round(calc_cost, 4),
                spec=spec,
                store_price=sp,
                brand_cost=round(bc, 4),
                profit_rate=profit_rate,
                level=LEVEL_DIRECT,
                is_semi=False,
            ))

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
