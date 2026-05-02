from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from mike_product_calc.calc.recipe import (
    get_semi_product_recipes,
    get_brand_cost_map,
    get_brand_spec_map,
    build_recipe_table,
    _parse_spec,
    _lookup_usage_map,
    LEVEL_DIRECT,
    LEVEL_SEMI,
    LEVEL_SUB,
)

REPO = Path(__file__).resolve().parents[1]
XLSX = REPO / "data" / "蜜可诗产品库.xlsx"


def _load_sheets() -> dict[str, pd.DataFrame]:
    """Minimal workbook loader for tests."""
    from mike_product_calc.data.loader import load_workbook
    return load_workbook(XLSX).sheets


@pytest.fixture(scope="module")
def sheets():
    return _load_sheets()


def test_get_brand_cost_map(sheets):
    """总原料成本表品牌成本列读取."""
    cost_map = get_brand_cost_map(sheets)
    assert isinstance(cost_map, dict)
    # At least one entry should exist
    assert len(cost_map) > 0
    # Values should be numeric
    for name, cost in cost_map.items():
        assert isinstance(name, str)
        assert isinstance(cost, (int, float))
        assert cost >= 0


def test_get_brand_spec_map(sheets):
    """总原料成本表规格读取."""
    spec_map = get_brand_spec_map(sheets)
    assert isinstance(spec_map, dict)
    if spec_map:
        name, spec = next(iter(spec_map.items()))
        assert isinstance(name, str)
        assert isinstance(spec, str)
        assert len(spec) > 0


def test_get_semi_product_recipes(sheets):
    """半成品配方表读取."""
    recipes = get_semi_product_recipes(sheets)
    assert isinstance(recipes, dict)
    # Keys should be semi-product names, values should be lists of dicts with item/qty
    for semi_name, ingredients in recipes.items():
        assert isinstance(semi_name, str)
        assert isinstance(ingredients, list)
        if ingredients:
            ing = ingredients[0]
            assert "item" in ing
            assert "usage_qty" in ing
            assert isinstance(ing["usage_qty"], float)


def test_build_recipe_table(sheets):
    """构建配方明细表."""
    # Use profit table to find a known product_key
    from mike_product_calc.calc.profit import sku_profit_table
    profit_df = sku_profit_table(sheets, basis="store", only_status="上线")
    assert not profit_df.empty

    product_key = profit_df["product_key"].iloc[0]
    table_df = build_recipe_table(sheets, product_key=product_key, basis="store")
    assert isinstance(table_df, pd.DataFrame)
    # Required columns
    expected_cols = ["item", "usage_qty", "cost", "spec", "store_price", "brand_cost", "profit_rate"]
    for col in expected_cols:
        assert col in table_df.columns, f"Missing column: {col}"


# ── Mock data tests ──────────────────────────────────────────────


def test_get_brand_cost_map_mock():
    sheets = {
        "总原料成本表": pd.DataFrame({
            "品项名称": ["原料A", "原料B"],
            "原料价格": [10.5, 20.3],
        })
    }
    result = get_brand_cost_map(sheets)
    assert result == {"原料A": 10.5, "原料B": 20.3}


def test_get_brand_cost_map_mock_missing_sheet():
    assert get_brand_cost_map({}) == {}


def test_get_brand_cost_map_mock_missing_columns():
    sheets = {"总原料成本表": pd.DataFrame({"foo": ["a"], "bar": [1]})}
    assert get_brand_cost_map(sheets) == {}


def test_get_brand_spec_map_mock():
    sheets = {
        "总原料成本表": pd.DataFrame({
            "品项名称": ["原料A", "原料B"],
            "规格": ["1 kg", "500 g"],
        })
    }
    result = get_brand_spec_map(sheets)
    assert result == {"原料A": "1 kg", "原料B": "500 g"}


def test_parse_spec_with_units():
    assert _parse_spec("1 kg") == 1.0
    assert _parse_spec("500 g") == 0.5
    assert _parse_spec("0.5 L") == 0.5
    assert _parse_spec("250 ml") == 0.25
    assert _parse_spec("—") is None
    assert _parse_spec("") is None
    assert _parse_spec("nan") is None
    assert _parse_spec("2 斤") == 1.0
    assert _parse_spec("10") == 10.0  # no unit, keep as-is


def test_lookup_usage_map_mock():
    """_lookup_usage_map returns usage qty for all ingredients of a product."""
    sheets = {
        "产品出品表_Gelato": pd.DataFrame({
            "品类": ["Gelato", "Gelato", "Gelato"],
            "品名": ["草莓", "草莓", "草莓"],
            "规格": ["杯", "杯", "杯"],
            "主原料": ["草莓果泥", "", ""],
            "配料": ["", "全脂牛奶", "细砂糖"],
            "用量": [0.15, 0.10, 0.05],
            "单位": ["kg", "L", "kg"],
        })
    }
    result = _lookup_usage_map(sheets, "Gelato|草莓|杯")
    assert result == {
        "草莓果泥": (0.15, "kg"),
        "全脂牛奶": (0.10, "L"),
        "细砂糖": (0.05, "kg"),
    }


def test_lookup_usage_map_mock_no_match():
    sheets = {
        "产品出品表_Gelato": pd.DataFrame({
            "品类": ["Gelato"],
            "品名": ["草莓"],
            "规格": ["杯"],
            "主原料": ["草莓果泥"],
            "用量": [0.15],
            "单位": ["kg"],
        })
    }
    result = _lookup_usage_map(sheets, "Gelato|香草|杯")
    assert result == {}


def test_level_constants():
    assert LEVEL_DIRECT == 0
    assert LEVEL_SEMI == 1
    assert LEVEL_SUB == 2
