from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Literal, Optional, Tuple

import pandas as pd

from mike_product_calc.data.shared import build_product_key, to_float, to_percent_0_1

# Backward-compatible aliases for older modules/tests that still import the
# private helpers from this module.
_build_product_key = build_product_key
_to_float = to_float


ProfitBasis = Literal["factory", "store"]
CostMode = Literal["computed", "workbook"]


@dataclass(frozen=True)
class ProfitRow:
    product_key: str
    sheet: str
    category: str
    name: str
    spec: str
    status: str
    price: Optional[float]

    # Unified-cost view:
    # - workbook_cost: from 产品毛利表_* columns (成本/门店成本)
    # - computed_cost: recomputed from 产品出品表_* + 总原料成本表 (price/unit_qty)
    # - cost: the chosen cost based on cost_mode
    workbook_cost: Optional[float]
    computed_cost: Optional[float]
    cost: Optional[float]
    cost_source: str

    gross_profit: Optional[float]
    gross_margin: Optional[float]
    workbook_margin: Optional[float]
    margin_delta: Optional[float]


def _margin(price: Optional[float], cost: Optional[float]) -> Optional[float]:
    if price is None or cost is None or price <= 0:
        return None
    return (price - cost) / price


def _profit(price: Optional[float], cost: Optional[float]) -> Optional[float]:
    if price is None or cost is None:
        return None
    return price - cost


def _gross_sheet_specs() -> Iterable[Tuple[str, str]]:
    return [
        ("产品毛利表_Gelato", "Gelato"),
        ("产品毛利表_雪花冰", "雪花冰"),
        # 当前真实工作簿没有单独的饮品毛利表
    ]


def _price_col_for_basis(df: pd.DataFrame, basis: ProfitBasis) -> Optional[str]:
    """Pick the correct price column from 总原料成本表.

    Convention (per Ud Lee):
    - 加价前单价 = 出厂单价 (factory)
    - 加价后单价 = 门店单价 (store)
    """

    if basis == "factory" and "加价前单价" in df.columns:
        return "加价前单价"
    if basis == "store" and "加价后单价" in df.columns:
        return "加价后单价"

    # fallback: any 单价-like column
    return next((c for c in df.columns if "原料价格" in c), None) or next(
        (c for c in df.columns if "单价" in c),
        None,
    )


def _ingredient_min_unit_cost_map(sheets: Dict[str, pd.DataFrame], *, basis: ProfitBasis) -> Dict[str, float]:
    """Return {item_name: min_unit_cost} computed from 总原料成本表.

    Rule: min_unit_cost = 单价 / (单位量 || 1)
    (单位量为空/<=0 → 当作 1)
    """

    df = sheets.get("总原料成本表")
    if df is None:
        return {}

    name_col = next((c for c in df.columns if "品项名称" in c), None)
    if not name_col:
        return {}

    price_col = _price_col_for_basis(df, basis)
    if not price_col:
        return {}

    unit_qty_col = next((c for c in df.columns if "单位量" in c or "单位数量" in c), None)

    out: Dict[str, float] = {}
    for _, r in df.iterrows():
        name = str(r.get(name_col, "")).strip()
        if not name:
            continue

        price = to_float(r.get(price_col))
        if price is None or price <= 0:
            continue

        unit_qty = to_float(r.get(unit_qty_col)) if unit_qty_col else None
        q = float(unit_qty) if (unit_qty is not None and unit_qty > 0) else 1.0
        out[name] = float(price) / q

    return out


def _sku_cost_map_from_outputs(sheets: Dict[str, pd.DataFrame], *, basis: ProfitBasis) -> Dict[str, float]:
    """Recompute per-SKU cost from 产品出品表_*.

    Cost per line = 用量 * min_unit_cost(item)
    Fallback: if item not found in 总原料成本表, use the row's 总成本/门店总成本 if present.
    """

    out_sheets = ["产品出品表_Gelato", "产品出品表_雪花冰", "产品出品表_饮品"]
    cost_col = "总成本" if basis == "factory" else "门店总成本"

    unit_cost_map = _ingredient_min_unit_cost_map(sheets, basis=basis)
    sku_cost: Dict[str, float] = {}

    for sheet_name in out_sheets:
        df_out = sheets.get(sheet_name)
        if df_out is None:
            continue

        keys = build_product_key(df_out)
        for idx, row in df_out.iterrows():
            key = str(keys.at[idx]).strip()
            if not key:
                continue

            mm = str(row.get("主原料", "")).strip()
            ing = str(row.get("配料", "")).strip()
            item = ing or mm
            if not item:
                continue

            qty = to_float(row.get("用量"))
            unit_cost = unit_cost_map.get(item)

            line_cost: Optional[float] = None
            if qty is not None and unit_cost is not None:
                line_cost = float(qty) * float(unit_cost)
            else:
                # fallback to workbook line cost
                line_cost = to_float(row.get(cost_col)) if cost_col in df_out.columns else None

            if line_cost is None:
                continue

            sku_cost[key] = sku_cost.get(key, 0.0) + float(line_cost)

    return sku_cost


