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
    return {
        "total": int(len(df)),
        "out_of_stock": int(counts.get("缺货", 0)),
        "low_stock": int(counts.get("低库存", 0)),
        "abnormal": int(counts.get("异常", 0)),
    }


def is_snapshot_stale(
    snapshot_at: datetime,
    *,
    now_utc: datetime | None = None,
    stale_hours: int = 2,
) -> bool:
    current = now_utc or datetime.now(timezone.utc)
    return (current - snapshot_at).total_seconds() > stale_hours * 3600
