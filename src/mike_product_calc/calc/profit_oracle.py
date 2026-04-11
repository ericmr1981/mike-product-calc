from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .profit import ProfitBasis, sku_profit_table


@dataclass(frozen=True)
class ProfitOracleThresholds:
    """Acceptance thresholds.

    - margin_delta_abs: absolute delta on gross margin (0~1 scale)
    - rmb_delta_abs: absolute delta in RMB for profit/cost consistency
    """

    margin_delta_abs: float = 1e-4
    rmb_delta_abs: float = 0.01


def sku_profit_consistency_table(
    sheets: dict[str, pd.DataFrame],
    *,
    basis: ProfitBasis = "factory",
    only_status: Optional[str] = None,
) -> pd.DataFrame:
    """Enrich sku_profit_table with workbook-implied profit/cost deltas.

    Workbook provides (price, cost, margin). If these are internally consistent:
      profit == price * margin
      cost == price * (1 - margin)

    We compute:
      - workbook_implied_profit
      - workbook_implied_cost
      - profit_delta_rmb = (price - cost) - workbook_implied_profit
      - cost_delta_rmb = cost - workbook_implied_cost

    This gives a RMB-level cross-check aligned with PRD requirement
    "与Excel交叉验证误差<0.01元".
    """

    df = sku_profit_table(sheets, basis=basis, only_status=only_status)
    if df.empty:
        return df

    out = df.copy()
    # When workbook_margin is missing, deltas are not meaningful.
    out["workbook_implied_profit"] = out["price"] * out["workbook_margin"]
    out["workbook_implied_cost"] = out["price"] * (1.0 - out["workbook_margin"])

    out["profit_delta_rmb"] = out["gross_profit"] - out["workbook_implied_profit"]
    out["cost_delta_rmb"] = out["cost"] - out["workbook_implied_cost"]

    # Null-out rows where workbook_margin unavailable
    m = out["workbook_margin"].isna() | out["price"].isna() | out["cost"].isna()
    out.loc[m, [
        "workbook_implied_profit",
        "workbook_implied_cost",
        "profit_delta_rmb",
        "cost_delta_rmb",
    ]] = None

    return out


def _fmt_num(v, *, digits: int = 4) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "-"
    try:
        return f"{float(v):.{digits}f}"
    except Exception:
        return str(v)


def _delta_stats(df: pd.DataFrame, col: str) -> dict:
    ser = df[col]
    ser = ser[~ser.isna()]
    if ser.empty:
        return {"count": 0}
    abs_ser = ser.abs()
    return {
        "count": int(ser.shape[0]),
        "mean_abs": float(abs_ser.mean()),
        "p95_abs": float(abs_ser.quantile(0.95)),
        "max_abs": float(abs_ser.max()),
    }


def render_profit_oracle_markdown(
    df: pd.DataFrame,
    *,
    basis: ProfitBasis,
    thresholds: ProfitOracleThresholds = ProfitOracleThresholds(),
    top_n: int = 20,
) -> str:
    """Render an inspectable report with pass/fail and top offenders."""

    if df.empty:
        return f"# F-002 Profit Oracle ({basis})\n\n(no rows)\n"

    stats_margin = _delta_stats(df, "margin_delta")
    stats_profit = _delta_stats(df, "profit_delta_rmb")
    stats_cost = _delta_stats(df, "cost_delta_rmb")

    def _count_over(col: str, thr: float) -> int:
        s = df[col]
        s = s[~s.isna()]
        if s.empty:
            return 0
        return int((s.abs() > thr).sum())

    n_margin_bad = _count_over("margin_delta", thresholds.margin_delta_abs)
    n_profit_bad = _count_over("profit_delta_rmb", thresholds.rmb_delta_abs)
    n_cost_bad = _count_over("cost_delta_rmb", thresholds.rmb_delta_abs)

    ok = (n_margin_bad == 0) and (n_profit_bad == 0) and (n_cost_bad == 0)

    md = []
    md.append(f"# F-002 Profit Oracle ({basis})")
    md.append("")
    md.append(f"- Rows: {df.shape[0]}")
    md.append(f"- Status: {'PASS' if ok else 'FAIL'}")
    md.append("")
    md.append("## Thresholds")
    md.append("")
    md.append(f"- margin_delta_abs <= {thresholds.margin_delta_abs} (0~1 scale)")
    md.append(f"- profit/cost delta <= {thresholds.rmb_delta_abs} RMB")
    md.append("")
    md.append("## Delta stats (abs)")
    md.append("")
    md.append(
        "| metric | count | mean_abs | p95_abs | max_abs | over_threshold |\n"
        "|---|---:|---:|---:|---:|---:|"
    )
    md.append(
        "| margin_delta | {count} | {mean_abs} | {p95_abs} | {max_abs} | {over} |".format(
            count=stats_margin.get("count", 0),
            mean_abs=_fmt_num(stats_margin.get("mean_abs"), digits=6),
            p95_abs=_fmt_num(stats_margin.get("p95_abs"), digits=6),
            max_abs=_fmt_num(stats_margin.get("max_abs"), digits=6),
            over=n_margin_bad,
        )
    )
    md.append(
        "| profit_delta_rmb | {count} | {mean_abs} | {p95_abs} | {max_abs} | {over} |".format(
            count=stats_profit.get("count", 0),
            mean_abs=_fmt_num(stats_profit.get("mean_abs"), digits=4),
            p95_abs=_fmt_num(stats_profit.get("p95_abs"), digits=4),
            max_abs=_fmt_num(stats_profit.get("max_abs"), digits=4),
            over=n_profit_bad,
        )
    )
    md.append(
        "| cost_delta_rmb | {count} | {mean_abs} | {p95_abs} | {max_abs} | {over} |".format(
            count=stats_cost.get("count", 0),
            mean_abs=_fmt_num(stats_cost.get("mean_abs"), digits=4),
            p95_abs=_fmt_num(stats_cost.get("p95_abs"), digits=4),
            max_abs=_fmt_num(stats_cost.get("max_abs"), digits=4),
            over=n_cost_bad,
        )
    )

    # Top offenders: we expose three views so it's easy to understand what went wrong.
    md.append("")
    md.append("## Top offenders")
    md.append("")

    def _top_table(col: str, digits: int = 4) -> str:
        if col not in df.columns:
            return ""
        part = df.dropna(subset=[col]).copy()
        if part.empty:
            return "(none)\n"
        part["_abs"] = part[col].abs()
        part = part.sort_values(["_abs"], ascending=False).head(top_n)
        cols = ["category", "name", "spec", "status", "price", "cost", "workbook_margin", "gross_margin", col]
        cols = [c for c in cols if c in part.columns]
        show = part[cols].copy()
        # percent columns to % for readability
        for pc in ["workbook_margin", "gross_margin", "margin_delta"]:
            if pc in show.columns:
                show[pc] = show[pc] * 100.0
        try:
            return show.to_markdown(index=False, floatfmt=f".{digits}f") + "\n"
        except Exception:
            return show.to_string(index=False) + "\n"

    md.append("### By abs(margin_delta) (percentage points)")
    md.append("")
    md.append(_top_table("margin_delta", digits=4))
    md.append("### By abs(profit_delta_rmb)")
    md.append("")
    md.append(_top_table("profit_delta_rmb", digits=4))
    md.append("### By abs(cost_delta_rmb)")
    md.append("")
    md.append(_top_table("cost_delta_rmb", digits=4))

    return "\n".join(md)
