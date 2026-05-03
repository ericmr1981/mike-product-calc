"""
purchase_suggestion.py — 采购建议引擎 for mike-product-calc.

输入: bom_expand_multi 的输出 DataFrame（需要含 latest_order_date 列）。
输出: 采购建议 DataFrame，含 order_date / arrival_date / is_urgent 等列。

用法:
    from mike_product_calc.calc.purchase_suggestion import build_purchase_list
    suggestion = build_purchase_list(demand_df)
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd


def build_purchase_list(
    demand_df: pd.DataFrame,
    *,
    order_date: Optional[date] = None,
    today: Optional[date] = None,
) -> pd.DataFrame:
    """
    Build purchase suggestion list from BOM demand DataFrame.

    Parameters
    ----------
    demand_df
        Output of prep_engine.bom_expand_multi().
        Required columns: material, total_purchase_qty, purchase_unit,
                          sku_keys, is_semi_finished, lead_days, latest_order_date.
        If latest_order_date is missing, order_date will be computed as
        order_date - lead_days from order_date arg (requires order_date).
    order_date
        Target delivery / arrival date for all items.
        If None, uses today.
    today
        Reference date for urgency check. Defaults to date.today().

    Returns
    -------
    pd.DataFrame with columns:
        order_date      — 下单日期（latest_order_date - lead_days）
        arrival_date    — 到货日期（latest_order_date，即目标交付日）
        material        — 原料名称
        qty             — 采购数量
        unit            — 单位
        source_skus     — 来源 SKU（逗号分隔）
        is_urgent       — 是否紧急（下单日已过）
    """
    if demand_df.empty:
        return pd.DataFrame(columns=[
            "order_date", "arrival_date", "material",
            "qty", "unit", "source_skus", "is_urgent",
        ])

    df = demand_df.copy()

    # Only raw materials (not semi-finished)
    df = df[~df.get("is_semi_finished", pd.Series(False))].copy()

    if df.empty:
        return pd.DataFrame(columns=[
            "order_date", "arrival_date", "material",
            "qty", "unit", "source_skus", "is_urgent",
        ])

    if today is None:
        today = date.today()

    # Resolve latest_order_date
    has_ld_col = "latest_order_date" in df.columns

    def make_arrival(row: pd.Series) -> Optional[str]:
        """arrival_date = order_date (target delivery date).
        latest_order_date from bom_expand_multi is already target_date - lead_days
        (i.e. the latest ORDER date), NOT the arrival date.
        """
        if order_date is not None:
            return order_date.strftime("%Y-%m-%d")
        return today.strftime("%Y-%m-%d")

    def make_order(row: pd.Series) -> Optional[str]:
        """order_date = latest_order_date (already target_date - lead_days from bom_expand_multi).
        Fallback: arrival_date - lead_days if latest_order_date is missing.
        """
        if has_ld_col and pd.notna(row.get("latest_order_date")):
            return str(row["latest_order_date"]).strip()
        arrival_str = make_arrival(row)
        lead_days = int(row.get("lead_days", 0) or 0)
        try:
            arrival_d = date.fromisoformat(arrival_str)
        except Exception:
            arrival_d = today
        order_d = arrival_d - timedelta(days=lead_days)
        return order_d.strftime("%Y-%m-%d")

    def is_urgent_check(row: pd.Series) -> bool:
        """True if order_date is on or before today."""
        od_str = make_order(row)
        try:
            od = date.fromisoformat(od_str)
            return od <= today
        except Exception:
            return False

    df["arrival_date"] = df.apply(make_arrival, axis=1)
    df["order_date"]    = df.apply(make_order, axis=1)
    df["is_urgent"]    = df.apply(is_urgent_check, axis=1)

    result = pd.DataFrame({
        "order_date":   df["order_date"],
        "arrival_date": df["arrival_date"],
        "material":     df["material"],
        "qty":          df["total_purchase_qty"].round(4),
        "unit":         df["purchase_unit"],
        "source_skus":  df["sku_keys"],
        "is_urgent":    df["is_urgent"],
    })

    # Sort: urgent first, then by arrival_date, then by material
    result = result.sort_values(
        ["is_urgent", "arrival_date", "material"],
        ascending=[False, True, True],
    ).reset_index(drop=True)

    return result
