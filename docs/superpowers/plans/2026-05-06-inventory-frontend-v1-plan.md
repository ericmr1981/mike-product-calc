# Inventory Storefront V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a storefront-first, mobile+desktop inventory dashboard in the existing Streamlit app using latest Supabase inventory snapshots.

**Architecture:** Keep `app.py` as entrypoint, but move inventory logic into focused modules: a data service (`data/inventory_view.py`) and a UI renderer (`ui/inventory_tab.py`). `app.py` only wires a new tab and passes the Supabase client. This keeps behavior testable and prevents further monolith growth.

**Tech Stack:** Python 3.9+, Streamlit, pandas, Supabase REST via existing `MpcSupabaseClient`, pytest.

---

## File Structure Map

- Create: `src/mike_product_calc/data/inventory_view.py`
- Create: `src/mike_product_calc/ui/__init__.py`
- Create: `src/mike_product_calc/ui/inventory_tab.py`
- Modify: `src/mike_product_calc/data/supabase_client.py` (add typed query helpers for latest inventory view + batch freshness)
- Modify: `app.py` (add Tab8 and call `render_inventory_tab`)
- Create: `tests/test_inventory_view.py`
- Create: `tests/test_inventory_tab.py`
- Modify: `README.md` (document Tab8 storefront inventory dashboard)

---

### Task 1: Build Inventory Data Service (Pure Logic + Tests)

**Files:**
- Create: `tests/test_inventory_view.py`
- Create: `src/mike_product_calc/data/inventory_view.py`

- [ ] **Step 1: Write the failing tests for status classification, KPI aggregation, and stale snapshot check**

```python
# tests/test_inventory_view.py
from datetime import datetime, timedelta, timezone
import pandas as pd

from mike_product_calc.data.inventory_view import (
    classify_inventory_row,
    build_inventory_kpis,
    is_snapshot_stale,
)


def test_classify_out_of_stock():
    row = {"available_qty": 0, "is_negative_stock": False, "has_amount_mismatch": False}
    assert classify_inventory_row(row, reorder_point=5) == "缺货"


def test_classify_low_stock():
    row = {"available_qty": 3, "is_negative_stock": False, "has_amount_mismatch": False}
    assert classify_inventory_row(row, reorder_point=5) == "低库存"


def test_classify_abnormal_overrides_other_status():
    row = {"available_qty": 9, "is_negative_stock": True, "has_amount_mismatch": False}
    assert classify_inventory_row(row, reorder_point=5) == "异常"


def test_build_inventory_kpis_counts_by_status():
    df = pd.DataFrame([
        {"inventory_status": "缺货"},
        {"inventory_status": "低库存"},
        {"inventory_status": "异常"},
        {"inventory_status": "正常"},
    ])
    got = build_inventory_kpis(df)
    assert got == {"total": 4, "out_of_stock": 1, "low_stock": 1, "abnormal": 1}


def test_snapshot_stale_true_when_older_than_threshold():
    snapshot_at = datetime.now(timezone.utc) - timedelta(hours=3)
    assert is_snapshot_stale(snapshot_at, now_utc=datetime.now(timezone.utc), stale_hours=2) is True
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest -q tests/test_inventory_view.py`
Expected: FAIL with `ModuleNotFoundError` for `mike_product_calc.data.inventory_view`.

- [ ] **Step 3: Implement minimal inventory view service**

```python
# src/mike_product_calc/data/inventory_view.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import pandas as pd


def classify_inventory_row(row: dict[str, Any], reorder_point: float) -> str:
    if bool(row.get("is_negative_stock")) or bool(row.get("has_amount_mismatch")):
        return "异常"
    available = float(row.get("available_qty") or 0)
    if available <= 0:
        return "缺货"
    if available <= reorder_point:
        return "低库存"
    return "正常"


def build_inventory_kpis(df: pd.DataFrame) -> dict[str, int]:
    c = df.get("inventory_status", pd.Series(dtype=str)).value_counts()
    return {
        "total": int(len(df)),
        "out_of_stock": int(c.get("缺货", 0)),
        "low_stock": int(c.get("低库存", 0)),
        "abnormal": int(c.get("异常", 0)),
    }


def is_snapshot_stale(snapshot_at: datetime, *, now_utc: datetime | None = None, stale_hours: int = 2) -> bool:
    now_utc = now_utc or datetime.now(timezone.utc)
    return (now_utc - snapshot_at).total_seconds() > stale_hours * 3600
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_inventory_view.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_inventory_view.py src/mike_product_calc/data/inventory_view.py
git commit -m "feat: add pure inventory view service and tests"
```

---

### Task 2: Add Supabase Query Helpers for Inventory Tab

**Files:**
- Modify: `src/mike_product_calc/data/supabase_client.py`
- Extend Test: `tests/test_supabase_client.py`

- [ ] **Step 1: Write failing tests for latest inventory and latest batch timestamp methods**

