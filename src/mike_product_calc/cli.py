"""
cli.py — 有状态、agent 友好 CLI for mike-product-calc.

Exit codes
----------
  0  — OK
  1  — 系统/参数错误 (SystemExit(1))
  2  — 业务校验失败 (SystemExit(2))

Output
-----
  默认 --format json: stdout 仅输出纯 JSON，无任何额外文字。
  支持 --out <file>: 将结果写入文件（JSON 或 CSV）。
  --format text: 人类可读的表格/文本格式。

State
-----
  mpc state init/load/save/list 管理会话状态（默认路径 repo/state/）。
  CLI 命令会自动加载当前 state 中的 xlsx_path 和 price_version。

硬规则 (CLI_UI_HARD_RULES.md)
-----------------------------
  1. 所有 core 业务逻辑只存在于 calc/* 和 data/* 模块。
  2. CLI 绝不复制或重写业务逻辑；调用同一套 core 用例。
  3. 任何新功能必须同时完善 CLI 和 UI (app.py)，测试覆盖双方。
  4. Exit code 语义不得改变。
  5. JSON 输出 schema 变更需要同步更新 tests/golden/ 对应文件。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from mike_product_calc.calc.capacity import score_capacity_from_plan
from mike_product_calc.calc.margin_target import target_pricing
from mike_product_calc.calc.material_sim import (
    MaterialPriceAdjustment,
    Scenario,
    ScenarioStore,
    compare_scenarios,
    get_builtin_scenarios,
    simulate_scenario,
)
from mike_product_calc.calc.optimizer import (
    OptimizationConstraint,
    enumerate_portfolios,
    explain_recommendation,
)
from mike_product_calc.calc.prep_engine import bom_expand_multi, gaps_only
from mike_product_calc.calc.profit import sku_profit_table
from mike_product_calc.calc.profit_oracle import (
    ProfitOracleThresholds,
    render_profit_oracle_markdown,
    sku_profit_consistency_table,
)
from mike_product_calc.calc.purchase_suggestion import build_purchase_list
from mike_product_calc.calc.scenarios import (
    PortfolioScenario,
    compare_portfolios,
    evaluate_multi_scenario,
    evaluate_portfolio,
    multi_scenario_comparison_df,
)
from mike_product_calc.data.loader import load_workbook
from mike_product_calc.data.validator import issues_to_dataframe, issues_to_report, validate_workbook
from mike_product_calc.model.production import ProductionPlan, ProductionRow
from mike_product_calc.state import MpcState, StateStore, get_store, _ensure_xlsx


# ══════════════════════════════════════════════════════════════════════════════════
# Output helpers
# ══════════════════════════════════════════════════════════════════════════════════

def _dump_json(obj: Any, *, out: Optional[str] = None) -> None:
    """Write JSON to file or stdout."""
    txt = json.dumps(obj, ensure_ascii=False, indent=2)
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
    else:
        sys.stdout.write(txt + "\n")


def _dump_csv(df: pd.DataFrame, *, out: Optional[str] = None) -> None:
    """Write CSV to file or stdout."""
    txt = df.to_csv(index=False)
    if out:
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
    else:
        sys.stdout.write(txt + "\n")


def _parse_only_status(v: str) -> Optional[str]:
    return None if str(v).strip() in {"(all)", "", "None", "none"} else str(v)


def _parse_sku_kv(items: List[str]) -> Dict[str, float]:
    """Parse repeated --sku "品类|品名|规格=qty" into {key: qty}."""
    out: Dict[str, float] = {}
    for it in items:
        s = str(it).strip()
        if not s:
            continue
        if "=" not in s:
            sys.stderr.write(f"Error: invalid --sku '{it}'. Expected format: 品类|品名|规格=qty\n")
            raise SystemExit(1)
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            sys.stderr.write(f"Error: invalid --sku '{it}': empty key\n")
            raise SystemExit(1)
        try:
            qty = float(v)
        except ValueError:
            sys.stderr.write(f"Error: --sku '{it}': qty must be numeric\n")
            raise SystemExit(1)
        out[k] = qty
    return out


def _load_sku_qty_from_args(args: argparse.Namespace) -> Dict[str, float]:
    if getattr(args, "sku", None):
        return _parse_sku_kv(list(args.sku))
    sel_json = getattr(args, "selections_json", None)
    if not sel_json:
        return {}
    p = Path(sel_json)
    if not p.exists():
        sys.stderr.write(f"Error: Selections JSON not found: {p}\n")
        raise SystemExit(1)
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "selections" in data:
        data = data["selections"]
    out: Dict[str, float] = {}
    for k, v in data.items():
        k = str(k).strip()
        if not k:
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            sys.stderr.write(f"Error: invalid qty for key '{k}' in selections JSON\n")
            raise SystemExit(1)
    return out


def _load_sheets(xlsx: str):
    """Load workbook sheets (shared by all commands)."""
    try:
        return load_workbook(xlsx).sheets
    except FileNotFoundError:
        sys.stderr.write(f"Error: xlsx not found: {xlsx}\n")
        raise SystemExit(1)
    except Exception as exc:
        sys.stderr.write(f"Error loading workbook: {exc}\n")
        raise SystemExit(1)


# ══════════════════════════════════════════════════════════════════════════════════
# State commands
# ══════════════════════════════════════════════════════════════════════════════════

def cmd_state_init(args: argparse.Namespace) -> int:
    """Initialise (or overwrite) a named state."""
    store = get_store()
    state = store.init(
        name=args.name or "default",
        xlsx_path=str(Path(args.xlsx).resolve()) if args.xlsx else None,
        price_version=args.price_version or "当前",
        scenario_name=args.scenario_name or "A",
        production_plan_name=args.production_plan,
        optimizer_max_capacity=int(args.max_capacity) if args.max_capacity else 200,
        optimizer_material_budget=float(args.material_budget) if args.material_budget else 50000.0,
        optimizer_min_sales_per_sku=int(args.min_sales) if args.min_sales else 1,
    )
    _dump_json({"cmd": "state-init", "name": state.name, "state": state.to_dict()})
    return 0


def cmd_state_load(args: argparse.Namespace) -> int:
    """Load and print a named state."""
    store = get_store()
    state = store.load(args.name or "default")
    _dump_json({"cmd": "state-load", "name": state.name, "state": state.to_dict()})
    return 0


def cmd_state_save(args: argparse.Namespace) -> int:
    """Save current session state (from --state-json) to a named state."""
    store = get_store()
    if args.state_json:
        try:
            with open(args.state_json, encoding="utf-8") as f:
                d = json.load(f)
            state = MpcState.from_dict(d)
            if args.name:
                state.name = args.name
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            sys.stderr.write(f"Error reading --state-json: {exc}\n")
            raise SystemExit(1)
    else:
        state = store.load(args.name or "default")
        state.touch()
    store.save(state)
    _dump_json({"cmd": "state-save", "name": state.name, "updated_at": state.updated_at})
    return 0


def cmd_state_list(args: argparse.Namespace) -> int:
    """List all saved state names."""
    store = get_store()
    names = store.list_states()
    _dump_json({"cmd": "state-list", "states": names})
    return 0


def cmd_state_delete(args: argparse.Namespace) -> int:
    """Delete a named state."""
    store = get_store()
    deleted = store.delete(args.name)
    _dump_json({"cmd": "state-delete", "name": args.name, "deleted": deleted})
    return 0


def cmd_state_snapshot(args: argparse.Namespace) -> int:
    """Save a timestamped snapshot of a named state."""
    store = get_store()
    ts = store.snapshot(args.name or "default")
    snaps = store.list_snapshots(args.name or "default")
    _dump_json({
        "cmd": "state-snapshot",
        "name": args.name or "default",
        "snapshot_id": ts,
        "snapshots_count": len(snaps),
        "snapshots": snaps,
    })
    return 0


def cmd_state_restore(args: argparse.Namespace) -> int:
    """Restore a named state from a snapshot ID (timestamp)."""
    store = get_store()
    state = store.restore_snapshot(args.snapshot_id, args.name or "default")
    _dump_json({
        "cmd": "state-restore",
        "name": state.name,
        "snapshot_id": args.snapshot_id,
        "state": state.to_dict(),
    })
    return 0


def cmd_state_snapshots_list(args: argparse.Namespace) -> int:
    """List available snapshots for a named state."""
    store = get_store()
    snaps = store.list_snapshots(args.name or "default")
    _dump_json({
        "cmd": "state-snapshots-list",
        "name": args.name or "default",
        "snapshots": snaps,
        "max_kept": store.MAX_SNAPSHOTS,
    })
    return 0


# ══════════════════════════════════════════════════════════════════════════════════
# Core business commands
# ══════════════════════════════════════════════════════════════════════════════════

def cmd_validate(args: argparse.Namespace) -> int:
    """Validate workbook and emit issue report."""
    xlsx = _ensure_xlsx_from_args(args)
    wb_sheets = _load_sheets(xlsx)
    issues = validate_workbook(wb_sheets)
    df = issues_to_dataframe(issues)
    has_error = any(i.severity == "error" for i in issues)
    report = issues_to_report(issues)

    sev = report.severity_counts
    payload = {
        "cmd": "validate",
        "xlsx": xlsx,
        "has_error": has_error,
        "summary": {
            "total": int(report.total_issues),
            "error": int(sev.error),
            "warn": int(sev.warn),
            "info": int(sev.info),
        },
        "out_csv": str(args.out) if args.out else None,
    }
    if args.format == "json":
        _dump_json(payload, out=args.out)
        if args.out:
            df.to_csv(Path(args.out).with_suffix(".csv"), index=False)
        return 2 if has_error else 0

    # Human-readable fallback
    print(report.markdown_summary())
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out, index=False)
        print(f"\nWrote {len(df)} rows to {out}")
    return 2 if has_error else 0


def cmd_profit_oracle(args: argparse.Namespace) -> int:
    """F-002 acceptance oracle: profit/margin consistency checks."""
    xlsx = _ensure_xlsx_from_args(args)
    sheets = _load_sheets(xlsx)
    only_status = _parse_only_status(args.only_status)
    bases = ["factory", "store"] if args.basis == "both" else [args.basis]
    thresholds = ProfitOracleThresholds(
        margin_delta_abs=float(args.margin_delta_abs),
        rmb_delta_abs=float(args.rmb_delta_abs),
    )
    reports: List[Dict[str, Any]] = []
    exit_code = 0
    for b in bases:
        df = sku_profit_consistency_table(sheets, basis=b, only_status=only_status)
        if not df.empty:
            bad_margin = int((df["margin_delta"].dropna().abs() > thresholds.margin_delta_abs).sum())
            bad_profit = int((df["profit_delta_rmb"].dropna().abs() > thresholds.rmb_delta_abs).sum())
            bad_cost   = int((df["cost_delta_rmb"].dropna().abs() > thresholds.rmb_delta_abs).sum())
            if bad_margin + bad_profit + bad_cost > 0:
                exit_code = 2
        else:
            bad_margin = bad_profit = bad_cost = 0
        reports.append({"basis": b, "rows": int(len(df)), "bad_margin": bad_margin,
                         "bad_profit": bad_profit, "bad_cost": bad_cost,
                         "thresholds": asdict(thresholds)})
    payload = {"cmd": "profit-oracle", "xlsx": xlsx, "only_status": only_status,
               "reports": reports, "exit_code": exit_code}
    if args.format == "json":
        _dump_json(payload, out=args.out)
        return exit_code
    combined = "\n\n---\n\n".join(
        render_profit_oracle_markdown(sku_profit_consistency_table(sheets, basis=b, only_status=only_status),
                                     basis=b, thresholds=thresholds, top_n=int(args.top))
        for b in bases
    )
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(combined, encoding="utf-8")
    else:
        print(combined)
    return exit_code


def cmd_sku_list(args: argparse.Namespace) -> int:
    """List available SKU product_keys (machine-friendly)."""
    xlsx = _ensure_xlsx_from_args(args)
    sheets = _load_sheets(xlsx)
    only_status = _parse_only_status(args.only_status)
    df = sku_profit_table(sheets, basis=args.basis, only_status=only_status,
                          cost_mode=getattr(args, "cost_mode", "computed"))
    if df.empty:
        _dump_json({"cmd": "sku-list", "xlsx": xlsx, "count": 0, "rows": []}, out=args.out)
        return 0
    if args.limit:
        df = df.head(int(args.limit)).copy()
    cols = ["product_key", "category", "name", "spec", "status", "price", "cost",
            "cost_source", "gross_margin"]
    cols = [c for c in cols if c in df.columns]
    if args.format == "json":
        payload = {"cmd": "sku-list", "xlsx": xlsx, "basis": args.basis,
                   "only_status": only_status, "count": int(len(df)), "rows": df[cols].to_dict(orient="records")}
        _dump_json(payload, out=args.out)
        return 0
    print(df[cols].to_string(index=False))
    return 0


def cmd_portfolio_eval(args: argparse.Namespace) -> int:
    """Evaluate a portfolio (multi-SKU with quantities)."""
    xlsx = _ensure_xlsx_from_args(args)
    sheets = _load_sheets(xlsx)
    sku_qty = _load_sku_qty_from_args(args)
    scenario = PortfolioScenario.from_dict(args.name, sku_qty)
    result = evaluate_portfolio(scenario, sheets, basis=args.basis)
    if args.format == "json":
        _dump_json({"cmd": "portfolio-eval", "xlsx": xlsx, "basis": args.basis, **asdict(result)}, out=args.out)
        return 0
    print(f"Scenario: {result.name} | Revenue: {result.total_revenue} | Cost: {result.total_cost} "
          f"| Profit: {result.total_profit} | Margin: {result.total_margin} | SKUs: {result.sku_count}")
    return 0


def cmd_portfolio_compare(args: argparse.Namespace) -> int:
    """Compare multiple scenarios (NAME=path.json)."""
    xlsx = _ensure_xlsx_from_args(args)
    sheets = _load_sheets(xlsx)
    scenarios: List[PortfolioScenario] = []
    for item in args.scenario_json or []:
        s = str(item).strip()
        if "=" not in s:
            sys.stderr.write(f"Error: invalid --scenario-json '{item}'. Expected NAME=path.json\n")
            raise SystemExit(1)
        name, path = s.split("=", 1)
        name, path = name.strip(), path.strip()
        if not name:
            sys.stderr.write("Error: --scenario-json: empty NAME\n")
            raise SystemExit(1)
        p = Path(path)
        if not p.exists():
            sys.stderr.write(f"Error: scenario json not found: {p}\n")
            raise SystemExit(1)
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "selections" in data:
            data = data["selections"]
        sku_qty = {str(k).strip(): float(v) for k, v in data.items() if str(k).strip()}
        scenarios.append(PortfolioScenario.from_dict(name, sku_qty))
    results = [evaluate_portfolio(s, sheets, basis=args.basis) for s in scenarios]
    df = compare_portfolios(results)
    if args.format == "json":
        _dump_json({"cmd": "portfolio-compare", "xlsx": xlsx, "basis": args.basis,
                    "rows": df.to_dict(orient="records")}, out=args.out)
        return 0
    print(df.to_string(index=False))
    return 0


def cmd_target_pricing(args: argparse.Namespace) -> int:
    """F-003: target-cost reverse pricing for a SKU."""
    xlsx = _ensure_xlsx_from_args(args)
    sheets = _load_sheets(xlsx)
    try:
        summary, df = target_pricing(
            sheets,
            product_key=args.product_key,
            target_margin=float(args.target_margin),
            basis=args.basis,
            locked_items=getattr(args, "lock", None) or None,
        )
    except (KeyError, ValueError) as exc:
        sys.stderr.write(f"Error: {exc}\n")
        return 1
    if df.empty:
        payload = {"cmd": "target-pricing", "xlsx": xlsx, "product_key": args.product_key,
                   "target_margin": float(args.target_margin), "rows": []}
        _dump_json(payload, out=args.out)
        return 0
    cols = [c for c in df.columns if c in df.columns]
    payload = {"cmd": "target-pricing", "xlsx": xlsx, "product_key": args.product_key,
               "target_margin": float(args.target_margin), "basis": args.basis,
               "summary": asdict(summary), "count": int(len(df)), "rows": df[cols].to_dict(orient="records")}
    _dump_json(payload, out=args.out)
    return 0


def cmd_material_sim(args: argparse.Namespace) -> int:
    """F-004: material price simulator — version management + comparison."""
    xlsx = _ensure_xlsx_from_args(args)
    sheets = _load_sheets(xlsx)
    sub = args.subcommand

    if sub == "versions":
        # List all saved versions (from state + built-in)
        store = get_store()
        state = store.load("default")
        builtin = ["当前", "保守", "理想", "旺季"]
        custom = list(state.material_sim_versions.keys())
        _dump_json({"cmd": "material-sim-versions", "builtin": builtin, "custom": custom,
                    "active": state.price_version})
        return 0

    if sub == "compare":
        a_name = args.scenario_a
        b_name = args.scenario_b
        # Build Scenario objects
        store = get_store()
        state = store.load("default")
        adj_a = _build_scenario_from_args(args, "a", state)
        adj_b = _build_scenario_from_args(args, "b", state)
        sc_a = Scenario(name=a_name, adjustments=tuple(adj_a))
        sc_b = Scenario(name=b_name, adjustments=tuple(adj_b))
        df = compare_scenarios(sc_a, sc_b, sheets, basis=args.basis)
        cols = [c for c in ["product_key", "name", "spec", "category", "price", "cost",
                             "gross_profit", "gross_margin", "gp_a", "gm_a", "gp_b", "gm_b",
                             "gp_delta_ab", "gm_delta_pp_ab", "high_risk"]
                if c in df.columns]
        high_risk_count = int(df["high_risk"].sum()) if "high_risk" in df.columns else 0
        payload = {"cmd": "material-sim-compare", "xlsx": xlsx, "scenario_a": a_name,
                   "scenario_b": b_name, "basis": args.basis, "high_risk_count": high_risk_count,
                   "count": int(len(df)), "rows": df[cols].to_dict(orient="records")}
        _dump_json(payload, out=args.out)
        return 2 if high_risk_count > 0 else 0

    if sub == "simulate":
        store = get_store()
        state = store.load("default")
        adj = _build_scenario_from_args(args, "", state)
        version_name = args.version or getattr(state, "price_version", "当前") or "当前"
        scenario = Scenario(name=version_name, adjustments=tuple(adj))
        df = simulate_scenario(sheets, scenario, basis=args.basis)
        cols = [c for c in ["product_key", "name", "category", "status", "price", "cost",
                             "adjusted_cost", "has_adjusted", "gross_profit", "adjusted_gross_profit",
                             "gp_delta", "margin_delta_pp"] if c in df.columns]
        payload = {"cmd": "material-sim-simulate", "xlsx": xlsx, "version": scenario.name,
                   "basis": args.basis, "count": int(len(df)), "rows": df[cols].to_dict(orient="records")}
        _dump_json(payload, out=args.out)
        return 0

    # list (default)
    _dump_json({"cmd": "material-sim", "subcommands": ["versions", "simulate", "compare"]})
    return 0


def _build_scenario_from_args(args: argparse.Namespace, suffix: str, state: MpcState) -> List[MaterialPriceAdjustment]:
    """Parse --adj-suffix args into MaterialPriceAdjustment list."""
    adj: List[MaterialPriceAdjustment] = []
    # Gather all --adj or --adj-a / --adj-b style args
    prefix = f"adj_{suffix}_" if suffix else "adj_"
    for attr in dir(args):
        if attr.startswith(prefix):
            items = getattr(args, attr) or []
            for it in items:
                s = str(it).strip()
                if "=" not in s:
                    sys.stderr.write(f"Error: invalid adjustment '{it}'. Expected item=qty\n")
                    raise SystemExit(1)
                item, price = s.split("=", 1)
                item = item.strip()
                try:
                    price_f = float(price.strip())
                except ValueError:
                    sys.stderr.write(f"Error: price must be numeric for '{item}'\n")
                    raise SystemExit(1)
                adj.append(MaterialPriceAdjustment(item=item, new_unit_price=price_f))
    return adj


def cmd_production_plan(args: argparse.Namespace) -> int:
    """F-005: production plan import/export."""
    xlsx = _ensure_xlsx_from_args(args)
    sheets = _load_sheets(xlsx)
    sub = args.subcommand

    if sub == "export":
        # Export named production plan to JSON
        plan_name = args.name or "default"
        store = get_store()
        state = store.load("default")
        if not state.last_portfolio_selections and not args.sku:
            payload = {"cmd": "production-plan-export", "name": plan_name, "rows": []}
        else:
            sku_qty = _load_sku_qty_from_args(args) or state.last_portfolio_selections
            rows_out = [{"sku_key": k, "qty": v} for k, v in sku_qty.items()]
            payload = {"cmd": "production-plan-export", "name": plan_name, "rows": rows_out,
                       "count": len(rows_out)}
        _dump_json(payload, out=args.out)
        return 0

    if sub == "import":
        # Import production plan from JSON file
        plan_path = args.__dict__.get("plan-json") or getattr(args, "plan-json", None)
        p = Path(plan_path)
        if not p.exists():
            sys.stderr.write(f"Error: plan JSON not found: {plan_path}\n")
            raise SystemExit(1)
        data = json.loads(p.read_text(encoding="utf-8"))
        selections = data.get("selections", data) if isinstance(data, dict) else {}
        sku_qty = {str(k).strip(): float(v) for k, v in selections.items() if str(k).strip()}
        # Save to state
        store = get_store()
        state = store.load("default")
        state.last_portfolio_selections = sku_qty
        state.production_plan_name = data.get("name", args.name or "imported")
        state.touch()
        store.save(state)
        payload = {"cmd": "production-plan-import", "name": state.production_plan_name,
                   "count": len(sku_qty), "rows": [{"sku_key": k, "qty": v} for k, v in sku_qty.items()]}
        _dump_json(payload, out=args.out)
        return 0

    if sub == "list":
        # List all saved production plans from state
        store = get_store()
        state = store.load("default")
        # Build a simple registry from state (stored plan names)
        plans = [state.production_plan_name] if state.production_plan_name else []
        payload = {"cmd": "production-plan-list", "plans": plans, "active": state.production_plan_name}
        _dump_json(payload)
        return 0

    _dump_json({"cmd": "production-plan", "subcommands": ["export", "import", "list"]})
    return 0


def cmd_prep_plan(args: argparse.Namespace) -> int:
    """F-006: BOM expansion → material demand table."""
    xlsx = _ensure_xlsx_from_args(args)
    sheets = _load_sheets(xlsx)
    sku_qty = _load_sku_qty_from_args(args)
    if not sku_qty:
        sys.stderr.write("Error: --sku or --selections-json required for prep-plan\n")
        raise SystemExit(1)
    order_date = None
    if args.order_date:
        try:
            order_date = date.fromisoformat(args.order_date)
        except ValueError:
            sys.stderr.write(f"Error: invalid --order-date format: {args.order_date}. Use YYYY-MM-DD.\n")
            raise SystemExit(1)
    df = bom_expand_multi(
        sheets, sku_qty, basis=args.basis, order_date=order_date,
        default_lead_days=int(args.lead_days) if args.lead_days else 3,
        default_loss_rate=float(args.loss_rate) if args.loss_rate else 0.0,
        default_safety_stock=float(args.safety_stock) if args.safety_stock else 0.0,
    )
    if df.empty:
        payload = {"cmd": "prep-plan", "xlsx": xlsx, "basis": args.basis, "count": 0, "rows": []}
        _dump_json(payload, out=args.out)
        return 0
    cols = [c for c in ["material", "level", "purchase_unit", "lead_days",
                         "total_plan_qty", "total_gross_qty", "total_safety_stock",
                         "total_purchase_qty", "unit_price", "total_cost",
                         "is_gap", "gap_reason", "is_semi_finished", "sku_keys", "latest_order_date"]
             if c in df.columns]
    payload = {"cmd": "prep-plan", "xlsx": xlsx, "basis": args.basis,
               "count": int(len(df)), "rows": df[cols].to_dict(orient="records")}
    if args.out and args.out.endswith(".csv"):
        _dump_csv(df[cols], out=args.out)
        return 0
    _dump_json(payload, out=args.out)
    return 0


def cmd_purchase_suggest(args: argparse.Namespace) -> int:
    """F-007: purchase suggestion from BOM demand."""
    xlsx = _ensure_xlsx_from_args(args)
    sheets = _load_sheets(xlsx)
    sku_qty = _load_sku_qty_from_args(args)
    if not sku_qty:
        sys.stderr.write("Error: --sku or --selections-json required for purchase-suggest\n")
        raise SystemExit(1)
    bom_df = bom_expand_multi(sheets, sku_qty, basis=args.basis)
    purchase_df = build_purchase_list(bom_df)
    if purchase_df.empty:
        payload = {"cmd": "purchase-suggest", "xlsx": xlsx, "basis": args.basis, "count": 0, "rows": []}
        _dump_json(payload, out=args.out)
        return 0
    cols = [c for c in ["order_date", "arrival_date", "material", "qty", "unit",
                         "source_skus", "is_urgent"] if c in purchase_df.columns]
    payload = {"cmd": "purchase-suggest", "xlsx": xlsx, "basis": args.basis,
               "count": int(len(purchase_df)), "rows": purchase_df[cols].to_dict(orient="records")}
    if args.out and args.out.endswith(".csv"):
        _dump_csv(purchase_df[cols], out=args.out)
        return 0
    _dump_json(payload, out=args.out)
    return 0


def cmd_optimizer(args: argparse.Namespace) -> int:
    """F-012: SKU portfolio optimizer."""
    xlsx = _ensure_xlsx_from_args(args)
    sheets = _load_sheets(xlsx)
    only_status = _parse_only_status(args.only_status)
    profit_df = sku_profit_table(sheets, basis=args.basis, only_status=only_status)
    if profit_df.empty:
        _dump_json({"cmd": "optimizer", "xlsx": xlsx, "basis": args.basis,
                     "recommendations": []})
        return 0
    # Filter to online SKUs with valid price/cost
    pool = profit_df[profit_df["price"].notna() & profit_df["cost"].notna() &
                     (profit_df["price"] > 0)].copy()
    constraints = OptimizationConstraint(
        max_capacity=int(args.max_capacity) if args.max_capacity else 200,
        material_budget=float(args.material_budget) if args.material_budget else 50000.0,
        min_sales_per_sku=int(args.min_sales) if args.min_sales else 1,
    )
    results = enumerate_portfolios(
        pool, constraints,
        max_qty_per_sku=int(args.max_qty_per_sku) if args.max_qty_per_sku else 20,
        max_combos=int(args.max_combos) if args.max_combos else 200_000,
        basis=args.basis,
    )
    recommendations = []
    for scenario, result, feasible in results:
        if result is None:
            continue
        recommendations.append({
            "name": scenario.name,
            "feasible": feasible,
            **asdict(result),
        })
    payload = {"cmd": "optimizer", "xlsx": xlsx, "basis": args.basis,
               "constraints": asdict(constraints), "count": len(recommendations),
               "recommendations": recommendations}
    _dump_json(payload, out=args.out)
    return 0


# ══════════════════════════════════════════════════════════════════════════════════
# Argument parser
# ══════════════════════════════════════════════════════════════════════════════════

def _add_state_subparser(sub: argparse._SubParsersAction) -> None:
    """Add `state` subcommand and its children."""
    p = sub.add_parser("state", help="State management: init/load/save/list/delete/snapshot/restore")
    s = p.add_subparsers(dest="state_cmd", required=True)

    # shared --name argument (add to each child; argparse doesn't inherit parent-level args)
    name_kw = {"--name"}  # marker for which args share "name"

    # init
    sp = s.add_parser("init",  help="Init or overwrite a named state")
    sp.add_argument("--name", default="default", help="State name")
    sp.add_argument("--xlsx", help="Default xlsx path")
    sp.add_argument("--price-version", default="当前", help="Price version")
    sp.add_argument("--scenario-name", default="A", help="Default scenario name")
    sp.add_argument("--production-plan", help="Production plan name")
    sp.add_argument("--max-capacity", help="Optimizer: max capacity")
    sp.add_argument("--material-budget", help="Optimizer: material budget")
    sp.add_argument("--min-sales", help="Optimizer: min sales per SKU")
    sp.set_defaults(func=cmd_state_init)

    # load
    sp = s.add_parser("load", help="Load and print a named state")
    sp.add_argument("--name", default="default", help="State name")
    sp.set_defaults(func=cmd_state_load)

    # save
    sp = s.add_parser("save", help="Save session state to disk")
    sp.add_argument("--name", default="default", help="State name")
    sp.add_argument("--state-json", help="JSON file with state object")
    sp.set_defaults(func=cmd_state_save)

    # list
    sp = s.add_parser("list", help="List all saved state names")
    sp.add_argument("--name", default="default", help="State name (unused, for consistency)")
    sp.set_defaults(func=cmd_state_list)

    # delete
    sp = s.add_parser("delete", help="Delete a named state")
    sp.add_argument("--name", default="default", help="State name")
    sp.set_defaults(func=cmd_state_delete)

    # snapshot
    sp = s.add_parser("snapshot", help="Save a timestamped snapshot of a named state")
    sp.add_argument("--name", default="default", help="State name")
    sp.set_defaults(func=cmd_state_snapshot)

    # restore
    sp = s.add_parser("restore", help="Restore a named state from a snapshot ID")
    sp.add_argument("snapshot_id", help="Snapshot ID (timestamp from snapshot list)")
    sp.add_argument("--name", default="default", help="State name")
    sp.set_defaults(func=cmd_state_restore)

    # snapshots-list
    sp = s.add_parser("snapshots", help="List available snapshots for a named state")
    sp.add_argument("--name", default="default", help="State name")
    sp.set_defaults(func=cmd_state_snapshots_list)


def _ensure_xlsx_from_args(args: argparse.Namespace) -> str:
    """Resolve xlsx path: CLI arg → state → error."""
    cli_xlsx = getattr(args, "xlsx", None)
    if cli_xlsx:
        p = Path(cli_xlsx)
        if p.exists():
            return str(p.resolve())
        sys.stderr.write(f"Error: xlsx not found: {cli_xlsx}\n")
        raise SystemExit(1)
    # Try state
    store = get_store()
    state = store.load("default")
    xlsx = state.effective_xlsx(None)
    if not xlsx:
        sys.stderr.write("Error: no xlsx path. Run 'mpc state init --xlsx <path>' first.\n")
        raise SystemExit(1)
    p = Path(xlsx)
    if not p.exists():
        sys.stderr.write(f"Error: xlsx not found in state: {xlsx}\n")
        raise SystemExit(1)
    return xlsx


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mike-product-calc",
        description="蜜可诗产品经营决策台 CLI")
    p.add_argument("--version", action="version", version="%(prog)s 0.2.0")
    sub = p.add_subparsers(dest="cmd", required=True)

    # ── validate ────────────────────────────────────────────────────────────────
    v = sub.add_parser("validate", help="Validate workbook and emit issue report")
    v.add_argument("xlsx", nargs="?", help="Path to 蜜可诗产品库.xlsx")
    v.add_argument("--out", help="Write issues CSV to path")
    v.add_argument("--format", choices=["md", "json"], default="json")
    v.set_defaults(func=cmd_validate)

    # ── profit-oracle ──────────────────────────────────────────────────────────
    o = sub.add_parser("profit-oracle", help="F-002: profit/margin consistency oracle")
    o.add_argument("xlsx", nargs="?", help="Path to xlsx")
    o.add_argument("--basis", choices=["factory", "store", "both"], default="both")
    o.add_argument("--only-status", default="上线")
    o.add_argument("--margin-delta-abs", default="1e-4")
    o.add_argument("--rmb-delta-abs", default="0.01")
    o.add_argument("--top", default="20")
    o.add_argument("--out", help="Write report to file")
    o.add_argument("--format", choices=["md", "json"], default="json")
    o.set_defaults(func=cmd_profit_oracle)

    # ── sku-list ────────────────────────────────────────────────────────────────
    s = sub.add_parser("sku-list", help="F-002: list available SKU product_keys")
    s.add_argument("xlsx", nargs="?", help="Path to xlsx")
    s.add_argument("--basis", choices=["factory", "store"], default="factory")
    s.add_argument("--only-status", default="上线")
    s.add_argument("--cost-mode", choices=["computed", "workbook"], default="computed")
    s.add_argument("--limit", default="50")
    s.add_argument("--format", choices=["text", "json"], default="json")
    s.add_argument("--out", help="Write JSON to file")
    s.set_defaults(func=cmd_sku_list)

    # ── portfolio-eval ─────────────────────────────────────────────────────────
    pe = sub.add_parser("portfolio-eval", help="F-008: evaluate a portfolio")
    pe.add_argument("xlsx", nargs="?", help="Path to xlsx")
    pe.add_argument("--basis", choices=["factory", "store"], default="factory")
    pe.add_argument("--name", default="A")
    pe.add_argument("--sku", action="append", default=[], help="品类|品名|规格=qty")
    pe.add_argument("--selections-json", help="JSON with selections")
    pe.add_argument("--format", choices=["text", "json"], default="json")
    pe.add_argument("--out", help="Write JSON to file")
    pe.set_defaults(func=cmd_portfolio_eval)

    # ── portfolio-compare ──────────────────────────────────────────────────────
    pc = sub.add_parser("portfolio-compare", help="F-010: compare multiple scenarios")
    pc.add_argument("xlsx", nargs="?", help="Path to xlsx")
    pc.add_argument("--basis", choices=["factory", "store"], default="factory")
    pc.add_argument("--scenario-json", action="append", default=[], help="NAME=path.json")
    pc.add_argument("--format", choices=["text", "json"], default="json")
    pc.add_argument("--out", help="Write JSON to file")
    pc.set_defaults(func=cmd_portfolio_compare)

    # ── target-pricing ────────────────────────────────────────────────────────
    tp = sub.add_parser("target-pricing", help="F-003: target-cost reverse pricing")
    tp.add_argument("xlsx", nargs="?", help="Path to xlsx")
    tp.add_argument("--product-key", required=True, help="SKU product_key")
    tp.add_argument("--target-margin", required=True, help="Target margin rate (e.g. 0.35)")
    tp.add_argument("--basis", choices=["factory", "store"], default="store")
    tp.add_argument("--lock", action="append", default=[], help="Lock specific material")
    tp.add_argument("--format", choices=["json"], default="json")
    tp.add_argument("--out", help="Write JSON to file")
    tp.set_defaults(func=cmd_target_pricing)

    # ── material-sim ──────────────────────────────────────────────────────────
    ms = sub.add_parser("material-sim", help="F-004: material price simulator")
    ms.add_argument("xlsx", nargs="?", help="Path to xlsx")
    ms.set_defaults(func=lambda a: ms.print_help())
    sm = ms.add_subparsers(dest="subcommand")

    ms_vers = sm.add_parser("versions", help="List all saved material price versions")
    ms_vers.set_defaults(func=cmd_material_sim)

    ms_sim = sm.add_parser("simulate", help="Simulate material price changes")
    ms_sim.add_argument("--version", help="Version name to save as")
    ms_sim.add_argument("--basis", choices=["factory", "store"], default="store")
    ms_sim.add_argument("--adj", action="append", default=[], help="item=price")
    ms_sim.add_argument("--format", choices=["json"], default="json")
    ms_sim.add_argument("--out", help="Write JSON to file")
    ms_sim.set_defaults(func=cmd_material_sim)

    ms_cmp = sm.add_parser("compare", help="Compare two scenarios")
    ms_cmp.add_argument("scenario_a", help="Scenario A name")
    ms_cmp.add_argument("scenario_b", help="Scenario B name")
    ms_cmp.add_argument("--basis", choices=["factory", "store"], default="store")
    for suf in ["a", "b"]:
        ms_cmp.add_argument(f"--adj-{suf}", action="append", default=[], help="item=price")
    ms_cmp.add_argument("--format", choices=["json"], default="json")
    ms_cmp.add_argument("--out", help="Write JSON to file")
    ms_cmp.set_defaults(func=cmd_material_sim)

    # ── production-plan ───────────────────────────────────────────────────────
    pp = sub.add_parser("production-plan", help="F-005: production plan import/export")
    pp.add_argument("xlsx", nargs="?", help="Path to xlsx")
    pp.set_defaults(func=lambda a: pp.print_help())
    ppm = pp.add_subparsers(dest="subcommand")

    pp_exp = ppm.add_parser("export", help="Export production plan to JSON")
    pp_exp.add_argument("--name", default="A", help="Plan name")
    pp_exp.add_argument("--sku", action="append", default=[], help="品类|品名|规格=qty")
    pp_exp.add_argument("--selections-json", help="JSON file")
    pp_exp.add_argument("--format", choices=["json"], default="json")
    pp_exp.add_argument("--out", help="Write JSON to file")
    pp_exp.set_defaults(func=cmd_production_plan)

    pp_imp = ppm.add_parser("import", help="Import production plan from JSON")
    pp_imp.add_argument("plan-json", help="Path to plan JSON file")
    pp_imp.add_argument("--name", help="Plan name override")
    pp_imp.add_argument("--out", help="Write JSON to file")
    pp_imp.set_defaults(func=cmd_production_plan)

    pp_lst = ppm.add_parser("list", help="List saved production plans")
    pp_lst.set_defaults(func=cmd_production_plan)

    # ── prep-plan ─────────────────────────────────────────────────────────────
    pr = sub.add_parser("prep-plan", help="F-006: BOM expansion → material demand")
    pr.add_argument("xlsx", nargs="?", help="Path to xlsx")
    pr.add_argument("--basis", choices=["factory", "store"], default="store")
    pr.add_argument("--sku", action="append", default=[], help="品类|品名|规格=qty")
    pr.add_argument("--selections-json", help="JSON with selections")
    pr.add_argument("--order-date", help="Target delivery date (YYYY-MM-DD)")
    pr.add_argument("--lead-days", default="3")
    pr.add_argument("--loss-rate", default="0.0")
    pr.add_argument("--safety-stock", default="0.0")
    pr.add_argument("--format", choices=["json"], default="json")
    pr.add_argument("--out", help="Write JSON/CSV to file")
    pr.set_defaults(func=cmd_prep_plan)

    # ── purchase-suggest ──────────────────────────────────────────────────────
    ps = sub.add_parser("purchase-suggest", help="F-007: purchase suggestion")
    ps.add_argument("xlsx", nargs="?", help="Path to xlsx")
    ps.add_argument("--basis", choices=["factory", "store"], default="store")
    ps.add_argument("--sku", action="append", default=[], help="品类|品名|规格=qty")
    ps.add_argument("--selections-json", help="JSON with selections")
    ps.add_argument("--format", choices=["json"], default="json")
    ps.add_argument("--out", help="Write JSON/CSV to file")
    ps.set_defaults(func=cmd_purchase_suggest)

    # ── optimizer ─────────────────────────────────────────────────────────────
    opt = sub.add_parser("optimizer", help="F-012: SKU portfolio optimizer")
    opt.add_argument("xlsx", nargs="?", help="Path to xlsx")
    opt.add_argument("--basis", choices=["factory", "store"], default="factory")
    opt.add_argument("--only-status", default="上线")
    opt.add_argument("--max-capacity", default="200")
    opt.add_argument("--material-budget", default="50000")
    opt.add_argument("--min-sales", default="1")
    opt.add_argument("--max-qty-per-sku", default="20")
    opt.add_argument("--max-combos", default="200000")
    opt.add_argument("--format", choices=["json"], default="json")
    opt.add_argument("--out", help="Write JSON to file")
    opt.set_defaults(func=cmd_optimizer)

    # ── state ─────────────────────────────────────────────────────────────────
    _add_state_subparser(sub)

    return p


# ══════════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════════

def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SystemExit as exc:
        return exc.code if exc.code in (0, 1, 2) else 1


if __name__ == "__main__":
    raise SystemExit(main())
