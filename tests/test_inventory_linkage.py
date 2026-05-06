import pandas as pd

from mike_product_calc.calc.inventory_linkage import build_replenishment_plan, summarize_shortage_alert


def test_build_replenishment_plan_gap_formula():
    bom = pd.DataFrame(
        [
            {"material": "草莓丁", "total_purchase_qty": 10.0, "purchase_unit": "包"},
            {"material": "牛奶", "total_purchase_qty": 8.0, "purchase_unit": "瓶"},
        ]
    )
    inv = pd.DataFrame(
        [
            {"item_name": "草莓丁", "available_qty": 4.0, "unit": "包", "warehouse_code": "GM002"},
            {"item_name": "牛奶", "available_qty": 9.0, "unit": "瓶", "warehouse_code": "GM002"},
        ]
    )

    out = build_replenishment_plan(bom, inv)

    strawberry = out[out["material"] == "草莓丁"].iloc[0]
    milk = out[out["material"] == "牛奶"].iloc[0]
    assert strawberry["shortage_qty"] == 6.0
    assert strawberry["suggested_replenish_qty"] == 6.0
    assert milk["shortage_qty"] == 0.0
    assert milk["suggested_replenish_qty"] == 0.0


def test_build_replenishment_plan_urgency_and_deterministic_order():
    bom = pd.DataFrame(
        [
            {"material": "B料", "total_purchase_qty": 8.0, "purchase_unit": "袋"},
            {"material": "A料", "total_purchase_qty": 5.0, "purchase_unit": "袋"},
            {"material": "C料", "total_purchase_qty": 2.0, "purchase_unit": "袋"},
        ]
    )
    inv = pd.DataFrame(
        [
            {"item_name": "A料", "available_qty": 0.0, "unit": "袋"},
            {"item_name": "B料", "available_qty": 3.0, "unit": "袋"},
            {"item_name": "C料", "available_qty": 5.0, "unit": "袋"},
        ]
    )

    out1 = build_replenishment_plan(bom, inv)
    out2 = build_replenishment_plan(bom, inv)

    assert out1["material"].tolist() == ["A料", "B料", "C料"]
    assert out1["urgency"].tolist() == ["高", "中", "低"]
    assert out1.equals(out2)


def test_summarize_shortage_alert_counts_shortage_items():
    plan = pd.DataFrame(
        [
            {"material": "A", "shortage_qty": 5.0},
            {"material": "B", "shortage_qty": 0.0},
            {"material": "C", "shortage_qty": -1.0},
        ]
    )

    summary = summarize_shortage_alert(plan)
    assert summary["shortage_items"] == 1
    assert summary["total_shortage_qty"] == 5.0


def test_build_replenishment_plan_fallback_unique_prefix_match():
    bom = pd.DataFrame(
        [
            {"material": "原味奶浆", "total_purchase_qty": 12.0, "purchase_unit": "袋"},
        ]
    )
    inv = pd.DataFrame(
        [
            {"item_name": "原味奶浆JYX001", "available_qty": 10.0, "unit": "袋", "warehouse_code": "GM002"},
        ]
    )

    out = build_replenishment_plan(bom, inv)
    row = out.iloc[0]
    assert row["available_qty"] == 10.0
    assert row["shortage_qty"] == 2.0
