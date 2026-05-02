from __future__ import annotations

import sys
import tempfile
import io
import json
import hashlib
from datetime import date, timedelta, datetime
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd
import streamlit as st

from mike_product_calc.calc.material_sim import (
    MaterialCatalog,
    Scenario,
    ScenarioStore,
    SkuCostInfo,
    MaterialPriceAdjustment,
    apply_scenario_to_sku_costs,
    build_sku_cost_table,
    compare_scenarios,
    get_builtin_scenarios,
    highlight_negative_margin_rows,
    recalc_profit_with_adjusted_costs,
)
from mike_product_calc.calc.prep_engine import (
    bom_expand,
    bom_expand_multi,
    highlight_gaps,
    gaps_only,
    sales_to_production,
)
from mike_product_calc.calc.profit import margin_delta_report, sku_cost_breakdown, sku_profit_table
from mike_product_calc.calc.target_pricing import suggest_adjustable_item_costs
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
from mike_product_calc.model.production import ProductionRow
from mike_product_calc.calc.optimizer import (
    OptimizationConstraint,
    enumerate_portfolios,
    explain_recommendation,
)
from mike_product_calc.data.loader import load_workbook
from mike_product_calc.data.validator import issues_to_dataframe, validate_workbook
from mike_product_calc.data.shared import build_product_key
from mike_product_calc.model.production import ProductionPlan, ProductionRow
from mike_product_calc.state import get_store


st.set_page_config(page_title="mike-product-calc", layout="wide")

st.title("蜜可诗产品经营决策台")
st.caption("当前版本：Excel 解析 / 校验、SKU 毛利分析（双口径）、F-002 oracle、F-003 第一版反推定价。")

# ── 上传文件持久化（磁盘级，可删除/替换）────────────────────────────────────
UPLOAD_DIR = ROOT / "data" / "uploads"
REGISTRY_PATH = UPLOAD_DIR / "registry.json"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _load_registry() -> list[dict]:
    if not REGISTRY_PATH.exists():
        return []
    try:
        data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_registry(items: list[dict]) -> None:
    REGISTRY_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _delete_file(file_id: str) -> None:
    items = _load_registry()
    keep: list[dict] = []
    for it in items:
        if it.get("id") == file_id:
            saved = it.get("saved_name")
            if saved:
                fp = UPLOAD_DIR / saved
                if fp.exists():
                    fp.unlink()
        else:
            keep.append(it)
    _save_registry(keep)


def _save_upload(bytes_data: bytes, orig_name: str) -> dict:
    fid = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_sha256_bytes(bytes_data)[:10]}"
    safe_name = orig_name.replace('/', '_').replace('\\', '_')
    saved_name = f"{fid}__{safe_name}"
    (UPLOAD_DIR / saved_name).write_bytes(bytes_data)
    return {
        "id": fid,
        "orig_name": orig_name,
        "saved_name": saved_name,
        "uploaded_at": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "size": len(bytes_data),
        "sha256": _sha256_bytes(bytes_data),
    }


# UI: file manager
with st.expander("📁 数据文件管理（永久保存，可删除/替换）", expanded=True):
    registry = _load_registry()

    # Choose current file
    labels = ["(请选择)"]
    id_by_label: dict[str, str] = {"(请选择)": ""}
    for it in sorted(registry, key=lambda x: x.get('uploaded_at', ''), reverse=True):
        label = f"{it.get('orig_name','')} | {str(it.get('id',''))[:8]} | {it.get('uploaded_at','')}"
        labels.append(label)
        id_by_label[label] = str(it.get('id',''))

    active_id = st.session_state.get('active_file_id', '')
    # default selection
    default_label = next((lb for lb, fid in id_by_label.items() if fid == active_id), "(请选择)")
    selected_label = st.selectbox("当前工作簿", options=labels, index=labels.index(default_label) if default_label in labels else 0)
    selected_id = id_by_label.get(selected_label, "")
    if selected_id:
        st.session_state['active_file_id'] = selected_id

    col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
    with col_f1:
        replace_current = st.checkbox('上传后替换当前（自动删除当前文件）', value=False)
    with col_f2:
        if st.button('🗑️ 删除当前文件'):
            if selected_id:
                _delete_file(selected_id)
                st.session_state['active_file_id'] = ''
                st.rerun()
            else:
                st.warning('请先选择一个文件再删除')
    with col_f3:
        st.write('')

    up = st.file_uploader('📂 上传/新增 蜜可诗产品库.xlsx', type=['xlsx'], key='xlsx_upload')
    if up is not None:
        b = up.getvalue()
        sha = _sha256_bytes(b)

        # Guard: skip if already processed this upload in this session
        if st.session_state.get('_last_upload_sha') == sha:
            st.rerun()

        # Deduplicate: if this exact content is already in registry, reuse it
        existing = _load_registry()
        dup = next((it for it in existing if it.get('sha256') == sha), None)
        if dup:
            st.session_state['active_file_id'] = dup['id']
            st.session_state['_last_upload_sha'] = sha
            st.warning(f"该文件已存在（{dup['orig_name']}），已选中。")
            st.rerun()

        entry = _save_upload(b, getattr(up, 'name', 'workbook.xlsx'))
        items = _load_registry()
        items.insert(0, entry)
        _save_registry(items)

        if replace_current and selected_id:
            _delete_file(selected_id)

        st.session_state['active_file_id'] = entry['id']
        st.session_state['_last_upload_sha'] = sha
        st.success(f"已保存：{entry['orig_name']}（{entry['id'][:8]}）")
        st.rerun()


def _resolve_active_workbook() -> tuple[bytes, str, str]:
    """Return (xlsx_bytes, display_name, resolved_path).

    resolved_path is a real filesystem path usable by CLI/state.
    """

    # 1) active from registry
    fid = st.session_state.get('active_file_id', '')
    if fid:
        for it in _load_registry():
            if str(it.get('id')) == str(fid):
                fp = UPLOAD_DIR / str(it.get('saved_name'))
                if fp.exists():
                    return fp.read_bytes(), str(it.get('orig_name') or fp.name), str(fp)

    # 2) fallback: env var
    _default_xlsx = os.environ.get('MIKE_DEFAULT_XLSX', '')
    if _default_xlsx and Path(_default_xlsx).exists():
        p = Path(_default_xlsx)
        return p.read_bytes(), p.name, str(p)

    # 3) fallback: auto-select the first xlsx in UPLOAD_DIR
    if UPLOAD_DIR.exists():
        for candidate in sorted(UPLOAD_DIR.glob('*.xlsx')):
            if candidate.stat().st_size > 0:
                entry = {
                    'id': candidate.stem,
                    'orig_name': candidate.name,
                    'saved_name': candidate.name,
                }
                return candidate.read_bytes(), candidate.name, str(candidate)

    # 4) fallback: use default xlsx in data/ root
    for default in sorted(Path('data').glob('*.xlsx')):
        if default.stat().st_size > 0:
            return default.read_bytes(), default.name, str(default)

    raise FileNotFoundError('No workbook selected/uploaded')


try:
    workbook_bytes, workbook_name, workbook_path = _resolve_active_workbook()
except FileNotFoundError:
    st.info('请先在上方上传/选择 xlsx 文件开始。')
    st.stop()
@st.cache_data(show_spinner=False)
def _load_and_validate(bytes_data: bytes):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "workbook.xlsx"
        p.write_bytes(bytes_data)
        wb = load_workbook(p)
        # wb is WorkbookData; wb.sheets is Dict[str, pd.DataFrame]
        # validate_workbook expects Dict[str, pd.DataFrame]
        issues = validate_workbook(wb.sheets)
        return wb, issues


with st.spinner("解析中..."):
    wb, issues = _load_and_validate(workbook_bytes)

sheet_names = list(wb.sheets.keys())


# ── CLI/UI shared state (disk) ─────────────────────────────────────────

_store = get_store()
if "mpc_state_name" not in st.session_state:
    st.session_state["mpc_state_name"] = "default"


