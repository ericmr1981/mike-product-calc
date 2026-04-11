from __future__ import annotations

from pathlib import Path

import pandas as pd

from mike_product_calc.data.loader import load_workbook
from mike_product_calc.data.validator import validate_workbook


def _write_minimal_xlsx(path: Path, *, sheet_count: int = 13):
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        for i in range(sheet_count):
            df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
            df.to_excel(w, sheet_name=f"S{i+1}", index=False)


def test_load_workbook_reads_all_sheets(tmp_path: Path):
    p = tmp_path / "wb.xlsx"
    _write_minimal_xlsx(p)

    wb = load_workbook(p)
    assert len(wb.sheets) == 13
    assert "S1" in wb.sheets
    assert wb.sheets["S1"].shape[0] == 2


def test_validate_workbook_warns_on_sheet_count_mismatch(tmp_path: Path):
    p = tmp_path / "wb.xlsx"
    _write_minimal_xlsx(p, sheet_count=2)

    wb = load_workbook(p)
    issues = validate_workbook(wb.sheets)
    assert any(i.rule == "sheet_count" for i in issues)


def test_cross_sheet_missing_product_row_and_price_missing():
    # Minimal fake workbook (only relevant sheets) to exercise F-001 rules.
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame(
            {
                "品类": ["Gelato"],
                "品名": ["A"],
                "规格": ["大"],
                "状态": ["上线"],
                "成本": [10.0],
                "门店成本": [11.0],
                "定价": [None],  # should trigger price_missing
                "毛利率": [0.1],
                "门店毛利率": [0.1],
            }
        ),
        # cost sheet intentionally missing this product => missing_product_row
        "产品成本计算表_Gelato": pd.DataFrame(
            {
                "品类": [],
                "品名": [],
                "100克成本": [],
                "制作类型": [],
                "规格": [],
                "状态": [],
                "成本": [],
                "单位成本": [],
                "门店成本": [],
                "门店单位成本": [],
            }
        ),
        "产品出品表_Gelato": pd.DataFrame(
            {
                "品类": [],
                "品名": [],
                "规格": [],
                "主原料": [],
                "配料": [],
                "用量": [],
                "单位成本": [],
                "总成本": [],
                "门店单位成本": [],
                "门店总成本": [],
            }
        ),
        # pad to 13 sheets to avoid sheet_count warning affecting this test
        **{f"S{i}": pd.DataFrame({"a": [1]}) for i in range(1, 11)},
    }

    issues = validate_workbook(sheets)
    assert any(i.rule == "missing_product_row" and i.severity == "error" for i in issues)
    assert any(i.rule == "price_missing" and i.severity == "error" for i in issues)


def test_cross_sheet_cost_mismatch():
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame(
            {
                "品类": ["Gelato"],
                "品名": ["A"],
                "规格": ["大"],
                "状态": ["上线"],
                "成本": [10.0],
                "门店成本": [11.0],
                "定价": [20.0],
                "毛利率": [0.1],
                "门店毛利率": [0.1],
            }
        ),
        "产品成本计算表_Gelato": pd.DataFrame(
            {
                "品类": ["Gelato"],
                "品名": ["A"],
                "100克成本": [0.0],
                "制作类型": ["X"],
                "规格": ["大"],
                "状态": ["上线"],
                "成本": [12.0],
                "单位成本": [0.0],
                "门店成本": [11.0],
                "门店单位成本": [0.0],
            }
        ),
        "产品出品表_Gelato": pd.DataFrame(
            {
                "品类": ["Gelato"],
                "品名": ["A"],
                "规格": ["大"],
                "主原料": ["A"],
                "配料": ["x"],
                "用量": [1.0],
                "单位成本": [1.0],
                "总成本": [1.0],
                "门店单位成本": [1.0],
                "门店总成本": [1.0],
            }
        ),
        **{f"S{i}": pd.DataFrame({"a": [1]}) for i in range(1, 11)},
    }

    issues = validate_workbook(sheets)
    assert any(i.rule == "cost_mismatch" for i in issues)

