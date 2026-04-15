from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import pandas as pd

from .profit import (
    ProfitBasis,
    _build_product_key,
    _ingredient_min_unit_cost_map,
    _to_float,
    ingredient_catalog,
)


# Categories treated as fixed cost — sourced from 总原料成本表.品项类别
FIXED_CATEGORIES = {
    "包材",
    "生产工具",
    "周边陈列",
    "生产消耗品",
}


def _is_fixed_category(cat: str) -> bool:
    c = str(cat or "").strip()
    return c in FIXED_CATEGORIES


@dataclass(frozen=True)
class TargetPricingResult:
    product_key: str
    basis: ProfitBasis
    price: float
    current_cost: float
    current_margin: float
    target_margin: float
    allowed_cost: float
    cost_gap: float
    fixed_cost: float
    adjustable_cost: float
    locked_cost: float
    adjustable_effective_cost: float
    scale_required: Optional[float]


def sku_ingredient_lines(
    sheets: dict[str, pd.DataFrame],
    *,
    product_key: str,
    basis: ProfitBasis = "store",
) -> pd.DataFrame:
    """Return per-ingredient lines for a SKU using 产品出品表_*.

    Output columns:
      item, qty, unit_cost, total_cost, category, is_fixed, sheet

    Cost categorisation is driven by 总原料成本表.品项类别, not heuristics alone.
    """

    out_sheets = ["产品出品表_Gelato", "产品出品表_雪花冰", "产品出品表_饮品"]
    df_out: Optional[pd.DataFrame] = None
    used_sheet: Optional[str] = None
    keys_ser: Optional[pd.Series] = None
    for s in out_sheets:
        df = sheets.get(s)
        if df is None:
            continue
        keys = _build_product_key(df)
        if (keys == product_key).any():
            df_out = df
            used_sheet = s
            keys_ser = keys
            break

    if df_out is None or used_sheet is None or keys_ser is None:
        return pd.DataFrame(columns=["item", "qty", "unit_cost", "total_cost", "category", "is_fixed", "sheet"])

    # workbook-driven category mapping
    cat = ingredient_catalog(sheets)
    name_to_cat = dict(zip(cat["name"], cat["category"]))

    qty_col = "用量"
    # Unified rule: unit_cost comes from 总原料成本表 (price/unit_qty),
    # with fallback to workbook columns if present.
    unit_col = "门店单位成本" if basis == "store" else "单位成本"
    total_col = "门店总成本" if basis == "store" else "总成本"
    unit_cost_map = _ingredient_min_unit_cost_map(sheets, basis=basis)

    part = df_out.loc[keys_ser == product_key].copy()
    if part.empty:
        return pd.DataFrame(columns=["item", "qty", "unit_cost", "total_cost", "category", "is_fixed", "sheet"])

    # Normalize line item name: prefer 配料, else 主原料
    mm = part["主原料"].fillna("").astype(str).map(str.strip) if "主原料" in part.columns else ""
    ing = part["配料"].fillna("").astype(str).map(str.strip) if "配料" in part.columns else ""
    item = ing.where(ing != "", mm)
    item = item.fillna("").astype(str).map(str.strip)

    part["qty"] = part[qty_col].map(_to_float) if qty_col in part.columns else None

    # unit_cost: prefer computed min_unit_cost from 总原料成本表, else fallback to workbook column.
    unit_cost_from_map = item.map(lambda x: unit_cost_map.get(str(x).strip()))
    unit_cost_series = unit_cost_from_map
    fallback_unit_cost = part[unit_col].map(_to_float) if unit_col in part.columns else None
    if fallback_unit_cost is not None:
        unit_cost_series = unit_cost_series.where(unit_cost_series.notna(), fallback_unit_cost)

    # total_cost: only compute qty * unit_cost when unit_cost comes from map.
    # Otherwise, prefer workbook total_cost column (it may include extra allocations).
    computed_total = None
    if part["qty"] is not None:
        computed_total = part["qty"] * unit_cost_from_map

    fallback_total_cost = part[total_col].map(_to_float) if total_col in part.columns else None
    if computed_total is not None:
        total_cost_series = computed_total
        if fallback_total_cost is not None:
            total_cost_series = total_cost_series.where(total_cost_series.notna(), fallback_total_cost)
    else:
        total_cost_series = fallback_total_cost

    out = pd.DataFrame(
        {
            "item": item,
            "qty": part["qty"],
            "unit_cost": unit_cost_series,
            "total_cost": total_cost_series,
            "category": item.map(lambda x: name_to_cat.get(str(x).strip(), "")),
        }
    )
    out = out[out["item"] != ""].copy()
    out["is_fixed"] = out["category"].map(_is_fixed_category)
    out["sheet"] = used_sheet
    out = out.reset_index(drop=True)
    return out


