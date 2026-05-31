from pathlib import Path

import inspect
import openpyxl
import pytest
from openpyxl import Workbook
from unittest.mock import MagicMock

from mike_product_calc.data.supabase_client import MpcSupabaseClient


def test_client_has_check_delivery_methods():
    methods = {name for name, _ in inspect.getmembers(MpcSupabaseClient, predicate=inspect.isfunction)}
    required = {
        "create_check_batch", "find_check_batch", "update_check_batch",
        "insert_check_items", "list_check_batches",
        "create_delivery_batch", "find_delivery_batch", "update_delivery_batch",
        "insert_delivery_items", "list_delivery_batches",
    }
    missing = required - methods
    assert not missing, f"Missing client methods: {missing}"


# ---------------------------------------------------------------------------
# Upload module tests
# ---------------------------------------------------------------------------

CHECK_EXPECTED_HEADERS = [
    "品项编码",
    "品项名称",
    "品项规格",
    "品项类别",
    "库存单位",
    "初盘数量",
    "复盘数量",
    "系统库存",
    "盘点差异",
    "库存均价",
    "差异金额",
    "明细状态",
]

DELIVERY_EXPECTED_HEADERS = [
    "品项编码",
    "品项名称",
    "品项规格",
    "品项类别",
    "库存单位",
    "数量",
]


def _make_check_xlsx(tmp_path: Path, rows: list[dict]) -> Path:
    """Create a test inventory check xlsx with the expected format."""
    fp = tmp_path / "盘点单明细 2026年05月25日.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "0"
    ws.append(CHECK_EXPECTED_HEADERS)
    for r in rows:
        ws.append([r.get(h, "") for h in CHECK_EXPECTED_HEADERS])
    wb.save(fp)
    return fp


def _make_delivery_xlsx(tmp_path: Path, rows: list[dict]) -> Path:
    """Create a test delivery xlsx with the expected format."""
    fp = tmp_path / "到货记录20250529.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "0"
    ws.append(DELIVERY_EXPECTED_HEADERS)
    for r in rows:
        ws.append([r.get(h, "") for h in DELIVERY_EXPECTED_HEADERS])
    wb.save(fp)
    return fp


def test_parse_check_at_from_filename():
    from mike_product_calc.data.inventory_check_upload import parse_check_at_from_filename

    dt = parse_check_at_from_filename("盘点单明细 2026年05月25日.xlsx")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 5
    assert dt.day == 25

    # File with time
    dt2 = parse_check_at_from_filename("盘点品项导出2026年05月31日22时00分01秒.xlsx")
    assert dt2 is not None
    assert dt2.day == 31
    assert dt2.hour == 22

    # Non-matching filename returns None
    assert parse_check_at_from_filename("仓库库存导出.xlsx") is None


def test_parse_delivery_at_from_filename():
    from mike_product_calc.data.inventory_check_upload import parse_delivery_at_from_filename

    dt = parse_delivery_at_from_filename("到货记录20250529.xlsx")
    assert dt is not None
    assert dt.year == 2025
    assert dt.month == 5
    assert dt.day == 29

    # Non-matching filename returns None
    assert parse_delivery_at_from_filename("盘点单明细.xlsx") is None


def test_file_sha256(tmp_path):
    from mike_product_calc.data.inventory_check_upload import file_sha256

    fp = tmp_path / "test.txt"
    fp.write_text("hello")
    sha = file_sha256(fp)
    assert sha == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_prepare_check_inventory_rows(tmp_path):
    from mike_product_calc.data.inventory_check_upload import prepare_check_inventory_rows

    rows_data = [
        {
            "品项编码": "WP0013",
            "品项名称": "冰碗5oz",
            "品项规格": "1000个/箱",
            "品项类别": "包材",
            "库存单位": "箱",
            "初盘数量": 1.8,
            "复盘数量": 1.8,
            "系统库存": 1.818,
            "盘点差异": -0.018,
            "库存均价": 328,
            "差异金额": -5.90,
            "明细状态": "已完成",
        },
        {
            "品项编码": "WP0014",
            "品项名称": "冰碗8oz",
            "品项规格": "1000个/箱",
            "品项类别": "包材",
            "库存单位": "箱",
            "初盘数量": 0.8,
            "复盘数量": 0.8,
            "系统库存": 0.850,
            "盘点差异": -0.050,
            "库存均价": 448,
            "差异金额": -22.40,
            "明细状态": "已完成",
        },
    ]
    fp = _make_check_xlsx(tmp_path, rows_data)
    result = prepare_check_inventory_rows(fp)
    assert len(result.items) == 2
    assert result.items[0]["item_code"] == "WP0013"
    assert result.items[0]["system_qty"] == 1.818
    assert result.items[0]["avg_price"] == 328.0
    assert result.items[0]["category"] == "包材"
    assert result.skipped_rows == 0


def test_prepare_check_inventory_rows_empty_required(tmp_path):
    from mike_product_calc.data.inventory_check_upload import prepare_check_inventory_rows

    rows_data = [
        {
            "品项编码": "",
            "品项名称": "冰碗5oz",
            "品项规格": "1000个/箱",
            "品项类别": "包材",
            "库存单位": "箱",
            "初盘数量": 1.8,
            "复盘数量": 1.8,
            "系统库存": 1.818,
            "盘点差异": -0.018,
            "库存均价": 328,
            "差异金额": -5.90,
            "明细状态": "已完成",
        },
    ]
    fp = _make_check_xlsx(tmp_path, rows_data)
    result = prepare_check_inventory_rows(fp)
    assert result.skipped_rows == 1
    assert result.errors.get("missing_required_item_code", 0) == 1


