from __future__ import annotations

import pandas as pd

from mike_product_calc.calc.profit import margin_delta_report, sku_cost_breakdown, sku_profit_table
from mike_product_calc.calc.target_pricing import suggest_adjustable_item_costs


def _base_sheets():
    return {
        "产品毛利表_Gelato": pd.DataFrame(
            {
                "品类": ["Gelato"],
                "品名": ["A"],
                "规格": ["大"],
                "状态": ["上线"],
                "成本": [10.0],
                "门店成本": [12.0],
                "定价": [20.0],
                "毛利率": [0.5],
                "门店毛利率": [0.4],
            }
        ),
        "产品出品表_Gelato": pd.DataFrame(
            {
                "品类": ["Gelato", "Gelato"],
                "品名": ["A", "A"],
                "规格": ["大", "大"],
                "主原料": ["mm", ""],
                "配料": ["x", "杯"],
                "总成本": [1.0, 2.0],
                "门店总成本": [1.1, 2.2],
            }
        ),
        "总原料成本表": pd.DataFrame(
            {
                "品项名称": ["x", "杯"],
                "品项类别": ["坚果", "包材"],
            }
        ),
    }


def test_sku_profit_table_factory_and_store_delta():
    sheets = _base_sheets()

    df_f = sku_profit_table(sheets, basis="factory", only_status="上线")
    assert df_f.shape[0] == 1
    assert abs(df_f.loc[0, "gross_margin"] - 0.5) < 1e-9
    assert df_f.loc[0, "margin_delta"] == 0.0

    df_s = sku_profit_table(sheets, basis="store", only_status="上线")
    assert abs(df_s.loc[0, "gross_margin"] - 0.4) < 1e-9
    assert df_s.loc[0, "margin_delta"] == 0.0


def test_margin_delta_report_orders_top_offenders():
    df = pd.DataFrame(
        {
            "category": ["Gelato", "Gelato", "雪花冰"],
            "product_key": ["a", "b", "c"],
            "margin_delta": [0.01, -0.03, 0.02],
        }
    )
    stats, top = margin_delta_report(df, top_n=2)
    assert not stats.empty
    assert not top.empty
    assert top.iloc[0]["product_key"] == "b"
    assert stats.loc[stats["category"] == "Gelato", "max_abs_delta_pp"].iloc[0] == 3.0


def test_sku_cost_breakdown_has_packaging_bucket():
    sheets = _base_sheets()
    key = "Gelato|A|大"
    df = sku_cost_breakdown(sheets, product_key=key, basis="factory")
    assert not df.empty
    assert "packaging" in set(df["bucket"].tolist())


def test_target_pricing_respects_locked_items():
    sheets = _base_sheets()
    key = "Gelato|A|大"
    df = suggest_adjustable_item_costs(
        sheets,
        product_key=key,
        target_margin_rate=0.5,
        basis="store",
        locked_items=["x"],
    )
    assert not df.empty
    locked = df.loc[df["item"] == "x"].iloc[0]
    assert bool(locked["is_locked"]) is True
    assert locked["suggested_cost_ideal"] == locked["cost"]
