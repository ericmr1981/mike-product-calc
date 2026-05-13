"""tests/test_coverage_analysis.py"""
from __future__ import annotations

import pandas as pd
import pytest

from mike_product_calc.calc.coverage_analysis import build_coverage_matrix, compute_coverage


class TestBuildCoverageMatrix:
    def test_basic_matrix(self):
        """bom_expand_multi(qty=1) per SKU -> matrix of (sku, material, qty)."""
        # Simulate bom_expand output for 2 SKUs
        sku1_rows = pd.DataFrame([
            {"sku_key": "Gelato|A|小杯", "material": "牛奶", "level": 1,
             "unit": "kg", "gross_qty": 0.2, "purchase_unit": "kg",
             "is_semi_finished": False, "is_gap": False, "gap_reason": None},
            {"sku_key": "Gelato|A|小杯", "material": "糖", "level": 2,
             "unit": "kg", "gross_qty": 0.05, "purchase_unit": "kg",
             "is_semi_finished": False, "is_gap": False, "gap_reason": None},
        ])
        sku2_rows = pd.DataFrame([
            {"sku_key": "饮品|B|杯", "material": "牛奶", "level": 1,
             "unit": "kg", "gross_qty": 0.3, "purchase_unit": "kg",
             "is_semi_finished": False, "is_gap": False, "gap_reason": None},
        ])
        sku_dfs = {"Gelato|A|小杯": sku1_rows, "饮品|B|杯": sku2_rows}
        matrix = build_coverage_matrix(sku_dfs)
        # Matrix: index=material, columns=sku_key, values=gross_qty
        assert matrix.loc["牛奶", "Gelato|A|小杯"] == 0.2
        assert matrix.loc["牛奶", "饮品|B|杯"] == 0.3
        assert matrix.loc["糖", "Gelato|A|小杯"] == 0.05
        # 饮品|B|杯 doesn't use 糖
        assert pd.isna(matrix.loc["糖", "饮品|B|杯"]) or matrix.loc["糖", "饮品|B|杯"] == 0

    def test_skips_semi_finished(self):
        """Semi-finished items are excluded from the matrix (they expand further)."""
        rows = pd.DataFrame([
            {"sku_key": "Gelato|A|小杯", "material": "半成品奶浆",
             "level": 1, "unit": "kg", "gross_qty": 0.3, "purchase_unit": "kg",
             "is_semi_finished": True, "is_gap": False, "gap_reason": None},
            {"sku_key": "Gelato|A|小杯", "material": "牛奶",
             "level": 2, "unit": "kg", "gross_qty": 0.2, "purchase_unit": "kg",
             "is_semi_finished": False, "is_gap": False, "gap_reason": None},
        ])
        sku_dfs = {"Gelato|A|小杯": rows}
        matrix = build_coverage_matrix(sku_dfs)
        assert "半成品奶浆" not in matrix.index
        assert "牛奶" in matrix.index

    def test_empty_input(self):
        """Empty dict -> empty DataFrame."""
        matrix = build_coverage_matrix({})
        assert matrix.empty


