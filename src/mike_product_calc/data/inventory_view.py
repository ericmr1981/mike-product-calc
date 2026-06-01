from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

import pandas as pd


def classify_inventory_row(row: Mapping[str, Any], reorder_point: float) -> str:
    if bool(row.get("is_negative_stock")) or bool(row.get("has_amount_mismatch")):
        return "异常"

    available_qty = float(row.get("available_qty") or 0)
    if available_qty <= 0:
        return "缺货"
    if available_qty <= reorder_point:
        return "低库存"
    return "正常"


def build_inventory_kpis(df: pd.DataFrame) -> dict[str, int]:
    counts = df.get("inventory_status", pd.Series(dtype=str)).value_counts()
    total_amount = df["current_amount"].sum() if "current_amount" in df.columns else 0.0

    tool_amount = 0.0
    if "current_amount" in df.columns:
        cat_lv2 = df["category_lv2"] if "category_lv2" in df.columns else pd.Series([""] * len(df))
        cat_lv1 = df["category_lv1"] if "category_lv1" in df.columns else pd.Series([""] * len(df))
        tool_mask = (
            cat_lv2.astype(str).str.contains("工具", na=False)
            | cat_lv1.astype(str).str.contains("工具", na=False)
        )
        tool_amount = df.loc[tool_mask, "current_amount"].sum()

    return {
        "total": int(len(df)),
        "out_of_stock": int(counts.get("缺货", 0)),
        "low_stock": int(counts.get("低库存", 0)),
        "abnormal": int(counts.get("异常", 0)),
        "total_amount": round(total_amount, 2),
        "tool_amount": round(tool_amount, 2),
    }


def classify_safety_status(available_qty: float, safety_stock: float | None) -> str:
    """Classify stock level relative to safety stock threshold.

    Returns 'zero_stock' (≤ 0), 'below_safety' (> 0 but < safety_stock), or 'normal'.
    """
    if available_qty <= 0:
        return "zero_stock"
    if safety_stock is not None and safety_stock > 0 and available_qty < safety_stock:
        return "below_safety"
    return "normal"


def is_snapshot_stale(
    snapshot_at: datetime,
    *,
    now_utc: datetime | None = None,
    stale_hours: int = 2,
) -> bool:
    current = now_utc or datetime.now(timezone.utc)
    return (current - snapshot_at).total_seconds() > stale_hours * 3600


def check_items_to_inventory_rows(items: list[dict]) -> list[dict]:
    """Convert inventory check items to inventory view format.

    Maps check item fields (system_qty, avg_price, etc.) to the format
    expected by build_inventory_kpis, shape_inventory_table, etc.
    """
    rows: list[dict] = []
    for item in items:
        system_qty = float(item.get("system_qty") or 0)
        avg_price = float(item.get("avg_price") or 0)
        data_warnings = item.get("data_warnings") or []

        current_amount = round(system_qty * avg_price, 2)
        is_negative = "negative_stock" in data_warnings
        has_mismatch = "amount_mismatch" in data_warnings

        rows.append({
            "item_code": item.get("item_code", ""),
            "item_name": item.get("item_name", ""),
            "spec": item.get("spec") or "",
            "unit": item.get("unit", ""),
            "category_lv2": item.get("category") or "",
            "category_lv1": "",
            "warehouse_name": "",
            "warehouse_code": "",
            "stock_qty": system_qty,
            "available_qty": system_qty,
            "current_amount": current_amount,
            "stock_unit_price": avg_price,
            "is_negative_stock": is_negative,
            "has_amount_mismatch": has_mismatch,
            "data_warnings": data_warnings,
            "_source": "check",
        })
    return rows
