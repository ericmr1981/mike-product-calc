# Overview Dashboard UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign Tab1 (`概览/校验`) into a management cockpit with risk-first layout, business overview, and action guidance while preserving existing data semantics.

**Architecture:** Keep `app.py` as the Streamlit entrypoint, but extract Tab1 aggregation/render helpers into focused utility functions in the same file for V1 scope control. Risk metrics come from latest inventory snapshot APIs and gracefully degrade when unavailable. Existing cached session data remains the source for business metrics.

**Tech Stack:** Python 3.9+, Streamlit, pandas, Supabase REST via existing `MpcSupabaseClient`, pytest.

---

## File Structure Map

- Modify: `app.py` (Tab1 layout + helper functions + style classes)
- Modify: `src/mike_product_calc/data/supabase_client.py` (optional helper for lightweight risk summary query if needed)
- Modify: `tests/test_supabase_client.py` (if client helper added)
- Create: `tests/test_overview_dashboard.py` (pure logic tests for risk state + action hints)
- Modify: `README.md` (update Tab1 description)

---

### Task 1: Add Pure Logic Helpers for Dashboard Risk Cards

**Files:**
- Create: `tests/test_overview_dashboard.py`
- Modify: `app.py`

- [ ] **Step 1: Write failing tests for risk-level mapping and action recommendation ordering**

```python
# tests/test_overview_dashboard.py
from app import _risk_level, _build_action_hints


def test_risk_level_mapping():
    assert _risk_level(0) == "normal"
    assert _risk_level(1) == "medium"
    assert _risk_level(5) == "high"


def test_action_hints_prioritize_risk_first():
    hints = _build_action_hints(out_of_stock=3, abnormal=1, snapshot_stale=True)
    assert hints[0].startswith("去 Tab8")
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest -q tests/test_overview_dashboard.py`
Expected: FAIL because helper functions do not exist.

- [ ] **Step 3: Implement minimal helpers in `app.py`**

```python
# app.py

def _risk_level(count: int) -> str:
    if count <= 0:
        return "normal"
    if count <= 2:
        return "medium"
    return "high"


def _build_action_hints(*, out_of_stock: int, abnormal: int, snapshot_stale: bool) -> list[str]:
    hints: list[str] = []
    if out_of_stock > 0:
        hints.append("去 Tab8 查看缺货项并确认受影响仓库")
    if abnormal > 0:
        hints.append("去 Tab8 检查异常项并核对库存台账")
    if snapshot_stale:
        hints.append("先刷新 Supabase 缓存，确认库存快照时效")
    if not hints:
        hints.append("当前状态良好，可转到 Tab4 继续产销计划")
    return hints
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python3 -m pytest -q tests/test_overview_dashboard.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_overview_dashboard.py
git commit -m "feat: add pure overview risk helper functions"
```

---

### Task 2: Add Risk Data Aggregation with Graceful Degradation

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add inventory risk aggregation helper in `app.py`**

```python
# app.py

def _collect_inventory_risk(client) -> dict:
    try:
        rows = client.list_latest_inventory_rows(limit=5000)
        snap = client.get_latest_inventory_snapshot_at()
    except Exception as exc:
        return {
            "ready": False,
            "error": str(exc),
            "out_of_stock": 0,
            "abnormal": 0,
            "snapshot_stale": False,
            "snapshot_at": None,
        }

    df = pd.DataFrame(rows)
    out_of_stock = 0
    abnormal = 0
    if not df.empty:
        out_of_stock = int((pd.to_numeric(df.get("available_qty"), errors="coerce").fillna(0) <= 0).sum())
        abnormal = int((df.get("is_negative_stock", False) | df.get("has_amount_mismatch", False)).sum())

    snapshot_stale = False
    if snap:
        try:
            dt = datetime.fromisoformat(str(snap).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            snapshot_stale = (datetime.now(timezone.utc) - dt).total_seconds() > 7200
        except Exception:
            snapshot_stale = False

    return {
        "ready": True,
        "error": "",
        "out_of_stock": out_of_stock,
        "abnormal": abnormal,
        "snapshot_stale": snapshot_stale,
        "snapshot_at": snap,
    }
```

