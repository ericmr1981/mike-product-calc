"""
Feature F-004 — 原料价格模拟器

单原料/批量调价 → 保存具名版本（当前/保守/理想/旺季）
→ 对比任意两版本：毛利变化、受影响SKU、高风险标红
→ 响应时间 <3s（全内存计算）
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .profit import ProfitBasis, _build_product_key, sku_profit_table
from mike_product_calc.data.shared import to_float


# ── Version ──────────────────────────────────────────────────────────────────

VERSION_NAMES = ["当前", "保守", "理想", "旺季"]

_SUFFIX_RE = re.compile(r"\s+\d+\.\d+$")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_name(name: str) -> str:
    """Compatibility helper used by legacy MaterialCatalog API."""
    n = _SUFFIX_RE.sub("", str(name).strip())
    return _WHITESPACE_RE.sub(" ", n).strip()


@dataclass
class MaterialCatalog:
    """Legacy API shim for app imports.

    New simulator logic no longer requires this class directly, but app.py and
    some external callers still import it.
    """

    base_unit_price: Dict[str, float]
    unit_label: Dict[str, str]
    qty_per_unit: Dict[str, float]
    usage_rows: Dict[str, List[Tuple[str, float, float, float]]] = field(default_factory=dict)
    inferred_base_price: Dict[str, float] = field(default_factory=dict)
    unmatched_materials: List[str] = field(default_factory=list)

    def base_price(self, material: str) -> float:
        key = _clean_name(material)
        if key in self.inferred_base_price:
            return float(self.inferred_base_price[key])
        p = self.base_unit_price.get(key)
        q = self.qty_per_unit.get(key)
        if p is not None and q is not None and q > 0:
            return float(p) / float(q)
        return 0.0

    @staticmethod
    def from_sheets(sheets: Dict[str, pd.DataFrame]) -> "MaterialCatalog":
        df_mat = sheets.get("总原料成本表")
        if df_mat is None:
            return MaterialCatalog(base_unit_price={}, unit_label={}, qty_per_unit={})

        name_col = next((c for c in df_mat.columns if "品项名称" in c), None)
        price_col = next((c for c in df_mat.columns if "原料价格" in c), None) or next((c for c in df_mat.columns if "单价" in c), None)
        unit_col = next((c for c in df_mat.columns if "订货单位" in c or "单位" in c), None)
        qty_col = next((c for c in df_mat.columns if "单位量" in c or "单位数量" in c), None)

        base_unit_price: Dict[str, float] = {}
        unit_label: Dict[str, str] = {}
        qty_per_unit: Dict[str, float] = {}
        inferred_base_price: Dict[str, float] = {}

        if name_col and price_col:
            for _, row in df_mat.iterrows():
                name = _clean_name(str(row.get(name_col, "")).strip())
                if not name:
                    continue
                price = to_float(row.get(price_col))
                qty = to_float(row.get(qty_col)) if qty_col else None
                if price is None or price <= 0:
                    continue
                base_unit_price[name] = float(price)
                if unit_col:
                    unit_label[name] = str(row.get(unit_col, "")).strip()
                if qty is not None and qty > 0:
                    qty_per_unit[name] = float(qty)
                    inferred_base_price[name] = float(price) / float(qty)
                else:
                    qty_per_unit[name] = 1.0
                    inferred_base_price[name] = float(price)

        return MaterialCatalog(
            base_unit_price=base_unit_price,
            unit_label=unit_label,
            qty_per_unit=qty_per_unit,
            usage_rows={},
            inferred_base_price=inferred_base_price,
            unmatched_materials=[],
        )

    def material_list_dataframe(self) -> pd.DataFrame:
        rows = []
        all_names = set(self.base_unit_price.keys()) | set(self.inferred_base_price.keys())
        for name in sorted(all_names):
            rows.append(
                {
                    "material": name,
                    "material_clean": name,
                    "base_unit_price_per_g": float(self.base_price(name)),
                    "matched_cost_table": name in self.base_unit_price,
                    "unit_label": self.unit_label.get(name, ""),
                    "qty_per_unit": float(self.qty_per_unit.get(name, 1.0)),
                }
            )
        return pd.DataFrame(rows)


@dataclass(frozen=True)
class SkuCostInfo:
    product_key: str
    name: str
    category: str
    price: Optional[float]
    cost: Optional[float]


@dataclass(frozen=True)
class MaterialPriceAdjustment:
    """One adjusted ingredient + new unit price."""

    item: str          # 原料品项名称（精确匹配总原料成本表.品项名称）
    new_unit_price: float  # 调整后单价


@dataclass
class Scenario:
    """A named version of material price overrides.

    Stored in memory; does NOT persist to disk in this module
    (persist to JSON/DB outside if needed).
    """

    name: str
    adjustments: Tuple[MaterialPriceAdjustment, ...] = field(default_factory=tuple)

    def __repr__(self) -> str:
        return f"Scenario({self.name}, {len(self.adjustments)} adj)"


class ScenarioStore:
    """In-memory scenario registry; thread-unsafe (single-user Streamlit context)."""

    def __init__(self) -> None:
        self._versions: Dict[str, Scenario] = {}

    def put(self, scenario: Scenario) -> None:
        self._versions[scenario.name] = scenario

    def get(self, name: str) -> Optional[Scenario]:
        return self._versions.get(name)

    def list_names(self) -> List[str]:
        return sorted(self._versions.keys())

    def delete(self, name: str) -> None:
        self._versions.pop(name, None)

    def clear(self) -> None:
        self._versions.clear()


# ── Core simulation ────────────────────────────────────────────────────────────

def _price_col_for_basis(df: pd.DataFrame, basis: ProfitBasis) -> Optional[str]:
    """Select the correct price column from 总原料成本表.

    Convention (per Ud Lee):
    - 加价前单价 = 出厂单价 (factory)
    - 加价后单价 = 门店单价 (store)
    """

    # Prefer explicit column names.
    if basis == "factory" and "加价前单价" in df.columns:
        return "加价前单价"
    if basis == "store" and "加价后单价" in df.columns:
        return "加价后单价"

    # Fallbacks for older/variant headers.
    # 兼容不同表头命名：优先“原料价格”，其次“单价”
    return next((c for c in df.columns if "原料价格" in c), None) or next(
        (c for c in df.columns if "单价" in c),
        None,
    )


def _ingredient_price_map(
    sheets: Dict[str, pd.DataFrame],
    *,
    basis: ProfitBasis,
) -> Dict[str, float]:
    """Return {item_name: min_unit_cost} from 总原料成本表.

    Business rule:
    - 价格 / 单位量 = 最小单位成本
    - 产品配方/出品表中的用量，按“最小单位”解释
    """
    df = sheets.get("总原料成本表")
    if df is None:
        return {}

    price_col = _price_col_for_basis(df, basis)
    unit_qty_col = next((c for c in df.columns if "单位量" in c or "单位数量" in c), None)
    name_col = next((c for c in df.columns if "品项名称" in c), None)
    if not price_col or not name_col:
        return {}

    out: Dict[str, float] = {}
    for _, r in df.iterrows():
        name = str(r.get(name_col, "")).strip()
        if not name:
            continue
        price = to_float(r.get(price_col))
        unit_qty = to_float(r.get(unit_qty_col)) if unit_qty_col else None

        if price is None or price <= 0:
            continue

        # 最小单位成本 = 价格 / 单位量
        # 如果单位量缺失，回退为旧逻辑（按价格直接当单位成本）
        min_unit_cost = (price / unit_qty) if (unit_qty is not None and unit_qty > 0) else price
        if min_unit_cost > 0:
            out[name] = min_unit_cost
    return out


def _adjust_map(adjustments: Iterable[MaterialPriceAdjustment]) -> Dict[str, float]:
    return {adj.item: adj.new_unit_price for adj in adjustments}


def _ingredient_unit_qty_map(sheets: Dict[str, pd.DataFrame]) -> Dict[str, float]:
    """Return {item_name: unit_qty} from 总原料成本表 (if present)."""
    df = sheets.get("总原料成本表")
    if df is None:
        return {}

    name_col = next((c for c in df.columns if "品项名称" in c), None)
    unit_qty_col = next((c for c in df.columns if "单位量" in c or "单位数量" in c), None)
    if not name_col or not unit_qty_col:
        return {}

    out: Dict[str, float] = {}
    for _, r in df.iterrows():
        name = str(r.get(name_col, "")).strip()
        qty = to_float(r.get(unit_qty_col))
        if name and qty is not None and qty > 0:
            out[name] = qty
    return out


def simulate_scenario(
    sheets: Dict[str, pd.DataFrame],
    scenario: Scenario,
    basis: ProfitBasis = "store",
) -> pd.DataFrame:
    """Return sku_profit_table computed with scenario price overrides applied.

    For every 产品出品表_* row, look up the adjusted unit price for each
    ingredient; sum adjusted costs → adjusted gross margin.
    """

    # 1. Base profit table (uses workbook prices)
    df = sku_profit_table(sheets, basis=basis, only_status=None)

    # 2. Build adjusted unit-price map
    base_prices = _ingredient_price_map(sheets, basis=basis)
    overrides = _adjust_map(scenario.adjustments)
    unit_qty_map = _ingredient_unit_qty_map(sheets)
    # UI 输入口径与“总原料成本表”一致（原料价格），换算到最小单位成本再参与计算
    overrides_min_unit: Dict[str, float] = {}
    for item, raw_price in overrides.items():
        q = unit_qty_map.get(item)
        if q is not None and q > 0:
            overrides_min_unit[item] = float(raw_price) / q
        else:
            overrides_min_unit[item] = float(raw_price)

    # 3. For each SKU, compute adjusted cost using 产品出品表_*
    out_sheets = ["产品出品表_Gelato", "产品出品表_雪花冰", "产品出品表_饮品"]
    sku_adjusted_cost: Dict[str, float] = {}

    for sheet_name in out_sheets:
        df_out = sheets.get(sheet_name)
        if df_out is None:
            continue
        keys = _build_product_key(df_out)
        cost_col = "总成本" if basis == "factory" else "门店总成本"
        if cost_col not in df_out.columns:
            continue

        for idx, row in df_out.iterrows():
            key = str(keys.at[idx]).strip()
            if not key:
                continue
            # Recompute cost using adjusted prices
            raw_cost = to_float(row.get(cost_col))
            # Find ingredient name
            mm = str(row.get("主原料", "")).strip()
            ing = str(row.get("配料", "")).strip()
            item_name = ing or mm
            if not item_name:
                continue

            # 配方消耗按最小单位解释：优先 qty * min_unit_cost
            qty = to_float(row.get("用量"))
            base = base_prices.get(item_name)
            adj = overrides_min_unit.get(item_name)

            if qty is not None and qty >= 0:
                # adj/base 都是“最小单位成本”口径
                effective_unit_cost = adj if (adj is not None and adj > 0) else base
                if effective_unit_cost is not None and effective_unit_cost > 0:
                    sku_adjusted_cost[key] = sku_adjusted_cost.get(key, 0) + qty * effective_unit_cost
                elif raw_cost is not None:
                    # 缺少成本映射时，回退到已有总成本
                    sku_adjusted_cost[key] = sku_adjusted_cost.get(key, 0) + raw_cost
            else:
                # 回退逻辑：按历史总成本同比例缩放
                if raw_cost is None:
                    continue
                if base is not None and base > 0 and adj is not None and adj > 0:
                    scale = adj / base
                    sku_adjusted_cost[key] = sku_adjusted_cost.get(key, 0) + raw_cost * scale
                else:
                    sku_adjusted_cost[key] = sku_adjusted_cost.get(key, 0) + raw_cost

    # 4. Merge adjusted costs into profit table
    df = df.copy()
    df["adjusted_cost"] = df["product_key"].map(sku_adjusted_cost)
    df["has_adjusted"] = df["product_key"].isin(sku_adjusted_cost)

    # Recompute margin with adjusted cost
    df["adjusted_gross_profit"] = df.apply(
        lambda r: (r["price"] - r["adjusted_cost"])
        if (pd.notna(r["price"]) and pd.notna(r["adjusted_cost"]) and r["price"] > 0)
        else None,
        axis=1,
    )
    df["adjusted_gross_margin"] = df.apply(
        lambda r: (r["price"] - r["adjusted_cost"]) / r["price"]
        if (pd.notna(r["price"]) and pd.notna(r["adjusted_cost"]) and r["price"] > 0)
        else None,
        axis=1,
    )

    # Gross profit delta (RMB)
    df["gp_delta"] = df.apply(
        lambda r: (r["adjusted_gross_profit"] - r["gross_profit"])
        if (pd.notna(r["adjusted_gross_profit"]) and pd.notna(r["gross_profit"]))
        else None,
        axis=1,
    )
    # Margin delta in percentage points
    df["margin_delta_pp"] = df.apply(
        lambda r: (r["adjusted_gross_margin"] - r["gross_margin"]) * 100
        if (pd.notna(r["adjusted_gross_margin"]) and pd.notna(r["gross_margin"]))
        else None,
        axis=1,
    )

    return df



def build_sku_cost_table(
    sheets: Dict[str, pd.DataFrame],
    basis: ProfitBasis = "store",
) -> pd.DataFrame:
    """Legacy compatibility API: return SKU-level base cost table."""
    df = sku_profit_table(sheets, basis=basis, only_status=None).copy()
    if df.empty:
        return pd.DataFrame(columns=["product_key", "name", "category", "price", "cost"])
    return df[["product_key", "name", "category", "price", "cost"]]


def apply_scenario_to_sku_costs(
    sheets: Dict[str, pd.DataFrame],
    scenario: Scenario,
    basis: ProfitBasis = "store",
) -> pd.DataFrame:
    """Legacy compatibility API: return SKU table with adjusted_cost column."""
    out = simulate_scenario(sheets, scenario, basis=basis)
    keep = [c for c in ["product_key", "name", "category", "price", "cost", "adjusted_cost"] if c in out.columns]
    return out[keep].copy() if keep else out


def recalc_profit_with_adjusted_costs(
    sheets: Dict[str, pd.DataFrame],
    scenario: Scenario,
    basis: ProfitBasis = "store",
) -> pd.DataFrame:
    """Legacy compatibility API: recompute profit fields under scenario."""
    return simulate_scenario(sheets, scenario, basis=basis)


def get_builtin_scenarios() -> Dict[str, Scenario]:
    """Legacy compatibility API: predefined scenario names."""
    return {name: Scenario(name=name, adjustments=()) for name in VERSION_NAMES}


def highlight_negative_margin_rows(df: pd.DataFrame, margin_col: str = "adjusted_gross_margin") -> pd.DataFrame:
    """Legacy compatibility API: add a negative-margin flag for UI highlighting."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if margin_col not in out.columns:
        return out
    out["is_negative_margin"] = out[margin_col].fillna(0) < 0
    return out

