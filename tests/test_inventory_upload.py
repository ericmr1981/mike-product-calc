from __future__ import annotations

from datetime import timezone
from pathlib import Path

from openpyxl import Workbook

from mike_product_calc.data.inventory_upload import (
    EXPECTED_HEADERS,
    InventoryUploadError,
    discover_inventory_files,
    parse_snapshot_at,
    prepare_inventory_rows,
)


def _build_workbook(path: Path, rows: list[list[object]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "仓库库存导出"
    ws.append(EXPECTED_HEADERS)
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_parse_snapshot_at_from_filename() -> None:
    dt = parse_snapshot_at("仓库库存导出2026年05月06日20时20分44秒.xlsx")
    assert dt.tzinfo == timezone.utc
    # 20:20:44 Asia/Shanghai -> 12:20:44 UTC
    assert dt.strftime("%Y-%m-%d %H:%M:%S") == "2026-05-06 12:20:44"


def test_prepare_inventory_rows_ok(tmp_path: Path) -> None:
    f = tmp_path / "仓库库存导出2026年05月06日20时20分44秒.xlsx"
    _build_workbook(
        f,
        [
            [
                "WP0192",
                "草莓丁",
                "1KG",
                "包",
                "辅料",
                "",
                "",
                "新天地广场",
                "GM002",
                4.0,
                4.0,
                0.0,
                0.0,
                0.0,
                80.0,
                20.0,
            ]
        ],
    )
    out = prepare_inventory_rows(f)
    assert len(out.items) == 1
    assert out.skipped_rows == 0
    assert out.errors == {}
    assert out.warnings == {}
    assert out.items[0]["item_code"] == "WP0192"
    assert out.items[0]["warehouse_code"] == "GM002"


def test_prepare_inventory_rows_warnings_and_errors(tmp_path: Path) -> None:
    f = tmp_path / "仓库库存导出2026年05月06日20时20分44秒.xlsx"
    _build_workbook(
        f,
        [
            [
                "WP0082",
                "芭乐",
                "",
                "克",
                "水果",
                "",
                "",
                "新天地广场",
                "GM002",
                -90.0,
                -90.0,
                0.0,
                0.0,
                0.0,
                -90.0,
                1.0,
            ],
            [
                "WP0082",
                "芭乐",
                "",
                "克",
                "水果",
                "",
                "",
                "新天地广场",
                "GM002",
                -90.0,
                -90.0,
                0.0,
                0.0,
                0.0,
                -90.0,
                1.0,
            ],
            [
                "",
                "缺编码",
                "",
                "克",
                "水果",
                "",
                "",
                "新天地广场",
                "GM002",
                1.0,
                1.0,
                0.0,
                0.0,
                0.0,
                1.0,
                1.0,
            ],
        ],
    )
    out = prepare_inventory_rows(f)
    assert len(out.items) == 1
    assert out.skipped_rows == 2
    assert out.warnings["negative_stock"] == 1
    assert out.warnings["empty_spec"] == 1
    assert out.errors["duplicate_item_warehouse_in_batch"] == 1
    assert out.errors["missing_required_item_code"] == 1


def test_prepare_inventory_rows_sheet_missing(tmp_path: Path) -> None:
    f = tmp_path / "bad.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    wb.save(f)
    try:
        prepare_inventory_rows(f)
    except InventoryUploadError as exc:
        assert "sheet_not_found" in str(exc)
    else:
        raise AssertionError("expected InventoryUploadError")


def test_discover_inventory_files(tmp_path: Path) -> None:
    f1 = tmp_path / "仓库库存导出2026年05月06日20时20分44秒.xlsx"
    f2 = tmp_path / "仓库库存导出2026年05月06日21时20分44秒.xlsx"
    _build_workbook(f1, [])
    _build_workbook(f2, [])
    files = discover_inventory_files(tmp_path)
    assert [p.name for p in files] == [f1.name, f2.name]
