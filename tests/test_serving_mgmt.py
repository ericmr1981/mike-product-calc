from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from mike_product_calc.calc.serving_mgmt import (
    get_serving_specs_with_toppings,
    get_final_products,
    format_spec_for_display,
)


def test_get_serving_specs_with_toppings():
    mock_client = MagicMock()
    mock_client.list_serving_specs.return_value = [
        {"id": "s1", "spec_name": "小杯", "quantity": 120,
         "serving_spec_toppings": [{"material_id": "m1", "quantity": 1}]},
    ]
    result = get_serving_specs_with_toppings(mock_client, "p1")
    assert len(result) == 1
    assert result[0]["spec_name"] == "小杯"


def test_get_final_products():
    mock_client = MagicMock()
    all_products = [
        {"id": "p1", "name": "木姜子甜橙", "is_final_product": True},
        {"id": "p2", "name": "半成品A", "is_final_product": False},
    ]
    def mock_list_products(is_final=None):
        if is_final is True:
            return [p for p in all_products if p["is_final_product"]]
        if is_final is False:
            return [p for p in all_products if not p["is_final_product"]]
        return list(all_products)
    mock_client.list_products.side_effect = mock_list_products
    result = get_final_products(mock_client)
    assert len(result) == 1
    assert result[0]["name"] == "木姜子甜橙"


def test_format_spec_for_display():
    spec = {
        "id": "s1",
        "spec_name": "小杯",
        "quantity": 120,
        "packaging_id": "pkg1",
        "serving_spec_toppings": [
            {"material_id": {"name": "冻干碎粒"}, "quantity": 1},
        ],
    }
    result = format_spec_for_display(spec)
    assert result["规格"] == "小杯"
    assert "冻干碎粒" in result["附加配料"]
