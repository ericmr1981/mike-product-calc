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


@dataclass(frozen=True)
class ProfitRow:
    product_key: str
    sheet: str
    category: str
    name: str
    spec: str
    status: str
    price: Optional[float]
    cost: Optional[float]
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


def sku_profit_table(
    sheets: Dict[str, pd.DataFrame],
    *,
    basis: ProfitBasis = "factory",
    only_status: Optional[str] = None,
) -> pd.DataFrame:
    rows: list[ProfitRow] = []

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
                cost = to_float(row.get("成本"))
                workbook_margin = to_percent_0_1(row.get("毛利率"))
            else:
                cost = to_float(row.get("门店成本"))
                workbook_margin = to_percent_0_1(row.get("门店毛利率"))

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
                    cost=cost,
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
    if cost_col not in df_out.columns:
        return pd.DataFrame(columns=["bucket", "item", "cost", "sheet"])

    catalog = ingredient_catalog(sheets)
    name_to_type = dict(zip(catalog["name"], catalog["type"]))

    part = df_out.loc[keys_series == product_key].copy()
    if part.empty:
        return pd.DataFrame(columns=["bucket", "item", "cost", "sheet"])

    part["_cost"] = part[cost_col].map(to_float)
    part = part[~part["_cost"].isna()]
    if part.empty:
        return pd.DataFrame(columns=["bucket", "item", "cost", "sheet"])

    main_material = part["主原料"].fillna("").astype(str).map(str.strip) if "主原料" in part.columns else ""
    ingredient = part["配料"].fillna("").astype(str).map(str.strip) if "配料" in part.columns else ""

    rows: list[dict] = []
    for idx, row in part.iterrows():
        mm = str(main_material.at[idx]).strip() if isinstance(main_material, pd.Series) else ""
        ing = str(ingredient.at[idx]).strip() if isinstance(ingredient, pd.Series) else ""
        item = ing or mm or "(unknown)"
        if mm and (ing == "" or ing == mm):
            bucket = "main_material"
        else:
            bucket = name_to_type.get(item, "ingredient")

        rows.append({"bucket": bucket, "item": item, "cost": float(row["_cost"]), "sheet": used_sheet})

    out = pd.DataFrame(rows)
    return (
        out.groupby(["bucket", "item", "sheet"], as_index=False)["cost"]
        .sum()
        .sort_values(["bucket", "cost"], ascending=[True, False])
        .reset_index(drop=True)
    )
