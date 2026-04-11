from __future__ import annotations

import pandas as pd

from mike_product_calc.calc.margin_target import (
    _is_fixed_category,
    FIXED_CATEGORIES,
    sku_ingredient_lines,
    target_pricing,
    TargetPricingResult,
)


def test_is_fixed_category_true():
    assert _is_fixed_category("包材") is True
    assert _is_fixed_category("生产工具") is True
    assert _is_fixed_category("周边陈列") is True
    assert _is_fixed_category("生产消耗品") is True


def test_is_fixed_category_false():
    assert _is_fixed_category("配料") is False
    assert _is_fixed_category("乳制品") is False
    assert _is_fixed_category("") is False


def test_sku_ingredient_lines_unknown_key():
    sheets = {
        "产品出品表_Gelato": pd.DataFrame({
            "品类": ["Gelato"], "品名": ["X"], "规格": ["S"],
            "主原料": ["m"], "配料": ["ing"],
            "用量": [1.0], "单位成本": [0.5], "总成本": [0.5],
            "门店单位成本": [0.6], "门店总成本": [0.6],
        }),
        "总原料成本表": pd.DataFrame({"品项名称": ["ing"], "品项类别": ["配料"]}),
    }
    df = sku_ingredient_lines(sheets, product_key="unknown|key", basis="factory")
    assert df.empty


def test_sku_ingredient_lines_fixed_category():
    """包材 items should be marked is_fixed=True."""
    sheets = {
        "产品出品表_Gelato": pd.DataFrame({
            "品类": ["Gelato"], "品名": ["A"], "规格": ["S"],
            "主原料": ["milk"], "配料": ["cup"],
            "用量": [1.0], "单位成本": [0.5], "总成本": [0.5],
            "门店单位成本": [0.6], "门店总成本": [0.6],
        }),
        "总原料成本表": pd.DataFrame({"品项名称": ["cup"], "品项类别": ["包材"], "品项类型": ["普通"]}),
    }
    df = sku_ingredient_lines(sheets, product_key="Gelato|A|S", basis="factory")
    assert not df.empty
    assert "is_fixed" in df.columns
    assert bool(df.iloc[0]["is_fixed"]) is True
    assert str(df.iloc[0]["category"]) == "包材"


def test_target_pricing_basic():
    """Price=20, cost=10, margin=0.5. Target 0.6 -> allowed_cost=8."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"], "品名": ["P"], "规格": ["S"],
            "状态": ["上线"],
            "成本": [10.0], "门店成本": [10.0],
            "定价": [20.0],
            "毛利率": [0.5], "门店毛利率": [0.5],
        }),
        "产品出品表_Gelato": pd.DataFrame({
            "品类": ["Gelato"], "品名": ["P"], "规格": ["S"],
            "主原料": ["milk"], "配料": ["sugar"],
            "用量": [1.0], "单位成本": [5.0], "总成本": [10.0],
            "门店单位成本": [5.0], "门店总成本": [10.0],
        }),
        "总原料成本表": pd.DataFrame({
            "品项名称": ["milk", "sugar"],
            "品项类别": ["乳制品", "调味酱"],
        }),
    }
    summary, suggest = target_pricing(sheets, product_key="Gelato|P|S", target_margin=0.6, basis="store")
    assert isinstance(summary, TargetPricingResult)
    assert summary.price == 20.0
    assert summary.current_cost == 10.0
    assert summary.allowed_cost == 8.0
    assert summary.cost_gap == -2.0  # need to reduce 2 RMB
    # is_fixed=False for both, scale_required = 8/10 = 0.8
    assert summary.scale_required is not None
    assert abs(summary.scale_required - 0.8) < 1e-9


def test_target_pricing_locked_items():
    """Locked items are excluded from scale calculation."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"], "品名": ["L"], "规格": ["S"],
            "状态": ["上线"],
            "成本": [10.0], "门店成本": [10.0],
            "定价": [20.0],
            "毛利率": [0.5], "门店毛利率": [0.5],
        }),
        "产品出品表_Gelato": pd.DataFrame({
            "品类": ["Gelato", "Gelato"],
            "品名": ["L", "L"],
            "规格": ["S", "S"],
            "主原料": ["milk", ""],
            "配料": ["", "sugar"],
            "用量": [1.0, 1.0],
            "单位成本": [5.0, 5.0],
            "总成本": [5.0, 5.0],
            "门店单位成本": [5.0, 5.0],
            "门店总成本": [5.0, 5.0],
        }),
        "总原料成本表": pd.DataFrame({
            "品项名称": ["milk", "sugar"],
            "品项类别": ["乳制品", "调味酱"],
        }),
    }
    # Lock milk (5 RMB). Unchangeable=5. Need total cost=8. Adjustable_effective=5 (sugar).
    # scale = (8 - 5) / 5 = 0.6
    # Note: milk has empty category -> not fixed; sugar=调味酱 -> not fixed.
    summary, suggest = target_pricing(
        sheets, product_key="Gelato|L|S", target_margin=0.6,
        basis="store", locked_items=["milk"],
    )
    assert abs(summary.locked_cost - 5.0) < 1e-9
    assert abs(summary.adjustable_effective_cost - 5.0) < 1e-9
    assert summary.scale_required is not None
    assert abs(summary.scale_required - 0.6) < 1e-9


def test_target_pricing_three_tiers():
    """Suggestion table contains three tiers when scale is defined."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"], "品名": ["T"], "规格": ["S"],
            "状态": ["上线"],
            "成本": [10.0], "门店成本": [10.0],
            "定价": [20.0],
            "毛利率": [0.5], "门店毛利率": [0.5],
        }),
        "产品出品表_Gelato": pd.DataFrame({
            "品类": ["Gelato"], "品名": ["T"], "规格": ["S"],
            "主原料": ["milk"], "配料": ["sugar"],
            "用量": [1.0], "单位成本": [5.0], "总成本": [10.0],
            "门店单位成本": [5.0], "门店总成本": [10.0],
        }),
        "总原料成本表": pd.DataFrame({
            "品项名称": ["milk", "sugar"],
            "品项类别": ["乳制品", "调味酱"],
        }),
    }
    _, suggest = target_pricing(sheets, product_key="Gelato|T|S", target_margin=0.6, basis="store")
    assert "tier" in suggest.columns
    tiers = sorted(suggest["tier"].unique())
    assert tiers == ["acceptable", "ideal", "redline"]


def test_target_pricing_unknown_product():
    """Unknown product_key raises KeyError."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"], "品名": ["X"], "规格": ["S"],
            "状态": ["上线"],
            "成本": [10.0], "门店成本": [10.0],
            "定价": [20.0],
            "毛利率": [0.5], "门店毛利率": [0.5],
        }),
    }
    try:
        target_pricing(sheets, product_key="Gelato|unknown|S", target_margin=0.6)
        assert False, "Expected KeyError"
    except KeyError:
        pass