def test_prepare_delivery_rows(tmp_path):
    from mike_product_calc.data.inventory_check_upload import prepare_delivery_rows

    rows_data = [
        {
            "品项编码": "WP0013",
            "品项名称": "冰碗5oz",
            "品项规格": "1000个/箱",
            "品项类别": "包材",
            "库存单位": "箱",
            "数量": 5,
        },
        {
            "品项编码": "WP0014",
            "品项名称": "冰碗8oz",
            "品项规格": "1000个/箱",
            "品项类别": "包材",
            "库存单位": "箱",
            "数量": 3,
        },
    ]
    fp = _make_delivery_xlsx(tmp_path, rows_data)
    result = prepare_delivery_rows(fp)
    assert len(result.items) == 2
    assert result.items[0]["item_code"] == "WP0013"
    assert result.items[0]["delivery_qty"] == 5.0
    assert result.items[0]["category"] == "包材"
    assert result.skipped_rows == 0


def test_prepare_delivery_rows_empty_code(tmp_path):
    from mike_product_calc.data.inventory_check_upload import prepare_delivery_rows

    rows_data = [
        {
            "品项编码": "",
            "品项名称": "冰碗5oz",
            "品项规格": "1000个/箱",
            "品项类别": "包材",
            "库存单位": "箱",
            "数量": 5,
        },
    ]
    fp = _make_delivery_xlsx(tmp_path, rows_data)
    result = prepare_delivery_rows(fp)
    assert result.skipped_rows == 1
    assert result.errors.get("missing_required_item_code", 0) == 1


def test_sync_check_inventory_file_dry_run(tmp_path):
    from mike_product_calc.data.inventory_check_upload import sync_check_inventory_file

    rows_data = [
        {
            "品项编码": "WP0013",
            "品项名称": "冰碗5oz",
            "品项规格": "1000个/箱",
            "品项类别": "包材",
            "库存单位": "箱",
            "初盘数量": 1.8, "复盘数量": 1.8,
            "系统库存": 1.818, "盘点差异": -0.018,
            "库存均价": 328, "差异金额": -5.90,
            "明细状态": "已完成",
        },
    ]
    fp = _make_check_xlsx(tmp_path, rows_data)
    result = sync_check_inventory_file(client=None, file_path=fp, dry_run=True)
    assert result["status"] == "dry_run"
    assert result["inserted_rows"] == 1
    assert result["skipped_rows"] == 0


def test_sync_check_inventory_file_duplicate(tmp_path):
    from mike_product_calc.data.inventory_check_upload import sync_check_inventory_file

    rows_data = [
        {
            "品项编码": "WP0013",
            "品项名称": "冰碗5oz",
            "品项规格": "1000个/箱",
            "品项类别": "包材",
            "库存单位": "箱",
            "初盘数量": 1.8, "复盘数量": 1.8,
            "系统库存": 1.818, "盘点差异": -0.018,
            "库存均价": 328, "差异金额": -5.90,
            "明细状态": "已完成",
        },
    ]
    fp = _make_check_xlsx(tmp_path, rows_data)

    mock_client = MagicMock(spec=MpcSupabaseClient)
    mock_client.find_check_batch.return_value = {"id": "existing-batch-id"}

    result = sync_check_inventory_file(client=mock_client, file_path=fp)
    assert result["status"] == "skipped_duplicate"
    assert result["batch_id"] == "existing-batch-id"
    assert result["inserted_rows"] == 0
    mock_client.find_check_batch.assert_called_once()


def test_sync_check_inventory_file_full_flow(tmp_path):
    from mike_product_calc.data.inventory_check_upload import sync_check_inventory_file

    rows_data = [
        {
            "品项编码": "WP0013",
            "品项名称": "冰碗5oz",
            "品项规格": "1000个/箱",
            "品项类别": "包材",
            "库存单位": "箱",
            "初盘数量": 1.8, "复盘数量": 1.8,
            "系统库存": 1.818, "盘点差异": -0.018,
            "库存均价": 328, "差异金额": -5.90,
            "明细状态": "已完成",
        },
    ]
    fp = _make_check_xlsx(tmp_path, rows_data)

    mock_client = MagicMock(spec=MpcSupabaseClient)
    mock_client.find_check_batch.return_value = None
    mock_client.create_check_batch.return_value = {"id": "new-batch-id"}

    result = sync_check_inventory_file(client=mock_client, file_path=fp)
    assert result["status"] == "imported"
    assert result["batch_id"] == "new-batch-id"
    assert result["inserted_rows"] == 1
    mock_client.find_check_batch.assert_called_once()
    mock_client.create_check_batch.assert_called_once()
    mock_client.insert_check_items.assert_called_once()
    mock_client.update_check_batch.assert_called_once()


def test_sync_delivery_file_full_flow(tmp_path):
    from mike_product_calc.data.inventory_check_upload import sync_delivery_file

    rows_data = [
        {
            "品项编码": "WP0013",
            "品项名称": "冰碗5oz",
            "品项规格": "1000个/箱",
            "品项类别": "包材",
            "库存单位": "箱",
            "数量": 5,
        },
    ]
    fp = _make_delivery_xlsx(tmp_path, rows_data)

    mock_client = MagicMock(spec=MpcSupabaseClient)
    mock_client.find_delivery_batch.return_value = None
    mock_client.create_delivery_batch.return_value = {"id": "new-delivery-id"}

    result = sync_delivery_file(client=mock_client, file_path=fp)
    assert result["status"] == "imported"
    assert result["batch_id"] == "new-delivery-id"
    assert result["inserted_rows"] == 1
    mock_client.find_delivery_batch.assert_called_once()
    mock_client.create_delivery_batch.assert_called_once()
