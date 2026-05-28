# Scenario Apply & Price History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to apply saved price scenarios to Supabase raw materials with full history tracking and rollback.

**Architecture:** Add 4 methods to `MpcSupabaseClient` for applying scenarios and managing history. Create `price_change_log` table via migration. Add UI buttons in Tab3 scenario section and a price history browser with rollback.

**Tech Stack:** Python/requests to Supabase REST API, Streamlit, PostgreSQL

---

### Task 1: Create `price_change_log` table in Supabase

**Files:**
- DB migration

- [ ] **Step 1: Apply migration to create table**

```sql
CREATE TABLE price_change_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id UUID NOT NULL,
  material_name TEXT NOT NULL,
  material_code TEXT,
  old_final_price NUMERIC,
  new_final_price NUMERIC,
  scenario_name TEXT NOT NULL,
  applied_by TEXT DEFAULT 'streamlit',
  applied_at TIMESTAMPTZ DEFAULT now(),
  rolled_back_at TIMESTAMPTZ,
  rollback_reason TEXT
);
CREATE INDEX idx_pcl_batch ON price_change_log(batch_id);
CREATE INDEX idx_pcl_material ON price_change_log(material_name);
CREATE INDEX idx_pcl_time ON price_change_log(applied_at DESC);
```

Use supabase MCP `apply_migration` with project_id = `ltwqcvqfwwvjrcwnwvvn`, name = `create_price_change_log`.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-05-29-scenario-apply-and-history-design.md
git commit -m "docs: scenario apply and history design spec"
```

---

### Task 2: Add price history methods to `supabase_client.py`

**Files:**
- Modify: `src/mike_product_calc/data/supabase_client.py`

- [ ] **Step 1: Add `_find_material_by_name` helper**

```python
def _find_material_by_name(self, name: str) -> dict | None:
    """Find a raw_material by exact name match."""
    all_mats = self.list_raw_materials()
    for m in all_mats:
        if str(m.get("name", "")).strip() == name.strip():
            return m
    return None
```

- [ ] **Step 2: Add `apply_scenario` method**

```python
def apply_scenario(self, scenario_name: str, adjustments: list) -> dict:
    """Apply a scenario's price adjustments to raw_materials table.
    
    adjustments: list of MaterialPriceAdjustment (item, new_unit_price)
    Returns: {batch_id, total, ok, errors[], changes[]}
    """
    import uuid
    batch_id = str(uuid.uuid4())
    changes = []
    ok_count = 0
    for adj in adjustments:
        mat = self._find_material_by_name(adj.item)
        if not mat:
            changes.append({"item": adj.item, "status": "not_found"})
            continue
        old_price = float(mat.get("final_price") or 0)
        new_price = float(adj.new_unit_price)
        # Update raw_material final_price
        try:
            self.update_raw_material(mat["id"], {"final_price": new_price})
        except requests.HTTPError:
            changes.append({"item": adj.item, "old": old_price, "status": "update_failed"})
            continue
        # Log the change
        log_entry = {
            "batch_id": batch_id,
            "material_name": adj.item,
            "material_code": mat.get("code", ""),
            "old_final_price": old_price,
            "new_final_price": new_price,
            "scenario_name": scenario_name,
        }
        try:
            requests.post(
                f"{self._base}/price_change_log",
                headers=self._headers(),
                json=[log_entry],
            )
        except requests.HTTPError:
            pass  # history write failure shouldn't block price update
        changes.append({"item": adj.item, "old": old_price, "new": new_price, "status": "ok"})
        ok_count += 1
    return {
        "batch_id": batch_id,
        "total": len(adjustments),
        "ok": ok_count,
        "changes": changes,
    }
```

- [ ] **Step 3: Add `rollback_batch` method**

```python
def rollback_batch(self, batch_id: str, reason: str = "") -> dict:
    """Rollback all price changes in a batch."""
    entries = self.query_table_where("price_change_log", {
        "batch_id": f"eq.{batch_id}",
        "rolled_back_at": "is.null",
    })
    rolled = 0
    for entry in entries:
        mat = self._find_material_by_name(entry["material_name"])
        if mat:
            try:
                self.update_raw_material(mat["id"], {"final_price": entry["old_final_price"]})
                rolled += 1
            except requests.HTTPError:
                pass
    # Mark batch as rolled back
    if entries:
        now_str = datetime.utcnow().isoformat()
        requests.patch(
            f"{self._base}/price_change_log?batch_id=eq.{batch_id}",
            headers=self._headers(),
            json={"rolled_back_at": now_str, "rollback_reason": reason},
        )
    return {"batch_id": batch_id, "rolled_back": rolled}
