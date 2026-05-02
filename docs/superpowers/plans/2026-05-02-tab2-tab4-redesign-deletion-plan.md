# Tab2/Tab4 Redesign + Module Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete 3 tabs (Tab6/Tab7/Tab8), enhance Tab2 with recipe breakdown, completely redesign Tab4 as product→SKU→recipe flow.

**Architecture:** A new `calc/recipe.py` module provides shared recipe breakdown logic for both Tab2 and Tab4. Tab deletions are purely UI+CLI removal (no logic migration needed). Tab4 is rebuilt as a 3-step flow in `app.py`.

**Tech Stack:** Python 3.9+, Streamlit, pandas, openpyxl

---

### Task 1: Create shared recipe module

**Files:**
- Create: `src/mike_product_calc/calc/recipe.py`
- Test: `tests/test_recipe.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_recipe.py
from __future__ import annotations

from pathlib import Path
import pandas as pd
import pytest

from mike_product_calc.calc.recipe import (
    get_semi_product_recipes,
    get_brand_cost_map,
    get_brand_spec_map,
    build_recipe_table,
    RecipeRow,
)

REPO = Path(__file__).resolve().parents[1]
XLSX = REPO / "data" / "蜜可诗产品库.xlsx"


def _load_sheets() -> dict[str, pd.DataFrame]:
    """Minimal workbook loader for tests."""
    from mike_product_calc.data.loader import load_workbook
    return load_workbook(XLSX).sheets


@pytest.fixture(scope="module")
def sheets():
    return _load_sheets()


def test_get_brand_cost_map(sheets):
    """总原料成本表品牌成本列读取."""
    cost_map = get_brand_cost_map(sheets)
    assert isinstance(cost_map, dict)
    # At least one entry should exist
    assert len(cost_map) > 0
    # Values should be numeric
    for name, cost in cost_map.items():
        assert isinstance(name, str)
        assert isinstance(cost, (int, float))
        assert cost >= 0


def test_get_brand_spec_map(sheets):
    """总原料成本表规格读取."""
    spec_map = get_brand_spec_map(sheets)
    assert isinstance(spec_map, dict)
    if spec_map:
        name, spec = next(iter(spec_map.items()))
        assert isinstance(name, str)
        assert isinstance(spec, str)
        assert len(spec) > 0


def test_get_semi_product_recipes(sheets):
    """半成品配方表读取."""
    recipes = get_semi_product_recipes(sheets)
    assert isinstance(recipes, dict)
    # Keys should be semi-product names, values should be lists of dicts with item/qty
    for semi_name, ingredients in recipes.items():
        assert isinstance(semi_name, str)
        assert isinstance(ingredients, list)
        if ingredients:
            ing = ingredients[0]
            assert "item" in ing
            assert "usage_qty" in ing
            assert isinstance(ing["usage_qty"], float)


def test_build_recipe_table(sheets):
    """构建配方明细表."""
    # Pick a known product_key that has recipe data
    profit_df = pd.read_excel(XLSX, sheet_name=0)  # fallback
    # Use profit table instead
    from mike_product_calc.calc.profit import sku_profit_table
    profit_df = sku_profit_table(sheets, basis="store", only_status="上线")
    assert not profit_df.empty

    product_key = profit_df["product_key"].iloc[0]
    table_df = build_recipe_table(sheets, product_key=product_key, basis="store")
    assert isinstance(table_df, pd.DataFrame)
    # Required columns
    expected_cols = ["item", "usage_qty", "cost", "spec", "store_price", "brand_cost", "profit_rate"]
    for col in expected_cols:
        assert col in table_df.columns, f"Missing column: {col}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=src pytest tests/test_recipe.py -v`