```python
# tests/test_supabase_client.py

def test_list_latest_inventory_rows(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"item_code": "WP0192"}]
        rows = client.list_latest_inventory_rows(limit=1000)
        assert rows[0]["item_code"] == "WP0192"


def test_get_latest_inventory_snapshot_at(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"snapshot_at": "2026-05-06T12:20:44+00:00"}]
        ts = client.get_latest_inventory_snapshot_at()
        assert ts == "2026-05-06T12:20:44+00:00"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest -q tests/test_supabase_client.py -k "latest_inventory"`
Expected: FAIL with `AttributeError` (`MpcSupabaseClient` missing methods).

- [ ] **Step 3: Implement methods in `MpcSupabaseClient`**

```python
# src/mike_product_calc/data/supabase_client.py

def list_latest_inventory_rows(self, limit: int = 5000) -> list[dict]:
    params = {"limit": str(limit), "order": "warehouse_code.asc,item_code.asc"}
    resp = requests.get(
        f"{self._base}/v_inventory_latest_item_by_warehouse",
        headers=self._headers(),
        params=params,
    )
    resp.raise_for_status()
    return resp.json()


def get_latest_inventory_snapshot_at(self) -> str | None:
    params = {"select": "snapshot_at", "order": "snapshot_at.desc", "limit": "1"}
    resp = requests.get(
        f"{self._base}/inventory_snapshot_batches",
        headers=self._headers(),
        params=params,
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0].get("snapshot_at") if rows else None
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_supabase_client.py -k "latest_inventory"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mike_product_calc/data/supabase_client.py tests/test_supabase_client.py
git commit -m "feat: add supabase helpers for latest inventory view"
```

---

### Task 3: Build Inventory Tab Renderer (UI Module)

**Files:**
- Create: `src/mike_product_calc/ui/__init__.py`
- Create: `src/mike_product_calc/ui/inventory_tab.py`
- Create: `tests/test_inventory_tab.py`

- [ ] **Step 1: Write failing tests for DataFrame shaping and default sorting**

```python
# tests/test_inventory_tab.py
import pandas as pd
from mike_product_calc.ui.inventory_tab import shape_inventory_table


def test_shape_inventory_table_adds_status_and_sort_priority():
    df = pd.DataFrame([
        {"item_code": "A", "available_qty": 10, "is_negative_stock": False, "has_amount_mismatch": False},
        {"item_code": "B", "available_qty": 0, "is_negative_stock": False, "has_amount_mismatch": False},
    ])
    out = shape_inventory_table(df, reorder_point=5)
    assert "inventory_status" in out.columns
    assert out.iloc[0]["item_code"] == "B"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest -q tests/test_inventory_tab.py`
Expected: FAIL with `ModuleNotFoundError` for `mike_product_calc.ui.inventory_tab`.

- [ ] **Step 3: Implement module and rendering entrypoint**

```python
# src/mike_product_calc/ui/inventory_tab.py
from __future__ import annotations

import pandas as pd
import streamlit as st

from mike_product_calc.data.inventory_view import classify_inventory_row, build_inventory_kpis


STATUS_PRIORITY = {"异常": 0, "缺货": 1, "低库存": 2, "正常": 3}


def shape_inventory_table(df: pd.DataFrame, reorder_point: float) -> pd.DataFrame:
    out = df.copy()
    out["inventory_status"] = out.apply(
        lambda r: classify_inventory_row(r.to_dict(), reorder_point=reorder_point), axis=1
    )
    out["_priority"] = out["inventory_status"].map(STATUS_PRIORITY).fillna(99)
    out = out.sort_values(["_priority", "available_qty", "item_code"], ascending=[True, True, True])
    return out


def render_inventory_tab(client) -> None:
    st.subheader("门店库存驾驶舱")
    reorder_point = st.number_input("低库存阈值", min_value=0.0, value=5.0, step=1.0)
    rows = client.list_latest_inventory_rows(limit=5000)
    if not rows:
        st.warning("暂无库存快照数据")
        return
    df = shape_inventory_table(pd.DataFrame(rows), reorder_point=float(reorder_point))
    kpi = build_inventory_kpis(df)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总品项", kpi["total"])
    c2.metric("缺货", kpi["out_of_stock"])
    c3.metric("低库存", kpi["low_stock"])
    c4.metric("异常", kpi["abnormal"])
    st.dataframe(df.drop(columns=["_priority"], errors="ignore"), use_container_width=True, hide_index=True)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_inventory_tab.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mike_product_calc/ui/__init__.py src/mike_product_calc/ui/inventory_tab.py tests/test_inventory_tab.py
git commit -m "feat: add inventory tab renderer with status-priority sorting"
```

---

### Task 4: Wire Tab8 into Streamlit App (`app.py`)

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add failing smoke assertion for new tab label**

```python
# tests/test_cli_smoke.py (lightweight guard)
def test_readme_mentions_inventory_tab():
    from pathlib import Path
    txt = Path("README.md").read_text(encoding="utf-8")
    assert "F-008" in txt
```

- [ ] **Step 2: Run the focused test first**

Run: `python3 -m pytest -q tests/test_cli_smoke.py -k "readme_mentions_inventory_tab"`
Expected: FAIL if README not yet aligned with new tab naming.

