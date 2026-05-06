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
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from mike_product_calc.calc.margin_target import target_pricing
from mike_product_calc.calc.material_sim import (
    MaterialPriceAdjustment,
    Scenario,
    compare_scenarios,
    simulate_scenario,
)
from mike_product_calc.calc.prep_engine import bom_expand_multi
from mike_product_calc.calc.profit import sku_profit_table
from mike_product_calc.calc.profit_oracle import (
    ProfitOracleThresholds,
    render_profit_oracle_markdown,
    sku_profit_consistency_table,
)
from mike_product_calc.calc.purchase_suggestion import build_purchase_list
from mike_product_calc.data.loader import load_workbook
from mike_product_calc.data.validator import issues_to_dataframe, issues_to_report, validate_workbook
from mike_product_calc.state import MpcState, get_store
from mike_product_calc.data.upload import (
    UploadRegistry,
    DuplicateFileError,
)
from mike_product_calc.data.cli_supabase import get_client


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


# ══════════════════════════════════════════════════════════════════════════════════
# Supabase CRUD commands (agent-friendly)
# ══════════════════════════════════════════════════════════════════════════════════

def cmd_material_list(args: argparse.Namespace) -> int:
    """List raw materials from Supabase."""
    client = get_client()
    materials = client.list_raw_materials()
    if args.category:
        materials = [m for m in materials if m.get("category") == args.category]
    if args.status:
        materials = [m for m in materials if m.get("status") == args.status]
    rows = [{k: v for k, v in m.items() if not k.startswith("_")} for m in materials]
    _dump_json({"cmd": "material-list", "count": len(rows), "rows": rows}, out=args.out)
    return 0


def cmd_material_get(args: argparse.Namespace) -> int:
    """Get a single raw material by ID."""
    client = get_client()
    mat = client.get_raw_material(args.id)
    if mat is None:
        _dump_json({"cmd": "material-get", "error": "not_found", "id": args.id}, out=args.out)
        return 1
    _dump_json({"cmd": "material-get", "material": mat}, out=args.out)
    return 0


def cmd_material_create(args: argparse.Namespace) -> int:
    """Create a raw material from a JSON file or inline JSON string."""
    client = get_client()
    data = _load_json_arg(args.data)
    mat = client.create_raw_material(data)
    _dump_json({"cmd": "material-create", "material": mat}, out=args.out)
    return 0


def cmd_material_update(args: argparse.Namespace) -> int:
    """Update a raw material by ID."""
    client = get_client()
    data = _load_json_arg(args.data)
    mat = client.update_raw_material(args.id, data)
    _dump_json({"cmd": "material-update", "id": args.id, "material": mat}, out=args.out)
    return 0


def cmd_material_delete(args: argparse.Namespace) -> int:
    """Delete a raw material by ID."""
    client = get_client()
    client.delete_raw_material(args.id)
    _dump_json({"cmd": "material-delete", "id": args.id, "deleted": True}, out=args.out)
    return 0


def cmd_product_compute_costs(args: argparse.Namespace) -> int:
    """Compute and update factory/store costs for a product (and its semi-product dependencies)."""
    client = get_client()
    result = client.compute_product_costs(args.id)
    _dump_json({"cmd": "product-compute-costs", "id": args.id, "result": result}, out=args.out)
    return 0


def cmd_product_list(args: argparse.Namespace) -> int:
    """List products from Supabase."""
    client = get_client()
    products = client.list_products(is_final=args.final_only or None)
    rows = [{k: v for k, v in p.items() if not k.startswith("_")} for p in products]
    _dump_json({"cmd": "product-list", "count": len(rows), "rows": rows}, out=args.out)
    return 0


def cmd_product_get(args: argparse.Namespace) -> int:
    """Get a single product by ID."""
    client = get_client()
    prod = client.get_product(args.id)
    if prod is None:
        _dump_json({"cmd": "product-get", "error": "not_found", "id": args.id}, out=args.out)
        return 1
    _dump_json({"cmd": "product-get", "product": prod}, out=args.out)
    return 0


