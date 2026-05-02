from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from mike_product_calc.calc.recipe import (
    get_semi_product_recipes,
    get_brand_cost_map,
    get_brand_spec_map,
    build_recipe_table,
    RecipeRow,
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