def sku_profit_table(
    sheets: Dict[str, pd.DataFrame],
    *,
    basis: ProfitBasis = "factory",
    only_status: Optional[str] = None,
    cost_mode: CostMode = "computed",
) -> pd.DataFrame:
    rows: list[ProfitRow] = []

    computed_cost_map = _sku_cost_map_from_outputs(sheets, basis=basis)

    for sheet_name, category_label in _gross_sheet_specs():
        df = sheets.get(sheet_name)
        if df is None:
            continue

        keys = build_product_key(df)
        for idx, row in df.iterrows():
            key = str(keys.at[idx]).strip()
            if not key:
                continue

            status = str(row.get("状态", "")).strip()
            if only_status is not None and status != only_status:
                continue

            price = to_float(row.get("定价"))

            if basis == "factory":
                workbook_cost = to_float(row.get("成本"))
                workbook_margin = to_percent_0_1(row.get("毛利率"))
            else:
                workbook_cost = to_float(row.get("门店成本"))
                workbook_margin = to_percent_0_1(row.get("门店毛利率"))

            computed_cost = computed_cost_map.get(key)

            if cost_mode == "workbook":
                cost = workbook_cost
                cost_source = "workbook"
            else:
                cost = computed_cost if computed_cost is not None else workbook_cost
                cost_source = "computed" if computed_cost is not None else "workbook_fallback"

            gross_margin = _margin(price, cost)
            gross_profit = _profit(price, cost)
            margin_delta = (
                gross_margin - workbook_margin
                if gross_margin is not None and workbook_margin is not None
                else None
            )

            rows.append(
                ProfitRow(
                    product_key=key,
                    sheet=sheet_name,
                    category=str(row.get("品类", "")).strip() or category_label,
                    name=str(row.get("品名", "")).strip(),
                    spec=str(row.get("规格", "")).strip(),
                    status=status,
                    price=price,
                    workbook_cost=workbook_cost,
                    computed_cost=computed_cost,
                    cost=cost,
                    cost_source=cost_source,
                    gross_profit=gross_profit,
                    gross_margin=gross_margin,
                    workbook_margin=workbook_margin,
                    margin_delta=margin_delta,
                )
            )

    out = pd.DataFrame([r.__dict__ for r in rows])
    if out.empty:
        return out
    return out.sort_values(["category", "name", "spec"]).reset_index(drop=True)


