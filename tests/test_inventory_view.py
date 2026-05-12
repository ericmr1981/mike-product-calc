from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from mike_product_calc.data.inventory_view import (
    build_inventory_kpis,
    classify_inventory_row,
    classify_safety_status,
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
    result = build_inventory_kpis(df)
    assert result["total"] == 4
    assert result["out_of_stock"] == 1
    assert result["low_stock"] == 1
    assert result["abnormal"] == 1
    assert result["total_amount"] == 0.0
    assert result["tool_amount"] == 0.0


def test_build_inventory_kpis_tool_amount() -> None:
    df = pd.DataFrame(
        [
            {"inventory_status": "正常", "current_amount": 100.0, "category_lv2": "原料"},
            {"inventory_status": "正常", "current_amount": 200.0, "category_lv2": "生产工具"},
            {"inventory_status": "正常", "current_amount": 50.0, "category_lv2": "生产工具"},
        ]
    )
    result = build_inventory_kpis(df)
    assert result["total_amount"] == 350.0
    assert result["tool_amount"] == 250.0


def test_is_snapshot_stale_when_older_than_threshold() -> None:
    now_utc = datetime.now(timezone.utc)
    snapshot_at = now_utc - timedelta(hours=3)
    assert is_snapshot_stale(snapshot_at, now_utc=now_utc, stale_hours=2) is True


def test_is_snapshot_not_stale_within_threshold() -> None:
    now_utc = datetime.now(timezone.utc)
    snapshot_at = now_utc - timedelta(minutes=90)
    assert is_snapshot_stale(snapshot_at, now_utc=now_utc, stale_hours=2) is False


def test_classify_safety_status_zero_stock() -> None:
    assert classify_safety_status(0, 10) == "zero_stock"
    assert classify_safety_status(-1, 10) == "zero_stock"


def test_classify_safety_status_below_safety() -> None:
    assert classify_safety_status(5, 10) == "below_safety"


def test_classify_safety_status_normal() -> None:
    assert classify_safety_status(15, 10) == "normal"
    assert classify_safety_status(10, 10) == "normal"
    assert classify_safety_status(5, None) == "normal"
    assert classify_safety_status(5, 0) == "normal"
