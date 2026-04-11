"""
optimizer.py — SKU Portfolio Optimizer for mike-product-calc.

V1: enumerate all feasible portfolios, pick Top-3 by total profit.
V2 (optional): scipy.optimize.linprog / minimize wrapper.

Core concepts:
  OptimizationConstraint  — input constraints (capacity / budget / min sales)
  enumerate_portfolios     — brute-force enumeration + ranking
  explain_recommendation   — human-readable reasoning for Top-3
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from mike_product_calc.calc.profit import ProfitBasis, sku_profit_table
from mike_product_calc.calc.scenarios import (
    PortfolioResult,
    PortfolioScenario,
    evaluate_portfolio,
)


# -------------------------------------------------------------------------------------------------
# Constraint
# -------------------------------------------------------------------------------------------------

@dataclass
class OptimizationConstraint:
    """Optimization constraints for portfolio selection."""

    max_capacity: int = 200          # max total production units (件数)
    material_budget: float = 50000.0 # max total material/product cost (元)
    min_sales_per_sku: int = 1       # min qty per selected SKU (件)

    @property
    def as_dict(self) -> Dict:
        return {
            "max_capacity": self.max_capacity,
            "material_budget": self.material_budget,
            "min_sales_per_sku": self.min_sales_per_sku,
        }


# -------------------------------------------------------------------------------------------------
# Enumeration
# -------------------------------------------------------------------------------------------------

def enumerate_portfolios(
    sku_pool: pd.DataFrame,
    constraints: OptimizationConstraint,
    max_qty_per_sku: int = 20,
    max_combos: int = 200_000,
    basis: ProfitBasis = "factory",
) -> List[Tuple[PortfolioScenario, PortfolioResult, bool]]:
    """
    Enumerate all feasible portfolios from the given SKU pool and return Top-3.

    Parameters
    ----------
    sku_pool
        Filtered DataFrame from sku_profit_table (must contain product_key,
        price, cost, gross_margin columns).
    constraints
        OptimizationConstraint defining feasibility bounds.
    max_qty_per_sku
        Upper bound for quantity enumeration per SKU.
    max_combos
        Hard cap on number of combinations to evaluate (prune search if exceeded).
    basis
        "factory" or "store" pricing basis.

    Returns
    -------
    List of (scenario, result, is_feasible) tuples, sorted by total_profit descending.
    Only feasible portfolios (within all constraints) are returned.
    """
    if sku_pool.empty:
        return []

    keys = sku_pool["product_key"].dropna().unique().tolist()
    n = len(keys)

    # Pre-fetch price / cost per SKU
    price_map: Dict[str, float] = {}
    cost_map: Dict[str, float] = {}
    for _, row in sku_pool.iterrows():
        k = str(row["product_key"])
        price_map[k] = float(row["price"]) if row["price"] is not None else 0.0
        cost_map[k] = float(row["cost"]) if row["cost"] is not None else 0.0

    min_q = constraints.min_sales_per_sku

    # Quantity range per SKU: 0..max_qty_per_sku, but we skip 0 < q < min_q for selected SKUs
    # We enumerate qty values from 0..max_qty_per_sku per SKU
    qty_range = list(range(max_qty_per_sku + 1))  # 0..max_qty

    feasible: List[Tuple[PortfolioScenario, PortfolioResult, float]] = []
    count = 0

    # Iterate over all combinations
    # Use itertools.product with early-pruning: skip when partial sum already violates constraints
    for combo in itertools.product(qty_range, repeat=n):
        count += 1
        if count > max_combos:
            # Hard cap — return what we have so far
            break

        # Build sku_qty dict for non-zero entries
        sku_qty: Dict[str, float] = {}
        total_units = 0
        total_cost = 0.0
        total_profit = 0.0

        valid = True
        for i, key in enumerate(keys):
            q = combo[i]
            if q == 0:
                continue
            if q < min_q:
                # If qty is non-zero but below minimum, invalid
                valid = False
                break
            cost_i = cost_map.get(key, 0.0)
            price_i = price_map.get(key, 0.0)
            profit_i = (price_i - cost_i) * q

            total_units += q
            total_cost += cost_i * q
            total_profit += profit_i
            sku_qty[key] = float(q)

        if not valid:
            continue

        # Prune: if partial cost already exceeds budget, skip
        if total_cost > constraints.material_budget:
            continue
        if total_units > constraints.max_capacity:
            continue

        # Feasible portfolio found
        scenario = PortfolioScenario.from_dict(f"方案_{len(feasible) + 1}", sku_qty)
        feasible.append((scenario, None, total_profit))  # placeholder; result filled below

    # Sort by total_profit descending
    feasible.sort(key=lambda x: x[2], reverse=True)

    # Build full results (evaluate_portfolio needs sheets — done outside or with dummy)
    # Since we don't have sheets here, we compute from sku_pool directly
    results: List[Tuple[PortfolioScenario, PortfolioResult, bool]] = []
    for scenario, _, _ in feasible[:3]:  # Return Top-3
        result = _quick_eval(scenario, sku_pool)
        results.append((scenario, result, True))

    return results


def _quick_eval(
    scenario: PortfolioScenario,
    sku_pool: pd.DataFrame,
) -> PortfolioResult:
    """
    Lightweight evaluation without sheets — uses sku_pool price/cost directly.
    """
    if not scenario.selections:
        return PortfolioResult.empty(scenario.name)

    price_map = dict(zip(sku_pool["product_key"], sku_pool["price"]))
    cost_map = dict(zip(sku_pool["product_key"], sku_pool["cost"]))
    name_map = dict(zip(sku_pool["product_key"], sku_pool.get("name", [])))
    cat_map  = dict(zip(sku_pool["product_key"], sku_pool.get("category", [])))

    total_rev = 0.0
    total_cost = 0.0
    sku_details: List[Dict] = []

    for key, qty in scenario.to_dict().items():
        p = float(price_map.get(key, 0.0) or 0.0)
        c = float(cost_map.get(key, 0.0) or 0.0)
        rev = p * qty
        cst = c * qty
        profit = rev - cst
        total_rev += rev
        total_cost += cst
        margin = (p - c) / p if p > 0 else None
        sku_details.append({
            "sku_key": key,
            "name": name_map.get(key, key),
            "category": cat_map.get(key, ""),
            "qty": qty,
            "price": p,
            "cost": c,
            "revenue": round(rev, 2),
            "cost_total": round(cst, 2),
            "profit": round(profit, 2),
            "margin": margin,
        })

    total_profit = total_rev - total_cost
    total_margin = (total_rev - total_cost) / total_rev if total_rev > 0 else None

    return PortfolioResult(
        name=scenario.name,
        total_revenue=round(total_rev, 2),
        total_cost=round(total_cost, 2),
        total_profit=round(total_profit, 2),
        total_margin=round(total_margin, 4) if total_margin is not None else None,
        material_variety=0,  # BOM not available without sheets
        capacity_pressure=0.0,
        sku_count=len(scenario.selections),
        sku_details=tuple(sku_details),
    )


# -------------------------------------------------------------------------------------------------
# Explanation
# -------------------------------------------------------------------------------------------------

def explain_recommendation(
    best: PortfolioScenario,
    alternatives: List[PortfolioScenario],
    sku_pool: pd.DataFrame,
) -> str:
    """
    Generate human-readable explanation for the top recommendation.

    Parameters
    ----------
    best
        Recommended portfolio scenario.
    alternatives
        List of 0–2 alternative scenarios.
    sku_pool
        SKU profit table for price/cost lookups.

    Returns
    -------
    Multi-line explanation string.
    """
    price_map = dict(zip(sku_pool["product_key"], sku_pool["price"]))
    cost_map  = dict(zip(sku_pool["product_key"], sku_pool["cost"]))
    name_map  = dict(zip(sku_pool["product_key"], sku_pool.get("name", [])))

    def _eval(s: PortfolioScenario) -> Tuple[float, float, float, int, List[dict]]:
        total_rev = 0.0
        total_cost = 0.0
        total_units = 0
        details: List[dict] = []
        for key, qty in s.to_dict().items():
            p = float(price_map.get(key, 0.0) or 0.0)
            c = float(cost_map.get(key, 0.0) or 0.0)
            rev = p * qty
            cst = c * qty
            profit = rev - cst
            total_rev += rev
            total_cost += cst
            total_units += int(qty)
            margin = (p - c) / p if p > 0 else None
            details.append({
                "sku_key": key,
                "name": name_map.get(key, key),
                "qty": qty,
                "price": p,
                "cost": c,
                "profit": profit,
                "margin": margin,
            })
        return total_rev, total_cost, total_rev - total_cost, total_units, details

    best_rev, best_cost, best_profit, best_units, best_details = _eval(best)
    best_margin = (best_profit / best_rev) if best_rev > 0 else 0.0
    best_sku_count = len(best.selections)

    lines = [
        f"💡 **推荐方案「{best.name}」核心逻辑**",
        "",
        f"• 选中 **{best_sku_count} 个 SKU**，总件数 **{best_units}**，总销售额 **¥{best_rev:,.2f}**",
        f"• 总成本 **¥{best_cost:,.2f}**，净利润 **¥{best_profit:,.2f}**，毛利率 **{best_margin*100:.1f}%**",
        "",
        "**选中产品明细：**",
    ]

    for detail in best_details:
        sku_name = detail["name"]
        margin_pct = f"{detail['margin']*100:.1f}%" if detail.get("margin") else "N/A"
        lines.append(
            f"  - {sku_name}: {int(detail['qty'])} 件 | 单价 ¥{detail['price']:.2f} "
            f"| 毛利 ¥{detail['profit']:.2f} | 毛利率 {margin_pct}"
        )

    if alternatives:
        lines.append("")
        lines.append("**备选方案对比：**")
        for alt in alternatives:
            if alt is None:
                continue
            alt_rev, alt_cost, alt_profit, alt_units, _ = _eval(alt)
            diff_profit = alt_profit - best_profit
            diff_str = f"+¥{diff_profit:,.2f}" if diff_profit >= 0 else f"¥{diff_profit:,.2f}"
            lines.append(
                f"  • 「{alt.name}」：{len(alt.selections)} SKU / {alt_units} 件 → "
                f"利润 ¥{alt_profit:,.2f}（与推荐差 {diff_str}）"
            )

    lines.append("")
    lines.append("**为何推荐此方案：**")
    lines.append(
        f"  在满足产能 {best_units} 件、原料成本 ¥{best_cost:,.2f} 的约束下，"
        f"该组合实现了最高的净利润 ¥{best_profit:,.2f}。"
    )

    # Highlight highest-margin SKU
    if best_details:
        best_detail = max(
            [d for d in best_details if d.get("margin") is not None],
            key=lambda d: d["margin"] or 0,
            default=None,
        )
        if best_detail:
            sku_name = best_detail["name"]
            lines.append(
                f"  其中「{sku_name}」毛利率最高（{best_detail['margin']*100:.1f}%），"
                f"是利润驱动主力。"
            )

    return "\n".join(lines)