```

- [ ] **Step 4: Add `list_price_change_batches` method**

```python
def list_price_change_batches(self) -> list[dict]:
    """List all batches with summary stats."""
    resp = requests.get(
        f"{self._base}/price_change_log",
        headers=self._headers(),
        params={"select": "batch_id,scenario_name,applied_at,rolled_back_at,material_name",
                "order": "applied_at.desc"},
    )
    resp.raise_for_status()
    rows = resp.json()
    # Group by batch_id
    batches: dict[str, dict] = {}
    for r in rows:
        bid = r["batch_id"]
        if bid not in batches:
            batches[bid] = {
                "batch_id": bid,
                "scenario_name": r["scenario_name"],
                "applied_at": r["applied_at"],
                "item_count": 0,
                "rolled_back_count": 0,
            }
        batches[bid]["item_count"] += 1
        if r.get("rolled_back_at"):
            batches[bid]["rolled_back_count"] += 1
    result = sorted(batches.values(), key=lambda b: b["applied_at"], reverse=True)
    for b in result:
        b["all_rolled_back"] = b["rolled_back_count"] == b["item_count"]
    return result
```

- [ ] **Step 5: Add `get_batch_details` method**

```python
def get_batch_details(self, batch_id: str) -> list[dict]:
    """Get all log entries for a batch."""
    return self.query_table_where("price_change_log", {
        "batch_id": f"eq.{batch_id}",
        "order": "material_name",
    })
```

- [ ] **Step 6: Add imports and verify compilation**

Add at top of file:
```python
from datetime import datetime
```

Run: `python -m py_compile src/mike_product_calc/data/supabase_client.py`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/mike_product_calc/data/supabase_client.py
git commit -m "feat: add apply_scenario and price history methods to supabase client"
```

---

### Task 3: Add UI in Tab3 — apply button and history view

**Files:**
- Modify: `app.py` (Tab3 scenario management section)

- [ ] **Step 1: Add import for Supabase client in app.py** (check if already imported)

The app already has `_st_supa` as the Supabase client instance in session_state.

- [ ] **Step 2: Replace the saved scenario list with actionable items**

Find the saved scenarios section (around line 1063-1068) and replace with:

```python
# ── Saved scenarios with apply-to-database ──
names = store.list_names()
if names:
    st.markdown("##### 已保存方案")
    for nm in names:
        sc = store.get(nm)
        adj_list = [f"{a.item} → {a.new_unit_price}" for a in (sc.adjustments if sc else [])]
        st.markdown(f"**{nm}**（{len(adj_list)} 项调价）：{', '.join(adj_list) if adj_list else '（无调整）'}")
        
        # Apply button row
        col_prev, col_apply = st.columns([1, 1])
        with col_prev:
            if st.button(f"预览影响", key=f"preview_{nm}"):
                preview_df = pd.DataFrame([
                    {"原料": a.item, "新门店价格": a.new_unit_price}
                    for a in (sc.adjustments if sc else [])
                ])
                st.dataframe(preview_df, hide_index=True, use_container_width=True)
        with col_apply:
            if st.button(f"应用到原料库", key=f"apply_{nm}", type="primary"):
                _apply_scenario(nm, sc.adjustments)
```

- [ ] **Step 3: Add `_apply_scenario` handler function**

After the `if names:` block (before the comparison section), add:

```python
def _apply_scenario(name: str, adjustments: tuple) -> None:
    """Apply scenario to Supabase raw_materials with confirmation."""
    if not adjustments:
        st.warning("该方案没有调价数据。")
        return
    # Confirm
    st.write(f"方案「{name}」将更新以下 {len(adjustments)} 项原料的门店价格：")
    confirm_df = pd.DataFrame([
        {"原料": a.item, "新门店价格": a.new_unit_price}
        for a in adjustments
    ])
    st.dataframe(confirm_df, hide_index=True, use_container_width=True)
    
    client = st.session_state.get("supabase_client")
    if not client:
        st.error("Supabase 未连接，无法应用到原料库。")
        return
    
    if st.button("确认应用", key=f"confirm_apply_{name}"):
        with st.spinner("正在应用到原料库..."):
            result = client.apply_scenario(name, list(adjustments))
        if result["ok"] > 0:
            st.success(f"已更新 {result['ok']}/{result['total']} 项原料的门店价格")
            st.cache_data.clear()
        errors = [c for c in result["changes"] if c.get("status") != "ok"]
        if errors:
            for e in errors:
                st.warning(f"未找到原料「{e['item']}」")
```