def cmd_recipe_list(args: argparse.Namespace) -> int:
    """List recipes (BOM) for a product."""
    client = get_client()
    recipes = client.list_recipes(args.product_id)
    _dump_json({"cmd": "recipe-list", "product_id": args.product_id, "count": len(recipes), "rows": recipes}, out=args.out)
    return 0


def cmd_recipe_set(args: argparse.Namespace) -> int:
    """Replace all recipes for a product (from JSON)."""
    client = get_client()
    data = _load_json_arg(args.data)
    result = client.set_recipes(args.product_id, data)
    _dump_json({"cmd": "recipe-set", "product_id": args.product_id, "count": len(result)}, out=args.out)
    return 0


def cmd_spec_list(args: argparse.Namespace) -> int:
    """List serving specs for a product."""
    client = get_client()
    specs = client.list_serving_specs(args.product_id)
    _dump_json({"cmd": "spec-list", "product_id": args.product_id, "count": len(specs), "rows": specs}, out=args.out)
    return 0


def cmd_spec_set(args: argparse.Namespace) -> int:
    """Replace all serving specs for a product (from JSON)."""
    client = get_client()
    data = _load_json_arg(args.data)
    result = client.set_serving_specs(args.product_id, data)
    _dump_json({"cmd": "spec-set", "product_id": args.product_id, "count": len(result)}, out=args.out)
    return 0


def _load_json_arg(data: str) -> dict | list:
    """Load JSON from a file path or inline string."""
    p = Path(data)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.stderr.write(f"Error: invalid JSON in file '{data}': {exc}\n")
            raise SystemExit(1)
    # Try inline JSON
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"Error: invalid JSON (file not found nor valid inline): {data}\n  {exc}\n")
        raise SystemExit(1)


# ══════════════════════════════════════════════════════════════════════════════════
# Argument parser
# ══════════════════════════════════════════════════════════════════════════════════

def _add_state_subparser(sub: argparse._SubParsersAction) -> None:
    """Add `state` subcommand and its children."""
    p = sub.add_parser("state", help="State management: init/load/save/list/delete/snapshot/restore")
    s = p.add_subparsers(dest="state_cmd", required=True)

    # shared --name argument (add to each child; argparse doesn't inherit parent-level args)
    # init
    sp = s.add_parser("init",  help="Init or overwrite a named state")
    sp.add_argument("--name", default="default", help="State name")
    sp.add_argument("--xlsx", help="Default xlsx path")
    sp.add_argument("--price-version", default="当前", help="Price version")
    sp.add_argument("--scenario-name", default="A", help="Default scenario name")
    sp.add_argument("--production-plan", help="Production plan name")
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