def _load_state_into_session(state_name: str) -> None:
    """Load disk state into Streamlit session_state once."""
    state = _store.load(state_name)

    # Always keep workbook path in sync (so CLI can operate on the same file)
    if workbook_path:
        state.xlsx_path = str(Path(workbook_path).resolve())

    # Init sim store
    if "sim_store" not in st.session_state:
        st.session_state["sim_store"] = ScenarioStore()

    # Load material sim versions
    sim_store: ScenarioStore = st.session_state["sim_store"]
    if state.material_sim_versions and not sim_store.list_names():
        for nm, adjs in state.material_sim_versions.items():
            adjustments = tuple(
                MaterialPriceAdjustment(item=str(a.get("item", "")).strip(), new_unit_price=float(a.get("new_unit_price", 0)))
                for a in (adjs or [])
                if str(a.get("item", "")).strip()
            )
            sim_store.put(Scenario(name=str(nm), adjustments=adjustments))

    # Production plans
    if "production_plans" not in st.session_state:
        st.session_state["production_plans"] = {}
    if "current_plan_name" not in st.session_state:
        st.session_state["current_plan_name"] = None

    plans: dict = st.session_state["production_plans"]
    if state.production_plans and not plans:
        for plan_name, rows in state.production_plans.items():
            rr: list[ProductionRow] = []
            for r in (rows or []):
                rr.append(
                    ProductionRow(
                        date=str(r.get("date", "")),
                        sku_key=str(r.get("sku_key", "")),
                        spec=str(r.get("spec", "")),
                        qty=float(r.get("qty", 0) or 0),
                        plan_type=str(r.get("plan_type", "sales")) if r.get("plan_type") else "sales",
                    )
                )
            plans[str(plan_name)] = rr

    # Portfolio versions (A/B/C)
    for slot, key in (("A", "portfolio_A"), ("B", "portfolio_B"), ("C", "portfolio_C")):
        if key not in st.session_state:
            st.session_state[key] = {}
        if state.portfolio_versions and state.portfolio_versions.get(slot) and not st.session_state[key]:
            st.session_state[key] = dict(state.portfolio_versions.get(slot) or {})

    # Persist updated xlsx_path back to disk (best-effort)
    state.touch()
    _store.save(state)


def _save_session_into_state(state_name: str) -> None:
    """Persist current Streamlit session_state into disk state."""
    state = _store.load(state_name)

    # workbook path
    if workbook_path:
        state.xlsx_path = str(Path(workbook_path).resolve())

    # sim versions
    sim_store: ScenarioStore = st.session_state.get("sim_store") or ScenarioStore()
    sim_versions: dict = {}
    for nm in sim_store.list_names():
        sc = sim_store.get(nm)
        if not sc:
            continue
        sim_versions[nm] = [
            {"item": a.item, "new_unit_price": float(a.new_unit_price)}
            for a in (sc.adjustments or ())
            if str(a.item).strip()
        ]
    state.material_sim_versions = sim_versions

    # production plans
    plans: dict = st.session_state.get("production_plans") or {}
    out_plans: dict = {}
    for plan_name, rows in plans.items():
        out_plans[str(plan_name)] = [
            {"date": r.date, "sku_key": r.sku_key, "spec": r.spec, "qty": float(r.qty), "plan_type": r.plan_type}
            for r in (rows or [])
        ]
    state.production_plans = out_plans

    # portfolios
    state.portfolio_versions = {
        "A": dict(st.session_state.get("portfolio_A") or {}),
        "B": dict(st.session_state.get("portfolio_B") or {}),
        "C": dict(st.session_state.get("portfolio_C") or {}),
    }

    state.touch()
    _store.save(state)


def _auto_save() -> None:
    """Save current UI session to disk state if auto-save is enabled."""
    if st.session_state.get("mpc_auto_save", True):
        _save_session_into_state(st.session_state.get("mpc_state_name", "default"))


# UI control for state management (sidebar)
with st.sidebar:
    st.markdown("### 💾 CLI/UI State")
    existing_states = ["default"] + [s for s in _store.list_states() if s != "default"]
    st.selectbox(
        "State 名称",
        options=existing_states,
        index=existing_states.index(st.session_state.get("mpc_state_name", "default"))
        if st.session_state.get("mpc_state_name", "default") in existing_states
        else 0,
        key="mpc_state_name",
    )

    # Auto-save toggle (default ON)
    if "mpc_auto_save" not in st.session_state:
        st.session_state["mpc_auto_save"] = True
    auto_save = st.checkbox("Auto-save（默认开启）", value=st.session_state["mpc_auto_save"],
                             help="开启后，每次保存版本/方案/计划时自动落盘，无需手动点 Save",
                             key="mpc_auto_save_chk")
    st.session_state["mpc_auto_save"] = auto_save

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        if st.button("⬇️ Load", use_container_width=True):
            st.session_state.pop("_mpc_state_synced", None)
            st.rerun()
    with col_s2:
        if st.button("⬆️ Save", use_container_width=True):
            _save_session_into_state(st.session_state["mpc_state_name"])
            st.success("state 已保存")
    with col_s3:
        if st.button("📸 Snapshot", use_container_width=True, help="保存当前 state 的快照"):
            snaps = _store.list_snapshots(st.session_state["mpc_state_name"])
            ts = _store.snapshot(st.session_state["mpc_state_name"])
            st.success(f"快照已保存（{len(snaps)+1} 份，最多保留 {_store.MAX_SNAPSHOTS} 份）")

    # Snapshot list + restore
    snaps = _store.list_snapshots(st.session_state["mpc_state_name"])
    if snaps:
        with st.expander("📸 Snapshots（可回滚）", expanded=False):
            snap_opts = [f"{s['ts']}" for s in snaps]
            snap_sel = st.selectbox("选择快照", options=snap_opts, key="_snap_sel")
            if st.button("↩️ Restore", key="_snap_restore_btn"):
                sid = next((s["id"] for s in snaps if s["ts"] == snap_sel), None)
                if sid:
                    _store.restore_snapshot(sid, st.session_state["mpc_state_name"])
                    st.session_state.pop("_mpc_state_synced", None)
                    st.rerun()
    st.caption(f"Workbook path: {workbook_path}")


# One-time sync
if "_mpc_state_synced" not in st.session_state:
    _load_state_into_session(st.session_state["mpc_state_name"])
    st.session_state["_mpc_state_synced"] = True


tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["概览/校验", "SKU 毛利分析（双口径）", "Sheet 浏览", "原料价格模拟器", "产销计划", "产品组合评估", "多场景对比", "选品优化器"])

with tab1:
    st.info("📌 **功能说明**：上传 Excel 文件后，系统自动解析并校验所有 sheet。\n"
             "**使用方法**：上传蜜可诗产品库.xlsx，等待解析完成后查看统计与校验报告。\n"
             "**字段含义**：Sheet 数 = 工作簿中 sheet 总数；Issues = 所有校验问题数（含警告）；"
             "Errors = 高严重性问题（需优先处理）。")
    st.subheader("Workbook 概览")
    col1, col2, col3 = st.columns(3)
    col1.metric("Sheet 数", len(sheet_names))
    col2.metric("Issues", len(issues))
    col3.metric("Errors", sum(1 for i in issues if i.severity == "error"))

    st.divider()

    st.subheader("数据健康/校验报告")
    df_issues = issues_to_dataframe(issues)
    st.dataframe(df_issues, use_container_width=True, height=360)

    csv = df_issues.to_csv(index=False).encode("utf-8")
    st.download_button(
        "下载 data_validation_report.csv",
        data=csv,
        file_name="data_validation_report.csv",
        mime="text/csv",
    )

