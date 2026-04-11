from __future__ import annotations

import argparse
from pathlib import Path

from mike_product_calc.data.loader import load_workbook
from mike_product_calc.data.validator import issues_to_dataframe, issues_to_report, validate_workbook
from mike_product_calc.calc.profit_oracle import (
    ProfitOracleThresholds,
    render_profit_oracle_markdown,
    sku_profit_consistency_table,
)


def cmd_validate(args: argparse.Namespace) -> int:
    wb = load_workbook(args.xlsx)
    issues = validate_workbook(wb.sheets)
    df = issues_to_dataframe(issues)

    # V2: print structured summary first
    report = issues_to_report(issues)
    print(report.markdown_summary())
    print()  # blank line before detail table

    # Sheet-level mapping notes (fuzzy matches, missing sheets)
    if wb.mapping.fuzzy:
        print("### Sheet name resolution (fuzzy matches)")
        for expected, actual in wb.mapping.fuzzy.items():
            print(f"  '{expected}' <- '{actual}'")
        print()
    if wb.mapping.missing:
        print(f"### Missing sheets ({len(wb.mapping.missing)}):")
        for s in wb.mapping.missing:
            print(f"  - '{s}'")
        print()

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        print(f"Wrote {len(df)} issue rows to {out}")
    else:
        print("---")
        print()
        print(df.to_string(index=False))

    # Non-zero when errors exist
    has_error = any(i.severity == "error" for i in issues)
    return 2 if has_error else 0


def cmd_profit_oracle(args: argparse.Namespace) -> int:
    wb = load_workbook(args.xlsx)

    only_status = None if str(args.only_status).strip() in {"(all)", "", "None", "none"} else args.only_status

    bases: list[str]
    if args.basis == "both":
        bases = ["factory", "store"]
    else:
        bases = [args.basis]

    thresholds = ProfitOracleThresholds(
        margin_delta_abs=float(args.margin_delta_abs),
        rmb_delta_abs=float(args.rmb_delta_abs),
    )

    reports: list[str] = []
    exit_code = 0
    for b in bases:
        df = sku_profit_consistency_table(wb.sheets, basis=b, only_status=only_status)
        md = render_profit_oracle_markdown(df, basis=b, thresholds=thresholds, top_n=int(args.top))
        reports.append(md)
        if not df.empty:
            bad_margin = (df["margin_delta"].dropna().abs() > thresholds.margin_delta_abs).sum()
            bad_profit = (df["profit_delta_rmb"].dropna().abs() > thresholds.rmb_delta_abs).sum()
            bad_cost = (df["cost_delta_rmb"].dropna().abs() > thresholds.rmb_delta_abs).sum()
            if (bad_margin + bad_profit + bad_cost) > 0:
                exit_code = 2

    combined = "\n\n---\n\n".join(reports)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(combined, encoding="utf-8")
        print(f"Wrote profit oracle report to {out}")
    else:
        print(combined)

    return exit_code


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mike-product-calc")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="Validate workbook and emit issue report")
    v.add_argument("xlsx", help="Path to 蜜可诗产品库.xlsx")
    v.add_argument("--out", help="Write issues to CSV")
    v.set_defaults(func=cmd_validate)

    o = sub.add_parser("profit-oracle", help="F-002 acceptance oracle: profit/margin consistency checks")
    o.add_argument("xlsx", help="Path to 蜜可诗产品库.xlsx")
    o.add_argument("--basis", choices=["factory", "store", "both"], default="both")
    o.add_argument("--only-status", default="上线", help="Filter by 状态; use '(all)' to disable")
    o.add_argument("--margin-delta-abs", default="1e-4", help="Abs threshold for margin_delta (0~1 scale)")
    o.add_argument("--rmb-delta-abs", default="0.01", help="Abs threshold in RMB for profit/cost deltas")
    o.add_argument("--top", default="20", help="Top offenders per view")
    o.add_argument("--out", help="Write report to markdown")
    o.set_defaults(func=cmd_profit_oracle)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