Expected: FAIL with ImportError (module doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

```python
# src/mike_product_calc/calc/recipe.py
"""
Recipe breakdown module — shared by Tab2 (F-003) and Tab4 (原料价格模拟器).

Provides:
- get_brand_cost_map / get_brand_spec_map — from 总原料成本表
- get_semi_product_recipes — from 半成品配方表_*
- build_recipe_table — full hierarchical recipe table for a SKU
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd


@dataclass
class RecipeRow:
    item: str
    usage_qty: float
    usage_unit: str
    cost: float
    spec: str
    store_price: float
    brand_cost: float
    profit_rate: float
    level: int  # 0=direct ingredient, 1=semi-product, 2=sub-ingredient
    is_semi: bool


def _find_col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    for c in candidates:
        for col in df.columns:
            if c in col:
                return col
    return None


def get_brand_cost_map(sheets: Dict[str, pd.DataFrame]) -> Dict[str, float]:
    """Read brand cost from 总原料成本表. Returns {material_name: brand_cost}."""
    df = sheets.get("总原料成本表")
    if df is None:
        return {}
    name_col = _find_col(df, "品项名称")
    cost_col = _find_col(df, "原料价格", "单价", "品牌成本")
    if not name_col or not cost_col:
        return {}
    out = {}
    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip()
        if not name:
            continue
        try:
            out[name] = float(row[cost_col])
        except (TypeError, ValueError):
            pass
    return out


def get_brand_spec_map(sheets: Dict[str, pd.DataFrame]) -> Dict[str, str]:
    """Read spec/unit from 总原料成本表. Returns {material_name: spec_string}."""
    df = sheets.get("总原料成本表")
    if df is None:
        return {}
    name_col = _find_col(df, "品项名称")
    spec_col = _find_col(df, "规格", "单位量", "单位数量")
    if not name_col or not spec_col:
        return {}
    out = {}
    for _, row in df.iterrows():
        name = str(row.get(name_col, "")).strip()
        if not name:
            continue
        spec = str(row.get(spec_col, "")).strip()
        if spec and spec != "nan":
            out[name] = spec
    return out


def get_semi_product_recipes(sheets: Dict[str, pd.DataFrame]) -> Dict[str, List[dict]]:
    """Read semi-product recipes from 半成品配方表_*.
    Returns {semi_product_name: [{item, usage_qty, usage_unit}, ...]}.
    """
    recipes: Dict[str, List[dict]] = {}
    for sheet_name in sheets:
        if "半成品配方表" not in sheet_name:
            continue
        df = sheets[sheet_name]
        # Try to find relevant columns
        semi_col = _find_col(df, "品名", "半成品")
        ing_col = _find_col(df, "配料", "原料")
        qty_col = _find_col(df, "用量")
        unit_col = _find_col(df, "单位")

        if not semi_col or not ing_col or not qty_col:
            continue

        for _, row in df.iterrows():
            semi = str(row.get(semi_col, "")).strip()
            ing = str(row.get(ing_col, "")).strip()
            if not semi or not ing:
                continue
            try:
                qty = float(row[qty_col])
            except (TypeError, ValueError):
                qty = 0.0
            unit = str(row.get(unit_col, "")).strip() if unit_col else ""
            if semi not in recipes:
                recipes[semi] = []
            recipes[semi].append({
                "item": ing,
                "usage_qty": qty,
                "usage_unit": unit,
            })
    return recipes


def _to_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_recipe_table(
    sheets: Dict[str, pd.DataFrame],
    *,
    product_key: str,
    basis: str = "store",
) -> pd.DataFrame:
    """Build hierarchical recipe table for a SKU.

    Columns: item | usage_qty | cost | spec | store_price | brand_cost | profit_rate
    """
    from mike_product_calc.calc.profit import sku_cost_breakdown

    # Get cost breakdown to find main materials
    breakdown = sku_cost_breakdown(sheets, product_key=product_key, basis=basis)
    if breakdown.empty:
        return pd.DataFrame()

    brand_cost_map = get_brand_cost_map(sheets)
    spec_map = get_brand_spec_map(sheets)
    semi_recipes = get_semi_product_recipes(sheets)

    # We also need to look up the 产品出品表 for usage qty per ingredient
    from mike_product_calc.calc.profit import ingredient_catalog
    catalog = ingredient_catalog(sheets)

    rows: List[RecipeRow] = []
    for _, b_row in breakdown.iterrows():
        item = b_row["item"]
        bucket = b_row["bucket"]
        cost_val = _to_float(b_row["cost"]) or 0.0

        # Look up usage qty from 产品出品表
        usage_qty = 0.0
        usage_unit = ""
        for sname in sheets:
            if "产品出品表" in sname:
                df = sheets[sname]
                # Build product keys
                pk = df.apply(lambda r: "|".join(
                    str(r.get(c, "")).strip()
                    for c in ["品类", "品名", "规格"] if c in df.columns
                ), axis=1)
                mask = pk == product_key
                if mask.any():
                    match = df[mask].iloc[0]
                    # Determine if this row matches current item
                    main_mat = str(match.get("主原料", "")).strip()
                    ing = str(match.get("配料", "")).strip()
                    row_item = ing or main_mat
                    if row_item == item:
                        usage_qty = _to_float(match.get("用量")) or 0.0
                        usage_unit = str(match.get("单位", "")).strip() or ""
                    break

        brand_cost = brand_cost_map.get(item, 0.0)
        spec = spec_map.get(item, "")

        # Check if this item is a semi-product with sub-recipes
        is_semi = item in semi_recipes

        if not is_semi:
            # Direct ingredient
            store_price = cost_val  # default: cost = store_price (= brand_cost in this scenario)
            # Actually for non-semi items, store_price starts as brand_cost
            store_price = brand_cost if brand_cost > 0 else cost_val
            calculated_cost = store_price  # simple material, cost ≈ store_price per unit
            # For per-usage cost, we need: cost = usage_qty * (store_price / spec_parsed)
            spec_parsed = _parse_spec(spec)
            if spec_parsed and spec_parsed > 0 and usage_qty > 0:
                calculated_cost = usage_qty * (store_price / spec_parsed)
            else:
                calculated_cost = cost_val

            profit_rate = _calc_profit_rate(store_price, brand_cost)

            rows.append(RecipeRow(
                item=item,
                usage_qty=usage_qty,
                usage_unit=usage_unit,
                cost=round(calculated_cost, 4),
                spec=spec,
                store_price=store_price,
                brand_cost=round(brand_cost, 4),
                profit_rate=round(profit_rate, 4),
                level=0,
                is_semi=False,
            ))
        else:
            # Semi-product: show the semi row + sub-ingredients
            sub_items = semi_recipes[item]
            semi_cost = 0.0
            sub_rows: List[RecipeRow] = []

            for sub in sub_items:
                sub_name = sub["item"]
                sub_qty = sub["usage_qty"]
                sub_unit = sub.get("usage_unit", "")
                sub_brand_cost = brand_cost_map.get(sub_name, 0.0)
                sub_spec = spec_map.get(sub_name, "")

                sub_store_price = sub_brand_cost if sub_brand_cost > 0 else 0.0
                sub_spec_parsed = _parse_spec(sub_spec)
                sub_cost = 0.0
                if sub_spec_parsed and sub_spec_parsed > 0 and sub_qty > 0:
                    sub_cost = sub_qty * (sub_store_price / sub_spec_parsed)

                sub_profit_rate = _calc_profit_rate(sub_store_price, sub_brand_cost)
                semi_cost += sub_cost

                sub_rows.append(RecipeRow(
                    item=sub_name,
                    usage_qty=sub_qty,
                    usage_unit=sub_unit,
                    cost=round(sub_cost, 4),
                    spec=sub_spec,
                    store_price=sub_store_price,
                    brand_cost=round(sub_brand_cost, 4),
                    profit_rate=round(sub_profit_rate, 4),
                    level=2,
                    is_semi=False,
                ))

            # Main semi row
            rows.append(RecipeRow(
                item=item,
                usage_qty=0,
                usage_unit="",
                cost=round(semi_cost, 4),
                spec="",
                store_price=0,
                brand_cost=0,
                profit_rate=0,
                level=1,
                is_semi=True,
            ))
            rows.extend(sub_rows)

    # Build DataFrame
    data = []
    for r in rows:
        data.append({
            "item": r.item,
            "usage_qty": r.usage_qty,
            "usage_unit": r.usage_unit,
            "cost": r.cost,
            "spec": r.spec,
            "store_price": r.store_price,
            "brand_cost": r.brand_cost,
            "profit_rate": r.profit_rate,
            "level": r.level,
            "is_semi": r.is_semi,
        })
    df = pd.DataFrame(data)
    return df


def _parse_spec(spec_str: str) -> Optional[float]:
    """Parse spec like '1 kg', '0.5 L', '500 g' → numeric value in base unit."""
    if not spec_str or spec_str in ("—", "-", "nan"):
        return None
    import re
    m = re.match(r"([\d.]+)", spec_str.strip())
    return float(m.group(1)) if m else None


def _calc_profit_rate(store_price: float, brand_cost: float) -> float:
    """利润率 = (门店价格 - 品牌成本) / 品牌成本"""
    if brand_cost and brand_cost > 0:
        return (store_price - brand_cost) / brand_cost
    return 0.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_recipe.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mike_product_calc/calc/recipe.py tests/test_recipe.py
git commit -m "feat: add shared recipe breakdown module for Tab2/Tab4"
```

---

### Task 2: Delete Tab6/Tab7/Tab8 from app.py

**Files:**
- Modify: `app.py` (remove ~700 lines of Tab6/Tab7/Tab8 code)
- Modify: `app.py` (remove imports for scenarios/optimizer/capacity)

- [ ] **Step 1: Remove imports from app.py header**

In `app.py`, remove these imports:
```python
from mike_product_calc.calc.scenarios import (
    PortfolioScenario,
    compare_portfolios,
    evaluate_portfolio,
    SalesAssumptionScenario,
    evaluate_multi_scenario,
    multi_scenario_comparison_df,
    multi_scenario_diff_table,
)
from mike_product_calc.calc.capacity import (
    capacity_to_dataframe,
    score_capacity_by_date,
    score_capacity_from_plan,
)
from mike_product_calc.calc.optimizer import (
    OptimizationConstraint,
    enumerate_portfolios,
    explain_recommendation,
)
```

Also remove the `_all_skus_for_portfolio` and `_init_portfolio_session` lines (~1106-1116).

- [ ] **Step 2: Remove portfolio state save code**

In the auto-save section, remove:
```python
# portfolios
state.portfolio_versions = {
    "A": dict(st.session_state.get("portfolio_A") or {}),
    "B": dict(st.session_state.get("portfolio_B") or {}),
    "C": dict(st.session_state.get("portfolio_C") or {}),
}
```

And remove the portfolio-load section:
```python
for slot, key in (("A", "portfolio_A"), ("B", "portfolio_B"), ("C", "portfolio_C")):
    ...
    st.session_state[key] = dict(state.portfolio_versions.get(slot) or {})
```

Also remove `state.last_portfolio_selections` references.

- [ ] **Step 3: Remove Tab6/Tab7/Tab8 content blocks and shrink tabs**

Replace:
```python
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["概览/校验", "SKU 毛利分析（双口径）", "Sheet 浏览", "原料价格模拟器", "产销计划", "产品组合评估", "多场景对比", "选品优化器"])
```

With:
```python
tab1, tab2, tab3, tab4, tab5 = st.tabs(["概览/校验", "SKU 毛利分析（双口径）", "Sheet 浏览", "原料价格模拟器", "产销计划"])
```

Then delete all code blocks:
- `with tab6:` ... (ends before `# ── Tab7`)
- `with tab7:` ... (ends before `# ── Tab8`)
- `with tab8:` ... (ends at end of file)

- [ ] **Step 4: Verify app.py loads without errors**

Run: `python3 -m py_compile app.py`
Expected: exit 0

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "refactor: remove Tab6/Tab7/Tab8 (产品组合评估/多场景对比/选品优化器)"
```

---

### Task 3: Delete calc modules and CLI commands

**Files:**
- Delete: `src/mike_product_calc/calc/scenarios.py`
- Delete: `src/mike_product_calc/calc/optimizer.py`
- Delete: `src/mike_product_calc/calc/capacity.py`
- Modify: `src/mike_product_calc/cli.py` (remove related commands)

- [ ] **Step 1: Delete calc module files**

```bash
rm src/mike_product_calc/calc/scenarios.py
rm src/mike_product_calc/calc/optimizer.py
rm src/mike_product_calc/calc/capacity.py
```

- [ ] **Step 2: Remove CLI commands from cli.py**

In `cli.py`, remove:
- Import lines for `capacity`, `optimizer`, `scenarios` modules
- `cmd_portfolio_eval` function
- `cmd_portfolio_compare` function
- `cmd_optimizer` function
- Argparse registrations for `portfolio-eval`, `portfolio-compare`, `optimizer`
- `_load_sku_qty_from_args` helper (only used by deleted commands)

- [ ] **Step 3: Verify compilation**

Run: `python3 -m py_compile src/mike_product_calc/cli.py && python3 -m py_compile app.py`
Expected: exit 0

- [ ] **Step 4: Delete related test files**

```bash
rm -f tests/test_tab6_e2e.py tests/test_tab7_e2e.py tests/test_tab8_9_10_11_e2e.py
```

- [ ] **Step 5: Modify CLI smoke tests**

In `tests/test_cli_smoke.py`, remove:
- Tests for `portfolio-eval`, `portfolio-compare`, `optimizer`, `production-plan`
- The `_first_sku` and `_load_sku_qty_from_args` helpers (if no longer used)
- Remove `--help` smoke test references to deleted commands

- [ ] **Step 6: Run tests**

Run: `PYTHONPATH=src pytest tests/test_cli_smoke.py -v --tb=short`
Expected: remaining tests pass

- [ ] **Step 7: Commit**

```bash
git add src/mike_product_calc/calc/ src/mike_product_calc/cli.py tests/
git commit -m "refactor: delete scenarios/optimizer/capacity modules and CLI commands"
```

---

### Task 4: Enhance Tab2 with recipe breakdown

**Files:**
- Modify: `app.py` (Tab2 F-003 section)

- [ ] **Step 1: Add recipe breakdown expand section in F-003**

After the existing F-003 table (around line 563), add a section that shows main material recipe breakdown. Use the `build_recipe_table` from the new recipe module. Add a button next to each main_material row to expand its sub-recipe.

In the cost waterfall section (around line 519-527), add a "展开配方" button for main_material rows:

```python
st.divider()
st.markdown("#### 主原料配方拆解")
breakdown = sku_cost_breakdown(wb.sheets, product_key=pick, basis=basis)
if not breakdown.empty:
    main_materials = breakdown[breakdown["bucket"] == "main_material"]["item"].unique().tolist()
    if main_materials:
        selected_mm = st.selectbox("选择主原料查看配方", options=main_materials)
        recipe_df = build_recipe_table(wb.sheets, product_key=pick, basis=basis)
        if not recipe_df.empty:
            # Filter to show only rows for this main material (level 1 semi + level 2 subs)
            # Or just show full recipe table
            display = recipe_df[recipe_df["level"] > 0].copy() if selected_mm else recipe_df
            st.dataframe(
                display,
                use_container_width=True,
                height=300,
                column_config={
                    "store_price": st.column_config.NumberColumn("门店价格", format="%.2f"),
                    "brand_cost": st.column_config.NumberColumn("品牌成本", format="%.2f"),
                    "cost": st.column_config.NumberColumn("成本", format="%.4f"),
                    "profit_rate": st.column_config.NumberColumn("利润率", format="%.2%"),
                },
            )
```

This goes right after the F-003 download button and before `with tab3:`.

- [ ] **Step 2: Add recipe module import**

In app.py header, add:
```python
from mike_product_calc.calc.recipe import build_recipe_table
```

- [ ] **Step 3: Verify app.py loads**

Run: `python3 -m py_compile app.py`
Expected: exit 0

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add recipe breakdown table to Tab2 F-003 section"
```

---

### Task 5: Redesign Tab4 — Step 1 & 2 (product selection + SKU list)

**Files:**
- Modify: `app.py` (Tab4 section, complete rewrite)

Replace the entire Tab4 content block (lines ~575-679) with the new 3-step design.

- [ ] **Step 1: Add new imports for Tab4**

In app.py header, add the recipe module import (already done in Task 4). Also ensure Scenario/ScenarioStore imports are kept.

- [ ] **Step 2: Write the new Tab4 Step 1 & 2**

Step 1: Product dropdown + basis selector
Step 2: SKU spec table with cost/margin

```python
# ── Tab4: 原料价格模拟器（重设计）────────────────────────────────

store: ScenarioStore = st.session_state["sim_store"]

with tab4:
    st.info("📌 **功能说明**：选产品 → 查看 SKU 规格毛利 → 展开配方明细，调整门店价格/售价，实时看毛利变化。\n"
             "**使用方法**：选择产品 → 选 SKU 规格 → 在配方表中调整门店价格或在右侧调售价 → 保存方案对比。")
    st.subheader("原料价格模拟器")
    st.caption("三步递进：选择产品 → SKU 规格毛利 → 配方明细与调价")

    # ── Step 1: Select product ──────────────────────────────────────
    profit_df_t4 = sku_profit_table(wb.sheets, basis="store", only_status=None)
    if profit_df_t4.empty:
        st.warning("无可用毛利数据。")
        st.stop()

    # Extract product-level keys (品类|品名)
    all_pks = profit_df_t4["product_key"].dropna().unique().tolist()
    product_options = sorted(set("|".join(pk.split("|")[:2]) for pk in all_pks if "|" in pk))

    col_prod, col_basis_t4 = st.columns([3, 1])
    with col_prod:
        selected_product = st.selectbox(
            "选择产品",
            options=product_options,
            placeholder="从毛利表中选取产品...",
        )
    with col_basis_t4:
        basis_t4 = st.radio(
            "口径",
            options=["factory", "store"],
            format_func=lambda x: "出厂口径" if x == "factory" else "门店口径",
            horizontal=True,
        )

    if not selected_product:
        st.info("👆 请在上方选择一个产品。")
        st.stop()

    # ── Step 2: SKU specs table ────────────────────────────────────
    skus_for_product = [
        pk for pk in all_pks
        if pk.startswith(selected_product + "|") or pk == selected_product
    ]
    sku_df = profit_df_t4[profit_df_t4["product_key"].isin(skus_for_product)].copy()

    if sku_df.empty:
        st.info("该产品下没有找到 SKU 数据。")
        st.stop()

    st.divider()
    st.markdown(f"##### {selected_product} — SKU 规格列表")

    display_t4 = sku_df.copy()
    display_t4["gross_margin"] = display_t4["gross_margin"].apply(
        lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A"
    )
    display_t4["gross_profit"] = display_t4["gross_profit"].round(2)

    # Add a "查看配方" column as a selectbox or button
    # Use a selectbox to pick which SKU to drill into
    sku_options = display_t4["product_key"].tolist()
    selected_sku = st.selectbox(
        "选择 SKU 查看配方",
        options=sku_options,
        format_func=lambda pk: pk.split("|")[-1] if "|" in pk else pk,
    )

    # Show the basic SKU table
    st.dataframe(display_t4, use_container_width=True, height=200)
```

- [ ] **Step 3: Run compile check**

Run: `python3 -m py_compile app.py`
Expected: exit 0

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: redesign Tab4 step 1-2 — product selection and SKU list"
```

---

### Task 6: Redesign Tab4 — Step 3 (recipe detail + pricing panel)

**Files:**
- Modify: `app.py` (continue Tab4 rewrite)

- [ ] **Step 1: Add Step 3 — recipe table with editable store_price + pricing panel**

After the SKU table in the `with tab4:` block, add the recipe detail section:

```python
    # ── Step 3: Recipe detail + pricing ─────────────────────────────
    st.divider()
    st.markdown(f"##### 配方明细 — {selected_sku.split('|')[-1] if '|' in selected_sku else selected_sku}")

    # Build recipe table
    recipe_key = f"recipe_store_prices_{selected_sku}_{basis_t4}"
    if recipe_key not in st.session_state:
        # Initialize from data
        recipe_df = build_recipe_table(wb.sheets, product_key=selected_sku, basis=basis_t4)
        if not recipe_df.empty:
            st.session_state[recipe_key] = recipe_df.to_dict("records")
        else:
            st.session_state[recipe_key] = []
    else:
        recipe_df = pd.DataFrame(st.session_state[recipe_key])

    if recipe_df.empty:
        st.info("暂无配方明细数据。")
    else:
        # Editable store_price column using data_editor
        editor_cols = ["item", "usage_qty", "cost", "spec", "store_price", "brand_cost", "profit_rate"]
        editor_df = recipe_df[editor_cols].copy() if all(c in recipe_df.columns for c in editor_cols) else recipe_df

        edited = st.data_editor(
            editor_df,
            use_container_width=True,
            height=400,
            column_config={
                "item": st.column_config.TextColumn("项目", disabled=True),
                "usage_qty": st.column_config.NumberColumn("用量", disabled=True, format="%.3f"),
                "cost": st.column_config.NumberColumn("成本", disabled=True, format="%.4f"),
                "spec": st.column_config.TextColumn("规格", disabled=True),
                "store_price": st.column_config.NumberColumn("门店价格", format="%.2f"),
                "brand_cost": st.column_config.NumberColumn("品牌成本", disabled=True, format="%.2f"),
                "profit_rate": st.column_config.NumberColumn("利润率", disabled=True, format="%.2f"),
            },
        )

        # Recalculate costs based on edited store_price
        total_cost = 0.0
        for i, row in edited.iterrows():
            if row.get("is_semi", False) or row.get("level", 0) == 1:
                continue  # skip semi-product summary row
            sp = _to_float(row.get("store_price"))
            bc = _to_float(row.get("brand_cost")) or 0.0
            spec_str = str(row.get("spec", "")).strip()
            spec_val = _parse_spec(spec_str)
            uq = _to_float(row.get("usage_qty")) or 0.0

            calculated_cost = 0.0
            if spec_val and spec_val > 0 and uq > 0 and sp is not None:
                calculated_cost = uq * (sp / spec_val)
            row["cost"] = round(calculated_cost, 4)
            row["profit_rate"] = round(_calc_profit_rate(sp or 0, bc), 4)
            total_cost += calculated_cost

        # Update session state
        st.session_state[recipe_key] = edited.to_dict("records")

        # ── Right panel: pricing & margin KPI cards ────────────────
        price_key = f"sku_price_{selected_sku}"
        default_price = _to_float(sku_df[sku_df["product_key"] == selected_sku]["price"].iloc[0]) or 0.0
        current_price = st.session_state.get(price_key, default_price)

        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            new_price = st.number_input("门店售价（元）", value=float(current_price), step=1.0, min_value=0.0, key=f"price_input_{selected_sku}")
            st.session_state[price_key] = new_price
        with col_p2:
            gross_profit = new_price - total_cost
            st.metric("总成本（元）", f"{total_cost:.2f}")
        with col_p3:
            margin_rate = (gross_profit / new_price * 100) if new_price > 0 else 0
            st.metric("毛利（元）", f"{gross_profit:.2f}", delta=f"{margin_rate:.1f}%")
```

Note: The `_to_float`, `_parse_spec`, and `_calc_profit_rate` helpers need to be available. Either import them from recipe module or define them locally.

Add near top of app.py:
```python
from mike_product_calc.calc.recipe import (
    build_recipe_table,
    _parse_spec,
    _calc_profit_rate,
)
```

- [ ] **Step 2: Add scenario save/compare section**

After the pricing panel, add:

```python
    # ── Scenario management ──────────────────────────────────────────
    st.divider()
    st.markdown("##### 方案管理")

    col_save_nm, col_save_btn = st.columns([3, 1])
    with col_save_nm:
        scenario_name = st.text_input("方案名称", placeholder="输入名称后保存", key="t4_scenario_name")
    with col_save_btn:
        st.write("")
        st.write("")
        if st.button("💾 保存方案", use_container_width=True):
            # Save current adjustments to ScenarioStore
            adjustments = []
            for _, row in edited.iterrows():
                if row.get("is_semi", False) or row.get("level", 0) == 1:
                    continue
                sp = _to_float(row.get("store_price"))
                if sp is not None and sp > 0:
                    name = str(row.get("item", "")).strip()
                    if name:
                        adjustments.append(MaterialPriceAdjustment(
                            item=name,
                            new_unit_price=sp,
                        ))
            if scenario_name and adjustments:
                store.put(Scenario(name=scenario_name, adjustments=tuple(adjustments)))
                st.success(f"方案「{scenario_name}」已保存")
                _auto_save()
                st.rerun()

    # Saved scenarios
    names = store.list_names()
    if names:
        st.markdown("##### 已保存方案")
        for nm in names:
            sc = store.get(nm)
            adj_list = [f"{a.item} → {a.new_unit_price}" for a in (sc.adjustments if sc else [])]
            st.markdown(f"**{nm}**（{len(adj_list)} 项调价）：{', '.join(adj_list) if adj_list else '（无调整）'}")

        if len(names) >= 2:
            st.divider()
            st.markdown("##### 方案对比")
            c_a, c_b = st.columns(2)
            with c_a:
                va = st.selectbox("方案 A", names, key="t4_cmp_a")
            with c_b:
                vb = st.selectbox("方案 B", names, index=min(1, len(names)-1), key="t4_cmp_b")
            if va != vb and st.button("🔍 对比"):
                s_a, s_b = store.get(va), store.get(vb)
                if s_a and s_b:
                    diff = compare_scenarios(s_a, s_b, wb.sheets, basis=basis_t4)
                    st.dataframe(diff, use_container_width=True, height=420)
```

- [ ] **Step 3: Run compile check**

Run: `python3 -m py_compile app.py`
Expected: exit 0

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: redesign Tab4 step 3 — recipe detail with editable pricing and scenario management"
```

---

### Task 7: Fix imports and clean up

**Files:**
- Modify: `app.py` (ensure correct imports)
- Modify: `src/mike_product_calc/calc/recipe.py` (export helpers)

- [ ] **Step 1: Verify all imports in app.py**

Ensure app.py has:
```python
from mike_product_calc.calc.recipe import build_recipe_table
from mike_product_calc.calc.material_sim import (
    Scenario, ScenarioStore, MaterialPriceAdjustment, compare_scenarios,
)
from mike_product_calc.calc.profit import margin_delta_report, sku_cost_breakdown, sku_profit_table
from mike_product_calc.calc.target_pricing import suggest_adjustable_item_costs
from mike_product_calc.data.validator import issues_to_dataframe, issues_to_report
```

Remove any lingering references to deleted modules.

- [ ] **Step 2: Full compile check**

Run: `python3 -m py_compile app.py && python3 -m py_compile src/mike_product_calc/cli.py`
Expected: exit 0

- [ ] **Step 3: Run all tests**

Run: `PYTHONPATH=src pytest tests/ -q --tb=short`
Expected: remaining tests pass

- [ ] **Step 4: Commit**

```bash
git add app.py src/ tests/
git commit -m "chore: clean up imports and verify compilation"
```

---

### Self-Review Checklist

1. **Spec coverage:** Every spec requirement maps to a task:
   - Delete Tab6/7/8 → Task 2 (app.py) + Task 3 (calc/cli)
   - Tab2 recipe breakdown → Task 4
   - Tab4 redesign → Tasks 5, 6
   - Shared recipe module → Task 1
   - CLI cleanup → Task 3
   - Test cleanup → Tasks 3, 7

2. **No placeholders:** All steps contain actual code and commands.

3. **Type consistency:** `build_recipe_table` signature consistent across Task 1 (definition) and Tasks 4/6 (usage). `_parse_spec` and `_calc_profit_rate` exported from recipe.py in Task 1, imported in app.py in Task 6.
