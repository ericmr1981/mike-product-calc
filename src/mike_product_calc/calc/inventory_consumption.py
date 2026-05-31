from __future__ import annotations

from typing import Any

import pandas as pd


def classify_depletion_urgency(days: float) -> str:
    """Classify depletion urgency based on estimated days remaining.

    Returns ``"urgent"`` (<3 days), ``"warning"`` (3-7 days), or ``"normal"`` (>7 days).
    """
    if days < 3:
        return "urgent"
    if days < 7:
        return "warning"
    return "normal"


def format_consumption_amount(amount: float | None) -> str:
    """Format a consumption amount as a currency string.

    Uses ``¥X,XXX.XX`` for amounts under 10,000 and ``¥X,XXX.XX万`` for amounts
    >= 10,000. Returns ``"-"`` for None.
    """
    if amount is None:
        return "-"
    if amount >= 100000:
        wan = amount / 10000
        return f"¥{wan:,.2f}万"
    return f"¥{amount:,.2f}"


def _to_float(value: Any) -> float:
    """Safely convert a value to float, returning 0.0 for None/non-numeric."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def build_consumption_kpis(rows: list[dict], *, days: int) -> dict[str, Any]:
    """Aggregate consumption KPI values from a list of consumption row dicts.

    Parameters
    ----------
    rows:
        List of dicts with keys: item_code, item_name, unit, category, start_qty,
        end_qty, delivery_qty, consumption_qty, consumption_amount, avg_price,
        item_type.
    days:
        Number of days over which consumption was measured.

    Returns
    -------
    dict with keys:
        total_consumption_amount, daily_avg_amount, consumption_item_count,
        total_matched_items, total_new_items, fastest_item_name,
        fastest_item_daily, top_category_name, top_category_amount.
    """
    if not rows:
        return {
            "total_consumption_amount": 0.0,
            "daily_avg_amount": 0.0,
            "consumption_item_count": 0,
            "total_matched_items": 0,
            "total_new_items": 0,
            "fastest_item_name": None,
            "fastest_item_daily": None,
            "top_category_name": None,
            "top_category_amount": None,
        }

    # Items with positive consumption
    consumed_items = [r for r in rows if _to_float(r.get("consumption_qty")) > 0]
    matched_items = [r for r in rows if r.get("item_type") == "matched"]
    new_items = [r for r in rows if r.get("item_type") == "new"]

    total_consumption_amount = sum(
        _to_float(r.get("consumption_amount")) for r in consumed_items
    )
    daily_avg_amount = total_consumption_amount / days

    # Fastest item: max consumption_qty / days
    fastest_item_name: str | None = None
    fastest_item_daily: float | None = None
    if consumed_items:
        fastest = max(consumed_items, key=lambda r: _to_float(r.get("consumption_qty")))
        fastest_item_name = fastest.get("item_name") or fastest.get("item_code")
        fastest_item_daily = _to_float(fastest["consumption_qty"]) / days

    # Top category by consumption_amount sum
    category_amounts: dict[str, float] = {}
    for r in consumed_items:
        cat = r.get("category")
        if cat:
            category_amounts[cat] = (
                category_amounts.get(cat, 0.0) + _to_float(r.get("consumption_amount"))
            )
    top_category_name: str | None = None
    top_category_amount: float | None = None
    if category_amounts:
        top_category_name = max(category_amounts, key=category_amounts.get)  # type: ignore[arg-type]
        top_category_amount = category_amounts[top_category_name]

    return {
        "total_consumption_amount": total_consumption_amount,
        "daily_avg_amount": daily_avg_amount,
        "consumption_item_count": len(consumed_items),
        "total_matched_items": len(matched_items),
        "total_new_items": len(new_items),
        "fastest_item_name": fastest_item_name,
        "fastest_item_daily": fastest_item_daily,
        "top_category_name": top_category_name,
        "top_category_amount": top_category_amount,
    }


def build_consumption_table(rows: list[dict], *, days: int) -> pd.DataFrame:
    """Build a consumption DataFrame with computed columns for display.

    Parameters
    ----------
    rows:
        List of dicts with keys: item_code, item_name, unit, category, start_qty,
        end_qty, delivery_qty, consumption_qty, consumption_amount, avg_price,
        item_type.
    days:
        Number of days over which consumption was measured.

    Returns
    -------
    pd.DataFrame with computed columns: 日均消耗, 预计耗尽天数, 消耗率, _depletion_urgency.
    Matched items sorted by consumption_qty desc, new items at bottom.
    """
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    # Compute daily average consumption
    df["日均消耗"] = 0.0
    matched_mask = df["item_type"] == "matched"
    df.loc[matched_mask, "日均消耗"] = df.loc[matched_mask, "consumption_qty"].apply(_to_float) / days

    # Compute depletion days
    end_qty = df["end_qty"].apply(_to_float)
    daily_avg = df["日均消耗"]

    def _depletion_days(row: pd.Series) -> str:
        ed = _to_float(row.get("end_qty"))
        da = _to_float(row.get("日均消耗"))
        if da <= 0:
            return "充足"
        depletion = ed / da
        if depletion > 365:
            return "充足"
        return f"{depletion:.1f}"

    df["预计耗尽天数"] = df.apply(_depletion_days, axis=1)

    # Compute consumption rate
    def _consumption_rate(row: pd.Series) -> float:
        cq = _to_float(row.get("consumption_qty"))
        sq = _to_float(row.get("start_qty"))
        if sq > 0:
            return round(cq / sq * 100, 2)
        return 0.0

    df["消耗率"] = df.apply(_consumption_rate, axis=1)

    # Compute depletion urgency
    def _urgency(row: pd.Series) -> str:
        raw = row.get("预计耗尽天数")
        if raw == "充足":
            return "normal"
        try:
            return classify_depletion_urgency(float(raw))
        except (ValueError, TypeError):
            return "normal"

    df["_depletion_urgency"] = df.apply(_urgency, axis=1)

    # Sort: matched items by consumption_qty desc, then new items at bottom
    consumption_float = df["consumption_qty"].apply(_to_float)
    is_new = df["item_type"] != "matched"
    df["_sort_new"] = is_new.astype(int)
    df["_sort_consumption"] = consumption_float * -1  # negate for desc sort
    df = df.sort_values(
        ["_sort_new", "_sort_consumption"],
        ascending=[True, True],
        kind="stable",
    ).reset_index(drop=True)

    # Drop internal sort columns
    df = df.drop(columns=["_sort_new", "_sort_consumption"])

    return df