def cmd_file(args: argparse.Namespace) -> int:
    """File management: upload / list / select / delete."""
    reg = UploadRegistry()
    sub = args.file_subcommand

    # ── file upload ───────────────────────────────────────────────────────────
    if sub == "upload":
        path = Path(args.path)
        if not path.exists():
            sys.stderr.write(f"Error: file not found: {path}\n")
            raise SystemExit(1)
        data = path.read_bytes()
        orig_name = path.name

        replace_id = getattr(args, "replace_id", None)
        replace = getattr(args, "replace", False) or bool(replace_id)

        try:
            item = reg.upload(
                data,
                orig_name,
                replace=replace,
                replace_id=replace_id,
                skip_duplicate=True,
            )
        except DuplicateFileError as exc:
            # Already exists — return it as-is
            existing = reg.find_by_id(exc.existing_id)
            payload = {
                "cmd": "file-upload",
                "orig_name": orig_name,
                "skipped": True,
                "existing_id": exc.existing_id,
                "existing_name": existing.orig_name if existing else None,
                "item": existing.to_dict() if existing else None,
            }
            _dump_json(payload, out=args.out)
            return 0

        # Optionally set as active file in state
        if getattr(args, "select", False):
            _set_state_xlsx(str(reg.upload_dir / item.saved_name))

        payload = {
            "cmd": "file-upload",
            "orig_name": item.orig_name,
            "id": item.id,
            "size": item.size,
            "sha256": item.sha256,
            "uploaded_at": item.uploaded_at,
            "selected": getattr(args, "select", False),
        }
        _dump_json(payload, out=args.out)
        return 0

    # ── file list ─────────────────────────────────────────────────────────────
    if sub == "list":
        items = reg.list_all()
        payload = {
            "cmd": "file-list",
            "count": len(items),
            "disk_usage_bytes": reg.disk_usage_bytes(),
            "items": [it.to_dict() for it in items],
        }
        _dump_json(payload, out=args.out)
        return 0

    # ── file select ───────────────────────────────────────────────────────────
    if sub == "select":
        file_id = getattr(args, "id", None)
        if not file_id:
            sys.stderr.write("Error: --id required for file select\n")
            raise SystemExit(1)

        item = reg.find_by_id(file_id)
        if item is None:
            sys.stderr.write(f"Error: file not found: {file_id}\n")
            raise SystemExit(1)

        fp = reg.resolve_path(file_id)
        if fp is None:
            sys.stderr.write(f"Error: file exists in registry but not on disk: {file_id}\n")
            raise SystemExit(1)

        _set_state_xlsx(str(fp))
        payload = {
            "cmd": "file-select",
            "id": item.id,
            "orig_name": item.orig_name,
            "xlsx_path": str(fp),
            "state_xlsx_updated": True,
        }
        _dump_json(payload, out=args.out)
        return 0

    # ── file delete ───────────────────────────────────────────────────────────
    if sub == "delete":
        file_id = getattr(args, "id", None)
        if not file_id:
            sys.stderr.write("Error: --id required for file delete\n")
            raise SystemExit(1)
        try:
            deleted = reg.delete(file_id, missing_ok=False)
        except FileNotFoundError:
            sys.stderr.write(f"Error: file not found: {file_id}\n")
            raise SystemExit(1)
        payload = {"cmd": "file-delete", "id": file_id, "deleted": deleted}
        _dump_json(payload, out=args.out)
        return 0

    # ── file info ─────────────────────────────────────────────────────────────
    if sub == "info":
        file_id = getattr(args, "id", None)
        if not file_id:
            sys.stderr.write("Error: --id required for file info\n")
            raise SystemExit(1)
        item = reg.find_by_id(file_id)
        if item is None:
            sys.stderr.write(f"Error: file not found: {file_id}\n")
            raise SystemExit(1)
        fp = reg.resolve_path(file_id)
        payload = {
            "cmd": "file-info",
            "item": item.to_dict(),
            "disk_path": str(fp) if fp else None,
            "disk_exists": fp.exists() if fp else False,
        }
        _dump_json(payload, out=args.out)
        return 0

    # fallback — shouldn't reach here
    _dump_json({"cmd": "file", "subcommands": ["upload", "list", "select", "delete", "info"]})
    return 0


