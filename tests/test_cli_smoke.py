"""
tests/test_cli_smoke.py — CLI smoke + golden tests for mike-product-calc.

Tests cover all CLI commands including the new Sprint-1 additions.
Each test verifies: exit code, stdout JSON parseability, key fields.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[1]
XLSX = REPO / "data" / "蜜可诗产品库.xlsx"
SRC = REPO / "src"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    cmd = [sys.executable, "-m", "mike_product_calc", *args]
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


# ── Helpers ──────────────────────────────────────────────────────────────────────

def _first_sku() -> str:
    """Return one real SKU key from the workbook."""
    r = _run_cli("sku-list", str(XLSX), "--basis", "factory", "--only-status", "上线",
                 "--limit", "1", "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    return payload["rows"][0]["product_key"]


# ── 1. State management ──────────────────────────────────────────────────────────

def test_cli_state_init():
    r = _run_cli("state", "init", "--xlsx", str(XLSX), "--price-version", "当前",
                 "--scenario-name", "A")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-init"
    assert payload["name"] == "default"
    assert payload["state"]["xlsx_path"] == str(XLSX.resolve())


def test_cli_state_list():
    r = _run_cli("state", "list")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-list"
    assert "states" in payload


def test_cli_state_load():
    r = _run_cli("state", "load")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-load"
    assert "state" in payload


def test_cli_state_save():
    r = _run_cli("state", "save", "--name", "test-session")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-save"


def test_cli_state_delete():
    r = _run_cli("state", "delete", "--name", "test-session")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-delete"


def test_cli_state_snapshot():
    r = _run_cli("state", "snapshot", "--name", "default")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-snapshot"
    assert "snapshot_id" in payload
    assert "snapshots" in payload


def test_cli_state_snapshots_list():
    r = _run_cli("state", "snapshots", "--name", "default")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-snapshots-list"
    assert "snapshots" in payload
    assert "max_kept" in payload


def test_cli_state_restore():
    # Take a snapshot first
    r0 = _run_cli("state", "snapshot", "--name", "default")
    assert r0.returncode == 0, r0.stderr
    snap_id = json.loads(r0.stdout)["snapshot_id"]
    # Restore it
    r = _run_cli("state", "restore", snap_id, "--name", "default")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-restore"
    assert payload["snapshot_id"] == snap_id


# ── 2. validate ─────────────────────────────────────────────────────────────────

def test_cli_validate_json():
    assert XLSX.exists()
    r = _run_cli("validate", str(XLSX), "--format", "json")
    # Exit 0 (no errors) or 2 (has errors) — both are valid business outcomes
    assert r.returncode in (0, 2), r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "validate"
    assert "summary" in payload
    assert payload["summary"]["total"] >= 0


def test_cli_validate_missing_file():
    r = _run_cli("validate", "/nonexistent/path.xlsx")
    assert r.returncode == 1


# ── 3. sku-list ────────────────────────────────────────────────────────────────

def test_cli_sku_list_json():
    r = _run_cli("sku-list", str(XLSX), "--basis", "factory", "--only-status", "上线",
                 "--limit", "3", "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "sku-list"
    assert payload["count"] >= 1
    assert "rows" in payload
    assert payload["rows"][0]["product_key"]


# ── 4. profit-oracle ───────────────────────────────────────────────────────────

def test_cli_profit_oracle_json():
    r = _run_cli("profit-oracle", str(XLSX), "--basis", "both", "--only-status", "上线",
                 "--margin-delta-abs", "0.1", "--rmb-delta-abs", "1", "--top", "3",
                 "--format", "json")
    assert r.returncode in (0, 2), r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "profit-oracle"
    assert "reports" in payload


# ── 5. portfolio-eval ─────────────────────────────────────────────────────────

def test_cli_portfolio_eval_json():
    sku = _first_sku()
    r = _run_cli("portfolio-eval", str(XLSX), "--basis", "factory", "--name", "A",
                 "--sku", f"{sku}=10", "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "portfolio-eval"
    assert payload["name"] == "A"
    assert payload["total_revenue"] >= 0


# ── 6. portfolio-compare ───────────────────────────────────────────────────────

def test_cli_portfolio_compare_json():
    sku = _first_sku()
    with TemporaryDirectory() as td:
        plan_a = Path(td) / "plan_A.json"
        plan_a.write_text(json.dumps({"selections": {sku: 5}}), encoding="utf-8")
        r = _run_cli("portfolio-compare", str(XLSX), "--basis", "factory",
                     "--scenario-json", f"A={plan_a}", "--format", "json")
        assert r.returncode == 0, r.stderr
        payload = json.loads(r.stdout)
        assert payload["cmd"] == "portfolio-compare"


# ── 7. target-pricing ─────────────────────────────────────────────────────────

def test_cli_target_pricing_json():
    sku = _first_sku()
    r = _run_cli("target-pricing", str(XLSX), "--product-key", sku,
                 "--target-margin", "0.35", "--basis", "store", "--format", "json")
    assert r.returncode in (0, 1), r.stderr
    if r.returncode == 0:
        payload = json.loads(r.stdout)
        assert payload["cmd"] == "target-pricing"
        assert "rows" in payload


# ── 8. material-sim ────────────────────────────────────────────────────────────

def test_cli_material_sim_versions():
    r = _run_cli("material-sim", str(XLSX), "versions")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "material-sim-versions"
    assert "builtin" in payload


def test_cli_material_sim_simulate():
    r = _run_cli("material-sim", str(XLSX), "simulate",
                 "--version", "test-version", "--basis", "store",
                 "--adj", "芒果=10", "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "material-sim-simulate"


def test_cli_material_sim_compare():
    r = _run_cli("material-sim", str(XLSX), "compare", "当前", "旺季",
                 "--basis", "store",
                 "--adj-a", "芒果=10",
                 "--adj-b", "芒果=15",
                 "--format", "json")
    assert r.returncode in (0, 2), r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "material-sim-compare"


# ── 9. production-plan ────────────────────────────────────────────────────────

def test_cli_production_plan_export():
    sku = _first_sku()
    r = _run_cli("production-plan", str(XLSX), "export",
                 "--name", "TestPlan", "--sku", f"{sku}=20",
                 "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "production-plan-export"


def test_cli_production_plan_list():
    r = _run_cli("production-plan", str(XLSX), "list")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "production-plan-list"


def test_cli_production_plan_import_export_cycle():
    """Import a plan JSON, then export it — round-trip test."""
    sku = _first_sku()
    with TemporaryDirectory() as td:
        plan_file = Path(td) / "imported_plan.json"
        plan_file.write_text(json.dumps({"name": "Imported", "selections": {sku: 7}}),
                             encoding="utf-8")
        r1 = _run_cli("production-plan", str(XLSX), "import", str(plan_file))
        assert r1.returncode == 0, r1.stderr

        r2 = _run_cli("production-plan", str(XLSX), "export", "--name", "Imported",
                      "--format", "json")
        assert r2.returncode == 0, r2.stderr
        payload = json.loads(r2.stdout)
        assert payload["name"] == "Imported"


# ── 10. prep-plan ─────────────────────────────────────────────────────────────

def test_cli_prep_plan_json():
    sku = _first_sku()
    r = _run_cli("prep-plan", str(XLSX), "--basis", "store",
                 "--sku", f"{sku}=5", "--lead-days", "3",
                 "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "prep-plan"
    assert "rows" in payload


def test_cli_prep_plan_missing_sku():
    r = _run_cli("prep-plan", str(XLSX), "--basis", "store")
    assert r.returncode == 1


# ── 11. purchase-suggest ───────────────────────────────────────────────────────

def test_cli_purchase_suggest_json():
    sku = _first_sku()
    r = _run_cli("purchase-suggest", str(XLSX), "--basis", "store",
                 "--sku", f"{sku}=5", "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "purchase-suggest"
    assert "rows" in payload


# ── 12. optimizer ──────────────────────────────────────────────────────────────

def test_cli_optimizer_json():
    r = _run_cli("optimizer", str(XLSX), "--basis", "factory",
                 "--only-status", "上线", "--max-capacity", "200",
                 "--material-budget", "50000", "--min-sales", "1",
                 "--max-qty-per-sku", "5", "--max-combos", "1000",
                 "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "optimizer"
    assert "recommendations" in payload


# ── 13. State auto-load ───────────────────────────────────────────────────────

def test_cli_auto_load_state_xlsx():
    """Commands should auto-load xlsx from state when not provided."""
    # Ensure state is set
    _run_cli("state", "init", "--xlsx", str(XLSX))
    # sku-list without explicit xlsx should work
    r = _run_cli("sku-list", "--basis", "factory", "--limit", "3", "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["count"] >= 1


# ── 14. JSON output parseability ─────────────────────────────────────────────

def test_cli_json_stderr_clean():
    """stdout must be pure JSON with no extra text."""
    r = _run_cli("sku-list", str(XLSX), "--basis", "factory", "--limit", "3",
                 "--format", "json")
    assert r.returncode == 0, r.stderr
    # Must not contain non-JSON text before/after
    stripped = r.stdout.strip()
    assert stripped.startswith("{"), f"stdout should be JSON object: {stripped[:50]}"
    parsed = json.loads(stripped)
    assert "cmd" in parsed


# ── 15. Exit code semantics ───────────────────────────────────────────────────

def test_cli_exit_code_2_on_validation_errors():
    """profit-oracle with strict thresholds should exit 2 when violations found."""
    r = _run_cli("profit-oracle", str(XLSX), "--basis", "both",
                 "--only-status", "上线",
                 "--margin-delta-abs", "1e-8",  # extremely strict
                 "--rmb-delta-abs", "0.001",
                 "--top", "3", "--format", "json")
    # exit_code field in payload tells us if violations were found
    payload = json.loads(r.stdout)
    # If there are violations, exit code should be 2
    for rep in payload.get("reports", []):
        if rep.get("bad_margin", 0) + rep.get("bad_profit", 0) + rep.get("bad_cost", 0) > 0:
            assert r.returncode == 2


# ── 16. --out flag ─────────────────────────────────────────────────────────────

def test_cli_out_flag_writes_file():
    sku = _first_sku()
    with TemporaryDirectory() as td:
        out_file = Path(td) / "output.json"
        r = _run_cli("sku-list", str(XLSX), "--basis", "factory", "--limit", "3",
                     "--format", "json", "--out", str(out_file))
        assert r.returncode == 0, r.stderr
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data["count"] >= 1


# ── 17. help ──────────────────────────────────────────────────────────────────

def test_cli_help_smoke():
    r = _run_cli("--help")
    assert r.returncode == 0
    text = r.stdout + r.stderr
    commands = ["validate", "sku-list", "profit-oracle", "portfolio-eval",
                "portfolio-compare", "target-pricing", "material-sim",
                "production-plan", "prep-plan", "purchase-suggest",
                "optimizer", "state"]
    for cmd in commands:
        assert cmd in text, f"'{cmd}' not found in --help output"
