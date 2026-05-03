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

from mike_product_calc.calc.recipe import build_recipe_table, _parse_spec, _calc_profit_rate
from mike_product_calc.calc.material_sim import (
    Scenario,
    ScenarioStore,
    MaterialPriceAdjustment,
    compare_scenarios,
)
from mike_product_calc.calc.prep_engine import (
    bom_expand_multi,
    gaps_only,
    sales_to_production,
)
from mike_product_calc.calc.profit import margin_delta_report, sku_cost_breakdown, sku_profit_table
from mike_product_calc.calc.target_pricing import suggest_adjustable_item_costs
from mike_product_calc.model.production import ProductionRow
from mike_product_calc.data.loader import load_workbook
from mike_product_calc.data.validator import issues_to_dataframe, validate_workbook
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


tab1, tab2, tab3, tab4, tab5 = st.tabs(["概览/校验", "SKU 毛利分析（双口径）", "Sheet 浏览", "原料价格模拟器", "产销计划"])

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

                st.divider()
                st.markdown("#### 主原料配方拆解")
                st.caption("展开主原料的配方，查看子配料明细。门店价格可调，自动重算成本。")

                recipe_df = build_recipe_table(wb.sheets, product_key=pick, basis=basis)
                if recipe_df.empty:
                    st.info("该 SKU 暂无配方明细数据。")
                else:
                    st.dataframe(
                        recipe_df,
                        use_container_width=True,
                        height=360,
                        column_config={
                            "usage_qty": st.column_config.NumberColumn("用量", format="%.1f"),
                            "cost": st.column_config.NumberColumn("成本", format="%.2f"),
                            "spec": st.column_config.TextColumn("规格"),
                            "store_price": st.column_config.NumberColumn("门店价格", format="%.2f"),
                            "brand_cost": st.column_config.NumberColumn("品牌成本", format="%.2f"),
                        "profit_rate": st.column_config.NumberColumn("利润率(%)", format="%.1f"),
                        },
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

# ── Tab4: 原料价格模拟器（重设计）────────────────────────────────

store: ScenarioStore = st.session_state["sim_store"]

with tab4:
    st.info("功能说明：选产品 → 查看 SKU 规格毛利 → 展开配方明细，调整门店价格/售价，实时看毛利变化。\n"
             "使用方法：选择产品 → 选 SKU 规格 → 在配方表中调整门店价格或在右侧调售价 → 保存方案对比。")
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
        )
    with col_basis_t4:
        basis_t4 = st.radio(
            "口径",
            options=["factory", "store"],
            format_func=lambda x: "出厂口径" if x == "factory" else "门店口径",
            horizontal=True,
        )

    if not selected_product:
        st.info("请在上方选择一个产品。")
        st.stop()

    # ── Step 2: SKU specs table ────────────────────────────────────
    skus_for_product = [
        pk for pk in all_pks
        if pk.startswith(selected_product + "|")
    ]
    sku_df = profit_df_t4[profit_df_t4["product_key"].isin(skus_for_product)].copy()

    if sku_df.empty:
        st.info("该产品下没有找到 SKU 数据。")
        st.stop()

    st.divider()
    st.markdown(f"##### {selected_product} — SKU 规格列表")

    display_t4 = sku_df.copy()
    display_t4["gross_margin_pct"] = display_t4["gross_margin"].apply(
        lambda x: f"{x*100:.1f}%" if pd.notna(x) else "N/A"
    )

    # SKU selector
    sku_options = display_t4["product_key"].tolist()
    selected_sku = st.selectbox(
        "选择 SKU 查看配方",
        options=sku_options,
        format_func=lambda pk: pk.split("|")[-1] if "|" in pk else pk,
    )

    # Show the basic SKU table
    st.dataframe(
        display_t4,
        use_container_width=True,
        height=200,
        column_config={
            "product_key": "SKU",
            "price": st.column_config.NumberColumn("定价", format="%.2f"),
            "cost": st.column_config.NumberColumn("成本", format="%.2f"),
            "gross_profit": st.column_config.NumberColumn("毛利", format="%.2f"),
            "gross_margin_pct": "毛利率",
        },
    )

    # ── Step 3: Recipe detail + pricing ─────────────────────────────
    st.divider()
    st.markdown(f"##### 配方明细 — {selected_sku.split('|')[-1] if '|' in selected_sku else selected_sku}")

    # Build recipe table
    recipe_df = build_recipe_table(wb.sheets, product_key=selected_sku, basis=basis_t4)

    if recipe_df.empty:
        st.info("暂无配方明细数据。")
    else:
        # Editable store_price column using data_editor
        editor_cols = ["item", "usage_qty", "cost", "spec", "store_price", "brand_cost", "profit_rate", "level", "is_semi"]
        editor_df = recipe_df[editor_cols].copy() if all(c in recipe_df.columns for c in editor_cols) else recipe_df

        # Add hierarchy indentation to item names
        if "level" in recipe_df.columns:
            editor_df["item"] = recipe_df.apply(
                lambda r: "↳ " + str(r["item"]) if r["level"] == 2 else str(r["item"]),
                axis=1,
            )

        edited = st.data_editor(
            editor_df,
            use_container_width=True,
            height=400,
            column_config={
                "item": st.column_config.TextColumn("项目", disabled=True),
                "usage_qty": st.column_config.NumberColumn("用量", disabled=True, format="%.1f"),
                "cost": st.column_config.NumberColumn("成本", disabled=True, format="%.2f"),
                "spec": st.column_config.TextColumn("规格", disabled=True),
                "store_price": st.column_config.NumberColumn("门店价格", format="%.2f"),
                "brand_cost": st.column_config.NumberColumn("品牌成本", disabled=True, format="%.2f"),
                "profit_rate": st.column_config.NumberColumn("利润率(%)", disabled=True, format="%.1f"),
                "is_semi": st.column_config.Column("类型", disabled=True, width="small"),
            },
        )

        # Recalculate costs based on edited store_price
        total_cost = 0.0
        recalc_data = edited.to_dict("records")
        for row in recalc_data:
            # Skip sub-ingredient rows (level=2) — their costs are included in the semi-parent row
            if row.get("level") == 2:
                continue

            orig_cost = row.get("cost", 0) or 0
            orig_sp = row.get("store_price", 0) or 0
            new_sp_val = row.get("store_price", 0) or 0

            try:
                new_sp_f = float(new_sp_val)
                orig_sp_f = float(orig_sp)
            except (TypeError, ValueError):
                continue

            # Cost is proportional to store_price for all ingredient types
            # (direct: cost = qty * store_price/spec; sub-ingredient: cost = batch_qty * store_price/spec * scale)
            # So new_cost = orig_cost * (new_store_price / orig_store_price)
            if orig_sp_f > 0 and abs(orig_sp_f - new_sp_f) > 0.0001:
                row["cost"] = round(float(orig_cost) * (new_sp_f / orig_sp_f), 2)
            # else keep original cost

            # Recalculate profit_rate
            try:
                bc_f = float(row.get("brand_cost", 0) or 0)
            except (TypeError, ValueError):
                bc_f = 0
            row["profit_rate"] = round(_calc_profit_rate(new_sp_f, bc_f) * 100, 1)

            row_cost = row.get("cost", 0) or 0
            try:
                total_cost += float(row_cost)
            except (TypeError, ValueError):
                pass

        # ── Pricing & margin KPI cards ──────────────────────────────
        default_price = float(sku_df[sku_df["product_key"] == selected_sku]["price"].iloc[0]) if not sku_df[sku_df["product_key"] == selected_sku].empty else 0.0
        price_key = f"t4_sku_price_{selected_sku}"
        current_price = st.session_state.get(price_key, default_price)

        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            new_price = st.number_input("门店售价（元）", value=float(current_price), step=1.0, min_value=0.0, key=f"t4_price_{selected_sku}")
            st.session_state[price_key] = new_price
        with col_p2:
            gross_profit = new_price - total_cost
            st.metric("总成本（元）", f"{total_cost:.2f}")
        with col_p3:
            margin_rate = (gross_profit / new_price * 100) if new_price > 0 else 0
            st.metric("毛利", f"{gross_profit:.2f} 元", delta=f"{margin_rate:.1f}%")

        # ── Scenario management ──────────────────────────────────────
        st.divider()
        st.markdown("##### 方案管理")

        col_save_nm, col_save_btn = st.columns([3, 1])
        with col_save_nm:
            scenario_name = st.text_input("方案名称", placeholder="输入名称后保存", key="t4_scenario_name")
        with col_save_btn:
            st.write("")
            st.write("")
            if st.button("保存方案", use_container_width=True):
                adjustments = []
                for row in recalc_data:
                    if row.get("level") == 2:
                        continue
                    sp = row.get("store_price")
                    name = str(row.get("item", "")).strip()
                    if name and sp is not None:
                        try:
                            sp_f = float(sp)
                            if sp_f > 0:
                                adjustments.append(MaterialPriceAdjustment(item=name, new_unit_price=sp_f))
                        except (TypeError, ValueError):
                            pass
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
                if va != vb and st.button("对比"):
                    s_a, s_b = store.get(va), store.get(vb)
                    if s_a and s_b:
                        diff = compare_scenarios(s_a, s_b, wb.sheets, basis=basis_t4)
                        st.dataframe(diff, use_container_width=True, height=420)
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