def margin_delta_report(df_profit: pd.DataFrame, *, top_n: int = 20) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return per-category delta stats and top offending SKU rows.

    Deltas are reported in percentage-points to make the oracle easier to read.
    """

    if df_profit.empty or "margin_delta" not in df_profit.columns:
        empty_stats = pd.DataFrame(columns=["category", "sku_count", "mean_abs_delta_pp", "p95_abs_delta_pp", "max_abs_delta_pp"])
        empty_top = pd.DataFrame(columns=list(df_profit.columns) + ["abs_margin_delta_pp"]) if not df_profit.empty else pd.DataFrame(columns=["abs_margin_delta_pp"])
        return empty_stats, empty_top

    df = df_profit.copy()
    df = df[df["margin_delta"].notna()].copy()
    if df.empty:
        empty_stats = pd.DataFrame(columns=["category", "sku_count", "mean_abs_delta_pp", "p95_abs_delta_pp", "max_abs_delta_pp"])
        empty_top = pd.DataFrame(columns=list(df_profit.columns) + ["abs_margin_delta_pp"])
        return empty_stats, empty_top

    df["abs_margin_delta_pp"] = df["margin_delta"].abs() * 100.0

    stats = (
        df.groupby("category", as_index=False)
        .agg(
            sku_count=("product_key", "count"),
            mean_abs_delta_pp=("abs_margin_delta_pp", "mean"),
            p95_abs_delta_pp=("abs_margin_delta_pp", lambda s: float(s.quantile(0.95))),
            max_abs_delta_pp=("abs_margin_delta_pp", "max"),
        )
        .sort_values(["max_abs_delta_pp", "mean_abs_delta_pp"], ascending=False)
        .reset_index(drop=True)
    )

    top = (
        df.sort_values("abs_margin_delta_pp", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    return stats, top


def ingredient_catalog(sheets: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    df = sheets.get("总原料成本表")
    if df is None:
        return pd.DataFrame(columns=["name", "type", "category"])

    if "品项名称" not in df.columns:
        return pd.DataFrame(columns=["name", "type", "category"])

    out = pd.DataFrame(
        {
            "name": df["品项名称"].fillna("").astype(str).map(str.strip),
            "category": df["品项类别"].fillna("").astype(str).map(str.strip) if "品项类别" in df.columns else "",
        }
    )
    out = out[out["name"] != ""].drop_duplicates(subset=["name"]).reset_index(drop=True)

    def _type(category: str) -> str:
        txt = str(category).strip()
        if txt == "":
            return "unknown"
        if any(token in txt for token in ["包", "耗材", "杯", "勺", "纸", "贴", "袋", "碗", "卡"]):
            return "packaging"
        return "ingredient"

    out["type"] = out["category"].map(_type)
    return out


def sku_cost_breakdown(
    sheets: Dict[str, pd.DataFrame],
    *,
    product_key: str,
    basis: ProfitBasis = "factory",
) -> pd.DataFrame:
    out_sheets = ["产品出品表_Gelato", "产品出品表_雪花冰", "产品出品表_饮品"]
    df_out: Optional[pd.DataFrame] = None
    used_sheet: Optional[str] = None
    keys_series: Optional[pd.Series] = None

    for sheet_name in out_sheets:
        df = sheets.get(sheet_name)
        if df is None:
            continue
        keys = build_product_key(df)
        if (keys == product_key).any():
            df_out = df
            used_sheet = sheet_name
            keys_series = keys
            break

    if df_out is None or used_sheet is None or keys_series is None:
        return pd.DataFrame(columns=["bucket", "item", "cost", "sheet"])

    cost_col = "总成本" if basis == "factory" else "门店总成本"

    catalog = ingredient_catalog(sheets)
    name_to_type = dict(zip(catalog["name"], catalog["type"]))
    unit_cost_map = _ingredient_min_unit_cost_map(sheets, basis=basis)

    part = df_out.loc[keys_series == product_key].copy()
    if part.empty:
        return pd.DataFrame(columns=["bucket", "item", "cost", "sheet"])

    main_material = part["主原料"].fillna("").astype(str).map(str.strip) if "主原料" in part.columns else ""
    ingredient = part["配料"].fillna("").astype(str).map(str.strip) if "配料" in part.columns else ""

    rows: list[dict] = []
    for idx, row in part.iterrows():
        mm = str(main_material.at[idx]).strip() if isinstance(main_material, pd.Series) else ""
        ing = str(ingredient.at[idx]).strip() if isinstance(ingredient, pd.Series) else ""
        item = ing or mm or "(unknown)"

        qty = to_float(row.get("用量"))
        unit_cost = unit_cost_map.get(item)

        line_cost: Optional[float] = None
        if qty is not None and unit_cost is not None:
            line_cost = float(qty) * float(unit_cost)
        elif cost_col in part.columns:
            line_cost = to_float(row.get(cost_col))

        if line_cost is None:
            continue

        if mm and (ing == "" or ing == mm):
            bucket = "main_material"
        else:
            bucket = name_to_type.get(item, "ingredient")

        rows.append({"bucket": bucket, "item": item, "cost": float(line_cost), "sheet": used_sheet})

    out = pd.DataFrame(rows)
    return (
        out.groupby(["bucket", "item", "sheet"], as_index=False)["cost"]
        .sum()
        .sort_values(["bucket", "cost"], ascending=[True, False])
        .reset_index(drop=True)
    )
