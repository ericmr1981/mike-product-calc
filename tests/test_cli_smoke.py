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
import tempfile
from tempfile import TemporaryDirectory

REPO = Path(__file__).resolve().parents[1]
XLSX = REPO / "data" / "蜜可诗产品库.xlsx"
SRC = REPO / "src"


def _run_cli(*args: str, state_dir: str | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    if state_dir:
        env["MPC_STATE_DIR"] = state_dir
    cmd = [sys.executable, "-m", "mike_product_calc", *args]
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


# ── 1. State management ──────────────────────────────────────────────────────────

def _state_dir():
    """Return a temporary state directory path that persists for the test scope."""
    return str(Path(tempfile.mkdtemp()))


def test_cli_state_init():
    sd = _state_dir()
    r = _run_cli("state", "init", "--xlsx", str(XLSX), "--price-version", "当前",
                 "--scenario-name", "A", state_dir=sd)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-init"
    assert payload["name"] == "default"
    assert payload["state"]["xlsx_path"] == str(XLSX.resolve())


def test_cli_state_list():
    sd = _state_dir()
    r = _run_cli("state", "list", state_dir=sd)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-list"
    assert "states" in payload


def test_cli_state_load():
    sd = _state_dir()
    _run_cli("state", "init", "--xlsx", str(XLSX), state_dir=sd)
    r = _run_cli("state", "load", state_dir=sd)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-load"
    assert "state" in payload


def test_cli_state_save():
    sd = _state_dir()
    r = _run_cli("state", "save", "--name", "test-session", state_dir=sd)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-save"


def test_cli_state_delete():
    sd = _state_dir()
    _run_cli("state", "init", "--xlsx", str(XLSX), "--name", "todelete", state_dir=sd)
    r = _run_cli("state", "delete", "--name", "todelete", state_dir=sd)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-delete"


def test_cli_state_snapshot():
    sd = _state_dir()
    _run_cli("state", "init", "--xlsx", str(XLSX), state_dir=sd)
    r = _run_cli("state", "snapshot", "--name", "default", state_dir=sd)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-snapshot"
    assert "snapshot_id" in payload
    assert "snapshots" in payload


def test_cli_state_snapshots_list():
    sd = _state_dir()
    _run_cli("state", "init", "--xlsx", str(XLSX), state_dir=sd)
    _run_cli("state", "snapshot", "--name", "default", state_dir=sd)
    r = _run_cli("state", "snapshots", "--name", "default", state_dir=sd)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "state-snapshots-list"
    assert "snapshots" in payload
    assert "max_kept" in payload


def test_cli_state_restore():
    sd = _state_dir()
    _run_cli("state", "init", "--xlsx", str(XLSX), state_dir=sd)
    # Take a snapshot first
    r0 = _run_cli("state", "snapshot", "--name", "default", state_dir=sd)
    assert r0.returncode == 0, r0.stderr
    snap_id = json.loads(r0.stdout)["snapshot_id"]
    # Restore it
    r = _run_cli("state", "restore", snap_id, "--name", "default", state_dir=sd)
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


# ── 5. target-pricing ─────────────────────────────────────────────────────────

def test_cli_target_pricing_json():
    r = _run_cli("sku-list", str(XLSX), "--basis", "factory", "--only-status", "上线",
                 "--limit", "1", "--format", "json")
    assert r.returncode == 0, r.stderr
    sku = json.loads(r.stdout)["rows"][0]["product_key"]
    r = _run_cli("target-pricing", str(XLSX), "--product-key", sku,
                 "--target-margin", "0.35", "--basis", "store", "--format", "json")
    assert r.returncode in (0, 1), r.stderr
    if r.returncode == 0:
        payload = json.loads(r.stdout)
        assert payload["cmd"] == "target-pricing"
        assert "rows" in payload


# ── 6. material-sim ────────────────────────────────────────────────────────────

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


# ── 7. prep-plan ─────────────────────────────────────────────────────────────

def test_cli_prep_plan_json():
    r = _run_cli("sku-list", str(XLSX), "--basis", "factory", "--only-status", "上线",
                 "--limit", "1", "--format", "json")
    assert r.returncode == 0, r.stderr
    sku = json.loads(r.stdout)["rows"][0]["product_key"]
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


# ── 8. purchase-suggest ───────────────────────────────────────────────────────

def test_cli_purchase_suggest_json():
    r = _run_cli("sku-list", str(XLSX), "--basis", "factory", "--only-status", "上线",
                 "--limit", "1", "--format", "json")
    assert r.returncode == 0, r.stderr
    sku = json.loads(r.stdout)["rows"][0]["product_key"]
    r = _run_cli("purchase-suggest", str(XLSX), "--basis", "store",
                 "--sku", f"{sku}=5", "--format", "json")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["cmd"] == "purchase-suggest"
    assert "rows" in payload


# ── 9. State auto-load ───────────────────────────────────────────────────────

def test_cli_auto_load_state_xlsx():
    """Commands should auto-load xlsx from state when not provided."""
    sd = _state_dir()
    _run_cli("state", "init", "--xlsx", str(XLSX), state_dir=sd)
    # sku-list without explicit xlsx should work
    r = _run_cli("sku-list", "--basis", "factory", "--limit", "3", "--format", "json", state_dir=sd)
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["count"] >= 1


# ── 10. JSON output parseability ─────────────────────────────────────────────

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


# ── 11. Exit code semantics ───────────────────────────────────────────────────

def test_cli_exit_code_2_on_validation_errors():
    """profit-oracle with strict thresholds should exit 2 when violations found."""
    sd = _state_dir()
    r = _run_cli("profit-oracle", str(XLSX), "--basis", "both",
                 "--only-status", "上线",
                 "--margin-delta-abs", "1e-8",  # extremely strict
                 "--rmb-delta-abs", "0.001",
                 "--top", "3", "--format", "json", state_dir=sd)
    # exit_code field in payload tells us if violations were found
    payload = json.loads(r.stdout)
    # If there are violations, exit code should be 2
    for rep in payload.get("reports", []):
        if rep.get("bad_margin", 0) + rep.get("bad_profit", 0) + rep.get("bad_cost", 0) > 0:
            assert r.returncode == 2


# ── 12. --out flag ─────────────────────────────────────────────────────────────

def test_cli_out_flag_writes_file():
    with TemporaryDirectory() as td:
        out_file = Path(td) / "output.json"
        r = _run_cli("sku-list", str(XLSX), "--basis", "factory", "--limit", "3",
                     "--format", "json", "--out", str(out_file))
        assert r.returncode == 0, r.stderr
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert data["count"] >= 1


# ── 13. help ──────────────────────────────────────────────────────────────────

def test_cli_help_smoke():
    r = _run_cli("--help")
    assert r.returncode == 0
    text = r.stdout + r.stderr
    commands = ["validate", "sku-list", "profit-oracle",
                "target-pricing", "material-sim",
                "prep-plan", "purchase-suggest",
                "state"]
    for cmd in commands:
        assert cmd in text, f"'{cmd}' not found in --help output"
