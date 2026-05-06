from __future__ import annotations

import pandas as pd

from mike_product_calc.ui.inventory_tab import apply_inventory_filters, shape_inventory_table


def test_shape_inventory_table_adds_status_column() -> None:
    df = pd.DataFrame(
        [
            {
                "item_code": "SKU-1",
                "available_qty": 0,
                "is_negative_stock": False,
                "has_amount_mismatch": False,
            },
            {
                "item_code": "SKU-2",
                "available_qty": 8,
                "is_negative_stock": False,
                "has_amount_mismatch": False,
            },
        ]
    )

    out = shape_inventory_table(df, reorder_point=5)

    assert "inventory_status" in out.columns
    statuses = set(out["inventory_status"].tolist())
    assert "缺货" in statuses
    assert "正常" in statuses


def test_shape_inventory_table_sorts_by_status_priority_then_qty_then_code() -> None:
    df = pd.DataFrame(
        [
            {
                "item_code": "N-2",
                "available_qty": 10,
                "is_negative_stock": False,
                "has_amount_mismatch": False,
            },
            {
                "item_code": "LOW-1",
                "available_qty": 2,
                "is_negative_stock": False,
                "has_amount_mismatch": False,
            },
            {
                "item_code": "OOS-1",
                "available_qty": 0,
                "is_negative_stock": False,
                "has_amount_mismatch": False,
            },
            {
                "item_code": "ABN-1",
                "available_qty": 99,
                "is_negative_stock": True,
                "has_amount_mismatch": False,
            },
            {
                "item_code": "LOW-0",
                "available_qty": 2,
                "is_negative_stock": False,
                "has_amount_mismatch": False,
            },
        ]
    )

    out = shape_inventory_table(df, reorder_point=5)

    assert out["item_code"].tolist() == ["ABN-1", "OOS-1", "LOW-0", "LOW-1", "N-2"]


def test_apply_inventory_filters_by_status_keyword_and_warehouse() -> None:
    df = pd.DataFrame(
        [
            {
                "item_code": "A",
                "item_name": "草莓丁",
                "inventory_status": "缺货",
                "warehouse_code": "GM002",
            },
            {
                "item_code": "B",
                "item_name": "牛轧糖",
                "inventory_status": "正常",
                "warehouse_code": "GM002",
            },
            {
                "item_code": "C",
                "item_name": "草莓酱",
                "inventory_status": "缺货",
                "warehouse_code": "GM001",
            },
        ]
    )

    out = apply_inventory_filters(df, status="缺货", keyword="草莓", warehouse_code="GM002")

    assert len(out) == 1
    assert out.iloc[0]["item_code"] == "A"


def test_apply_inventory_filters_noop_for_all_filters_and_empty_keyword() -> None:
    df = pd.DataFrame(
        [
            {"item_code": "A", "inventory_status": "正常", "warehouse_code": "GM001"},
            {"item_code": "B", "inventory_status": "缺货", "warehouse_code": "GM002"},
        ]
    )

    out = apply_inventory_filters(df, status="全部", keyword="   ", warehouse_code="全部")

    assert out["item_code"].tolist() == ["A", "B"]