with tab2:
    st.info("📌 **功能说明**：查看所有上线 SKU 的毛利数据，支持出厂/门店双口径切换。\n"
             "**使用方法**：选择口径和状态过滤，查看毛利表；切换 Tab 查看成本瀑布或目标成本反推。\n"
             "**字段含义**：price=定价；cost=出厂成本；store_cost=门店成本；gross_profit=毛利额；"
             "gross_margin=毛利率（%）。")
    st.subheader("SKU 毛利分析（双口径）")
    st.caption("口径说明：出厂口径=定价-成本；门店口径=定价-门店成本（以产品毛利表为数据源）。")

    basis = st.radio(
        "选择口径",
        options=["factory", "store"],
        format_func=lambda x: "出厂口径" if x == "factory" else "门店口径",
        horizontal=True,
    )
    status_only = st.selectbox("状态过滤", options=["(全部)", "上线", "下线"], index=1)
    only_status = None if status_only == "(全部)" else status_only

    df_profit = sku_profit_table(wb.sheets, basis=basis, only_status=only_status)
    if df_profit.empty:
        st.warning("未找到可分析的 产品毛利表_* 数据（或当前工作簿缺少对应 sheet）。")
    else:
        show = df_profit.copy()
        show["gross_profit"] = show["gross_profit"].round(2)
        show["gross_margin"] = (show["gross_margin"] * 100).round(2)
        show["workbook_margin"] = (show["workbook_margin"] * 100).round(2)
        show["margin_delta"] = (show["margin_delta"] * 100).round(2)

        st.dataframe(
            show,
            use_container_width=True,
            height=380,
            column_config={
                "gross_profit": st.column_config.NumberColumn("gross_profit(元)"),
                "gross_margin": st.column_config.NumberColumn("gross_margin(%)"),
                "workbook_margin": st.column_config.NumberColumn("workbook_margin(%)"),
                "margin_delta": st.column_config.NumberColumn("delta(pp)"),
            },
        )

        st.divider()
        st.markdown("#### F-002 验收 Oracle（与 Excel 交叉验证）")
        stats_df, top_df = margin_delta_report(df_profit, top_n=20)
        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.caption("按品类统计的毛利率绝对偏差（百分点）")
            st.dataframe(stats_df.round(4), use_container_width=True, height=220)
        with col_b:
            top_show = top_df.copy()
            if not top_show.empty:
                top_show["gross_profit"] = top_show["gross_profit"].round(2)
                top_show["gross_margin"] = (top_show["gross_margin"] * 100).round(2)
                top_show["workbook_margin"] = (top_show["workbook_margin"] * 100).round(2)
                top_show["margin_delta"] = (top_show["margin_delta"] * 100).round(2)
                top_show["abs_margin_delta_pp"] = top_show["abs_margin_delta_pp"].round(4)
            st.caption("Top-N 偏差最大的 SKU")
            st.dataframe(top_show, use_container_width=True, height=220)

        st.download_button(
            "下载 F-002 Top 偏差 CSV",
            data=top_df.to_csv(index=False).encode("utf-8"),
            file_name="f002_margin_delta_top.csv",
            mime="text/csv",
        )

        st.divider()
        st.markdown("#### 成本瀑布（Best-effort）")
        pick = st.selectbox("选择一个 SKU (ProductKey)", options=show["product_key"].tolist())
        breakdown = sku_cost_breakdown(wb.sheets, product_key=pick, basis=basis)
        if breakdown.empty:
            st.info("该 SKU 暂无出品表成本明细（或缺少 产品出品表_* / 总成本 列）。")
        else:
            st.dataframe(breakdown, use_container_width=True, height=240)
            agg = breakdown.groupby("bucket", as_index=False)["cost"].sum().sort_values("cost", ascending=False)
            st.bar_chart(agg.set_index("bucket")["cost"])

            st.divider()
            st.markdown("#### F-003 目标毛利率反推原料定价（第一版）")
            default_margin = 72 if basis == "store" else 80
            target_margin_pct = st.slider("目标毛利率(%)", min_value=1, max_value=99, value=default_margin)
            lock_candidates = breakdown["item"].dropna().astype(str).tolist()
            locked_items = st.multiselect("锁定不参与调整的原料/项目", options=lock_candidates)

            pricing_df = suggest_adjustable_item_costs(
                wb.sheets,
                product_key=pick,
                target_margin_rate=target_margin_pct / 100.0,
                basis=basis,
                locked_items=locked_items,
            )
            if pricing_df.empty:
                st.info("当前无法生成反推定价建议（可能缺少价格/成本/成本明细）。")
            else:
                display_cols = [
                    "item",
                    "bucket",
                    "cost",
                    "is_fixed",
                    "is_locked",
                    "is_adjustable",
                    "suggested_cost_ideal",
                    "suggested_cost_acceptable",
                    "suggested_cost_redline",
                ]
                st.dataframe(pricing_df[display_cols], use_container_width=True, height=260)
                st.download_button(
                    "下载 F-003 反推定价 CSV",
                    data=pricing_df.to_csv(index=False).encode("utf-8"),
                    file_name="f003_target_pricing.csv",
                    mime="text/csv",
                )

with tab3:
    st.info("📌 **功能说明**：浏览工作簿中任意 sheet 的原始数据。\n"
             "**使用方法**：下拉选择 sheet 名称，查看行列数据。\n"
             "**字段含义**：Rows=数据行数；Cols=列数；表格内容即对应 sheet 的原始数据。")
    st.subheader("Sheet 浏览")
    selected = st.selectbox("选择 sheet", sheet_names)
    df = wb.sheets[selected]
    st.write(f"Rows: {df.shape[0]} | Cols: {df.shape[1]}")
    st.dataframe(df.head(200), use_container_width=True, height=420)

# ── Tab4: 原料价格模拟器 ───────────────────────────────────────────────

store: ScenarioStore = st.session_state["sim_store"]

with tab4:
    st.info("📌 **功能说明**：调整原料单价，实时预览毛利变化，保存调价版本并与基准对比。\n"
             "**使用方法**：选择或新建版本 → 添加调价原料+新单价 → 保存 → 与其他版本对比。\n"
             "**字段含义**：原料=来自总原料成本表；新单价=调整后的采购价；"
             "高风险=SKU 调整后毛利<0（标红）。")
    st.subheader("原料价格模拟器（F-004）")
    st.caption("调整原料单价 → 实时重算毛利 → 保存版本 → 对比任意两版本差异")

    # ── Version management ──────────────────────────────────────────
    existing = store.list_names()
    default_choice = "（新建版本）"
    choice = st.selectbox("选择版本", [default_choice] + existing)
    version_name = st.text_input("新版本名称").strip() if choice == default_choice else choice

    current = store.get(version_name) if version_name else None
    adj_items = [(a.item, a.new_unit_price) for a in current.adjustments] if current else []

    # Build ingredient list
    raw_df = wb.sheets.get("总原料成本表")
    price_col = next((c for c in raw_df.columns if "单价" in c), None) if raw_df is not None else None
    name_col = next((c for c in raw_df.columns if "品项名称" in c), None) if raw_df is not None else None
    ingredient_options = (
        sorted({str(r.get(name_col, "")).strip() for *_, r in raw_df.iterrows() if str(r.get(name_col, "")).strip()})
        if raw_df is not None and price_col and name_col else []
    )

    # ── Adjustment editor ────────────────────────────────────────────
    st.markdown("##### 调价明细")
    n = st.number_input("调价原料数", min_value=0, max_value=20, value=len(adj_items), step=1)
    adjustments: List[MaterialPriceAdjustment] = []
    for i in range(int(n)):
        col1, col2 = st.columns([3, 1])
        item_name = col1.selectbox(
            f"原料 #{i+1}", options=ingredient_options,
            index=ingredient_options.index(adj_items[i][0]) if i < len(adj_items) and adj_items[i][0] in ingredient_options else 0,
        )
        new_price = col2.number_input("新单价", value=adj_items[i][1] if i < len(adj_items) else 0.0, step=0.01, format="%.4f", key=f"sim_price_{i}")
        if item_name and new_price > 0:
            adjustments.append(MaterialPriceAdjustment(item=item_name, new_unit_price=new_price))

    sim_basis = st.radio("口径", ["store", "factory"], format_func=lambda x: "门店口径" if x == "store" else "出厂口径", horizontal=True)

    # Save / clear
    col_save, col_clear, col_clear2 = st.columns([1, 1, 2])
    with col_save:
        save_disabled = not (version_name and adjustments)
        save_label = "💾 保存"
        if version_name and version_name in existing and choice != default_choice:
            save_label = "⚠️ 覆盖保存"
        if col_save.button(save_label, disabled=save_disabled):
            store.put(Scenario(name=version_name, adjustments=tuple(adjustments)))
            st.success(f"已保存版本：{version_name}")
            _auto_save()
            st.rerun()
    with col_clear:
        confirm_clear = st.checkbox("确认清空？", value=False, key="clear_confirm_chk")
    with col_clear2:
        if col_clear2.button("🗑 清空所有版本", disabled=not (confirm_clear and existing)):
            store.clear()
            st.success("已清空所有版本")
            st.rerun()

    # ── Comparison ──────────────────────────────────────────────────
    st.divider()
    st.markdown("##### 版本对比")
    names = store.list_names()
    if len(names) >= 2:
        c_a, c_b = st.columns(2)
        with c_a:
            va = st.selectbox("版本 A", names, key="cmp_a")
        with c_b:
            vb = st.selectbox("版本 B", names, index=min(1, len(names)-1), key="cmp_b")
        compare_disabled = va == vb
        if compare_disabled:
            st.info("请选择两个不同的版本进行对比")
        if st.button("🔍 对比两版本", disabled=compare_disabled):
            s_a, s_b = store.get(va), store.get(vb)
            if s_a and s_b:
                diff = compare_scenarios(s_a, s_b, wb.sheets, basis=sim_basis)
                st.dataframe(diff, use_container_width=True, height=420)
                st.download_button(f"下载 {va}_vs_{vb}.csv", data=diff.to_csv(index=False).encode("utf-8"),
                                   file_name=f"sim_{va}_vs_{vb}.csv", mime="text/csv")
    elif len(names) == 1:
        s1 = store.get(names[0])
        if s1:
            st.markdown(f"**{names[0]}** vs 基准（原始数据）")
            diff = compare_scenarios(Scenario(name="基准", adjustments=()), s1, wb.sheets, basis=sim_basis)
            st.dataframe(diff, use_container_width=True, height=420)
            st.download_button(f"下载 {names[0]}_vs_baseline.csv", data=diff.to_csv(index=False).encode("utf-8"),
                               file_name=f"sim_{names[0]}_vs_baseline.csv", mime="text/csv")
    else:
        st.info("保存至少一个版本后即可进行对比分析。")

    # List saved versions
    if names:
        st.divider()
        st.markdown("##### 已保存版本")
        for nm in names:
            sc = store.get(nm)
            adj_list = [f"{a.item} → {a.new_unit_price}" for a in (sc.adjustments if sc else [])]
            st.markdown(f"**{nm}**（{len(adj_list)} 项调价）：{', '.join(adj_list) if adj_list else '（无调整）'}")

# ── Tab5: 产销计划 ────────────────────────────────────────────────────

# Build SKU list from workbook for dropdown
_profit_df = sku_profit_table(wb.sheets, basis="factory", only_status=None)
_all_skus = sorted(_profit_df["product_key"].dropna().unique().tolist())

