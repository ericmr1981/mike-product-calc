from __future__ import annotations

import pandas as pd

from mike_product_calc.calc.profit_oracle import (
    ProfitOracleThresholds,
    sku_profit_consistency_table,
    render_profit_oracle_markdown,
)


def test_profit_consistency_table_clean():
    """All three columns computed; margin/profit/cost deltas are zero when consistent."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"],
            "品名": ["X"],
            "规格": ["S"],
            "状态": ["上线"],
            "成本": [10.0],
            "门店成本": [12.0],
            "定价": [20.0],
            "毛利率": [0.5],        # price*margin = 20*0.5 = 10 = cost ✓
            "门店毛利率": [0.4],    # 20*0.4 = 8 != 12 (store not consistent)
        }),
    }
    df = sku_profit_consistency_table(sheets, basis="factory", only_status="上线")
    assert df.shape[0] == 1
    assert "profit_delta_rmb" in df.columns
    assert "cost_delta_rmb" in df.columns
    # price=20, margin=0.5 => implied_profit=10, implied_cost=10, actual_profit=10, actual_cost=10
    assert abs(df.iloc[0]["profit_delta_rmb"]) < 1e-9
    assert abs(df.iloc[0]["cost_delta_rmb"]) < 1e-9


def test_profit_consistency_table_store():
    """Store basis uses 门店成本 + 门店毛利率."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"],
            "品名": ["Y"],
            "规格": ["M"],
            "状态": ["上线"],
            "成本": [8.0],
            "门店成本": [12.0],
            "定价": [20.0],
            "毛利率": [0.4],
            "门店毛利率": [0.4],
        }),
    }
    df = sku_profit_consistency_table(sheets, basis="store", only_status="上线")
    assert df.shape[0] == 1
    # implied_profit=20*0.4=8, actual_profit=20-12=8
    assert abs(df.iloc[0]["profit_delta_rmb"]) < 1e-9
    assert abs(df.iloc[0]["cost_delta_rmb"]) < 1e-9


def test_profit_consistency_null_margin():
    """When workbook_margin is absent, all delta columns are null."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"],
            "品名": ["Z"],
            "规格": ["L"],
            "状态": ["上线"],
            "成本": [10.0],
            "门店成本": [12.0],
            "定价": [20.0],
            "毛利率": [None],
            "门店毛利率": [None],
        }),
    }
    df = sku_profit_consistency_table(sheets, basis="factory", only_status="上线")
    assert df.shape[0] == 1
    assert pd.isna(df.iloc[0]["profit_delta_rmb"])
    assert pd.isna(df.iloc[0]["cost_delta_rmb"])


def test_profit_consistency_offending_row():
    """A row with a margin mismatch is flagged."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"],
            "品名": ["Bad"],
            "规格": ["XL"],
            "状态": ["上线"],
            "成本": [10.0],       # gross_margin = 10/20 = 0.5
            "门店成本": [12.0],
            "定价": [20.0],
            "毛利率": [0.45],     # workbook says 0.45, actual is 0.5 -> delta=0.05
            "门店毛利率": [0.4],
        }),
    }
    df = sku_profit_consistency_table(sheets, basis="factory", only_status="上线")
    assert df.shape[0] == 1
    assert abs(df.iloc[0]["margin_delta"] - 0.05) < 1e-9


def test_render_profit_oracle_pass():
    """Clean data produces a PASS report."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"],
            "品名": ["Clean"],
            "规格": ["S"],
            "状态": ["上线"],
            "成本": [10.0],
            "门店成本": [12.0],
            "定价": [20.0],
            "毛利率": [0.5],
            "门店毛利率": [0.4],
        }),
    }
    df = sku_profit_consistency_table(sheets, basis="factory", only_status="上线")
    md = render_profit_oracle_markdown(df, basis="factory")
    assert "PASS" in md
    assert "FAIL" not in md


def test_render_profit_oracle_fail():
    """Offending data produces a FAIL report."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"],
            "品名": ["Dirty"],
            "规格": ["S"],
            "状态": ["上线"],
            "成本": [10.0],
            "门店成本": [12.0],
            "定价": [20.0],
            "毛利率": [0.45],   # mismatch with actual 0.5
            "门店毛利率": [0.4],
        }),
    }
    df = sku_profit_consistency_table(sheets, basis="factory", only_status="上线")
    md = render_profit_oracle_markdown(
        df, basis="factory",
        thresholds=ProfitOracleThresholds(margin_delta_abs=1e-4, rmb_delta_abs=0.01),
    )
    assert "FAIL" in md
