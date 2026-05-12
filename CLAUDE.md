# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Local development
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Optional: install CLI for `mpc` / `mike-product-calc` commands
pip install -e .

# Run Streamlit UI (upload xlsx manually, or set env var for auto-load)
streamlit run app.py
MIKE_DEFAULT_XLSX=/path/to/蜜可诗产品库.xlsx streamlit run app.py

# Run all tests
pytest tests/ -q

# Run a single test
pytest tests/test_cli_smoke.py::test_cli_validate_json -v

# Compile check (no runtime)
python -m py_compile src/mike_product_calc/cli.py

# CLI usage (editable install required, or set PYTHONPATH=src)
mpc validate path/to/workbook.xlsx
python -m mike_product_calc state init --xlsx path/to/workbook.xlsx

# Validation oracle (exit 2 = business rule violations)
bash scripts/validate.sh path/to/workbook.xlsx [out.csv]
```

## Architecture

A Streamlit + Python decision-support app for 蜜可诗 (Mike) product operations. Business data comes from an Excel workbook (`data/蜜可诗产品库.xlsx`, not in repo) and can be synced to Supabase.

### Layer structure

- **`app.py`** — Streamlit UI entry point (8 tabs, 12 feature codes). Orchestrates data loading, calls calc modules, renders via st.dataframe/st.plotly_chart.
- **`src/mike_product_calc/cli.py`** — CLI entry point (`mpc` / `mike-product-calc`). Parallel to app.py — same business logic, agent-friendly JSON output. **Hard rule**: all core logic lives in calc/ and data/; CLI and UI never duplicate it.
- **`src/mike_product_calc/calc/`** — Business logic modules:
  - `profit.py` — SKU profit tables, margin delta reports (F-002)
  - `profit_oracle.py` — Consistency checks; acceptance oracle
  - `margin_target.py` / `target_pricing.py` — Reverse pricing from target margin (F-003)
  - `material_sim.py` — Material price scenario management and comparison (F-004)
  - `material_mgmt.py` — Material catalog search, categories, stats
  - `recipe.py` / `recipe_mgmt.py` — Recipe BOM tables, ingredient pool, profit rate calc
  - `serving_mgmt.py` — Final product (serving) definitions
  - `prep_engine.py` — BOM expansion (3-level), gap detection (F-006)
  - `purchase_suggestion.py` — Purchase list generation (F-007)
  - `inventory_linkage.py` — Replenishment planning, shortage alerts
  - `scenarios.py` — Portfolio evaluation and multi-scenario comparison (F-008/F-010)
  - `optimizer.py` — Portfolio enumeration optimization (F-012)
  - `capacity.py` — Capacity scoring (F-011)
- **`src/mike_product_calc/data/`** — Excel loading (`loader.py`: fuzzy sheet matching, auto header detection), validation (`validator.py`: ValidationIssue/SheetSpec/ValidationReport), file upload registry (`upload.py`), shared utils (`shared.py`). Supabase upload/adapter (`cli_supabase.py`, `supabase_adapter.py`, `supabase_client.py`). Inventory data sources (`data_source.py`, `inventory_upload.py`, `inventory_view.py`).
- **`src/mike_product_calc/sync/excel_sync.py`** — Excel → Supabase sync engine with diff preview and conflict resolution.
- **`src/mike_product_calc/model/production.py`** — Production plan data model (Pydantic, F-005).
- **`src/mike_product_calc/ui/inventory_tab.py`** — Streamlet UI components for inventory tab.
- **`src/mike_product_calc/state.py`** — Session state management (MpcState dataclass, JSON-persisted in `state/` dir). Supports named states, snapshots, and restore.

### Key conventions

- **`src/` layout**: Development uses `PYTHONPATH=src` or `pip install -e .`. Tests insert src into sys.path via conftest.py.
- **CLI exit codes**: 0 = OK, 1 = system/argument error, 2 = business validation failure
- **CLI JSON output**: stdout is pure JSON only, no extra text. Use `--format text` for human-readable or `--out <file>` to write to disk.
- **12 features (F-001 through F-012)**, each mapped to a tab in the Streamlit UI and a CLI command.
- **Supabase integration**: Optional cloud backend. `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` env vars required. Excel data can be uploaded (via CLI) or synced incrementally.

### Tests

- **`tests/test_cli_smoke.py`** — End-to-end CLI tests: run each command, parse JSON output, validate exit codes and key fields. Uses subprocess against real xlsx in `data/` directory.
- **`tests/test_*.py`** — Unit tests for individual calc/data modules.
- **`tests/test_tab*_e2e.py`** — End-to-end tests for specific tab/feature flows.
- **`tests/test_inventory*.py`** — Inventory upload, view, and linkage tests.
- **`tests/test_recipe*.py`** / `tests/test_serving_mgmt.py` — Recipe and serving mgmt tests.
- **`tests/test_supabase_client.py`** / `tests/test_excel_sync.py` — Supabase integration tests.
- Tests require `data/蜜可诗产品库.xlsx` to exist (not in repo).