Wait, I can't use `st.write` inside a button callback that way. Let me use `st.popover` or a dialog instead. Actually, the simplest approach is to use `st.popover` for confirmation.

Let me restructure:

```python
    with col_apply:
        with st.popover(f"应用到原料库", key=f"apply_pop_{nm}"):
            st.markdown(f"### 确认应用方案「{nm}」")
            st.write(f"将更新 {len(sc.adjustments)} 项原料的门店价格：")
            confirm_df = pd.DataFrame([
                {"原料": a.item, "当前价格": "?", "新价格": a.new_unit_price}
                for a in (sc.adjustments if sc else [])
            ])
            st.dataframe(confirm_df, hide_index=True, use_container_width=True)
            if st.button("确认应用", key=f"confirm_{nm}", type="primary"):
                client = st.session_state.get("supabase_client")
                if not client:
                    st.error("Supabase 未连接")
                else:
                    with st.spinner("正在应用..."):
                        result = client.apply_scenario(nm, list(sc.adjustments))
                    if result["ok"] > 0:
                        st.success(f"已更新 {result['ok']}/{result['total']} 项原料")
                        st.cache_data.clear()
                        st.rerun()
                    errors = [c for c in result["changes"] if c.get("status") != "ok"]
                    if errors:
                        for e in errors:
                            st.warning(f"原料「{e['item']}」未找到")
```

- [ ] **Step 4: Add price change history section**

After the scenario comparison section (before `# ── Tab5: 产销计划`), add:

```python
        # ── Price change history ──
        st.divider()
        st.markdown("##### 价格变更记录")
        
        client = st.session_state.get("supabase_client")
        if client:
            batches = client.list_price_change_batches()
            if batches:
                for b in batches[:10]:
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        st.caption(f"{b['scenario_name']}")
                        st.text(b["applied_at"][:16] if b["applied_at"] else "")
                    with col2:
                        st.text(f"{b['item_count']} 项")
                    with col3:
                        if b["all_rolled_back"]:
                            st.text("✅ 已回滚")
                        else:
                            st.text("生效中")
                    with col4:
                        if st.button("查看", key=f"view_batch_{b['batch_id']}"):
                            st.session_state[f"_view_batch_{b['batch_id']}"] = True
                        if not b["all_rolled_back"]:
                            if st.button("回滚", key=f"rollback_{b['batch_id']}"):
                                client.rollback_batch(b["batch_id"], "用户手动回滚")
                                st.success("已回滚")
                                st.cache_data.clear()
                                st.rerun()
                    
                    # Show batch details if "查看" was clicked
                    if st.session_state.get(f"_view_batch_{b['batch_id']}", False):
                        details = client.get_batch_details(b["batch_id"])
                        detail_df = pd.DataFrame([
                            {
                                "原料": d["material_name"],
                                "旧价格": float(d["old_final_price"]),
                                "新价格": float(d["new_final_price"]),
                                "回滚": "是" if d.get("rolled_back_at") else "否",
                            }
                            for d in details
                        ])
                        st.dataframe(detail_df, hide_index=True, use_container_width=True)
            else:
                st.caption("暂无价格变更记录。")
```

- [ ] **Step 5: Verify compilation**

Run: `python -m py_compile app.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: add scenario apply and price history UI to material simulator"
```

---

### Task 4: Create migration and full integration test

- [ ] **Step 1: Create the migration in Supabase**

Use MCP `apply_migration`:
- project_id: `ltwqcvqfwwvjrcwnwvvn`
- name: `create_price_change_log`
- SQL: CREATE TABLE + indexes from Task 1

- [ ] **Step 2: Run full flow test**

1. Restart Streamlit: `streamlit run app.py`
2. Go to Tab3, select a product, edit some prices
3. Save as "测试方案"
4. Click "应用到原料库" → confirm
5. Verify price_change_log has entries
6. Click "回滚" → verify prices restored

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete scenario apply and price history feature"
git push
```