# Production SKU pool: 配方表品名 + 配方表配料 + 出品表配料
_production_skus_list: list[str] = []
for _sname in wb.sheets:
    if "产品配方表" in _sname or "半成品配方表" in _sname:
        _df = wb.sheets[_sname]
        for _col in ("品名", "配料"):
            if _col in _df.columns:
                for _v in _df[_col].dropna().unique():
                    _v_str = str(_v).strip()
                    if _v_str and _v_str not in ("nan", "") and _v_str not in _production_skus_list:
                        _production_skus_list.append(_v_str)
    elif "产品出品表" in _sname:
        _df = wb.sheets[_sname]
        if "配料" in _df.columns:
            for _v in _df["配料"].dropna().unique():
                _v_str = str(_v).strip()
                if _v_str and _v_str not in ("nan", "") and _v_str not in _production_skus_list:
                    _production_skus_list.append(_v_str)
_production_skus = sorted(_production_skus_list)


def _parse_date(s) -> Optional[date]:
    if s is None:
        return None
    if isinstance(s, date):
        return s
    s = str(s).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except Exception:
        try:
            return pd.to_datetime(s).date()
        except Exception:
            return None


def _date_str(d: Optional[date]) -> str:
    """Convert date to YYYY-MM-DD string for display/storage."""
    if d is None:
        return ""
    return d.strftime("%Y-%m-%d")


def _init_session():
    if "production_plans" not in st.session_state:
        st.session_state["production_plans"] = {}  # Dict[str, List[ProductionRow]]
    if "current_plan_name" not in st.session_state:
        st.session_state["current_plan_name"] = None


