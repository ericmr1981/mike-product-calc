from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest
from mike_product_calc.sync.excel_sync import (
    SyncResult,
    preview_sync_raw_materials,
    execute_sync_raw_materials,
    preview_sync_products_recipes,
    execute_sync_products_recipes,
    preview_sync_serving_specs,
    execute_sync_serving_specs,
)

REPO = Path(__file__).resolve().parents[1]
XLSX = REPO / "data" / "蜜可诗产品库.xlsx"


def _make_sheets() -> dict[str, pd.DataFrame]:
    from mike_product_calc.data.loader import load_workbook
    return load_workbook(XLSX).sheets


@pytest.fixture(scope="module")
def sheets():
    return _make_sheets()


def test_preview_sync_raw_materials(sheets):
    """预览原料同步返回差异条目."""
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = []
    result = preview_sync_raw_materials(sheets, mock_client)
    assert isinstance(result, list)
    assert len(result) > 0  # 总原料成本表非空
    assert "name" in result[0]
    assert "action" in result[0]


def test_preview_sync_products_recipes(sheets):
    """预览产品配方同步返回差异."""
    mock_client = MagicMock()
    mock_client.list_products.return_value = []
    mock_client.list_recipes.return_value = []
    result = preview_sync_products_recipes(sheets, mock_client)
    assert isinstance(result, list)
    assert len(result) > 0


def test_execute_sync_raw_materials(sheets):
    """执行原料同步返回 SyncResult."""
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = []
    mock_client.upsert_raw_materials.return_value = []
    result = execute_sync_raw_materials(sheets, mock_client, resolve_conflicts="skip")
    assert isinstance(result, SyncResult)
    assert result.inserts >= 0
