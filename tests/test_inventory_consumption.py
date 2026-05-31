from __future__ import annotations

import pandas as pd
import pytest

from mike_product_calc.calc.inventory_consumption import (
    build_consumption_kpis,
    build_consumption_table,
    classify_depletion_urgency,
    format_consumption_amount,
)


def test_build_consumption_kpis() -> None:
    rows = [
        {"item_code": "A", "consumption_qty": 10, "consumption_amount": 500, "avg_price": 50, "start_qty": 20, "end_qty": 10, "item_type": "matched"},
        {"item_code": "B", "consumption_qty": 5, "consumption_amount": 100, "avg_price": 20, "start_qty": 10, "end_qty": 5, "item_type": "matched"},
        {"item_code": "C", "consumption_qty": 0, "consumption_amount": 0, "avg_price": 10, "start_qty": 5, "end_qty": 5, "item_type": "matched"},
        {"item_code": "D", "consumption_qty": None, "consumption_amount": None, "avg_price": 30, "start_qty": None, "end_qty": 15, "item_type": "new"},
    ]
    kpis = build_consumption_kpis(rows, days=6)
    assert kpis["total_consumption_amount"] == 600.0
    assert kpis["daily_avg_amount"] == 100.0
    assert kpis["consumption_item_count"] == 2
    assert kpis["total_matched_items"] == 3
    assert kpis["total_new_items"] == 1
    assert kpis["fastest_item_daily"] == pytest.approx(10.0 / 6)  # 1.666...
    assert kpis["fastest_item_name"] == "A"


def test_build_consumption_kpis_top_category() -> None:
    rows = [
        {"item_code": "A", "consumption_qty": 10, "consumption_amount": 500, "category": "包材", "item_type": "matched"},
        {"item_code": "B", "consumption_qty": 5, "consumption_amount": 100, "category": "调味酱", "item_type": "matched"},
        {"item_code": "C", "consumption_qty": 3, "consumption_amount": 200, "category": "调味酱", "item_type": "matched"},
    ]
    kpis = build_consumption_kpis(rows, days=6)
    assert kpis["top_category_name"] == "包材"
    assert kpis["top_category_amount"] == 500.0


def test_build_consumption_kpis_fastest_item() -> None:
    rows = [
        {"item_code": "A", "consumption_qty": 30, "consumption_amount": 150, "item_name": "北海道牛乳60", "unit": "箱", "end_qty": 10, "item_type": "matched"},
        {"item_code": "B", "consumption_qty": 10, "consumption_amount": 50, "item_name": "雀巢淡奶油", "unit": "箱", "end_qty": 5, "item_type": "matched"},
    ]
    kpis = build_consumption_kpis(rows, days=6)
    assert kpis["fastest_item_name"] == "北海道牛乳60"
    assert kpis["fastest_item_daily"] == 5.0


def test_build_consumption_table() -> None:
    rows = [
        {"item_code": "WP0013", "item_name": "冰碗5oz", "unit": "箱", "category": "包材",
         "start_qty": 1.818, "end_qty": 1.796, "delivery_qty": 0,
         "consumption_qty": 0.022, "avg_price": 328, "consumption_amount": 7.22,
         "item_type": "matched"},
    ]
    df = build_consumption_table(rows, days=6)
    assert len(df) == 1
    assert df.iloc[0]["预计耗尽天数"] == "充足"


def test_classify_depletion_urgency() -> None:
    assert classify_depletion_urgency(1) == "urgent"
    assert classify_depletion_urgency(5) == "warning"
    assert classify_depletion_urgency(10) == "normal"


def test_build_consumption_table_depletion_highlight() -> None:
    rows = [
        {"item_code": "A", "consumption_qty": 10, "consumption_amount": 500, "end_qty": 5, "start_qty": 15, "delivery_qty": 0, "avg_price": 50, "item_name": "Test", "unit": "箱", "category": "包材", "item_type": "matched"},
        {"item_code": "B", "consumption_qty": 5, "consumption_amount": 100, "end_qty": 2, "start_qty": 7, "delivery_qty": 0, "avg_price": 20, "item_name": "Test2", "unit": "箱", "category": "调味酱", "item_type": "matched"},
    ]
    df = build_consumption_table(rows, days=6)
    assert df[df["item_code"] == "A"]["_depletion_urgency"].iloc[0] == "warning"
    assert df[df["item_code"] == "B"]["_depletion_urgency"].iloc[0] == "urgent"


def test_format_consumption_amount() -> None:
    assert format_consumption_amount(12345) == "¥12,345.00"
    assert format_consumption_amount(12345678) == "¥1,234.57万"
    assert format_consumption_amount(0) == "¥0.00"
    assert format_consumption_amount(None) == "-"


def test_build_consumption_kpis_empty_rows() -> None:
    """Edge case: empty rows list should return all zeros."""
    kpis = build_consumption_kpis([], days=30)
    assert kpis["total_consumption_amount"] == 0.0
    assert kpis["daily_avg_amount"] == 0.0
    assert kpis["consumption_item_count"] == 0
    assert kpis["total_matched_items"] == 0
    assert kpis["total_new_items"] == 0
    assert kpis["fastest_item_name"] is None
    assert kpis["fastest_item_daily"] is None
    assert kpis["top_category_name"] is None
    assert kpis["top_category_amount"] is None


def test_build_consumption_table_new_items_sorted_bottom() -> None:
    """New items should appear at the bottom of the table."""
    rows = [
        {"item_code": "A", "consumption_qty": 10, "consumption_amount": 500, "end_qty": 5, "start_qty": 15, "delivery_qty": 0, "avg_price": 50, "item_name": "Old", "unit": "箱", "category": "包材", "item_type": "matched"},
        {"item_code": "B", "consumption_qty": None, "consumption_amount": None, "end_qty": 15, "start_qty": None, "delivery_qty": 10, "avg_price": 30, "item_name": "New", "unit": "个", "category": "工具", "item_type": "new"},
    ]
    df = build_consumption_table(rows, days=6)
    assert len(df) == 2
    # Matched items come first, then new items
    assert df.iloc[0]["item_code"] == "A"
    assert df.iloc[1]["item_code"] == "B"


def test_build_consumption_table_zero_daily_avg() -> None:
    """When daily average is 0, depletion days should be '充足'."""
    rows = [
        {"item_code": "A", "consumption_qty": 0, "consumption_amount": 0, "end_qty": 10, "start_qty": 10, "delivery_qty": 0, "avg_price": 50, "item_name": "Test", "unit": "箱", "category": "包材", "item_type": "matched"},
    ]
    df = build_consumption_table(rows, days=6)
    assert df.iloc[0]["预计耗尽天数"] == "充足"