with tab5:
    st.info("📌 **功能说明**：① 录入销售计划 → ② 生成生产计划 → ③ 展开 BOM 计算原料需求 → ④ 成本核算。\n"
             "**使用方法**：从上至下按步骤操作。\n"
             "**销售SKU**=产品毛利表成品；**生产项**=配方中的冰激淋基底。")
    _init_session()
    plans: dict = st.session_state["production_plans"]
    SALES_KEY = "销售计划_当前"
    PROD_KEY = "生产计划_当前"

    # ════════════════════════════════════════════════════════════════════
    # Step 1: 销售计划录入
    # ════════════════════════════════════════════════════════════════════
    st.subheader("📋 Step 1: 销售计划录入")
    st.caption("录入成品销售预测 — SKU 来自产品毛利表")
    _saved_sales_msg = st.session_state.pop("_msg_sales_saved", None)
    if _saved_sales_msg:
        st.success(_saved_sales_msg)

    col_s1, col_s2 = st.columns([1, 2])
    with col_s1:
        st.download_button(
            "📥 模板(销售)",
            data=pd.DataFrame([{"日期": "2026-04-24", "SKU": "Gelato|榛子巧克力布朗尼|小杯", "数量": 36}]).to_csv(index=False).encode("utf-8-sig"),
            file_name="sales_plan_template.csv", mime="text/csv", key="sales_tmpl",
        )
    with col_s2:
        reset_both = st.button("🔄 重置销售计划和生产计划", use_container_width=True, key="reset_both")

    # CSV upload: sales
    csv_sales = st.file_uploader("📤 上传销售计划（CSV / Excel）", type=[".csv", ".xlsx"], key="csv_sales")
    if csv_sales:
        _sid = f"{csv_sales.name}_{csv_sales.size}"
        if st.session_state.get("_csv_sales_id") != _sid:
            try:
                fname = csv_sales.name.lower()
                if fname.endswith(".xlsx"):
                    import_df = pd.read_excel(csv_sales, dtype=object)
                elif fname.endswith(".csv"):
                    import_df = pd.read_csv(csv_sales, encoding="utf-8-sig")
                else:
                    st.error(f"不支持的文件格式，请上传 .csv 或 .xlsx 文件")
                    st.session_state["_csv_sales_id"] = _sid
                    st.rerun()
                if {"日期", "SKU", "数量"}.issubset(set(import_df.columns)):
                    imported = []
                    for _, r in import_df.iterrows():
                        d = _date_str(_parse_date(r["日期"]))
                        if not d: continue
                        imported.append(ProductionRow(
                            date=d, sku_key=str(r["SKU"]) if pd.notna(r["SKU"]) else "",
                            spec="",
                            qty=float(r["数量"]) if pd.notna(r["数量"]) else 0, plan_type="sales",
                        ))
                    plans[SALES_KEY] = imported
                    st.session_state["_csv_sales_id"] = _sid
                    st.session_state["_csv_import_msg"] = f"✅ 导入 {len(imported)} 行销售计划"
                    _auto_save()
                    st.rerun()
                else:
                    st.error("CSV 需要列: 日期, SKU, 数量")
            except Exception as e:
                st.error(f"读取 CSV 失败: {e}")

    _csv_msg = st.session_state.pop("_csv_import_msg", None)
    if _csv_msg:
        st.success(_csv_msg)

    # Sales editor — always reads/writes SALES_KEY
    sales_rows = plans.get(SALES_KEY, [])
    sales_default = [{"日期": r.date, "SKU": r.sku_key, "数量": r.qty}
                     for r in sales_rows if r.plan_type == "sales"]
    if reset_both:
        sales_default = []
        plans.pop(PROD_KEY, None)
    while len(sales_default) < 5:
        sales_default.append({"日期": "", "SKU": "", "数量": 0})

    edited_sales = st.data_editor(
        pd.DataFrame(sales_default), num_rows="dynamic", use_container_width=True,
        height=300,
        column_config={
            "日期": st.column_config.TextColumn("日期", required=True),
            "SKU": st.column_config.SelectboxColumn("SKU", options=_all_skus),
            "数量": st.column_config.NumberColumn("数量", min_value=0, format="%d"),
        },
        key="sales_editor",
    )

    if st.button("✅ 保存销售计划", type="primary", key="save_sales", use_container_width=True):
        rows = []
        for _, row in edited_sales.iterrows():
            d = _date_str(_parse_date(row["日期"]))
            if not d: continue
            rows.append(ProductionRow(
                date=d, sku_key=str(row["SKU"]) if pd.notna(row["SKU"]) else "",
                spec="",
                qty=float(row["数量"]) if pd.notna(row["数量"]) else 0, plan_type="sales",
            ))
        plans[SALES_KEY] = rows
        _auto_save()
        st.session_state["_msg_sales_saved"] = f"✅ 已保存销售计划（{len(rows)} 行）"
        st.rerun()

    # ════════════════════════════════════════════════════════════════════
    # Step 2: 生产计划
    # ════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("🏭 Step 2: 生产计划")
    st.caption("从销售计划生成后可直接编辑，也可手动录入调整")

    col_g1, col_g2, col_g3 = st.columns([1, 1, 2])
    lead_days = st.number_input("备货提前天数", min_value=0, max_value=30, value=1, key="lead_days")
    gen_clicked = st.button("🚀 从销售计划生成生产计划", type="primary", use_container_width=True, key="gen_btn")

    # Track generation version to force data_editor re-render
    if "prod_gen_version" not in st.session_state:
        st.session_state["prod_gen_version"] = 0

    if gen_clicked:
        sales_rows = plans.get(SALES_KEY, [])
        if not sales_rows:
            st.warning("请先录入并保存销售计划")
        else:
            # Warn if any sales rows lack spec (neither in SKU nor spec field)
            no_spec_rows = [r for r in sales_rows if len(r.sku_key.split("|")) < 3 and not r.spec]
            if no_spec_rows:
                st.warning(f"⚠️ {len(no_spec_rows)} 行销售计划缺少规格信息（SKU 中无「|规格」且「规格」列为空），"
                           f"可能匹配多个出品规格导致数量偏高。建议补充规格后重新生成。")
            with st.spinner("根据配方展开生产计划…"):
                prod_rows = sales_to_production(sales_rows, wb.sheets, lead_days=lead_days)
            if prod_rows:
                plans[PROD_KEY] = prod_rows
                st.session_state["prod_gen_version"] += 1
                _auto_save()
                st.success(f"✅ 已生成生产计划（{len(prod_rows)} 行），可直接在下表编辑")
            else:
                st.warning("无法展开为生产计划（销售 SKU 缺少配方数据）")

    _saved_prod_msg = st.session_state.pop("_msg_prod_saved", None)
    if _saved_prod_msg:
        st.success(_saved_prod_msg)

    # Production editor — always reads/writes PROD_KEY (generated or manually saved)
    prod_rows = plans.get(PROD_KEY, [])
    prod_data_rows = [{"日期": r.date, "生产项": r.sku_key, "数量": r.qty}
                      for r in prod_rows if r.plan_type == "production"]
    if not prod_data_rows:
        st.info("👆 先在「销售计划录入」中输入并保存销售计划，然后点击「从销售计划生成生产计划」。也可在此直接编辑录入。")
    while len(prod_data_rows) < 5:
        prod_data_rows.append({"日期": "", "生产项": "", "数量": 0})

    edited_prod = st.data_editor(
        pd.DataFrame(prod_data_rows), num_rows="dynamic", use_container_width=True,
        height=300,
        column_config={
            "日期": st.column_config.TextColumn("日期", required=True),
            "生产项": st.column_config.SelectboxColumn("生产项", options=_production_skus),
            "数量": st.column_config.NumberColumn("数量", min_value=0, format="%d"),
        },
        key=f"prod_editor_v{st.session_state['prod_gen_version']}",
    )

    if st.button("💾 保存生产计划", type="primary", use_container_width=True, key="save_prod"):
            rows = []
            for _, row in edited_prod.iterrows():
                d = _date_str(_parse_date(row["日期"]))
                if not d: continue
                rows.append(ProductionRow(
                    date=d, sku_key=str(row["生产项"]) if pd.notna(row["生产项"]) else "",
                    spec="", qty=float(row["数量"]) if pd.notna(row["数量"]) else 0,
                    plan_type="production",
                ))
            plans[PROD_KEY] = rows
            _auto_save()
            st.session_state["_msg_prod_saved"] = f"✅ 已保存生产计划（{len(rows)} 行）"
            st.rerun()

    # ════════════════════════════════════════════════════════════════════
    # ════════════════════════════════════════════════════════════════════
    # Step 3: BOM 展开 — 原料需求计算
    # ════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("🔍 Step 3: BOM 展开 — 原料需求计算")
    st.caption("三级展开：SKU → 主原料/配料 → 原料；支持损耗率、最小采购单位、批次取整、提前期。")

    col_bom1, col_bom2, col_bom3, col_bom4 = st.columns([2, 1, 1, 2])
    with col_bom1:
        bom_lead_days = st.number_input(
            "提前期（天）", min_value=0, max_value=90, value=3, key="bom_lead_days"
        )
    with col_bom2:
        bom_loss_rate = st.number_input(
            "损耗率（%）", min_value=0, max_value=100, value=0, key="bom_loss_rate"
        ) / 100.0
    with col_bom3:
        bom_basis_opts = ["store", "factory"]
        bom_basis_label = {"store": "门店(加价后单价)", "factory": "出厂(加价前单价)"}
        bom_basis = st.selectbox(
            "单价口径", options=bom_basis_opts,
            format_func=lambda x: bom_basis_label[x], key="bom_basis",
        )
    with col_bom4:
        st.write("")
        st.write("")
        run_expand = st.button("🔍 展开 BOM", type="primary", use_container_width=True, key="run_bom")

    col_bom_date1, col_bom_date2 = st.columns([1, 1])
    with col_bom_date1:
        bom_start = st.date_input("开始日期", value=None, key="bom_start")
    with col_bom_date2:
        bom_end = st.date_input("结束日期", value=None, key="bom_end")

    # ── Expand logic ──
    bom_result = st.session_state.get("_bom_result")
    bom_elapsed = st.session_state.get("_bom_elapsed")

    if run_expand:
        bom_rows: List[ProductionRow] = plans.get(PROD_KEY, [])
        if not bom_rows:
            st.info("请先完成 Step 2 生成生产计划。")
        else:
            start_dt = bom_start
            end_dt = bom_end
            filtered = []
            for r in bom_rows:
                rdate = _parse_date(r.date)
                if rdate is None:
                    filtered.append(r)
                    continue
                if start_dt and rdate < start_dt:
                    continue
                if end_dt and rdate > end_dt:
                    continue
                filtered.append(r)

            if not filtered:
                st.info("日期范围内无数据。")
            else:
                sku_qty: Dict[str, float] = {}
                for r in filtered:
                    k = str(r.sku_key).strip()
                    if k:
                        sku_qty[k] = sku_qty.get(k, 0.0) + float(r.qty)

                target_date: Optional[date] = end_dt
                with st.spinner("BOM 展开中…"):
                    t0 = datetime.now()
                    result = bom_expand_multi(
                        wb.sheets, sku_qty,
                        order_date=target_date, basis=bom_basis,
                        default_lead_days=bom_lead_days,
                        default_loss_rate=bom_loss_rate,
                        default_safety_stock=0.0,
                    )
                    elapsed = (datetime.now() - t0).total_seconds()
                st.success(f"展开完成，耗时 {elapsed:.2f}s")
                st.session_state["_bom_result"] = result
                st.session_state["_bom_elapsed"] = elapsed
                bom_result = result
                bom_elapsed = elapsed

    if bom_result is not None and not bom_result.empty:
        inner_tab_a, inner_tab_b, inner_tab_c = st.tabs(
            ["📦 原料需求汇总", "⚠️ 缺口预警", "📊 统计概览"]
        )

        with inner_tab_a:
            st.markdown("#### 原料需求汇总表")
            display_cols = [
                "material", "level", "purchase_unit", "lead_days",
                "total_plan_qty", "total_gross_qty", "total_purchase_qty",
                "unit_price", "total_cost", "is_gap", "gap_reason",
                "is_semi_finished",
            ]
            display = bom_result[display_cols].copy()
            display["is_gap"] = display["is_gap"].map(
                lambda x: "⚠️ 缺口" if x else "✅ 正常"
            )
            st.dataframe(
                display, use_container_width=True, height=500,
                column_config={
                    "material": st.column_config.TextColumn("原料名称"),
                    "level": st.column_config.TextColumn("层级"),
                    "purchase_unit": st.column_config.TextColumn("采购单位"),
                    "lead_days": st.column_config.NumberColumn("提前期(天)"),
                    "total_plan_qty": st.column_config.NumberColumn("计划用量", format="%.2f"),
                    "total_gross_qty": st.column_config.NumberColumn("总需求(含损耗)", format="%.2f"),
                    "total_purchase_qty": st.column_config.NumberColumn("建议采购量", format="%.2f"),
                    "unit_price": st.column_config.NumberColumn("单价(元)", format="%.4f"),
                    "total_cost": st.column_config.NumberColumn("采购成本(元)", format="%.2f"),
                    "is_gap": st.column_config.TextColumn("状态"),
                    "gap_reason": st.column_config.TextColumn("缺口原因"),
                    "is_semi_finished": st.column_config.TextColumn("是否半成品"),
                },
            )
            csv_data = bom_result.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "📥 下载原料需求 CSV", data=csv_data,
                file_name="bom_material_demand.csv", mime="text/csv",
            )

        with inner_tab_b:
            st.markdown("#### 缺口预警（无有效单价 / 供应不稳定）")
            gaps = gaps_only(bom_result)
            if gaps.empty:
                st.success("✅ 所有原料均有有效单价且供应稳定")
            else:
                gap_display = gaps[[
                    "material", "gap_reason", "total_purchase_qty",
                    "unit_price", "is_semi_finished",
                ]].copy()
                st.warning(f"发现 {len(gaps)} 个缺口项：")
                st.dataframe(gap_display, use_container_width=True, height=400)

        with inner_tab_c:
            st.markdown("#### 统计概览")
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
            col_stat1.metric("原料种类", len(bom_result))
            col_stat2.metric("总采购成本(元)", f"{bom_result['total_cost'].sum():.2f}")
            col_stat3.metric("半成品种类", int(bom_result["is_semi_finished"].sum()))
            col_stat4.metric("缺口数量", int(bom_result["is_gap"].sum()))

            if not bom_result["total_cost"].isna().all():
                by_level = (
                    bom_result.groupby("level")
                    .agg({"material": "count", "total_purchase_qty": "sum", "total_cost": "sum"})
                    .rename(columns={"material": "原料种类数"})
                )
                st.markdown("##### 按层级统计")
                st.dataframe(by_level, use_container_width=True)

        # ════════════════════════════════════════════════════════════════════
        # Step 4: 成本核算概览
        # ════════════════════════════════════════════════════════════════════
        st.divider()
        st.subheader("💰 Step 4: 成本核算概览")
        total_cost = bom_result["total_cost"].sum()
        total_purchase = bom_result["total_purchase_qty"].sum()
        material_count = len(bom_result)
        semi_count = int(bom_result["is_semi_finished"].sum())
        gap_count = int(bom_result["is_gap"].sum())

        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        col_c1.metric("原料种类", material_count)
        col_c2.metric("总原料成本(元)", f"{total_cost:.2f}")
        col_c3.metric("半成品种类", semi_count)
        col_c4.metric("缺口数", gap_count)

        # Cost breakdown by category (semi-finished vs raw)
        st.markdown("##### 成本构成")
        cost_by_type = bom_result.groupby("is_semi_finished").agg(
            原料数=("material", "count"),
            采购量=("total_purchase_qty", "sum"),
            成本=("total_cost", "sum"),
        ).reset_index()
        cost_by_type["类型"] = cost_by_type["is_semi_finished"].map({True: "半成品", False: "原料"})
        st.dataframe(cost_by_type[[
            "类型", "原料数", "采购量", "成本"
        ]].style.format({
            "采购量": "{:.2f}", "成本": "{:.2f}",
        }), use_container_width=True)

    elif run_expand and bom_result is not None and bom_result.empty:
        st.info("BOM 展开结果为空（可能选中的 SKU 在出品表中无配料数据）。")
    else:
        st.info("👆 完成 Step 2 后，在上方设置参数并点击「展开 BOM」，查看原料需求与成本。")

