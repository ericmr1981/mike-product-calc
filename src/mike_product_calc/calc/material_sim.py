"""
F-004: Material Price Simulator
==============================
Single / bulk material price adjustment; versioned scenarios (current / conservative
/ ideal / peak-season / user-named); diff two scenarios: gross margin change,
affected SKU list; < 3 s re-calculation; negative-margin SKUs highlighted.

All simulation is in-memory; original sheets are never mutated.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from mike_product_calc.calc.profit import (
    ProfitBasis,
    _gross_sheet_specs,
    _margin,
    _profit,
    sku_profit_table,
)
from mike_product_calc.data.shared import build_product_key, to_float

# -------------------------------------------------------------------------------------------------
# Material catalogue
# -------------------------------------------------------------------------------------------------

# Patterns stripped from recipe / 出品 names to match 总原料成本表 entries.
_SUFFIX_RE = re.compile(r"\s+\d+\.\d+$")  # e.g. " 木姜子甜橙 2.0" → "木姜子甜橙"
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_name(name: str) -> str:
    """Strip trailing size-suffixes and extra whitespace."""
    n = _SUFFIX_RE.sub("", str(name).strip())
    return _WHITESPACE_RE.sub(" ", n).strip()


@dataclass
class MaterialCatalog:
    """All unique materials with base unit prices and inferred qty-per-unit."""

    # material_name → base unit price  (元 / unit_from_cost_table)
    base_unit_price: Dict[str, float]
    # material_name → qty unit string from 总原料成本表 (e.g. "g", "袋")
    unit_label: Dict[str, str]
    # material_name → qty per unit (e.g. 2000 g/袋)
    qty_per_unit: Dict[str, float]
    # material_name → all recipe/output rows that use this material
    # (recipe_name, qty, unit_cost) — used to back-out implied qty
    usage_rows: Dict[str, List[Tuple[str, float, float]]] = field(default_factory=dict)
    # material_name → mean unit cost inferred from recipe rows
    inferred_base_price: Dict[str, float] = field(default_factory=dict)
    # materials NOT found in 总原料成本表 (only have recipe-based inference)
    unmatched_materials: List[str] = field(default_factory=list)

    def base_price(self, material: str) -> float:
        """Return base unit price in 元/g equivalent."""
        key = _clean_name(material)
        if key in self.base_unit_price and key in self.qty_per_unit:
            return self.base_unit_price[key] / self.qty_per_unit[key]
        return self.inferred_base_price.get(key, 0.0)

    @staticmethod
    def from_sheets(sheets: Dict[str, pd.DataFrame]) -> "MaterialCatalog":
        df_mat = sheets.get("总原料成本表")
        if df_mat is None:
            return MaterialCatalog(
                base_unit_price={},
                unit_label={},
                qty_per_unit={},
            )

        # Parse unit price table
        base_unit_price: Dict[str, float] = {}
        unit_label: Dict[str, str] = {}
        qty_per_unit: Dict[str, float] = {}

        for _, row in df_mat.iterrows():
            name = str(row.get("品项名称", "")).strip()
            price = to_float(row.get("加价后单价"))
            unit = str(row.get("订货单位", "")).strip()
            qty = to_float(row.get("单位量"))
            if name and price is not None and price > 0:
                base_unit_price[name] = price
                unit_label[name] = unit
                # Infer qty_per_unit from unit string
                qty_str = str(row.get("单位量", "")).strip()
                q = to_float(qty_str) if qty_str else None
                if q is None or q <= 0:
                    # Try to extract number from unit column
                    q = 1.0  # fallback: 1 unit
                qty_per_unit[name] = q

        # Collect all materials from recipe + 出品 tables
        usage_rows: Dict[str, List[Tuple[str, float, float]]] = {}
        recipe_sheets = ["产品配方表_Gelato", "产品配方表_雪花冰"]
        output_sheets = ["产品出品表_Gelato", "产品出品表_雪花冰", "产品出品表_饮品"]

        all_material_names: set = set()

        for sheet_name in recipe_sheets + output_sheets:
            df = sheets.get(sheet_name)
            if df is None:
                continue
            material_cols = ["配料", "主原料"]
            for col in material_cols:
                if col not in df.columns:
                    continue
                for _, row in df.iterrows():
                    mat = str(row.get(col, "")).strip()
                    if not mat or mat.lower() in {"nan", "none"}:
                        continue
                    qty = to_float(row.get("用量", 0)) or 0.0
                    unit_cost = to_float(row.get("单位成本", 0)) or 0.0
                    total_cost = to_float(row.get("总成本", 0)) or 0.0
                    all_material_names.add(mat)
                    usage_rows.setdefault(mat, []).append((sheet_name, qty, unit_cost, total_cost))

        # Build inferred base price from usage rows
        # For each material: weight-average unit cost from rows where we have valid data
        inferred_base_price: Dict[str, float] = {}
        unmatched_materials: List[str] = []

        for mat, rows in usage_rows.items():
            key = _clean_name(mat)
            # Check if in 总原料成本表
            if key in base_unit_price:
                # Compute 元/g from cost table
                unit_qty = qty_per_unit.get(key, 1.0)
                inferred_base_price[key] = base_unit_price[key] / unit_qty
            else:
                # Infer from recipe rows: total_cost / qty
                valid_rows = [(q, tc) for (_, q, uc, tc) in rows if q > 0 and tc > 0]
                if valid_rows:
                    # Weight by cost contribution
                    total_cost_weight = sum(tc for (_, tc) in valid_rows)
                    weighted = sum((tc / q) * (tc / total_cost_weight) for (q, tc) in valid_rows)
                    # Simpler: average unit cost weighted by cost
                    avg_unit_cost = sum(tc / q for (q, tc) in valid_rows) / len(valid_rows)
                    inferred_base_price[key] = avg_unit_cost
                    unmatched_materials.append(key)
                else:
                    # Use unit_cost from row if available
                    unit_costs = [uc for (_, q, uc, tc) in rows if uc > 0]
                    if unit_costs:
                        inferred_base_price[key] = sum(unit_costs) / len(unit_costs)
                        unmatched_materials.append(key)

        return MaterialCatalog(
            base_unit_price=base_unit_price,
            unit_label=unit_label,
            qty_per_unit=qty_per_unit,
            usage_rows=usage_rows,
            inferred_base_price=inferred_base_price,
            unmatched_materials=unmatched_materials,
        )

    def material_list_dataframe(self) -> pd.DataFrame:
        """Return a DataFrame with current material prices for the UI."""
        all_names = set(self.usage_rows.keys())
        rows = []
        for name in sorted(all_names):
            key = _clean_name(name)
            base = self.inferred_base_price.get(key, 0.0)
            matched = key in self.base_unit_price
            unit = self.unit_label.get(key, "?")
            qty_per_u = self.qty_per_unit.get(key, 1.0)
            rows.append({
                "material": name,
                "material_clean": key,
                "base_unit_price_per_g": round(base, 6),
                "matched_cost_table": matched,
                "unit_label": unit,
                "qty_per_unit": qty_per_u,
            })
        return pd.DataFrame(rows)


# -------------------------------------------------------------------------------------------------
# Scenario
# -------------------------------------------------------------------------------------------------

@dataclass
class Scenario:
    """A named material price scenario with per-material multipliers."""

    name: str
    description: str = ""
    # material_clean_name → price multiplier (> 1 = price up)
    multipliers: Dict[str, float] = field(default_factory=dict)
    is_builtin: bool = False

    def adjusted_price(self, catalog: MaterialCatalog, material: str) -> float:
        key = _clean_name(material)
        base = catalog.inferred_base_price.get(key, 0.0)
        mult = self.multipliers.get(key, 1.0)
        return base * mult

    def total_cost_for_sku(
        self,
        catalog: MaterialCatalog,
        material_rows: List[Tuple[str, float]],
    ) -> float:
        """Compute total material cost for a SKU given a list of (material_name, qty)."""
        cost = 0.0
        for mat, qty in material_rows:
            key = _clean_name(mat)
            base = catalog.inferred_base_price.get(key, 0.0)
            mult = self.multipliers.get(key, 1.0)
            cost += qty * base * mult
        return cost


# -------------------------------------------------------------------------------------------------
# SKU material cost extractor
# -------------------------------------------------------------------------------------------------

@dataclass
class SkuMaterialKey:
    """Unique key for a SKU within a sheet context."""
    category: str
    name: str
    spec: str
    sheet: str  # which sheet this row came from

    def product_key(self) -> str:
        return f"{self.category}|{self.name}|{self.spec}"

    def sku_name_key(self) -> str:
        """For matching recipe-level entries (no spec)."""
        return f"{self.category}|{self.name}"


def _extract_sku_materials_from_output(
    sheets: Dict[str, pd.DataFrame],
    output_sheet: str,
) -> Dict[str, List[Tuple[str, float]]]:
    """
    Extract (material_name, qty) for each SKU+spec from an output sheet.
    Returns dict: "category|name|spec" → [(material, qty), ...]
    """
    df = sheets.get(output_sheet)
    if df is None:
        return {}

    result: Dict[str, List[Tuple[str, float]]] = {}
    keys = build_product_key(df)

    for idx, row in df.iterrows():
        key_str = str(keys.at[idx]).strip()
        if not key_str:
            continue
        category = str(row.get("品类", "")).strip()
        name = str(row.get("品名", "")).strip()
        spec = str(row.get("规格", "")).strip()
        full_key = f"{category}|{name}|{spec}"

        # Extract materials from 主原料 and 配料
        for col in ["主原料", "配料"]:
            if col not in row:
                continue
            mat = str(row.get(col, "")).strip()
            if not mat or mat.lower() in {"nan", "none"}:
                continue
            qty = to_float(row.get("用量", 0)) or 0.0
            if qty > 0:
                result.setdefault(full_key, []).append((mat, qty))

    return result


def _extract_sku_materials_from_recipe(
    sheets: Dict[str, pd.DataFrame],
    recipe_sheet: str,
) -> Dict[str, List[Tuple[str, float]]]:
    """
    Extract (material_name, qty) from a recipe sheet (SKU name only, no spec).
    Returns dict: "category|name" → [(material, qty), ...]
    """
    df = sheets.get(recipe_sheet)
    if df is None:
        return {}

    result: Dict[str, List[Tuple[str, float]]] = {}
    for _, row in df.iterrows():
        category = str(row.get("品类", "")).strip()
        name = str(row.get("品名", "")).strip()
        if not name:
            continue
        sku_key = f"{category}|{name}"
        mat = str(row.get("配料", "")).strip()
        if not mat or mat.lower() in {"nan", "none"}:
            continue
        # Infer qty from total_cost / unit_cost
        total_cost = to_float(row.get("总成本", 0)) or 0.0
        unit_cost = to_float(row.get("单位成本", 0)) or 0.0
        if total_cost > 0 and unit_cost > 0:
            qty = total_cost / unit_cost
        else:
            qty = to_float(row.get("用量", 0)) or 0.0
        if qty > 0:
            result.setdefault(sku_key, []).append((mat, qty))

    return result


def _get_sku_overhead_ratio(
    sheets: Dict[str, pd.DataFrame],
    output_sheet: str,
    sku_key: str,
) -> float:
    """
    Compute overhead ratio = 1 - (material_cost_sum / 总成本) for a SKU.
    This ratio represents fixed overhead / allocation that is NOT material-driven.
    """
    df = sheets.get(output_sheet)
    if df is None:
        return 0.0

    # Find the cost row for this SKU
    # The cost might be in a summary row or need to be computed
    # For now, compute from recipe rows
    return 0.0  # We handle overhead differently — see below


# -------------------------------------------------------------------------------------------------
# Core simulation engine
# -------------------------------------------------------------------------------------------------

def _build_sku_material_map(
    sheets: Dict[str, pd.DataFrame],
) -> Dict[str, List[Tuple[str, float]]]:
    """
    Merge material usage from all recipe and output sheets into a single
    dict: "category|name|spec" → [(material, qty), ...].
    """
    combined: Dict[str, List[Tuple[str, float]]] = {}

    for sheet_name in ["产品出品表_Gelato", "产品出品表_雪花冰", "产品出品表_饮品"]:
        for sku_key, rows in _extract_sku_materials_from_output(sheets, sheet_name).items():
            combined.setdefault(sku_key, []).extend(rows)

    for sheet_name in ["产品配方表_Gelato", "产品配方表_雪花冰"]:
        for sku_name_key, rows in _extract_sku_materials_from_recipe(sheets, sheet_name).items():
            # Recipe has no spec — spread across all spec variants found in output
            # We'll just add with the name-key; caller must merge with spec-level
            combined.setdefault(sku_name_key, []).extend(rows)

    return combined


@dataclass
class SkuCostInfo:
    """Per-SKU cost breakdown used in simulation."""
    product_key: str       # "category|name|spec"
    sku_name_key: str      # "category|name"
    total_material_cost: float
    overhead: float       # fixed overhead (元)
    overhead_ratio: float # fraction of cost that is fixed overhead
    material_rows: List[Tuple[str, float]]  # (material, qty)
    sheet: str


def build_sku_cost_table(
    sheets: Dict[str, pd.DataFrame],
    catalog: MaterialCatalog,
) -> Tuple[Dict[str, SkuCostInfo], Dict[str, float]]:
    """
    Build per-SKU cost breakdown from all sheets.
    Returns:
        sku_cost_map: product_key → SkuCostInfo
        sku_current_cost: product_key → current 总成本 from 毛利表
    """
    sku_cost_map: Dict[str, SkuCostInfo] = {}
    sku_current_cost: Dict[str, float] = {}

    # Get current costs from 产品毛利表
    df_profit = sku_profit_table(sheets, basis="factory", only_status=None)
    if not df_profit.empty:
        for _, row in df_profit.iterrows():
            pk = str(row.get("product_key", "")).strip()
            cost = to_float(row.get("cost")) or 0.0
            if pk:
                sku_current_cost[pk] = cost

    # Merge material usage from 出品表
    material_usage: Dict[str, List[Tuple[str, float]]] = {}
    for sheet_name in ["产品出品表_Gelato", "产品出品表_雪花冰", "产品出品表_饮品"]:
        df_out = sheets.get(sheet_name)
        if df_out is None:
            continue
        keys = build_product_key(df_out)
        for idx, row in df_out.iterrows():
            key_str = str(keys.at[idx]).strip()
            if not key_str:
                continue
            for col in ["主原料", "配料"]:
                if col not in row:
                    continue
                mat = str(row.get(col, "")).strip()
                if not mat or mat.lower() in {"nan", "none"}:
                    continue
                qty = to_float(row.get("用量", 0)) or 0.0
                total_cost = to_float(row.get("总成本", 0)) or 0.0
                if qty > 0:
                    material_usage.setdefault(key_str, []).append((mat, qty))

    # Merge from 配方表 (SKU name level, no spec)
    for sheet_name in ["产品配方表_Gelato", "产品配方表_雪花冰"]:
        df_recipe = sheets.get(sheet_name)
        if df_recipe is None:
            continue
        for _, row in df_recipe.iterrows():
            category = str(row.get("品类", "")).strip()
            name = str(row.get("品名", "")).strip()
            if not name:
                continue
            sku_name_key = f"{category}|{name}"
            mat = str(row.get("配料", "")).strip()
            if not mat or mat.lower() in {"nan", "none"}:
                continue
            total_cost = to_float(row.get("总成本", 0)) or 0.0
            unit_cost = to_float(row.get("单位成本", 0)) or 0.0
            if total_cost > 0 and unit_cost > 0:
                qty = total_cost / unit_cost
            else:
                qty = to_float(row.get("用量", 0)) or 0.0
            if qty > 0:
                material_usage.setdefault(sku_name_key, []).append((mat, qty))

    # Deduplicate material lists
    for key in material_usage:
        seen: set = set()
        deduped = []
        for mat, qty in material_usage[key]:
            if mat not in seen:
                seen.add(mat)
                deduped.append((mat, qty))
        material_usage[key] = deduped

    # Compute current material cost for each SKU
    for product_key, mat_rows in material_usage.items():
        current_mat_cost = 0.0
        for mat, qty in mat_rows:
            key = _clean_name(mat)
            base = catalog.inferred_base_price.get(key, 0.0)
            current_mat_cost += qty * base

        # Get current 总成本
        current_total = sku_current_cost.get(product_key, current_mat_cost)
        overhead = max(0.0, current_total - current_mat_cost)
        overhead_ratio = overhead / current_total if current_total > 0 else 0.0

        sku_cost_map[product_key] = SkuCostInfo(
            product_key=product_key,
            sku_name_key=product_key.rsplit("|", 1)[0] if "|" in product_key else product_key,
            total_material_cost=current_mat_cost,
            overhead=overhead,
            overhead_ratio=overhead_ratio,
            material_rows=mat_rows,
            sheet="产品毛利表",
        )

    return sku_cost_map, sku_current_cost


def apply_scenario_to_sku_costs(
    sku_cost_map: Dict[str, SkuCostInfo],
    catalog: MaterialCatalog,
    scenario: Scenario,
) -> Dict[str, float]:
    """
    Apply a scenario's multipliers to get adjusted 总成本 for each SKU.
    Returns: product_key → adjusted cost
    """
    result: Dict[str, float] = {}
    for pk, info in sku_cost_map.items():
        mat_cost = 0.0
        for mat, qty in info.material_rows:
            key = _clean_name(mat)
            base = catalog.inferred_base_price.get(key, 0.0)
            mult = scenario.multipliers.get(key, 1.0)
            mat_cost += qty * base * mult
        result[pk] = mat_cost + info.overhead
    return result


def recalc_profit_with_adjusted_costs(
    sheets: Dict[str, pd.DataFrame],
    adjusted_costs: Dict[str, float],
) -> pd.DataFrame:
    """
    Recalculate the profit table using adjusted costs.
    Returns a DataFrame in the same format as sku_profit_table.
    """
    # Build the profit table using the base logic, but with cost overrides
    base_df = sku_profit_table(sheets, basis="factory", only_status=None)

    if base_df.empty:
        return base_df

    # Apply cost overrides
    df = base_df.copy()
    df["adjusted_cost"] = df["product_key"].map(
        lambda pk: adjusted_costs.get(str(pk).strip(), None)
    )
    has_adjustment = df["adjusted_cost"].notna()

    # Recompute gross_profit and gross_margin with adjusted costs
    df["gross_profit_original"] = df["gross_profit"]
    df["gross_margin_original"] = df["gross_margin"]

    for idx in df[has_adjustment].index:
        price = df.at[idx, "price"]
        adj_cost = df.at[idx, "adjusted_cost"]
        if price is not None and adj_cost is not None and price > 0:
            df.at[idx, "gross_profit"] = price - adj_cost
            df.at[idx, "gross_margin"] = (price - adj_cost) / price

    return df


# -------------------------------------------------------------------------------------------------
# Scenario comparison
# -------------------------------------------------------------------------------------------------

@dataclass
class ScenarioComparison:
    """Diff between two scenarios."""
    scenario_a: str
    scenario_b: str
    comparison_df: pd.DataFrame  # per-SKU diff table
    high_risk_skus: List[str]  # SKUs with negative margin in scenario_b
    affected_skus: List[str]  # SKUs where margin changed


def compare_scenarios(
    sheets: Dict[str, pd.DataFrame],
    sku_cost_map: Dict[str, SkuCostInfo],
    catalog: MaterialCatalog,
    scenario_a: Scenario,
    scenario_b: Scenario,
) -> ScenarioComparison:
    """Compare two scenarios and return a diff DataFrame."""

    costs_a = apply_scenario_to_sku_costs(sku_cost_map, catalog, scenario_a)
    costs_b = apply_scenario_to_sku_costs(sku_cost_map, catalog, scenario_b)

    df_profit = sku_profit_table(sheets, basis="factory", only_status=None)
    if df_profit.empty:
        return ScenarioComparison(
            scenario_a=scenario_a.name,
            scenario_b=scenario_b.name,
            comparison_df=pd.DataFrame(),
            high_risk_skus=[],
            affected_skus=[],
        )

    df = df_profit.copy()

    # Compute margin for both scenarios
    def _margin_row(row: pd.Series, costs: Dict[str, float]) -> Optional[float]:
        pk = str(row.get("product_key", "")).strip()
        price = to_float(row.get("price"))
        cost = costs.get(pk)
        if price is None or cost is None or price <= 0:
            return None
        return (price - cost) / price

    df["margin_a"] = df.apply(lambda r: _margin_row(r, costs_a), axis=1)
    df["margin_b"] = df.apply(lambda r: _margin_row(r, costs_b), axis=1)
    df["cost_a"] = df["product_key"].map(lambda pk: costs_a.get(str(pk).strip(), None))
    df["cost_b"] = df["product_key"].map(lambda pk: costs_b.get(str(pk).strip(), None))
    df["cost_delta"] = df["cost_b"] - df["cost_a"]
    df["margin_delta_pp"] = (df["margin_b"] - df["margin_a"]) * 100.0

    # High risk: negative margin in scenario_b
    high_risk_mask = df["margin_b"].notna() & (df["margin_b"] < 0)
    high_risk_skus = df.loc[high_risk_mask, "product_key"].tolist()

    # Affected: margin changed by more than 0.01 pp
    affected_mask = df["margin_delta_pp"].notna() & (df["margin_delta_pp"].abs() > 0.01)
    affected_skus = df.loc[affected_mask, "product_key"].tolist()

    # Select and rename columns for display
    display_cols = [
        "product_key", "category", "name", "spec", "status",
        "price", "cost_a", "cost_b", "cost_delta",
        "gross_margin", "margin_a", "margin_b", "margin_delta_pp",
    ]
    available = [c for c in display_cols if c in df.columns]
    comparison_df = df[available].copy()

    # Format percentages
    for col in ["gross_margin", "margin_a", "margin_b"]:
        if col in comparison_df.columns:
            comparison_df[col] = (comparison_df[col] * 100).round(2)

    comparison_df = comparison_df.round({"cost_delta": 4, "margin_delta_pp": 4})
    comparison_df = comparison_df.sort_values("margin_delta_pp", key=abs, ascending=False)

    return ScenarioComparison(
        scenario_a=scenario_a.name,
        scenario_b=scenario_b.name,
        comparison_df=comparison_df,
        high_risk_skus=high_risk_skus,
        affected_skus=affected_skus,
    )


# -------------------------------------------------------------------------------------------------
# Built-in scenarios
# -------------------------------------------------------------------------------------------------

BUILTIN_SCENARIOS: Dict[str, Scenario] = {}


def get_builtin_scenarios() -> Dict[str, Scenario]:
    """Return the four built-in scenarios."""
    return {
        "当前": Scenario(
            name="当前",
            description="原始数据，无价格调整",
            multipliers={},
            is_builtin=True,
        ),
        "保守": Scenario(
            name="保守",
            description="原料价格上调 5%（通胀压力）",
            multipliers={},  # filled in by UI based on selected materials
            is_builtin=True,
        ),
        "理想": Scenario(
            name="理想",
            description="原料价格下调 10%（批量采购优惠）",
            multipliers={},
            is_builtin=True,
        ),
        "旺季": Scenario(
            name="旺季",
            description="旺季原料上调 15%（供需溢价）",
            multipliers={},
            is_builtin=True,
        ),
    }


# -------------------------------------------------------------------------------------------------
# High-risk highlighting helper
# -------------------------------------------------------------------------------------------------

def highlight_negative_margin_rows(df: pd.DataFrame, margin_col: str = "margin_b") -> pd.DataFrame:
    """Return a copy of df with a 'risk' column: 'high' if margin < 0, else 'ok'."""
    result = df.copy()
    result["risk"] = "ok"
    mask = result[margin_col].notna() & (result[margin_col] < 0)
    result.loc[mask, "risk"] = "high"
    return result