def target_pricing(
    sheets: dict[str, pd.DataFrame],
    *,
    product_key: str,
    target_margin: float,
    basis: ProfitBasis = "store",
    locked_items: Optional[Iterable[str]] = None,
) -> tuple[TargetPricingResult, pd.DataFrame]:
    """Compute target pricing suggestion for one SKU.

    - basis defaults to store because PRD is framed as "目标门店毛利率".
    - locked_items are excluded from adjustment.

    Returns (summary, suggestion_table).
    """

    locked_set = {str(x).strip() for x in (locked_items or []) if str(x).strip()}

    # Pull price/cost from 产品毛利表_*
    from .profit import sku_profit_table

    df = sku_profit_table(sheets, basis=basis, only_status=None)
    row = df.loc[df["product_key"] == product_key]
    if row.empty:
        raise KeyError(f"Unknown product_key: {product_key}")
    r0 = row.iloc[0]
    price = float(r0["price"]) if pd.notna(r0["price"]) else 0.0
    current_cost = float(r0["cost"]) if pd.notna(r0["cost"]) else 0.0
    current_margin = float(r0["gross_margin"]) if pd.notna(r0["gross_margin"]) else 0.0

    if price <= 0:
        raise ValueError("Invalid price; cannot compute target pricing")
    if not (0 <= target_margin <= 1):
        raise ValueError("target_margin must be between 0 and 1")

    allowed_cost = price * (1.0 - target_margin)
    cost_gap = allowed_cost - current_cost

    lines = sku_ingredient_lines(sheets, product_key=product_key, basis=basis)
    if lines.empty:
        # best-effort: no ingredient lines, cannot suggest per-item adjustments
        summary = TargetPricingResult(
            product_key=product_key,
            basis=basis,
            price=price,
            current_cost=current_cost,
            current_margin=current_margin,
            target_margin=target_margin,
            allowed_cost=allowed_cost,
            cost_gap=cost_gap,
            fixed_cost=0.0,
            adjustable_cost=0.0,
            locked_cost=0.0,
            adjustable_effective_cost=0.0,
            scale_required=None,
        )
        return summary, pd.DataFrame(columns=[
            "tier", "item", "category", "is_fixed", "locked",
            "current_unit_cost", "suggested_unit_cost", "unit_delta",
            "current_total_cost", "suggested_total_cost", "total_delta",
        ])

    lines = lines.copy()
    lines["locked"] = lines["item"].map(lambda x: str(x).strip() in locked_set)
    lines["current_total_cost"] = lines["total_cost"].fillna(0.0)
    lines["current_unit_cost"] = lines["unit_cost"]

    fixed_cost = float(lines.loc[lines["is_fixed"], "current_total_cost"].sum())
    adjustable_cost = float(lines.loc[~lines["is_fixed"], "current_total_cost"].sum())
    locked_cost = float(lines.loc[lines["locked"], "current_total_cost"].sum())
    adjustable_effective_cost = float(lines.loc[(~lines["is_fixed"]) & (~lines["locked"]), "current_total_cost"].sum())

    # How much to scale adjustable & unlocked items to hit target exactly (ideal).
    unchangeable = fixed_cost + locked_cost
    required_adjustable_total = allowed_cost - unchangeable
    if adjustable_effective_cost <= 0:
        scale_required = None
    else:
        scale_required = required_adjustable_total / adjustable_effective_cost

    summary = TargetPricingResult(
        product_key=product_key,
        basis=basis,
        price=price,
        current_cost=current_cost,
        current_margin=current_margin,
        target_margin=target_margin,
        allowed_cost=allowed_cost,
        cost_gap=cost_gap,
        fixed_cost=fixed_cost,
        adjustable_cost=adjustable_cost,
        locked_cost=locked_cost,
        adjustable_effective_cost=adjustable_effective_cost,
        scale_required=scale_required,
    )

    def _make_tier(tier: str, scale: Optional[float]) -> pd.DataFrame:
        part = lines.copy()
        part["tier"] = tier
        part["suggested_unit_cost"] = part["current_unit_cost"]
        part["suggested_total_cost"] = part["current_total_cost"]

        if scale is not None:
            mask = (~part["is_fixed"]) & (~part["locked"]) & (~part["current_unit_cost"].isna())
            part.loc[mask, "suggested_unit_cost"] = part.loc[mask, "current_unit_cost"] * float(scale)
            mask2 = (~part["is_fixed"]) & (~part["locked"]) & (~part["current_total_cost"].isna())
            part.loc[mask2, "suggested_total_cost"] = part.loc[mask2, "current_total_cost"] * float(scale)

        part["unit_delta"] = part["suggested_unit_cost"] - part["current_unit_cost"]
        part["total_delta"] = part["suggested_total_cost"] - part["current_total_cost"]
        return part[[
            "tier",
            "item",
            "category",
            "is_fixed",
            "locked",
            "current_unit_cost",
            "suggested_unit_cost",
            "unit_delta",
            "current_total_cost",
            "suggested_total_cost",
            "total_delta",
        ]]

    # Tiers are explicit and inspectable:
    # - ideal: hit target exactly (scale_required)
    # - acceptable: halfway move toward ideal
    # - redline: negotiation buffer (more aggressive than ideal by 10%)
    if scale_required is None:
        tiers = [_make_tier("ideal", None)]
    else:
        acceptable = 1.0 + 0.5 * (scale_required - 1.0)
        redline = scale_required
        if scale_required < 1.0:
            # Need cost reduction; add 10% negotiation buffer
            redline = 1.0 + 1.1 * (scale_required - 1.0)
        tiers = [
            _make_tier("ideal", scale_required),
            _make_tier("acceptable", acceptable),
            _make_tier("redline", redline),
        ]

    suggest = pd.concat(tiers, ignore_index=True)
    return summary, suggest