# ── Tab6: 产品组合评估 ─────────────────────────────────────────────────

# Build SKU list once
_all_skus_for_portfolio = sorted(_profit_df["product_key"].dropna().unique().tolist())


def _init_portfolio_session():
    """Initialize session-state slots for portfolio A/B/C."""
    for slot in ("portfolio_A", "portfolio_B", "portfolio_C"):
        if slot not in st.session_state:
            st.session_state[slot] = {}  # {sku_key: qty}


with tab6:
    st.info("📌 **功能说明**：多选产品+填数量，实时计算总销售额/成本/毛利/净利/原料种类/产能压力。\n"
             "**使用方法**：multiselect 选 SKU → 填数量 → 切换口径 → 实时查看 KPI；保存方案 A/B/C 后可对比。\n"
             "**字段含义**：Revenue=定价×数量；Gross_profit=毛利额；Capacity_pressure=产能压力评分（0-100）；"
             "material_variety=SKU 涉及的不同原料种类数。")
    _init_portfolio_session()

    st.subheader("产品组合评估（实时联动）")
    st.caption(
        "选品 + 填数量，实时计算总销售额 / 成本 / 毛利 / 净利 / 原料种类 / 产能压力。"
        "方案 A / B / C 保存后支持对比分析。"
    )

    # ── Controls row ───────────────────────────────────────────────
    col_ctl1, col_ctl2 = st.columns([3, 1])

    with col_ctl1:
        selected_skus = st.multiselect(
            "选择产品（可多选）",
            options=_all_skus_for_portfolio,
            default=[],
            placeholder="从毛利表选取 SKU...",
            key="portfolio_sku_multiselect",
        )

    with col_ctl2:
        basis_portfolio = st.radio(
            "口径",
            options=["factory", "store"],
            format_func=lambda x: "出厂口径" if x == "factory" else "门店口径",
            horizontal=True,
            key="portfolio_basis_radio",
        )

    # ── Quantity inputs ─────────────────────────────────────────────
    if selected_skus:
        st.markdown("##### 设置各 SKU 数量")
        # Build columns: 3 per row
        n_cols = 3
        rows_needed = (len(selected_skus) + n_cols - 1) // n_cols
        qty_values: Dict[str, float] = {}

        for row_idx in range(rows_needed):
            cols = st.columns(n_cols)
            for col_idx in range(n_cols):
                sku_idx = row_idx * n_cols + col_idx
                if sku_idx >= len(selected_skus):
                    break
                sku_key = selected_skus[sku_idx]
                # Try to restore from last saved session
                default_val = st.session_state.get(f"_last_qty_{sku_key}", 1)
                qty = cols[col_idx].number_input(
                    f"{sku_key.split('|')[1] if '|' in sku_key else sku_key}",
                    min_value=0.0,
                    value=float(default_val),
                    step=1.0,
                    key=f"portfolio_qty_{sku_key}",
                )
                qty_values[sku_key] = qty

        # ── KPI cards ────────────────────────────────────────────────
        st.divider()
        st.markdown("##### 实时 KPI")

        # Evaluate live
        live_scenario = PortfolioScenario(
            name="当前方案",
            selections=tuple(sorted(qty_values.items())),
        )
        live_result = evaluate_portfolio(live_scenario, wb.sheets, basis=basis_portfolio)

        kpi_col1, kpi_col2, kpi_col3, kpi_col4, kpi_col5, kpi_col6 = st.columns(6)
        kpi_col1.metric("总销售额(元)", f"{live_result.total_revenue:,.2f}")
        kpi_col2.metric("总成本(元)", f"{live_result.total_cost:,.2f}")
        kpi_col3.metric("总毛利(元)", f"{live_result.total_profit:,.2f}")
        margin_str = (
            f"{live_result.total_margin * 100:.2f}%"
            if live_result.total_margin is not None
            else "N/A"
        )
        kpi_col4.metric("毛利率", margin_str)
        kpi_col5.metric("原料种类", live_result.material_variety)
        kpi_col6.metric("产能压力", f"{live_result.capacity_pressure}/100")

        # Save scenario buttons
        st.divider()
        col_save_a, col_save_b, col_save_c, col_sku_count = st.columns(4)
        with col_save_a:
            if st.button("💾 保存为方案 A", key="save_portfolio_A"):
                st.session_state["portfolio_A"] = dict(qty_values)
                # Persist last qty for restore
                for k, v in qty_values.items():
                    st.session_state[f"_last_qty_{k}"] = v
                st.success("✅ 方案 A 已保存")
                _auto_save()

        with col_save_b:
            if st.button("💾 保存为方案 B", key="save_portfolio_B"):
                st.session_state["portfolio_B"] = dict(qty_values)
                for k, v in qty_values.items():
                    st.session_state[f"_last_qty_{k}"] = v
                st.success("✅ 方案 B 已保存")
                _auto_save()

        with col_save_c:
            if st.button("💾 保存为方案 C", key="save_portfolio_C"):
                st.session_state["portfolio_C"] = dict(qty_values)
                for k, v in qty_values.items():
                    st.session_state[f"_last_qty_{k}"] = v
                st.success("✅ 方案 C 已保存")
                _auto_save()

        with col_sku_count:
            st.metric("SKU 数量", live_result.sku_count)

    else:
        st.info("👆 从上方多选产品开始，输入数量即可实时查看 KPI。")

    # ── Saved scenarios quick-view ──────────────────────────────────
    st.divider()
    st.markdown("##### 已保存方案概览")
    saved_rows = []
    for slot_key, label in [("portfolio_A", "方案A"), ("portfolio_B", "方案B"), ("portfolio_C", "方案C")]:
        saved = st.session_state.get(slot_key, {})
        if saved:
            scenario = PortfolioScenario.from_dict(label, saved)
            result = evaluate_portfolio(scenario, wb.sheets, basis=basis_portfolio)
            saved_rows.append(result)
        else:
            saved_rows.append(None)

    saved_labels = [("portfolio_A", "方案A"), ("portfolio_B", "方案B"), ("portfolio_C", "方案C")]
    for (slot_key, label), result in zip(saved_labels, saved_rows):
        saved = st.session_state.get(slot_key, {})
        if not saved:
            continue
        with st.expander(f"📋 {label}（{len(saved)} 个 SKU）", expanded=False):
            sku_lines = "\n".join(f"  - {k.split('|')[1] if '|' in k else k}: {v} 件" for k, v in saved.items())
            st.markdown(f"```\n{sku_lines}\n```")
            if result:
                st.write(
                    f"💰 销售额: {result.total_revenue:,.2f} | "
                    f"毛利: {result.total_profit:,.2f} | "
                    f"毛利率: {'{:.2f}%'.format(result.total_margin * 100) if result.total_margin else 'N/A'} | "
                    f"产能压力: {result.capacity_pressure}/100"
                )

    # ── Comparison view ──────────────────────────────────────────────
    valid_results = [r for r in saved_rows if r is not None]
    if len(valid_results) >= 2:
        st.divider()
        st.markdown("##### 多方案对比")
        compare_df = compare_portfolios(valid_results)

        # Display base results
        base_display = compare_df[~compare_df["name"].str.contains(" vs ", na=False)].copy()
        base_display["total_margin_pct"] = base_display["total_margin_pct"].apply(
            lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A"
        )
        st.dataframe(base_display, use_container_width=True, height=200)

        # Display diffs
        diff_df = compare_df[compare_df["name"].str.contains(" vs ", na=False)].copy()
        if not diff_df.empty:
            st.markdown("**差异（相对于第一个方案）**")
            diff_df["total_margin_pct"] = diff_df["total_margin_pct"].apply(
                lambda x: f"{'+' if pd.notna(x) and x >= 0 else ''}{x:.2f}%" if pd.notna(x) else "N/A"
            )
            st.dataframe(diff_df, use_container_width=True, height=120)

        st.download_button(
            "📥 下载对比 CSV",
            data=compare_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="portfolio_comparison.csv",
            mime="text/csv",
            key="portfolio_compare_download",
        )


# ── Tab7: 多场景对比 ─────────────────────────────────────────────────


def _init_multi_scenario_session():
    if "ms_scenarios" not in st.session_state:
        st.session_state["ms_scenarios"] = {}  # name -> dict of {sku_key: qty}