- [ ] **Step 2: Compile-check after adding helper**

Run: `python3 -m py_compile app.py`
Expected: no output (success).

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add risk aggregation for overview cockpit"
```

---

### Task 3: Rebuild Tab1 Layout (Risk-first, Business-second)

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Replace current Tab1 metric block with cockpit sections**

```python
# app.py (inside with tab1:)
_heading_with_help("运营控制台概览", "风险优先、经营次级、动作导向")

risk = _collect_inventory_risk(_st_supa)

st.markdown("#### 风险区")
r1, r2, r3 = st.columns(3)
r1.metric("缺货项", risk["out_of_stock"])
r2.metric("异常项", risk["abnormal"])
r3.metric("快照时效", "过期" if risk["snapshot_stale"] else "正常")

st.markdown("#### 经营区")
b1, b2, b3, b4 = st.columns(4)
b1.metric("原料总数", _stats["total"])
b2.metric("产品数", len(_prods_c))
b3.metric("最终成品", _final)
b4.metric("出品规格", _specs_count)

st.markdown("#### 建议动作")
for i, hint in enumerate(_build_action_hints(
    out_of_stock=risk["out_of_stock"],
    abnormal=risk["abnormal"],
    snapshot_stale=risk["snapshot_stale"],
), start=1):
    st.markdown(f"{i}. {hint}")
```

- [ ] **Step 2: Add light CSS classes for risk/business card differentiation**

```python
# app.py (style block)
.overview-risk-card { border-left: 4px solid #dc2626; }
.overview-business-card { border-left: 4px solid #0891b2; }
```

- [ ] **Step 3: Run compile check**

Run: `python3 -m py_compile app.py`
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: redesign tab1 as risk-first management cockpit"
```

---

### Task 4: Mobile Readability and Degraded-State UX

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add degraded-state cards for unavailable inventory risk data**

```python
# app.py
if not risk["ready"]:
    st.warning("库存风险数据未就绪，当前仅展示经营指标。")
    st.caption(risk["error"])
```

- [ ] **Step 2: Ensure mobile order is risk -> business -> actions**

```python
# app.py style/media query adjustments
# keep card sections in vertical flow under max-width:768px
```

- [ ] **Step 3: Compile check**

Run: `python3 -m py_compile app.py`
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: improve tab1 degraded-state and mobile readability"
```

---

### Task 5: Final Verification + README Update

**Files:**
- Modify: `README.md`
- Verify: `app.py`, `tests/test_overview_dashboard.py`

- [ ] **Step 1: Update README for redesigned Tab1**

```markdown
# README updates
- Tab1 升级为“运营控制台概览”
- 风险区（缺货/异常/快照时效）在上
- 经营区（原料/产品/成品/规格）在下
- 建议动作区引导跳转 Tab8/Tab4
```

- [ ] **Step 2: Run tests**

Run: `python3 -m pytest -q tests/test_overview_dashboard.py tests/test_inventory_tab.py -k "overview or inventory"`
Expected: PASS.

- [ ] **Step 3: Run compile verification**

Run: `python3 -m py_compile app.py`
Expected: no output.

- [ ] **Step 4: Commit final integration**

```bash
git add README.md app.py tests/test_overview_dashboard.py
git commit -m "feat: deliver tab1 cockpit ui redesign"
```

- [ ] **Step 5: Push branch**

```bash
git push origin main
```

---

## Self-Review Checklist

- Spec coverage: risk-first, business-second, action guidance, mobile support, and degraded-state behavior are all mapped.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: risk keys remain `out_of_stock`, `abnormal`, `snapshot_stale`, `snapshot_at` across tasks.