- [ ] **Step 3: Integrate new tab in `app.py`**

```python
# app.py (core edits)
from mike_product_calc.ui.inventory_tab import render_inventory_tab

# old:
# tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([...])
# new:
 tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "概览/校验", "原数据", "原料价格模拟器", "产销计划", "原料管理", "配方管理", "出品规格", "门店库存"
])

with tab8:
    render_inventory_tab(_st_supa)
```

- [ ] **Step 4: Run compile + focused test**

Run: `python3 -m py_compile app.py src/mike_product_calc/ui/inventory_tab.py`
Expected: no output (success).

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: wire storefront inventory tab into streamlit app"
```

---

### Task 5: Add Snapshot Freshness Warning + Storefront Filters

**Files:**
- Modify: `src/mike_product_calc/ui/inventory_tab.py`
- Modify: `tests/test_inventory_tab.py`

- [ ] **Step 1: Write failing tests for filter behavior and freshness banner condition**

```python
# tests/test_inventory_tab.py
from mike_product_calc.ui.inventory_tab import apply_inventory_filters


def test_apply_inventory_filters_by_status_and_keyword():
    df = pd.DataFrame([
        {"item_code": "A", "item_name": "草莓丁", "inventory_status": "缺货", "warehouse_code": "GM002"},
        {"item_code": "B", "item_name": "牛轧糖", "inventory_status": "正常", "warehouse_code": "GM002"},
    ])
    out = apply_inventory_filters(df, status="缺货", keyword="草莓", warehouse_code="GM002")
    assert len(out) == 1
    assert out.iloc[0]["item_code"] == "A"
```

- [ ] **Step 2: Run test to verify failure**

Run: `python3 -m pytest -q tests/test_inventory_tab.py -k "apply_inventory_filters"`
Expected: FAIL (`apply_inventory_filters` not found).

- [ ] **Step 3: Implement filters + freshness UI hook**

```python
# src/mike_product_calc/ui/inventory_tab.py

def apply_inventory_filters(df: pd.DataFrame, *, status: str, keyword: str, warehouse_code: str) -> pd.DataFrame:
    out = df
    if warehouse_code != "全部":
        out = out[out["warehouse_code"] == warehouse_code]
    if status != "全部":
        out = out[out["inventory_status"] == status]
    if keyword.strip():
        k = keyword.strip()
        out = out[
            out["item_code"].astype(str).str.contains(k, case=False, na=False)
            | out["item_name"].astype(str).str.contains(k, case=False, na=False)
        ]
    return out

# inside render_inventory_tab
snapshot_at = client.get_latest_inventory_snapshot_at()
if snapshot_at and is_snapshot_stale(datetime.fromisoformat(snapshot_at.replace("Z", "+00:00"))):
    st.error(f"库存快照已超过 2 小时未更新（最近: {snapshot_at}）")
```

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest -q tests/test_inventory_tab.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/mike_product_calc/ui/inventory_tab.py tests/test_inventory_tab.py
git commit -m "feat: add storefront filters and snapshot freshness warning"
```

---

### Task 6: Final Verification + Docs Update

**Files:**
- Modify: `README.md`
- Verify: `tests/test_inventory_view.py`, `tests/test_inventory_tab.py`, `tests/test_supabase_client.py`, `app.py`

- [ ] **Step 1: Update README sections for Tab8 usage and low-stock threshold default**

```markdown
# README.md additions
- 新增 F-008 门店库存页（双端自适应）
- 默认低库存阈值 = 5（页面可调）
- 数据源 = v_inventory_latest_item_by_warehouse
```

- [ ] **Step 2: Run targeted full verification**

Run:
`python3 -m pytest -q tests/test_inventory_view.py tests/test_inventory_tab.py tests/test_supabase_client.py tests/test_cli_smoke.py -k "inventory or supabase_client"`
Expected: PASS.

- [ ] **Step 3: Run compile check**

Run:
`python3 -m py_compile app.py src/mike_product_calc/data/inventory_view.py src/mike_product_calc/ui/inventory_tab.py src/mike_product_calc/data/supabase_client.py`
Expected: no output (success).

- [ ] **Step 4: Commit docs and final integration**

```bash
git add README.md app.py src/mike_product_calc/data/inventory_view.py src/mike_product_calc/ui/inventory_tab.py src/mike_product_calc/data/supabase_client.py tests/test_inventory_view.py tests/test_inventory_tab.py tests/test_supabase_client.py
git commit -m "feat: deliver storefront-first inventory dashboard v1"
```

- [ ] **Step 5: Push branch**

```bash
git push origin codex/inventory-management
```

---

## Self-Review Checklist

- Spec coverage: includes dashboard/list/replenishment/anomaly views, mobile+desktop strategy, stale snapshot warning, status rules, and test strategy.
- Placeholder scan: no `TBD`/`TODO`/implicit “do later” steps.
- Type consistency: status labels fixed as `正常/低库存/缺货/异常`; threshold naming fixed as `reorder_point`.