with tab7:
    st.info("📌 **功能说明**：创建多组销量假设（A/B/C），对比各方案下的总利润、原料需求、SKU 变动。\n"
             "**使用方法**：新建多个场景并填入 SKU 数量 → 点击「对比场景」→ 查看汇总表+差异表。\n"
             "**字段含义**：total_profit=该方案净利润；material_qty=总原料需求量；"
             "sku_count=方案包含的 SKU 数；diff 表=相对于基准方案的变化量。")
    _init_multi_scenario_session()

    st.subheader("多场景对比（F-010）")
    st.caption("创建多组销量假设（A/B/C），对比各方案下的原料需求 + 利润，输出差异表。")

    ms_scenarios: dict = st.session_state["ms_scenarios"]

    # ── Controls ─────────────────────────────────────────────────────
    col_ms1, col_ms2 = st.columns([3, 1])

    with col_ms1:
        ms_basis = st.radio(
            "口径",
            options=["factory", "store"],
            format_func=lambda x: "出厂口径" if x == "factory" else "门店口径",
            horizontal=True,
            key="ms_basis_radio",
        )

    with col_ms2:
        st.write("")
        st.write("")
        run_compare = st.button("🔍 对比场景", type="primary", use_container_width=True)

    # ── Scenario management ────────────────────────────────────────────
    st.divider()
    st.markdown("##### 场景管理")

    col_mng1, col_mng2, col_mng3 = st.columns([2, 2, 1])
    with col_mng1:
        ms_new_name = st.text_input("新场景名", placeholder="输入名称后保存", key="ms_new_name")
    with col_mng2:
        existing_ms = list(ms_scenarios.keys())
        ms_copy_src = st.selectbox("复制历史场景", options=[""] + existing_ms, key="ms_copy_src")
    with col_mng3:
        st.write("")
        ms_save = st.button("💾 保存", use_container_width=True, key="ms_save_btn")

    if ms_save and ms_new_name:
        src = ms_copy_src
        if src and src in ms_scenarios:
            ms_scenarios[ms_new_name] = dict(ms_scenarios[src])
            st.success(f"已复制场景：{ms_new_name}")
        else:
            if ms_new_name not in ms_scenarios:
                ms_scenarios[ms_new_name] = {}
                st.info(f"已创建场景「{ms_new_name}」，请在下方选择 SKU 并点击「更新」添加数据")
        st.session_state["ms_scenarios"] = ms_scenarios
        st.rerun()

    # ── Edit selected scenario ─────────────────────────────────────────
    if ms_scenarios:
        st.markdown("##### 编辑场景")
        edit_ms = st.selectbox(
            "选择场景",
            options=list(ms_scenarios.keys()),
            key="ms_edit_select",
        )
        current_dict = ms_scenarios.get(edit_ms, {})

        # SKU multiselect from profit table
        ms_pool_keys = sorted(_profit_df["product_key"].dropna().unique().tolist())
        selected_ms_skus = st.multiselect(
            "选择 SKU（多选）",
            options=ms_pool_keys,
            default=[k for k in ms_pool_keys if k in current_dict],
            key="ms_sku_multiselect",
        )

        # Quantity per SKU
        ms_qty_dict: Dict[str, float] = {}
        if selected_ms_skus:
            n_cols = 3
            rows_needed = (len(selected_ms_skus) + n_cols - 1) // n_cols
            for row_idx in range(rows_needed):
                cols = st.columns(n_cols)
                for col_idx in range(n_cols):
                    sku_idx = row_idx * n_cols + col_idx
                    if sku_idx >= len(selected_ms_skus):
                        break
                    sku_key = selected_ms_skus[sku_idx]
                    default_val = current_dict.get(sku_key, 1)
                    qty = cols[col_idx].number_input(
                        f"{sku_key.split('|')[1] if '|' in sku_key else sku_key}",
                        min_value=0.0,
                        value=float(default_val),
                        step=1.0,
                        key=f"ms_qty_{edit_ms}_{sku_key}",
                    )
                    ms_qty_dict[sku_key] = qty

        col_upd1, col_upd2, col_upd3 = st.columns(3)
        with col_upd1:
            if st.button("✅ 更新", key="ms_update_btn"):
                ms_scenarios[edit_ms] = ms_qty_dict
                st.session_state["ms_scenarios"] = ms_scenarios
                st.success(f"已更新：{edit_ms}")
                st.rerun()
        with col_upd2:
            if st.button("🗑 删除场景", key="ms_delete_btn"):
                ms_scenarios.pop(edit_ms, None)
                st.session_state["ms_scenarios"] = ms_scenarios
                st.success(f"已删除：{edit_ms}")
                st.rerun()

    # ── Comparison run ─────────────────────────────────────────────────
    if run_compare:
        if len(ms_scenarios) < 1:
            st.warning("请先创建并保存至少一个场景。")
        else:
            scenarios_to_eval = [
                SalesAssumptionScenario.from_dict(name, dict(sku_dict))
                for name, sku_dict in ms_scenarios.items()
                if sku_dict
            ]
            if len(scenarios_to_eval) < 1:
                st.warning("所有场景的 SKU 数量均为 0，无法对比。")
            else:
                with st.spinner("对比分析中…"):
                    results = evaluate_multi_scenario(scenarios_to_eval, wb.sheets, basis=ms_basis)
                comp_df = multi_scenario_comparison_df(results)
                sku_diff = multi_scenario_diff_table(results)
                # Cache results in session state to survive widget changes
                st.session_state["ms_results"] = results
                st.session_state["ms_comp_df"] = comp_df
                st.session_state["ms_sku_diff"] = sku_diff
                st.session_state["ms_results_basis"] = ms_basis

    # Show cached results (survives widget changes) — invalidate if basis changed
    _ms_show = st.session_state.get("ms_results")
    if _ms_show is not None and st.session_state.get("ms_results_basis") != ms_basis:
        st.session_state.pop("ms_results", None)
        st.session_state.pop("ms_comp_df", None)
        st.session_state.pop("ms_sku_diff", None)
        _ms_show = None

    if _ms_show is not None:
        results = _ms_show
        comp_df = st.session_state["ms_comp_df"]
        sku_diff = st.session_state.get("ms_sku_diff")

        st.divider()
        st.markdown("#### 场景对比汇总")

        # KPI row
        r0 = results[0]
        col_mk1, col_mk2, col_mk3, col_mk4, col_mk5 = st.columns(5)
        col_mk1.metric("场景数", len(results))
        col_mk2.metric("最优利润", f"{max(r.total_profit for r in results):,.2f}元")
        col_mk3.metric(
            "最高毛利率",
            f"{max((r.total_margin or 0)*100 for r in results):.2f}%"
            if results else "N/A",
        )
        col_mk4.metric("最大原料需求", f"{max(r.total_material_qty for r in results):.2f}")
        col_mk5.metric("最优场景", max(results, key=lambda r: r.total_profit).scenario_name)

        # Comparison table
        st.markdown("##### 对比表（绝对值）")
        disp = comp_df[~comp_df["scenario"].str.contains(" vs ", na=False)].copy()
        disp["total_margin_pct"] = disp["total_margin_pct"].apply(
            lambda x: f"{x:.2f}%" if pd.notna(x) else "N/A"
        )
        st.dataframe(disp, use_container_width=True, height=300)

        # Diff table
        diff = comp_df[comp_df["scenario"].str.contains(" vs ", na=False)].copy()
        if not diff.empty:
            st.markdown("##### 差异表（相对于第一个场景）")
            diff["total_margin_pct"] = diff["total_margin_pct"].apply(
                lambda x: f"{'+' if pd.notna(x) and x >= 0 else ''}{x:.2f}%" if pd.notna(x) else "N/A"
            )
            st.dataframe(diff, use_container_width=True, height=200)

        # SKU diff
        if sku_diff is not None and not sku_diff.empty:
            st.markdown("##### SKU 变动明细（qty 跨场景变化的 SKU）")
            st.dataframe(sku_diff, use_container_width=True, height=300)

        # Download
        csv_ms = comp_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 下载场景对比 CSV",
            data=csv_ms,
            file_name="multi_scenario_comparison.csv",
            mime="text/csv",
        )

    if _ms_show is None and not run_compare:
        st.divider()
        st.info(
            "👆 在上方创建并保存场景，然后点击「对比场景」开始分析。\n\n"
            "提示：\n"
            "• 每个场景代表一组不同的销量假设（可复制历史场景快速创建）\n"
            "• 对比表展示各场景的总利润、毛利率、原料需求\n"
            "• 差异表高亮哪些 SKU 数量/利润在不同场景间发生变化"
        )


# ── Tab8: 选品优化器 ─────────────────────────────────────────────────


