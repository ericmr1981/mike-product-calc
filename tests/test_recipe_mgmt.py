from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from mike_product_calc.calc.recipe_mgmt import (
    get_product_with_recipes,
    build_ingredient_pool,
)

def test_get_product_with_recipes():
    mock_client = MagicMock()
    mock_client.get_product.return_value = {"id": "p1", "name": "测试产品"}
    mock_client.list_recipes.return_value = [
        {"id": "r1", "quantity": 100, "ingredient_source": "raw", "raw_material_id": {"name": "橙子酱"}},
    ]
    result = get_product_with_recipes(mock_client, "p1")
    assert result["product"]["name"] == "测试产品"
    assert len(result["recipes"]) == 1

def test_build_ingredient_pool():
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = [
        {"id": "rm1", "name": "橙子酱", "category": "调味酱", "final_price": 35.84},
    ]
    mock_client.list_products.return_value = [
        {"id": "p1", "name": "木姜子甜橙 2.0", "is_final_product": False},
    ]
    pool = build_ingredient_pool(mock_client)
    assert "raw_materials" in pool
    assert "products" in pool
    assert len(pool["raw_materials"]) == 1
    assert len(pool["products"]) == 1
