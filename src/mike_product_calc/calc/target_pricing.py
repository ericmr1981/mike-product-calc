from __future__ import annotations

from typing import Dict, Iterable, Optional

import pandas as pd

from mike_product_calc.calc.profit import ProfitBasis, sku_cost_breakdown, sku_profit_table


def suggest_adjustable_item_costs(
    sheets: Dict[str, pd.DataFrame],
    *,
    product_key: str,
    target_margin_rate: float,
    basis: ProfitBasis = "store",
    locked_items: Optional[Iterable[str]] = None,
) -> pd.DataFrame:
    """First-cut reverse pricing for F-003.

    Uses the existing cost breakdown as the allocation surface.
    - fixed cost: packaging
    - adjustable cost: main_material + ingredient
    - locked items remain unchanged
    """

    locked = {str(x).strip() for x in (locked_items or []) if str(x).strip()}

    profit_df = sku_profit_table(sheets, basis=basis, only_status=None)
    if profit_df.empty:
        return pd.DataFrame()

    row = profit_df.loc[profit_df["product_key"] == product_key]
    if row.empty:
        return pd.DataFrame()
    sku = row.iloc[0]
    price = sku.get("price")
    current_cost = sku.get("cost")
    if price is None or current_cost is None:
        return pd.DataFrame()

    breakdown = sku_cost_breakdown(sheets, product_key=product_key, basis=basis)
    if breakdown.empty:
        return pd.DataFrame()

    breakdown = breakdown.copy()
    breakdown["is_fixed"] = breakdown["bucket"].eq("packaging")
    breakdown["is_locked"] = breakdown["item"].isin(locked)
    breakdown["is_adjustable"] = ~breakdown["is_fixed"] & ~breakdown["is_locked"]

    target_allowable_cost = float(price) * (1 - float(target_margin_rate))
    current_cost_gap = target_allowable_cost - float(current_cost)

    adjustable_cost_total = float(breakdown.loc[breakdown["is_adjustable"], "cost"].sum())
    if adjustable_cost_total <= 0:
        breakdown["weight"] = 0.0
        breakdown["suggested_cost_ideal"] = breakdown["cost"]
        breakdown["suggested_cost_acceptable"] = breakdown["cost"]
        breakdown["suggested_cost_redline"] = breakdown["cost"]
    else:
        breakdown["weight"] = breakdown["cost"].where(breakdown["is_adjustable"], 0.0) / adjustable_cost_total
        delta = breakdown["weight"] * current_cost_gap
        breakdown["suggested_cost_ideal"] = breakdown["cost"] + delta
        breakdown["suggested_cost_acceptable"] = breakdown["cost"] + delta * 0.7
        breakdown["suggested_cost_redline"] = breakdown["cost"] + delta * 0.4

    breakdown["suggested_cost_ideal"] = breakdown["suggested_cost_ideal"].clip(lower=0)
    breakdown["suggested_cost_acceptable"] = breakdown["suggested_cost_acceptable"].clip(lower=0)
    breakdown["suggested_cost_redline"] = breakdown["suggested_cost_redline"].clip(lower=0)

    breakdown.insert(0, "product_key", product_key)
    breakdown.insert(1, "basis", basis)
    breakdown.insert(2, "target_margin_rate", float(target_margin_rate))
    breakdown.insert(3, "price", float(price))
    breakdown.insert(4, "current_cost", float(current_cost))
    breakdown.insert(5, "target_allowable_cost", float(target_allowable_cost))
    breakdown.insert(6, "current_cost_gap", float(current_cost_gap))
    return breakdown.reset_index(drop=True)
