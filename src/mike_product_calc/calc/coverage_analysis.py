"""coverage_analysis.py — Coverage days analysis based on BOM + inventory + sales forecast."""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd


def build_coverage_matrix(
    sku_bom_dfs: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Build a material x SKU matrix of per-unit material quantities.

    Args:
        sku_bom_dfs: {sku_key: DataFrame from bom_expand(sku_key, plan_qty=1)}
                     Only raw materials (is_semi_finished=False) are included.

    Returns:
        DataFrame with material as index, SKU keys as columns,
        values = gross_qty (effective qty per unit, including loss rate).
        Missing combinations are filled with 0.
    """
    if not sku_bom_dfs:
        return pd.DataFrame()

    records = []
    for sku_key, df in sku_bom_dfs.items():
        if df.empty:
            continue
        raw = df[df["is_semi_finished"] == False].copy()
        for _, row in raw.iterrows():
            records.append({
                "sku_key": sku_key,
                "material": row["material"],
                "qty_per_unit": row.get("gross_qty", row.get("purchase_qty", 0)),
            })

    if not records:
        return pd.DataFrame()

    matrix = pd.DataFrame(records).pivot_table(
        index="material", columns="sku_key", values="qty_per_unit",
        aggfunc="sum", fill_value=0.0,
    )
    matrix.index.name = "material"
    return matrix


def _classify_coverage(days: Optional[float]) -> str:
    """Classify coverage days into status level."""
    if days is None:
        return "-"
    if days >= 30:
        return "充足"
    if days >= 14:
        return "一般"
    if days >= 7:
        return "不足"
    return "紧急"


def compute_coverage(
    bom_matrix: pd.DataFrame,
    weekly_sales: Dict[str, float],
    inventory: Dict[str, float],
    safety_stock: Optional[Dict[str, float]] = None,
    gap_materials: Optional[Dict[str, str]] = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute coverage days for SKUs and materials.

    Args:
        bom_matrix: material x SKU matrix from build_coverage_matrix().
        weekly_sales: {sku_key: weekly_sales_qty}.
        inventory: {material_name: available_qty}.
        safety_stock: {material_name: safety_stock_qty}. Default empty.
        gap_materials: {material_name: gap_reason}. SKUs won't be limited by gaps.

    Returns:
        (sku_coverage_df, material_coverage_df):
        - sku_coverage_df columns: sku_key, limiting_material, coverage_days, status
        - material_coverage_df columns: material, available_qty, safety_stock,
          effective_qty, daily_consumption, coverage_days, status
    """
    if bom_matrix.empty:
        empty_sku = pd.DataFrame(columns=["sku_key", "limiting_material", "coverage_days", "status"])
        empty_mat = pd.DataFrame(columns=["material", "available_qty", "safety_stock",
                                            "effective_qty", "daily_consumption",
                                            "coverage_days", "status"])
        return empty_sku, empty_mat

    safety_stock = safety_stock or {}
    gap_materials = gap_materials or {}

    # Filter to SKUs with positive weekly sales
    active_skus = {k: v for k, v in weekly_sales.items() if v > 0}
    if not active_skus:
        # All SKUs have zero sales — no consumption
        sku_rows = []
        for sku in bom_matrix.columns:
            sku_rows.append({
                "sku_key": sku,
                "limiting_material": None,
                "coverage_days": None,
                "status": "-",
            })
        mat_rows = []
        for mat in bom_matrix.index:
            mat_rows.append({
                "material": mat,
                "available_qty": inventory.get(mat, 0),
                "safety_stock": safety_stock.get(mat, 0),
                "effective_qty": max(0, inventory.get(mat, 0) - safety_stock.get(mat, 0)),
                "daily_consumption": 0.0,
                "coverage_days": float('inf'),
                "status": "充足",
            })
        return pd.DataFrame(sku_rows), pd.DataFrame(mat_rows)

    # Filter matrix to only active SKUs
    active_sku_keys = [s for s in bom_matrix.columns if s in active_skus]
    active_matrix = bom_matrix[active_sku_keys]

    # Compute daily consumption per material
    # daily_consumption[m] = sum(sku) weekly_sales[sku] / 7 x qty_per_unit[m, sku]
    daily_rate = pd.Series(
        {sku: qty / 7.0 for sku, qty in active_skus.items()},
        name="daily_rate",
    )
    # Multiply each SKU column by its daily rate and sum across columns
    daily_consumption = active_matrix.mul(daily_rate, axis=1).sum(axis=1)

    # Compute material coverage
    mat_rows = []
    for mat in bom_matrix.index:
        avail = inventory.get(mat, 0.0)
        ss = safety_stock.get(mat, 0.0)
        effective = max(0, avail - ss)
        dc = daily_consumption.get(mat, 0.0)
        is_gap = mat in gap_materials

        if is_gap or dc == 0:
            if is_gap:
                days = None
                status = gap_materials.get(mat, "-")
            else:
                days = float('inf')
                status = "充足"
        else:
            days = effective / dc
            status = _classify_coverage(days)

        mat_rows.append({
            "material": mat,
            "available_qty": round(avail, 2),
            "safety_stock": round(ss, 2),
            "effective_qty": round(effective, 2),
            "daily_consumption": round(dc, 4),
            "coverage_days": round(days, 1) if days is not None else (0.0 if not is_gap and dc > 0 else None),
            "status": status,
        })

    material_cov_df = pd.DataFrame(mat_rows)

    # Compute SKU coverage
    sku_rows = []
    for sku in bom_matrix.columns:
        ws = weekly_sales.get(sku, 0)
        if ws == 0:
            sku_rows.append({
                "sku_key": sku,
                "weekly_sales": 0,
                "limiting_material": None,
                "coverage_days": None,
                "status": "-",
            })
            continue

        # Get materials used by this SKU (excluding gaps)
        sku_materials = bom_matrix.index[bom_matrix[sku] > 0]
        non_gap_mats = [m for m in sku_materials if m not in gap_materials]

        if not non_gap_mats:
            sku_rows.append({
                "sku_key": sku,
                "weekly_sales": ws,
                "limiting_material": None,
                "coverage_days": None,
                "status": "-",
            })
            continue

        # Find minimum coverage among non-gap materials
        mat_cov_map = dict(zip(material_cov_df["material"], material_cov_df["coverage_days"]))
        mat_status_map = dict(zip(material_cov_df["material"], material_cov_df["status"]))

        min_mat = min(non_gap_mats, key=lambda m: mat_cov_map.get(m, float("inf")))
        min_days = mat_cov_map.get(min_mat)

        sku_rows.append({
            "sku_key": sku,
            "weekly_sales": ws,
            "limiting_material": min_mat,
            "coverage_days": min_days,
            "status": mat_status_map.get(min_mat, "-"),
        })

    sku_cov_df = pd.DataFrame(sku_rows)
    return sku_cov_df, material_cov_df
