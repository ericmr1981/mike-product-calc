from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest
from mike_product_calc.sync.excel_sync import (
    SyncResult,
    preview_sync_raw_materials,
    execute_sync_raw_materials,
    preview_sync_raw_materials_two_files,
    execute_sync_raw_materials_two_files,
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


def test_preview_sync_raw_materials_detects_unit_change():
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = [
        {
            "name": "牛奶",
            "code": "RM001",
            "category": "乳制品",
            "item_type": "普通",
            "unit": "瓶",
            "unit_amount": 1.0,
            "base_price": 10.0,
            "final_price": 12.0,
            "status": "上线",
        }
    ]
    sheets = {
        "总原料成本表": pd.DataFrame(
            [
                {
                    "品项编码": "RM001",
                    "品项名称": "牛奶",
                    "品项类别": "乳制品",
                    "品项类型": "普通",
                    "订货单位": "箱",
                    "单位量": 1.0,
                    "加价前单价": 10.0,
                    "加价后单价": 12.0,
                    "生效状态": "已生效",
                }
            ]
        )
    }
    result = preview_sync_raw_materials(sheets, mock_client)
    assert len(result) == 1
    assert result[0]["action"] == "update"
    assert "unit" in result[0]["fields_changed"]


def test_execute_sync_raw_materials_counts_updates_for_non_price_fields():
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = [
        {
            "name": "牛奶",
            "code": "RM001",
            "category": "乳制品",
            "item_type": "普通",
            "unit": "瓶",
            "unit_amount": 1.0,
            "base_price": 10.0,
            "final_price": 12.0,
            "status": "上线",
        }
    ]
    sheets = {
        "总原料成本表": pd.DataFrame(
            [
                {
                    "品项编码": "RM001",
                    "品项名称": "牛奶",
                    "品项类别": "乳制品",
                    "品项类型": "普通",
                    "订货单位": "箱",
                    "单位量": 1.0,
                    "加价前单价": 10.0,
                    "加价后单价": 12.0,
                    "生效状态": "已生效",
                }
            ]
        )
    }

    result = execute_sync_raw_materials(sheets, mock_client, resolve_conflicts="skip")
    assert result.inserts == 0
    assert result.updates == 1
    mock_client.upsert_raw_materials.assert_called_once()


def test_parse_raw_materials_with_template_export_sheet_name():
    from mike_product_calc.sync.excel_sync import _parse_raw_materials

    sheets = {
        "模板加价规则导出": pd.DataFrame(
            [
                {
                    "模板编号": "1",
                    "品项编码": "WP0001",
                    "品项名称": "测试原料",
                    "品项类型": "普通",
                    "品项类别": "包材",
                    "订货单位": "箱",
                    "生效状态": "已生效",
                    "加价前单价": 10,
                    "加价后单价": 12,
                }
            ]
        )
    }
    rows = _parse_raw_materials(sheets)
    assert len(rows) == 1
    assert rows[0]["name"] == "测试原料"
    assert rows[0]["code"] == "WP0001"


def test_preview_sync_raw_materials_two_files_uses_expected_field_mapping():
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = []
    item_sheets = {
        "品项导出": pd.DataFrame(
            [
                {
                    "品项编码": "WP0001",
                    "品项名称": "测试原料",
                    "品项类别": "包材",
                    "库存单位": "袋",
                    "消耗单位数量值": 2000,
                    "是否启用": "是",
                }
            ]
        )
    }
    markup_sheets = {
        "模板加价规则导出": pd.DataFrame(
            [
                {
                    "品项编码": "WP0001",
                    "品项名称": "测试原料",
                    "品项类型": "普通",
                    "品项类别": "包材",
                    "订货单位": "箱",
                    "生效状态": "已生效",
                    "加价前单价": 10,
                    "加价后单价": 12,
                }
            ]
        )
    }

    result = preview_sync_raw_materials_two_files(item_sheets, markup_sheets, mock_client)
    assert len(result) == 1
    assert result[0]["action"] == "insert"


def test_execute_sync_raw_materials_two_files_uses_expected_field_mapping():
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = []
    mock_client.upsert_raw_materials.return_value = []
    item_sheets = {
        "品项导出": pd.DataFrame(
            [
                {
                    "品项编码": "WP0001",
                    "品项名称": "测试原料",
                    "品项类别": "包材",
                    "库存单位": "袋",
                    "消耗单位数量值": 2000,
                    "是否启用": "是",
                }
            ]
        )
    }
    markup_sheets = {
        "模板加价规则导出": pd.DataFrame(
            [
                {
                    "品项编码": "WP0001",
                    "品项名称": "测试原料",
                    "品项类型": "普通",
                    "品项类别": "包材",
                    "订货单位": "箱",
                    "生效状态": "已生效",
                    "加价前单价": 10,
                    "加价后单价": 12,
                }
            ]
        )
    }

    result = execute_sync_raw_materials_two_files(item_sheets, markup_sheets, mock_client)
    assert result.inserts == 1
    assert result.updates == 0
    mock_client.upsert_raw_materials.assert_called_once()
    upsert_records = mock_client.upsert_raw_materials.call_args.args[0]
    assert len(upsert_records) == 1
    rec = upsert_records[0]
    assert rec["unit"] == "袋"
    assert rec["unit_amount"] == 2000
    assert rec["base_price"] == 10
    assert rec["final_price"] == 12
    assert rec["item_consume_unit_qty"] == 2000
    assert rec["markup_mode"] == ""
    assert rec["item_raw_payload"]["品项编码"] == "WP0001"
    assert rec["markup_raw_payload"]["品项编码"] == "WP0001"


def test_execute_sync_raw_materials_two_files_allows_missing_price():
    mock_client = MagicMock()
    mock_client.list_raw_materials.return_value = []
    mock_client.upsert_raw_materials.return_value = []
    item_sheets = {
        "品项导出": pd.DataFrame(
            [
                {
                    "品项编码": "WP0002",
                    "品项名称": "无价格原料",
                    "品项类别": "包材",
                    "库存单位": "个",
                    "消耗单位数量值": 1,
                    "是否启用": "是",
                }
            ]
        )
    }
    markup_sheets = {"模板加价规则导出": pd.DataFrame(columns=["品项编码", "品项名称", "加价前单价", "加价后单价"])}

    result = execute_sync_raw_materials_two_files(item_sheets, markup_sheets, mock_client)
    assert result.inserts == 1
    assert result.updates == 0
    mock_client.upsert_raw_materials.assert_called_once()
    upsert_records = mock_client.upsert_raw_materials.call_args.args[0]
    rec = upsert_records[0]
    assert rec["code"] == "WP0002"
    assert rec["base_price"] is None
    assert rec["final_price"] is None


def test_preview_sync_raw_materials_two_files_matches_by_code_only():
    mock_client = MagicMock()
    # Same name exists in DB but code different: should be treated as insert.
    mock_client.list_raw_materials.return_value = [
        {
            "code": "OLD0001",
            "name": "同名不同编码",
            "category": "包材",
            "item_type": "普通",
            "unit": "个",
            "unit_amount": 1,
            "base_price": 1,
            "final_price": 2,
            "status": "上线",
        }
    ]
    item_sheets = {
        "品项导出": pd.DataFrame(
            [
                {
                    "品项编码": "NEW0001",
                    "品项名称": "同名不同编码",
                    "品项类别": "包材",
                    "库存单位": "个",
                    "消耗单位数量值": 1,
                    "是否启用": "是",
                }
            ]
        )
    }
    markup_sheets = {"模板加价规则导出": pd.DataFrame(columns=["品项编码", "品项名称", "加价前单价", "加价后单价"])}

    result = preview_sync_raw_materials_two_files(item_sheets, markup_sheets, mock_client)
    assert len(result) == 1
    assert result[0]["action"] == "insert"