with tab8:
    st.info("📌 **功能说明**：在给定约束（产能/预算/销量下限）下，枚举所有可行 SKU 组合，返回利润 Top-3 并给出推荐理由。\n"
             "**使用方法**：选择候选 SKU 池 → 设置约束条件 → 点击「运行优化」→ 查看推荐方案。\n"
             "**字段含义**：max_capacity=单品总件数上限；material_budget=原料采购总预算（元）；"
             "min_sales_per_sku=每个 SKU 的最低销量门槛。")
    st.subheader("选品优化器（F-012）")
    st.caption(
        "输入产能 / 原料预算 / 销量下限约束，枚举所有可行组合，"
        "返回利润最高的 Top-3 方案并提供可解释原因。"
    )

    # ── Step 1: Build SKU pool ──────────────────────────────────────
    col_pool1, col_pool2 = st.columns([3, 1])

    with col_pool1:
        basis_opt = st.radio(
            "口径",
            options=["factory", "store"],
            format_func=lambda x: "出厂口径" if x == "factory" else "门店口径",
            horizontal=True,
            key="opt_basis_radio",
        )

    with col_pool2:
        status_filter_opts = ["(全部)", "上线", "下线"]
        status_filter = st.selectbox(
            "状态过滤", options=status_filter_opts, index=0, key="opt_status_filter"
        )

    only_status_opt = None if status_filter == "(全部)" else status_filter
    sku_pool_df = sku_profit_table(wb.sheets, basis=basis_opt, only_status=only_status_opt)

    if sku_pool_df.empty:
        st.warning("SKU 池为空（工作簿中无可用的产品毛利表数据）。")
        st.stop()

    # SKU pool selection (multiselect)
    pool_keys = sorted(sku_pool_df["product_key"].dropna().unique().tolist())
    default_pool = pool_keys[:8]  # pre-select first 8

    st.markdown("##### SKU 候选池（选择参与优化的 SKU）")
    selected_pool_keys = st.multiselect(
        "SKU 候选池",
        options=pool_keys,
        default=[k for k in default_pool if k in pool_keys],
        placeholder="至少选 2 个 SKU...",
        key="opt_sku_pool",
    )

    if len(selected_pool_keys) < 2:
        st.info("👆 请在上方至少选择 2 个 SKU 以开始优化。")
        st.stop()

    # ── Step 2: Constraint inputs ────────────────────────────────────
    st.markdown("##### 约束条件")
    col_c1, col_c2, col_c3 = st.columns(3)

    with col_c1:
        max_capacity = st.number_input(
            "最大产能（总件数）",
            min_value=1,
            max_value=5000,
            value=200,
            step=10,
            key="opt_max_capacity",
        )

    with col_c2:
        material_budget = st.number_input(
            "原料预算（元）",
            min_value=0.0,
            max_value=1_000_000.0,
            value=50000.0,
            step=1000.0,
            format="%.0f",
            key="opt_material_budget",
        )

    with col_c3:
        min_sales_per_sku = st.number_input(
            "单品最低销量（件）",
            min_value=1,
            max_value=100,
            value=1,
            step=1,
            key="opt_min_sales",
        )

    col_e1, col_e2 = st.columns([1, 3])
    with col_e1:
        max_qty_per_sku = st.number_input(
            "单品最大枚举量",
            min_value=1,
            max_value=50,
            value=20,
            step=1,
            key="opt_max_qty",
        )

    with col_e2:
        st.write("")
        st.write("")
        run_optimize = st.button("🚀 运行优化", type="primary", use_container_width=True)

    # ── Step 3: Run / show cached optimization ───────────────────────
    if run_optimize:
        constraints = OptimizationConstraint(
            max_capacity=max_capacity,
            material_budget=material_budget,
            min_sales_per_sku=min_sales_per_sku,
        )
        filtered_pool = sku_pool_df[sku_pool_df["product_key"].isin(selected_pool_keys)].copy()
        with st.spinner(f"枚举中…（候选 SKU {len(filtered_pool)} 个）× {max_qty_per_sku} 个数量级"):
            results = enumerate_portfolios(
                sku_pool=filtered_pool,
                constraints=constraints,
                max_qty_per_sku=max_qty_per_sku,
                max_combos=300_000,
                basis=basis_opt,
            )
        st.session_state["opt_results"] = results
        st.session_state["opt_filtered_pool"] = filtered_pool

    # Show cached results if available (survives widget changes)
    opt_results = st.session_state.get("opt_results")
    opt_filtered_pool = st.session_state.get("opt_filtered_pool")

    if opt_results is None:
        st.divider()
        st.info(
            "👆 设置约束条件和 SKU 候选池后，点击「运行优化」开始枚举。"
            "提示：枚举量越大（单品最大枚举量）搜索越精细，但耗时更长。"
        )
        st.stop()

    results = opt_results
    filtered_pool = opt_filtered_pool

    # Re-evaluate Top-3 with full BOM data for accurate metrics
    if results and wb.sheets:
        for idx in range(min(3, len(results))):
            scenario = results[idx][0]
            full_result = evaluate_portfolio(scenario, wb.sheets, basis=basis_opt)
            if full_result:
                # Replace _quick_eval result with full evaluation result
                results[idx] = (scenario, full_result, results[idx][2])

    if not results:
        st.warning(
            "⚠️ 未找到满足约束的可行组合。"
            "请尝试放宽约束条件（增加产能 / 原料预算 / 降低单品最低销量）。"
        )
        st.stop()

    # Separate best and alternatives
    best_scenario, best_result, _ = results[0]
    alt1 = results[1] if len(results) > 1 else None
    alt2 = results[2] if len(results) > 2 else None

    # ── Step 4: Display Top-3 ────────────────────────────────────────
    st.divider()
    st.markdown(f"#### 🏆 推荐方案（Top-3，共 `{len(selected_pool_keys)}` 个候选 SKU）")

    # Summary metric row
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("方案", best_scenario.name)
    col_m2.metric("选中 SKU 数", best_result.sku_count)
    total_units_best = sum(int(q) for _, q in best_scenario.selections)
    col_m3.metric("总件数", total_units_best)
    col_m4.metric(
        "净利润(元)",
        f"{best_result.total_profit:,.2f}",
        delta=f"vs 方案数 {len(results)}",
    )

    # Tab sub-panels for each plan
    sub_tabs = st.tabs([
        f"🥇 {best_scenario.name}",
        f"🥈 {alt1[0].name}" if alt1 else "🥈 备选2",
        f"🥉 {alt2[0].name}" if alt2 else "🥉 备选3",
    ])

    def _render_plan(sub_tab, scenario, result):
        with sub_tab:
            if result is None:
                st.info("无可用方案")
                return
            col_k1, col_k2, col_k3, col_k4, col_k5 = st.columns(5)
            col_k1.metric("总销售额(元)", f"{result.total_revenue:,.2f}")
            col_k2.metric("总成本(元)", f"{result.total_cost:,.2f}")
            col_k3.metric("净利润(元)", f"{result.total_profit:,.2f}")
            margin_str = f"{result.total_margin*100:.2f}%" if result.total_margin is not None else "N/A"
            col_k4.metric("毛利率", margin_str)
            col_k5.metric("SKU 数量", result.sku_count)

            st.markdown("##### SKU 明细")
            if result.sku_details:
                detail_rows = []
                for d in result.sku_details:
                    detail_rows.append({
                        "品名": d.get("name", d["sku_key"]),
                        "SKU": d["sku_key"],
                        "数量": int(d["qty"]),
                        "单价": f"¥{d['price']:.2f}",
                        "成本": f"¥{d['cost']:.2f}",
                        "销售额": f"¥{d['revenue']:.2f}",
                        "毛利": f"¥{d['profit']:.2f}",
                        "毛利率": f"{d['margin']*100:.1f}%" if d.get("margin") else "N/A",
                    })
                detail_df = pd.DataFrame(detail_rows)
                st.dataframe(detail_df, use_container_width=True, height=320)

    _render_plan(sub_tabs[0], best_scenario, best_result)
    _render_plan(
        sub_tabs[1],
        alt1[0] if alt1 else None,
        alt1[1] if alt1 else None,
    )
    _render_plan(
        sub_tabs[2],
        alt2[0] if alt2 else None,
        alt2[1] if alt2 else None,
    )

    # ── Explanation ───────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 💡 推荐原因（可解释分析）")
    alternatives_for_explain = []
    if alt1:
        alternatives_for_explain.append(alt1[0])
    if alt2:
        alternatives_for_explain.append(alt2[0])

    explanation = explain_recommendation(
        best=best_scenario,
        alternatives=alternatives_for_explain,
        sku_pool=filtered_pool,
    )
    st.markdown(explanation)

    # ── Download Top-3 CSV ───────────────────────────────────────────
    st.divider()
    all_rows = []
    for idx, (scenario, result, _) in enumerate(results):
        rank_label = ["🥇 推荐", "🥈 备选1", "🥉 备选2"][idx]
        for d in (result.sku_details or []):
            all_rows.append({
                "排名": rank_label,
                "方案名": scenario.name,
                "品名": d.get("name", d["sku_key"]),
                "SKU": d["sku_key"],
                "数量": int(d["qty"]),
                "单价": d["price"],
                "成本": d["cost"],
                "销售额": d["revenue"],
                "毛利": d["profit"],
                "毛利率": d.get("margin"),
                "总净利润": result.total_profit,
                "总毛利率": result.total_margin,
            })

    if all_rows:
        opt_csv_df = pd.DataFrame(all_rows)
        csv_bytes = opt_csv_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 下载 Top-3 方案明细 CSV",
            data=csv_bytes,
            file_name="optimizer_top3_portfolios.csv",
            mime="text/csv",
        )
