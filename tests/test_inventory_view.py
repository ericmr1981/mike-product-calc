from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from mike_product_calc.data.inventory_view import (
    build_inventory_kpis,
    classify_inventory_row,
    is_snapshot_stale,
)


def test_classify_inventory_out_of_stock() -> None:
    row = {"available_qty": 0, "is_negative_stock": False, "has_amount_mismatch": False}
    assert classify_inventory_row(row, reorder_point=5) == "缺货"


def test_classify_inventory_low_stock() -> None:
    row = {"available_qty": 3, "is_negative_stock": False, "has_amount_mismatch": False}
    assert classify_inventory_row(row, reorder_point=5) == "低库存"


def test_classify_inventory_abnormal_takes_precedence() -> None:
    row = {"available_qty": 0, "is_negative_stock": True, "has_amount_mismatch": False}
    assert classify_inventory_row(row, reorder_point=5) == "异常"


def test_build_inventory_kpis_counts_statuses() -> None:
    df = pd.DataFrame(
        [
            {"inventory_status": "缺货"},
            {"inventory_status": "低库存"},
            {"inventory_status": "异常"},
            {"inventory_status": "正常"},
        ]
    )
    assert build_inventory_kpis(df) == {
        "total": 4,
        "out_of_stock": 1,
        "low_stock": 1,
        "abnormal": 1,
    }


def test_is_snapshot_stale_when_older_than_threshold() -> None:
    now_utc = datetime.now(timezone.utc)
    snapshot_at = now_utc - timedelta(hours=3)
    assert is_snapshot_stale(snapshot_at, now_utc=now_utc, stale_hours=2) is True


def test_is_snapshot_not_stale_within_threshold() -> None:
    now_utc = datetime.now(timezone.utc)
    snapshot_at = now_utc - timedelta(minutes=90)
    assert is_snapshot_stale(snapshot_at, now_utc=now_utc, stale_hours=2) is False