def compare_scenarios(
    a: Scenario,
    b: Scenario,
    sheets: Dict[str, pd.DataFrame],
    basis: ProfitBasis = "store",
) -> pd.DataFrame:
    """Return SKU-level diff table: a vs b gross_profit and gross_margin."""

    df_a = simulate_scenario(sheets, a, basis=basis)
    df_b = simulate_scenario(sheets, b, basis=basis)

    base = sku_profit_table(sheets, basis=basis, only_status=None)[[
        "product_key", "name", "spec", "category", "price", "cost", "gross_profit", "gross_margin"
    ]].copy()

    merged = base.merge(
        df_a[["product_key", "adjusted_gross_profit", "adjusted_gross_margin"]].rename(
            columns={
                "adjusted_gross_profit": "gp_a",
                "adjusted_gross_margin": "gm_a",
            }
        ),
        on="product_key",
        how="left",
    ).merge(
        df_b[["product_key", "adjusted_gross_profit", "adjusted_gross_margin"]].rename(
            columns={
                "adjusted_gross_profit": "gp_b",
                "adjusted_gross_margin": "gm_b",
            }
        ),
        on="product_key",
        how="left",
    )

    merged["gp_delta_ab"] = (merged["gp_b"] - merged["gp_a"]).round(4)
    merged["gm_delta_pp_ab"] = ((merged["gm_b"] - merged["gm_a"]) * 100).round(4)
    merged["high_risk"] = (
        (merged["gm_a"].fillna(0) < 0) | (merged["gm_b"].fillna(0) < 0)
    )

    for col in ["gross_profit", "gp_a", "gp_b"]:
        merged[col] = merged[col].round(4)
    for col in ["gross_margin", "gm_a", "gm_b"]:
        merged[col] = (merged[col] * 100).round(2)

    return merged


def high_risk_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Return rows where adjusted gross margin < 0."""
    if df is None or df.empty:
        return pd.DataFrame()
    risk = df[df["adjusted_gross_margin"].fillna(0) < 0].copy()
    risk["abs_risk"] = risk["adjusted_gross_margin"].abs() * risk["price"]
    return risk.sort_values("abs_risk", ascending=False)