class TestComputeCoverage:
    def test_single_sku_single_material(self):
        """Basic: 1 SKU, 1 material, compute coverage days."""
        matrix = pd.DataFrame({"Gelato|A|小杯": [0.2]}, index=pd.Index(["牛奶"]))
        matrix.index.name = "material"
        weekly_sales = {"Gelato|A|小杯": 140}  # 20/day
        inventory = {"牛奶": 50.0}
        sku_cov, mat_cov = compute_coverage(matrix, weekly_sales, inventory)

        # material: 50 / (140/7 * 0.2) = 50 / 4.0 = 12.5
        assert len(mat_cov) == 1
        assert mat_cov.iloc[0]["material"] == "牛奶"
        assert round(mat_cov.iloc[0]["coverage_days"], 1) == 12.5

        # SKU: same
        assert len(sku_cov) == 1
        assert sku_cov.iloc[0]["sku_key"] == "Gelato|A|小杯"
        assert sku_cov.iloc[0]["coverage_days"] == pytest.approx(12.5)

    def test_multi_sku_aggregation(self):
        """2 SKUs share a material -> daily consumption sums."""
        matrix = pd.DataFrame({
            "Gelato|A|小杯": [0.2],
            "饮品|B|杯": [0.3],
        }, index=pd.Index(["牛奶"]))
        matrix.index.name = "material"
        weekly_sales = {"Gelato|A|小杯": 140, "饮品|B|杯": 70}
        inventory = {"牛奶": 70.0}
        sku_cov, mat_cov = compute_coverage(matrix, weekly_sales, inventory)

        # daily: 140/7*0.2 + 70/7*0.3 = 4.0 + 3.0 = 7.0
        # coverage: 70 / 7.0 = 10.0
        assert round(mat_cov.iloc[0]["coverage_days"], 1) == 10.0

    def test_sku_coverage_is_min_of_materials(self):
        """SKU uses 2 materials -> coverage = min of both."""
        matrix = pd.DataFrame({
            "Gelato|A|小杯": [0.2, 0.05],
        }, index=pd.Index(["牛奶", "糖"]))
        matrix.index.name = "material"
        weekly_sales = {"Gelato|A|小杯": 140}  # 20/day
        inventory = {"牛奶": 50.0, "糖": 10.0}
        sku_cov, mat_cov = compute_coverage(matrix, weekly_sales, inventory)

        # 牛奶: 50/(20*0.2) = 12.5
        # 糖: 10/(20*0.05) = 10.0 -> limiting material = 糖
        assert sku_cov.iloc[0]["limiting_material"] == "糖"
        assert sku_cov.iloc[0]["coverage_days"] == pytest.approx(10.0)

    def test_safety_stock_deduction(self):
        """Safety stock is deducted from available inventory."""
        matrix = pd.DataFrame({
            "Gelato|A|小杯": [0.2],
        }, index=pd.Index(["牛奶"]))
        matrix.index.name = "material"
        weekly_sales = {"Gelato|A|小杯": 140}
        inventory = {"牛奶": 50.0}
        safety_stock = {"牛奶": 10.0}
        sku_cov, mat_cov = compute_coverage(matrix, weekly_sales, inventory, safety_stock)
        # effective: 50-10=40, daily: 4.0 -> 10.0
        assert round(mat_cov.iloc[0]["coverage_days"], 1) == 10.0

    def test_zero_sales_sku_excluded(self):
        """SKU with 0 weekly sales doesn't participate in material consumption."""
        matrix = pd.DataFrame({
            "Gelato|A|小杯": [0.2],
            "饮品|B|杯": [0.3],
        }, index=pd.Index(["牛奶"]))
        matrix.index.name = "material"
        weekly_sales = {"Gelato|A|小杯": 140, "饮品|B|杯": 0}
        inventory = {"牛奶": 50.0}
        sku_cov, mat_cov = compute_coverage(matrix, weekly_sales, inventory)
        # daily: only 140/7*0.2 = 4.0
        assert round(mat_cov.iloc[0]["coverage_days"], 1) == 12.5
        # zero-sales SKU: coverage_days should be None/NaN
        zero_sku = sku_cov[sku_cov["sku_key"] == "饮品|B|杯"]
        assert pd.isna(zero_sku.iloc[0]["coverage_days"])

    def test_no_inventory_for_material(self):
        """Material with no inventory record -> coverage_days = 0, status = 紧急."""
        matrix = pd.DataFrame({
            "Gelato|A|小杯": [0.2],
        }, index=pd.Index(["未知原料"]))
        matrix.index.name = "material"
        weekly_sales = {"Gelato|A|小杯": 140}
        inventory = {"牛奶": 50.0}  # 未知原料 not in inventory
        sku_cov, mat_cov = compute_coverage(matrix, weekly_sales, inventory)
        assert mat_cov.iloc[0]["coverage_days"] == 0.0
        assert mat_cov.iloc[0]["status"] == "紧急"

    def test_material_not_consumed(self):
        """Material in inventory but not used by any SKU -> not in material output."""
        matrix = pd.DataFrame({
            "Gelato|A|小杯": [0.2],
        }, index=pd.Index(["牛奶"]))
        matrix.index.name = "material"
        weekly_sales = {"Gelato|A|小杯": 140}
        inventory = {"牛奶": 50.0, "无关原料": 100.0}
        sku_cov, mat_cov = compute_coverage(matrix, weekly_sales, inventory)
        # 无关原料 not in matrix, so not in material coverage output
        assert "无关原料" not in mat_cov["material"].values

    def test_gap_material_flagged(self):
        """Gap materials are flagged and don't affect SKU coverage."""
        matrix = pd.DataFrame({
            "Gelato|A|小杯": [0.2, 0.0],
        }, index=pd.Index(["牛奶", "糖"]))
        matrix.index.name = "material"
        # Simulate gap via metadata (material not in inventory + is_gap=True)
        weekly_sales = {"Gelato|A|小杯": 140}
        inventory = {"牛奶": 50.0}
        gap_materials = {"糖": "no price data"}
        sku_cov, mat_cov = compute_coverage(matrix, weekly_sales, inventory,
                                            gap_materials=gap_materials)
        # 糖 is a gap — SKU coverage should only consider 牛奶
        assert sku_cov.iloc[0]["coverage_days"] == pytest.approx(12.5)

    def test_material_zero_consumption(self):
        """Material in BOM but zero consumption -> coverage_days = inf, status = 充足."""
        matrix = pd.DataFrame({
            "Gelato|A|小杯": [0.2],
        }, index=pd.Index(["牛奶"]))
        matrix.index.name = "material"
        weekly_sales = {"Gelato|A|小杯": 0}  # zero sales
        inventory = {"牛奶": 50.0}
        sku_cov, mat_cov = compute_coverage(matrix, weekly_sales, inventory)
        assert mat_cov.iloc[0]["coverage_days"] is None
        assert mat_cov.iloc[0]["status"] == "∞"

    def test_coverage_status_classification(self):
        """Verify status thresholds: >=30 充足, 14-29 一般, 7-13 不足, <7 紧急."""
        # daily consumption = 1.0 per material (10/day * 0.1 qty)
        # coverage thresholds: >=30 充足, 14-29 一般, 7-13 不足, <7 紧急
        inventory_scenarios = {"充足原料": 30.0, "一般原料": 20.0, "不足原料": 10.0, "紧急原料": 5.0}
        matrix_data = {}
        for mat, inv in inventory_scenarios.items():
            matrix_data[mat] = [0.1]  # one SKU uses each material
        matrix = pd.DataFrame(matrix_data, index=pd.Index(["SKU1"]))
        matrix = matrix.T
        matrix.index.name = "material"
        matrix.columns = ["SKU1"]
        weekly_sales = {"SKU1": 70}  # 10/day
        # daily per material: 10*0.1 = 1.0
        # coverage = inv / 1.0
        sku_cov, mat_cov = compute_coverage(matrix, weekly_sales, inventory_scenarios)
        statuses = dict(zip(mat_cov["material"], mat_cov["status"]))
        assert statuses["充足原料"] == "充足"
        assert statuses["一般原料"] == "一般"
        assert statuses["不足原料"] == "不足"
        assert statuses["紧急原料"] == "紧急"
