from __future__ import annotations

from typing import Any

import pandas as pd


_PLAN_COLUMNS = [
    "material",
    "demand_qty",
    "available_qty",
    "shortage_qty",
    "suggested_replenish_qty",
    "unit",
    "urgency",
]

_URGENCY_RANK = {"高": 0, "中": 1, "低": 2}


def _to_float_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)


def _empty_plan() -> pd.DataFrame:
    return pd.DataFrame(columns=_PLAN_COLUMNS)


def _resolve_available_qty(material: str, inv_exact: pd.DataFrame) -> float:
    """Resolve available qty by exact match first, then unique prefix match.

    Why:
    - BOM material names may be shorter aliases (e.g. ``原味奶浆``),
      while inventory names include full code suffix (e.g. ``原味奶浆JYX001``).
    - We only apply fuzzy fallback when the candidate is unique, to avoid
      accidental mismatches when multiple inventory names share the prefix.
    """
    m = str(material or "").strip()
    if not m:
        return 0.0

    exact = inv_exact[inv_exact["material"] == m]
    if not exact.empty:
        return float(exact["available_qty"].sum())

    starts = inv_exact[inv_exact["material"].astype(str).str.startswith(m, na=False)]
    if len(starts) == 1:
        return float(starts["available_qty"].iloc[0])
    return 0.0


def build_replenishment_plan(bom_df: pd.DataFrame, inv_df: pd.DataFrame) -> pd.DataFrame:
    if bom_df is None or bom_df.empty:
        return _empty_plan()

    bom = bom_df.copy()
    if "material" not in bom.columns:
        if "item_name" in bom.columns:
            bom = bom.rename(columns={"item_name": "material"})
        else:
            return _empty_plan()

    if "demand_qty" not in bom.columns and "total_purchase_qty" in bom.columns:
        bom = bom.rename(columns={"total_purchase_qty": "demand_qty"})
    if "unit" not in bom.columns and "purchase_unit" in bom.columns:
        bom = bom.rename(columns={"purchase_unit": "unit"})

    if "demand_qty" not in bom.columns:
        bom["demand_qty"] = 0.0
    if "unit" not in bom.columns:
        bom["unit"] = ""

    bom["material"] = bom["material"].astype(str).str.strip()
    bom["demand_qty"] = _to_float_series(bom["demand_qty"])
    bom["unit"] = bom["unit"].fillna("").astype(str)

    if inv_df is None or inv_df.empty:
        inv = pd.DataFrame(columns=["material", "available_qty", "unit"])
    else:
        inv = inv_df.copy()
        if "material" not in inv.columns:
            if "item_name" in inv.columns:
                inv = inv.rename(columns={"item_name": "material"})
            else:
                inv["material"] = ""
        if "available_qty" not in inv.columns:
            inv["available_qty"] = 0.0
        if "unit" not in inv.columns:
            inv["unit"] = ""

        inv["material"] = inv["material"].astype(str).str.strip()
        inv["available_qty"] = _to_float_series(inv["available_qty"])
        inv["unit"] = inv["unit"].fillna("").astype(str)
        inv = (
            inv.sort_values(["material", "unit"], kind="stable")
            .groupby("material", as_index=False)
            .agg({"available_qty": "sum", "unit": "first"})
        )

    out = bom[["material", "demand_qty", "unit"]].copy()
    out["available_qty"] = out["material"].apply(lambda m: _resolve_available_qty(m, inv))

    out["shortage_qty"] = (out["demand_qty"] - out["available_qty"]).clip(lower=0.0)
    out["suggested_replenish_qty"] = out["shortage_qty"]

    out["urgency"] = "低"
    out.loc[out["shortage_qty"] > 0.0, "urgency"] = "中"
    out.loc[(out["shortage_qty"] > 0.0) & (out["available_qty"] <= 0.0), "urgency"] = "高"

    out["_urgency_rank"] = out["urgency"].map(_URGENCY_RANK).fillna(99).astype(int)
    out = out.sort_values(
        ["_urgency_rank", "shortage_qty", "material", "unit"],
        ascending=[True, False, True, True],
        kind="stable",
    ).reset_index(drop=True)

    return out[_PLAN_COLUMNS]


def summarize_shortage_alert(plan_df: pd.DataFrame) -> dict[str, Any]:
    if plan_df is None or plan_df.empty or "shortage_qty" not in plan_df.columns:
        return {"shortage_items": 0, "total_shortage_qty": 0.0}

    shortage_qty = _to_float_series(plan_df["shortage_qty"])
    shortage_mask = shortage_qty > 0.0
    return {
        "shortage_items": int(shortage_mask.sum()),
        "total_shortage_qty": float(shortage_qty[shortage_mask].sum()),
    }
