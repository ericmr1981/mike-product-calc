"""
scenarios.py — Portfolio scenario evaluation for mike-product-calc.

Core concepts:
  PortfolioScenario  — a named selection of SKUs with quantities
  PortfolioResult    — evaluation output for one scenario
  evaluate_portfolio — compute all KPIs for a scenario
  compare_portfolios — diff table across multiple scenarios
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Tuple

import pandas as pd

from mike_product_calc.calc.prep_engine import bom_expand_multi
from mike_product_calc.calc.profit import ProfitBasis, sku_profit_table


# -------------------------------------------------------------------------------------------------
# Data structures
# -------------------------------------------------------------------------------------------------

PortfolioScenarioKey = str  # e.g. "A", "B", "C"
Selection = Tuple[str, float]  # (sku_key, qty)


@dataclass(frozen=True)
class PortfolioScenario:
    name: str
    selections: Tuple[Selection, ...]  # immutable tuple of (sku_key, qty)

    @classmethod
    def from_dict(cls, name: str, d: Dict[str, float]) -> "PortfolioScenario":
        """Build from {sku_key: qty} dict."""
        selections = tuple(sorted(d.items()))
        return cls(name=name, selections=selections)

    def to_dict(self) -> Dict[str, float]:
        return dict(self.selections)


@dataclass(frozen=True)
class PortfolioResult:
    name: str
    # Financial KPIs
    total_revenue: float
    total_cost: float
    total_profit: float
    total_margin: float  # fraction, 0-1 (None if no revenue)
    # Operational KPIs
    material_variety: int      # count of unique raw materials
    capacity_pressure: float   # normalised composite score (0-100)
    sku_count: int             # number of SKUs in portfolio
    sku_details: Tuple[Dict, ...]  # per-SKU breakdown

    @classmethod
    def empty(cls, name: str) -> "PortfolioResult":
        return cls(
            name=name,
            total_revenue=0.0,
            total_cost=0.0,
            total_profit=0.0,
            total_margin=None,
            material_variety=0,
            capacity_pressure=0.0,
            sku_count=0,
            sku_details=(),
        )


# -------------------------------------------------------------------------------------------------
# Evaluation
# -------------------------------------------------------------------------------------------------

def _compute_capacity_pressure(
    sheets: Dict[str, pd.DataFrame],
    sku_qty: Dict[str, float],
) -> float:
    """
    Compute a composite capacity-pressure score (0–100) based on:
      - SKU count (complexity)
      - Total production units (volume load)
      - Number of distinct material categories (supply chain complexity)

    We run bom_expand_multi on the selected SKUs to get a demand-level view,
    then score each dimension and combine with weights.
    """
    if not sku_qty:
        return 0.0

    # Run BOM expansion to get material-level demand
    bom_df = bom_expand_multi(sheets, sku_qty)

    # Dimension 1: SKU count (normalised, cap at 20 SKUs → 100)
    sku_cnt = len(sku_qty)
    sku_score = min(sku_cnt / 20.0, 1.0) * 40.0

    # Dimension 2: Total production units (normalised, cap at 500 units → 100)
    total_units = sum(sku_qty.values())
    volume_score = min(total_units / 500.0, 1.0) * 30.0

    # Dimension 3: Material variety (from BOM expansion, cap at 30 → 100)
    if not bom_df.empty:
        material_cnt = len(bom_df)
    else:
        material_cnt = sku_cnt  # fallback: at least sku_count
    material_score = min(material_cnt / 30.0, 1.0) * 30.0

    return round(sku_score + volume_score + material_score, 1)


def evaluate_portfolio(
    scenario: PortfolioScenario,
    sheets: Dict[str, pd.DataFrame],
    basis: ProfitBasis = "factory",
) -> PortfolioResult:
    """
    Evaluate a portfolio scenario and return KPIs.

    Parameters
    ----------
    scenario
        PortfolioScenario with selections = tuple of (sku_key, qty).
    sheets
        All workbook sheets (wb.sheets dict).
    basis
        "factory" or "store" pricing/cost basis.

    Returns
    -------
    PortfolioResult with financial + operational KPIs.
    """
    if not scenario.selections:
        return PortfolioResult.empty(scenario.name)

    # Build {sku_key: qty} dict
    sku_qty: Dict[str, float] = dict(scenario.selections)

    # Fetch profit table for all selected SKUs
    profit_df = sku_profit_table(sheets, basis=basis, only_status=None)
    if profit_df.empty:
        return PortfolioResult.empty(scenario.name)

    # Filter to selected SKUs only
    profit_df = profit_df[profit_df["product_key"].isin(sku_qty.keys())].copy()

    sku_details: List[Dict] = []
    total_revenue = 0.0
    total_cost = 0.0

    for _, row in profit_df.iterrows():
        key = str(row["product_key"])
        qty = sku_qty.get(key, 0.0)
        price = row["price"] if row["price"] is not None else 0.0
        cost = row["cost"] if row["cost"] is not None else 0.0

        rev = price * qty
        cst = cost * qty
        profit_ = rev - cst

        total_revenue += rev
        total_cost += cst

        sku_details.append({
            "sku_key": key,
            "name": row.get("name", key),
            "category": row.get("category", ""),
            "qty": qty,
            "price": price,
            "cost": cost,
            "revenue": round(rev, 2),
            "cost_total": round(cst, 2),
            "profit": round(profit_, 2),
            "margin": row["gross_margin"],
        })

    total_profit = total_revenue - total_cost
    total_margin = (total_revenue - total_cost) / total_revenue if total_revenue > 0 else None

    # Compute capacity pressure (uses bom_expand_multi internally)
    capacity_pressure = _compute_capacity_pressure(sheets, sku_qty)

    # Material variety: run BOM to count unique raw materials
    bom_df = bom_expand_multi(sheets, sku_qty)
    material_variety = len(bom_df) if not bom_df.empty else 0

    return PortfolioResult(
        name=scenario.name,
        total_revenue=round(total_revenue, 2),
        total_cost=round(total_cost, 2),
        total_profit=round(total_profit, 2),
        total_margin=round(total_margin, 4) if total_margin is not None else None,
        material_variety=material_variety,
        capacity_pressure=capacity_pressure,
        sku_count=len(scenario.selections),
        sku_details=tuple(sku_details),
    )


# -------------------------------------------------------------------------------------------------
# Comparison
# -------------------------------------------------------------------------------------------------

def compare_portfolios(
    results: List[PortfolioResult],
) -> pd.DataFrame:
    """
    Build a comparison DataFrame across multiple portfolio results.

    Columns: name, total_revenue, total_cost, total_profit,
             total_margin(%), material_variety, capacity_pressure, sku_count
    """
    if not results:
        return pd.DataFrame(columns=[
            "name", "total_revenue", "total_cost", "total_profit",
            "total_margin_pct", "material_variety", "capacity_pressure", "sku_count",
        ])

    rows = []
    for r in results:
        rows.append({
            "name": r.name,
            "total_revenue": r.total_revenue,
            "total_cost": r.total_cost,
            "total_profit": r.total_profit,
            "total_margin_pct": round(r.total_margin * 100, 2) if r.total_margin is not None else None,
            "material_variety": r.material_variety,
            "capacity_pressure": r.capacity_pressure,
            "sku_count": r.sku_count,
        })

    df = pd.DataFrame(rows)

    # Add diff columns vs. first result (baseline)
    if len(df) > 1:
        base = rows[0]
        diff_rows = []
        for r in rows[1:]:
            diff_rows.append({
                "name": f"{r['name']} vs {base['name']}",
                "total_revenue": round(r["total_revenue"] - base["total_revenue"], 2),
                "total_cost":    round(r["total_cost"] - base["total_cost"], 2),
                "total_profit": round(r["total_profit"] - base["total_profit"], 2),
                "total_margin_pct": (
                    round((r["total_margin_pct"] or 0) - (base["total_margin_pct"] or 0), 2)
                    if r["total_margin_pct"] is not None and base["total_margin_pct"] is not None
                    else None
                ),
                "material_variety": r["material_variety"] - base["material_variety"],
                "capacity_pressure": round(r["capacity_pressure"] - base["capacity_pressure"], 1),
                "sku_count": r["sku_count"] - base["sku_count"],
            })
        if diff_rows:
            df = pd.concat([df, pd.DataFrame(diff_rows)], ignore_index=True)

    return df


# =============================================================================
# F-010: 多场景对比
# =============================================================================

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SalesAssumptionScenario:
    """A named scenario with a specific sales assumption set.

    Used for F-010 多场景对比: e.g. "旺季A" vs "淡季B" with different
    sales volumes per SKU, compared on both profit and material demand.
    """

    name: str
    selections: Tuple[Selection, ...]  # (sku_key, qty) — qty is the assumed sales volume

    def to_dict(self) -> Dict[str, float]:
        return dict(self.selections)

    @classmethod
    def from_dict(cls, name: str, d: Dict[str, float]) -> "SalesAssumptionScenario":
        return cls(name=name, selections=tuple(sorted(d.items())))


@dataclass
class ScenarioComparisonResult:
    """Result of comparing multiple sales assumption scenarios."""

    scenario_name: str
    total_revenue: float
    total_cost: float
    total_profit: float
    total_margin: Optional[float]  # fraction 0-1
    total_material_qty: float  # total raw material demand
    material_count: int         # number of distinct raw materials
    sku_count: int
    sku_details: Tuple[Dict, ...]


def _eval_scenario(
    scenario: SalesAssumptionScenario,
    sheets: Dict[str, pd.DataFrame],
    basis: ProfitBasis,
) -> ScenarioComparisonResult:
    """Evaluate a SalesAssumptionScenario: profit + material demand."""

    sku_qty = dict(scenario.selections)
    profit_df = sku_profit_table(sheets, basis=basis, only_status=None)

    if profit_df.empty or not sku_qty:
        return ScenarioComparisonResult(
            scenario_name=scenario.name,
            total_revenue=0.0, total_cost=0.0, total_profit=0.0,
            total_margin=None, total_material_qty=0.0,
            material_count=0, sku_count=0, sku_details=(),
        )

    profit_df = profit_df[profit_df["product_key"].isin(sku_qty.keys())].copy()

    total_rev = 0.0
    total_cst = 0.0
    sku_details: List[Dict] = []

    for _, row in profit_df.iterrows():
        key = str(row["product_key"])
        qty = sku_qty.get(key, 0.0)
        price = row["price"] if row["price"] is not None else 0.0
        cost = row["cost"] if row["cost"] is not None else 0.0
        rev = price * qty
        cst = cost * qty
        total_rev += rev
        total_cst += cst
        sku_details.append({
            "sku_key": key,
            "name": row.get("name", key),
            "qty": qty,
            "revenue": round(rev, 2),
            "cost": round(cst, 2),
            "profit": round(rev - cst, 2),
        })

    total_profit = total_rev - total_cst
    total_margin = (total_rev - total_cst) / total_rev if total_rev > 0 else None

    # BOM for material demand
    bom_df = bom_expand_multi(sheets, sku_qty)
    total_material_qty = float(bom_df["total_purchase_qty"].sum()) if not bom_df.empty else 0.0
    material_count = len(bom_df) if not bom_df.empty else 0

    return ScenarioComparisonResult(
        scenario_name=scenario.name,
        total_revenue=round(total_rev, 2),
        total_cost=round(total_cst, 2),
        total_profit=round(total_profit, 2),
        total_margin=round(total_margin, 4) if total_margin is not None else None,
        total_material_qty=round(total_material_qty, 4),
        material_count=material_count,
        sku_count=len(scenario.selections),
        sku_details=tuple(sku_details),
    )


def evaluate_multi_scenario(
    scenarios: List[SalesAssumptionScenario],
    sheets: Dict[str, pd.DataFrame],
    basis: ProfitBasis = "store",
) -> List[ScenarioComparisonResult]:
    """Evaluate all scenarios and return comparison results."""
    return [_eval_scenario(s, sheets, basis) for s in scenarios]


def multi_scenario_comparison_df(
    results: List[ScenarioComparisonResult],
) -> pd.DataFrame:
    """Build a comparison DataFrame from multiple ScenarioComparisonResults."""
    if not results:
        return pd.DataFrame(columns=[
            "scenario", "total_revenue", "total_cost", "total_profit",
            "total_margin_pct", "material_qty", "material_count", "sku_count",
        ])

    rows = []
    for r in results:
        rows.append({
            "scenario": r.scenario_name,
            "total_revenue": r.total_revenue,
            "total_cost": r.total_cost,
            "total_profit": r.total_profit,
            "total_margin_pct": round(r.total_margin * 100, 2) if r.total_margin is not None else None,
            "material_qty": r.total_material_qty,
            "material_count": r.material_count,
            "sku_count": r.sku_count,
        })

    df = pd.DataFrame(rows)

    # Add diff vs. first scenario (baseline)
    if len(df) > 1:
        base = rows[0]
        diffs = []
        for r in rows[1:]:
            diffs.append({
                "scenario": f"{r['scenario']} vs {base['scenario']}",
                "total_revenue": round(r["total_revenue"] - base["total_revenue"], 2),
                "total_cost": round(r["total_cost"] - base["total_cost"], 2),
                "total_profit": round(r["total_profit"] - base["total_profit"], 2),
                "total_margin_pct": (
                    round((r["total_margin_pct"] or 0) - (base["total_margin_pct"] or 0), 2)
                    if r["total_margin_pct"] is not None and base["total_margin_pct"] is not None
                    else None
                ),
                "material_qty": round(r["material_qty"] - base["material_qty"], 4),
                "material_count": r["material_count"] - base["material_count"],
                "sku_count": r["sku_count"] - base["sku_count"],
            })
        if diffs:
            df = pd.concat([df, pd.DataFrame(diffs)], ignore_index=True)

    return df


def multi_scenario_diff_table(
    results: List[ScenarioComparisonResult],
) -> pd.DataFrame:
    """Return per-SKU diff table: which SKUs changed quantity/profit across scenarios."""
    if len(results) < 2:
        return pd.DataFrame(columns=["sku_key", "name", "scenario", "qty", "profit"])

    all_rows = []
    for r in results:
        for d in r.sku_details:
            all_rows.append({
                "sku_key": d["sku_key"],
                "name": d["name"],
                "scenario": r.scenario_name,
                "qty": d["qty"],
                "profit": d["profit"],
            })

    df = pd.DataFrame(all_rows)
    if df.empty:
        return df

    # Pivot: rows = SKU, cols = scenario values
    qty_pivot = df.pivot_table(index=["sku_key", "name"], columns="scenario", values="qty", aggfunc="sum").reset_index()
    qty_pivot.columns.name = None

    # Identify changed SKUs (where qty differs across scenarios)
    scenario_cols = [c for c in qty_pivot.columns if c not in ("sku_key", "name")]
    if len(scenario_cols) >= 2:
        first_col = scenario_cols[0]
        qty_pivot["qty_changed"] = qty_pivot[scenario_cols].apply(
            lambda row: any(pd.notna(row[c]) and row[c] != row[first_col] for c in scenario_cols[1:]),
            axis=1,
        )
        changed = qty_pivot[qty_pivot["qty_changed"]].drop(columns="qty_changed")
    else:
        changed = qty_pivot

    return changed