def _set_state_xlsx(xlsx_path: str) -> None:
    """Update the default state's xlsx_path to point to the given file."""
    store = get_store()
    state = store.load("default")
    state.xlsx_path = xlsx_path
    state.touch()
    store.save(state)


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

    # ── file ──────────────────────────────────────────────────────────────────
    f = sub.add_parser("file", help="File management: upload / list / select / delete / info")
    f.set_defaults(func=cmd_file)
    fm = f.add_subparsers(dest="file_subcommand")

    # upload
    fu = fm.add_parser("upload", help="Upload a file and register it")
    fu.add_argument("path", help="Path to the .xlsx file to upload")
    fu.add_argument("--select", action="store_true", help="Also select this file as active")
    fu.add_argument("--replace-id", help="Replace existing file by ID")
    fu.add_argument("--out", help="Write JSON output to file")

    # list
    fl = fm.add_parser("list", help="List all registered files")
    fl.add_argument("--out", help="Write JSON output to file")

    # select
    fs = fm.add_parser("select", help="Set active file (updates default state xlsx_path)")
    fs.add_argument("--id", required=True, help="File ID (or prefix)")
    fs.add_argument("--out", help="Write JSON output to file")

    # delete
    fd = fm.add_parser("delete", help="Delete a registered file")
    fd.add_argument("--id", required=True, help="File ID (or prefix)")
    fd.add_argument("--out", help="Write JSON output to file")

    # info
    fi = fm.add_parser("info", help="Show details of a registered file")
    fi.add_argument("--id", required=True, help="File ID (or prefix)")
    fi.add_argument("--out", help="Write JSON output to file")

    # ── material ──────────────────────────────────────────────────────────────
    mat = sub.add_parser("material", help="Raw material CRUD (Supabase)")
    mat.set_defaults(func=lambda a: mat.print_help())
    msub = mat.add_subparsers(dest="material_cmd")
    ml = msub.add_parser("list", help="List raw materials")
    ml.add_argument("--category", help="Filter by category")
    ml.add_argument("--status", help="Filter by status")
    ml.set_defaults(func=cmd_material_list)
    mg = msub.add_parser("get", help="Get a raw material by ID")
    mg.add_argument("id", help="Material UUID")
    mg.set_defaults(func=cmd_material_get)
    mc = msub.add_parser("create", help="Create a raw material from JSON")
    mc.add_argument("data", help="JSON file path or inline JSON string")
    mc.set_defaults(func=cmd_material_create)
    mu = msub.add_parser("update", help="Update a raw material by ID from JSON")
    mu.add_argument("id", help="Material UUID")
    mu.add_argument("data", help="JSON file path or inline JSON")
    mu.set_defaults(func=cmd_material_update)
    md = msub.add_parser("delete", help="Delete a raw material by ID")
    md.add_argument("id", help="Material UUID")
    md.set_defaults(func=cmd_material_delete)
    for _p in [ml, mg, mc, mu, md]:
        _p.add_argument("--out", help="Write JSON output to file")

    # ── product ───────────────────────────────────────────────────────────────
    prod = sub.add_parser("product", help="Product CRUD (Supabase)")
    prod.set_defaults(func=lambda a: prod.print_help())
    psub = prod.add_subparsers(dest="product_cmd")
    pl = psub.add_parser("list", help="List products")
    pl.add_argument("--final-only", action="store_true", help="Only final products")
    pl.set_defaults(func=cmd_product_list)
    pg = psub.add_parser("get", help="Get a product by ID")
    pg.add_argument("id", help="Product UUID")
    pg.set_defaults(func=cmd_product_get)
    pc = psub.add_parser("compute-costs", help="Compute factory/store costs from recipes")
    pc.add_argument("id", help="Product UUID")
    pc.set_defaults(func=cmd_product_compute_costs)
    for _p in [pl, pg, pc]:
        _p.add_argument("--out", help="Write JSON output to file")

    # ── recipe ────────────────────────────────────────────────────────────────
    rec = sub.add_parser("recipe", help="Recipe (BOM) management (Supabase)")
    rec.set_defaults(func=lambda a: rec.print_help())
    rsub = rec.add_subparsers(dest="recipe_cmd")
    rl = rsub.add_parser("list", help="List recipes for a product")
    rl.add_argument("product_id", help="Product UUID")
    rl.set_defaults(func=cmd_recipe_list)
    rs = rsub.add_parser("set", help="Replace all recipes for a product (from JSON)")
    rs.add_argument("product_id", help="Product UUID")
    rs.add_argument("data", help="JSON file path or inline JSON array")
    rs.set_defaults(func=cmd_recipe_set)
    for _p in [rl, rs]:
        _p.add_argument("--out", help="Write JSON output to file")

    # ── spec ──────────────────────────────────────────────────────────────────
    spec = sub.add_parser("spec", help="Serving spec management (Supabase)")
    spec.set_defaults(func=lambda a: spec.print_help())
    ssub = spec.add_subparsers(dest="spec_cmd")
    sl = ssub.add_parser("list", help="List serving specs for a product")
    sl.add_argument("product_id", help="Product UUID")
    sl.set_defaults(func=cmd_spec_list)
    ss = ssub.add_parser("set", help="Replace all serving specs for a product (from JSON)")
    ss.add_argument("product_id", help="Product UUID")
    ss.add_argument("data", help="JSON file path or inline JSON array")
    ss.set_defaults(func=cmd_spec_set)
    for _p in [sl, ss]:
        _p.add_argument("--out", help="Write JSON output to file")

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
