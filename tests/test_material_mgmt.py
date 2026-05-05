from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from mike_product_calc.calc.material_mgmt import (
    get_categories,
    get_material_stats,
    search_materials,
)

def test_get_categories():
    """get_categories returns sorted unique categories."""
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = [
        {"category": "调味酱"},
        {"category": "包材"},
        {"category": "调味酱"},
        {"category": "乳制品"},
    ]
    result = get_categories(mock_client)
    assert result == sorted(["调味酱", "包材", "乳制品"])

def test_get_material_stats():
    """get_material_stats returns counts by status and category."""
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = [
        {"status": "已生效", "category": "调味酱"},
        {"status": "已生效", "category": "调味酱"},
        {"status": "已失效", "category": "包材"},
    ]
    stats = get_material_stats(mock_client)
    assert stats["total"] == 3
    assert stats["active"] == 2
    assert stats["inactive"] == 1
    assert stats["by_category"]["调味酱"] == 2

def test_search_materials():
    """search_materials filters by search term and category."""
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = [
        {"name": "橙子酱", "category": "调味酱", "status": "已生效"},
        {"name": "苹果酱", "category": "调味酱", "status": "已生效"},
    ]
    result = search_materials(mock_client, search="橙子", category="调味酱")
    assert len(result) == 1
    assert result[0]["name"] == "橙子酱"
