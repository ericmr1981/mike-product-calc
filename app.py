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
)
from mike_product_calc.calc.purchase_suggestion import build_purchase_list
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


st.set_page_config(page_title="mike-product-calc", layout="wide")

st.title("蜜可诗产品经营决策台 (mike-product-calc)")
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
        entry = _save_upload(b, getattr(up, 'name', 'workbook.xlsx'))
        items = _load_registry()
        items.insert(0, entry)
        _save_registry(items)

        if replace_current and selected_id:
            _delete_file(selected_id)

        st.session_state['active_file_id'] = entry['id']
        st.success(f"已保存：{entry['orig_name']}（{entry['id'][:8]}）")
        st.rerun()


def _resolve_active_workbook_bytes() -> tuple[bytes, str]:
    # 1) active from registry
    fid = st.session_state.get('active_file_id', '')
    if fid:
        for it in _load_registry():
            if str(it.get('id')) == str(fid):
                fp = UPLOAD_DIR / str(it.get('saved_name'))
                if fp.exists():
                    return fp.read_bytes(), str(it.get('orig_name') or fp.name)

    # 2) fallback: env var
    _default_xlsx = os.environ.get('MIKE_DEFAULT_XLSX', '')
    if _default_xlsx and Path(_default_xlsx).exists():
        p = Path(_default_xlsx)
        return p.read_bytes(), p.name

    raise FileNotFoundError('No workbook selected/uploaded')


try:
    workbook_bytes, workbook_name = _resolve_active_workbook_bytes()
except FileNotFoundError:
    st.info('请先在上方上传/选择 xlsx 文件开始。')
    st.stop()
@st.cache_data(show_spinner=False)
def _load_and_validate(bytes_data: bytes):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "workbook.xlsx"
        p.write_bytes(bytes_data)
        wb = load_workbook(p)
        issues = validate_workbook(wb.sheets)
        return wb, issues


with st.spinner("解析中..."):
    wb, issues = _load_and_validate(workbook_bytes)

sheet_names = list(wb.sheets.keys())

# ── Tab4 状态初始化（原料价格模拟器 session 级存储）─────────────────────
if "sim_store" not in st.session_state:
    st.session_state["sim_store"] = ScenarioStore()

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11 = st.tabs(["概览/校验", "SKU 毛利分析（双口径）", "Sheet 浏览", "原料价格模拟器", "生产计划录入", "备料计划", "采购建议", "产品组合评估", "多场景对比", "选品优化器", "产能需求估算"])

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
    col_save, col_clear = st.columns(2)
    if col_save.button("💾 保存版本", disabled=not (version_name and adjustments)):
        store.put(Scenario(name=version_name, adjustments=tuple(adjustments)))
        st.success(f"已保存版本：{version_name}")
        st.rerun()
    if col_clear.button("🗑 清空所有版本"):
        store.clear()
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
        if st.button("🔍 对比两版本"):
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
            from mike_product_calc.calc.material_sim import Scenario as BaseScenario
            diff = compare_scenarios(BaseScenario(name="基准", adjustments=()), s1, wb.sheets, basis=sim_basis)
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

# ── Tab5: 生产计划录入 ────────────────────────────────────────────────

# Build SKU list from workbook for dropdown
_profit_df = sku_profit_table(wb.sheets, basis="factory", only_status=None)
_all_skus = sorted(_profit_df["product_key"].dropna().unique().tolist())

# SKU pool for production plan: from 产品出品表 (ingredients/outputs of production line)
_out_sheet_names = [k for k in wb.sheets if k.startswith("产品出品表_")]
_production_skus_list: list[str] = []
for _sname in _out_sheet_names:
    _df_out = wb.sheets[_sname]
    _keys = build_product_key(_df_out)
    for _k in _keys.dropna().unique():
        _k_str = str(_k).strip()
        if _k_str and _k_str not in _production_skus_list:
            _production_skus_list.append(_k_str)
_production_skus = sorted(_production_skus_list)


def _init_session():
    if "production_plans" not in st.session_state:
        st.session_state["production_plans"] = {}  # Dict[str, List[ProductionRow]]
    if "current_plan_name" not in st.session_state:
        st.session_state["current_plan_name"] = None


with tab5:
    st.info("📌 **功能说明**：录入和管理生产/销量计划场景，支持 CSV 批量导入。\n"
             "**使用方法**：选择计划类型（销量/生产）→ 输入场景名 → 编辑数据 → 保存；可复制历史场景。\n"
             "**字段含义**：SKU（销量计划=产品毛利表可售成品，生产计划=产品出品表配料）；"
             "规格=产品尺寸/容量；数量=计划件数；日期=计划执行日期。")
    _init_session()
    plans: dict = st.session_state["production_plans"]
    current = st.session_state.get("current_plan_name")

    # ── Scenario management ──────────────────────────────────────────
    st.subheader("场景管理")
    col_mg1, col_mg2, col_mg3 = st.columns([2, 2, 1])

    with col_mg1:
        plan_type_filter = st.radio(
            "计划类型",
            options=["sales", "production"],
            format_func=lambda x: "销量计划" if x == "sales" else "生产计划",
            horizontal=True,
            key="plan_type_radio",
        )
    with col_mg2:
        new_name = st.text_input("新场景名", placeholder="输入场景名后保存")
    with col_mg3:
        st.write("")
        save_clicked = st.button("💾 保存当前", use_container_width=True)

    # Load / copy from history
    col_action1, col_action2, col_action3 = st.columns([1, 1, 1])
    with col_action1:
        saved_names = list(plans.keys())
        copy_source = st.selectbox("📋 复制历史计划", options=[""] + saved_names, key="copy_source_sel")
        if copy_source and st.button("复制", key="do_copy_btn"):
            src_rows = plans.get(copy_source, [])
            default_name = f"{copy_source}_副本"
            counter = 1
            while default_name in plans:
                counter += 1
                default_name = f"{copy_source}_副本{counter}"
            plans[default_name] = [ProductionRow(
                date=r.date, sku_key=r.sku_key, spec=r.spec,
                qty=r.qty, plan_type=r.plan_type,
            ) for r in src_rows]
            st.session_state["current_plan_name"] = default_name
            st.rerun()

    with col_action2:
        # Switch plan
        switch_target = st.selectbox("🔀 切换场景", options=[""] + saved_names, key="switch_sel")
        if switch_target and st.button("切换", key="do_switch_btn"):
            st.session_state["current_plan_name"] = switch_target
            st.rerun()

    with col_action3:
        if current and st.button("🗑 删除当前场景", key="delete_btn"):
            plans.pop(current, None)
            st.session_state["current_plan_name"] = None
            st.rerun()

    # Save new plan
    if save_clicked and new_name:
        # Merge current working rows into new name
        rows_key = f"{new_name}__{plan_type_filter}"
        if rows_key in plans:
            existing = plans[rows_key]
        else:
            existing = []
        plans[new_name] = existing
        st.session_state["current_plan_name"] = new_name
        st.rerun()

    # ── Multi-row editor ─────────────────────────────────────────────
    st.divider()
    st.subheader("计划数据录入")

    # Template download
    template_df = pd.DataFrame(columns=["日期", "SKU", "规格", "数量", "计划类型"])
    st.download_button(
        "📥 下载 CSV 模板",
        data=template_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="production_plan_template.csv",
        mime="text/csv",
        key="download_template_btn",
    )

    # CSV upload
    uploaded_csv = st.file_uploader("📤 上传 CSV 回填", type=["csv"], key="csv_upload")
    if uploaded_csv:
        try:
            import_df = pd.read_csv(uploaded_csv)
            required_cols = {"日期", "SKU", "规格", "数量", "计划类型"}
            if required_cols.issubset(set(import_df.columns)):
                st.session_state["_imported_rows"] = import_df.to_dict("records")
                st.success(f"已读取 {len(import_df)} 行，可用于回填")
            else:
                st.warning("CSV 列不完整，需要: 日期, SKU, 规格, 数量, 计划类型")
        except Exception as e:
            st.error(f"读取 CSV 失败: {e}")

    # Plan name selector for editing
    all_plan_names = list(plans.keys())
    edit_plan = st.selectbox("✏️ 编辑场景", options=["(新建空计划)"] + all_plan_names,
                              index=(all_plan_names.index(current) + 1) if current in all_plan_names else 0,
                              key="edit_plan_sel")

    # Use imported rows or existing
    default_rows = st.session_state.get("_imported_rows", [])
    if edit_plan != "(新建空计划)" and edit_plan in plans and not default_rows:
        existing_rows = plans[edit_plan]
        default_rows = [{"日期": r.date, "SKU": r.sku_key, "规格": r.spec,
                          "数量": r.qty, "计划类型": r.plan_type} for r in existing_rows]
    elif edit_plan == "(新建空计划)":
        default_rows = []

    # Clear imported after use
    st.session_state.pop("_imported_rows", None)

    # Number of rows to show
    num_rows = st.number_input("行数", min_value=1, max_value=200, value=max(len(default_rows), 5), step=1, key="num_rows_input")

    # Build editor data
    while len(default_rows) < num_rows:
        default_rows.append({"日期": "", "SKU": "", "规格": "", "数量": 0, "计划类型": plan_type_filter})
    editor_df = pd.DataFrame(default_rows[:num_rows])
    editor_df["计划类型"] = editor_df["计划类型"].fillna(plan_type_filter)

    # ── SKU pool by plan type ────────────────────────────────────────
    # 销量计划 → 产品毛利表（可售成品）；生产计划 → 产品出品表（生产配料）
    if plan_type_filter == "production":
        _editor_sku_options = _production_skus
    else:
        _editor_sku_options = _all_skus

    # data_editor
    st.caption("直接编辑下表，或上传 CSV 回填。日期格式：YYYY-MM-DD")
    edited_df = st.data_editor(
        editor_df,
        num_rows="dynamic",
        use_container_width=True,
        height=min(num_rows * 40 + 60, 500),
        column_config={
            "日期": st.column_config.TextColumn("日期（YYYY-MM-DD）", required=True),
            "SKU": st.column_config.SelectboxColumn("SKU", options=_editor_sku_options, required=False),
            "规格": st.column_config.TextColumn("规格"),
            "数量": st.column_config.NumberColumn("数量", min_value=0, format="%d"),
            "计划类型": st.column_config.SelectboxColumn(
                "计划类型",
                options=["sales", "production"],
                format_func=lambda x: "销量计划" if x == "sales" else "生产计划",
            ),
        },
        key="plan_editor",
    )

    col_save1, col_save2, col_save3 = st.columns([1, 1, 2])
    with col_save1:
        if st.button("✅ 保存", key="save_plan_btn"):
            save_name = edit_plan if edit_plan != "(新建空计划)" else (new_name or f"未命名计划_{len(plans)}")
            rows = []
            for _, row in edited_df.iterrows():
                _d = row["日期"]
                _d_str = _date_str(_parse_date(_d)) if not isinstance(_d, str) else _d
                if _d_str:
                    rows.append(ProductionRow(
                        date=_d_str,
                        sku_key=str(row["SKU"]) if pd.notna(row["SKU"]) else "",
                        spec=str(row["规格"]) if pd.notna(row["规格"]) else "",
                        qty=float(row["数量"]) if pd.notna(row["数量"]) else 0,
                        plan_type=str(row["计划类型"]) if pd.notna(row["计划类型"]) else plan_type_filter,
                    ))
            plans[save_name] = rows
            st.session_state["current_plan_name"] = save_name
            st.success(f"已保存：{save_name}（{len(rows)} 行）")
            st.rerun()

    with col_save2:
        if st.button("🔄 重置", key="reset_plan_btn"):
            st.session_state.pop("_imported_rows", None)
            st.rerun()

    # ── Preview saved plans ──────────────────────────────────────────
    if plans:
        st.divider()
        st.subheader("已保存场景概览")
        preview_plan = st.selectbox("查看场景", options=list(plans.keys()), key="preview_sel")
        if preview_plan:
            rows = plans[preview_plan]
            if rows:
                preview_df = pd.DataFrame([
                    {"日期": r.date, "SKU": r.sku_key, "规格": r.spec,
                     "数量": r.qty, "计划类型": "销量计划" if r.plan_type == "sales" else "生产计划"}
                    for r in rows
                ])
                st.dataframe(preview_df, use_container_width=True, height=300)
            else:
                st.info("该场景暂无数据")


# ── Tab6: 备料计划 ─────────────────────────────────────────────────────

import datetime as dt


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


with tab6:
    st.info("📌 **功能说明**：基于生产计划场景，展开三级 BOM（SKU→主原料/配料→原料），输出原料需求表和缺口预警。\n"
             "**使用方法**：选择场景+日期范围+提前期+损耗率，点击「展开 BOM」生成原料需求表。\n"
             "**字段含义**：total_purchase_qty=含损耗的安全备量；lead_days=提前采购天数；"
             "is_gap=无有效单价或供应状态异常；latest_order_date=最晚下单日。")
    st.subheader("备料计划 — BOM 展开引擎")
    st.caption("三级展开：SKU → 主原料/配料 → 原料；支持损耗率、安全库存、最小采购单位、批次取整、提前期。")

    # ── Init session ─────────────────────────────────────────────────
    _init_session()
    plans: dict = st.session_state["production_plans"]

    # ── Controls ─────────────────────────────────────────────────────
    col_ctrl1, col_ctrl2, col_ctrl3, col_ctrl4, col_ctrl5 = st.columns([2, 2, 1, 1, 1])

    with col_ctrl1:
        scenario_opts = [""] + list(plans.keys())
        selected_scenario = st.selectbox("选择场景", options=scenario_opts, key="prep_scenario")

    with col_ctrl2:
        plan_type_opts = ["all", "sales", "production"]
        plan_type_label = {"all": "全部", "sales": "销量计划", "production": "生产计划"}
        selected_type = st.selectbox(
            "计划类型",
            options=plan_type_opts,
            format_func=lambda x: plan_type_label[x],
            key="prep_plan_type",
        )

    with col_ctrl3:
        default_ld = st.number_input(
            "提前期（天）",
            min_value=0,
            max_value=90,
            value=3,
            key="prep_lead_days",
        )

    with col_ctrl4:
        default_loss = st.number_input(
            "损耗率（%）",
            min_value=0,
            max_value=100,
            value=0,
            key="prep_loss_rate",
        ) / 100.0

    with col_ctrl5:
        basis_opts = ["store", "factory"]
        basis_label = {"store": "门店(加价后单价)", "factory": "出厂(加价前单价)"}
        selected_basis = st.selectbox(
            "单价口径",
            options=basis_opts,
            format_func=lambda x: basis_label[x],
            key="prep_basis",
        )

    col_date1, col_date2, col_date3 = st.columns([1, 1, 2])
    with col_date1:
        start_date = st.date_input("开始日期", value=None, key="prep_start")
    with col_date2:
        end_date = st.date_input("结束日期", value=None, key="prep_end")
    with col_date3:
        st.write("")
        st.write("")
        run_expand = st.button("🔍 展开 BOM", type="primary", use_container_width=True)

    # ── Expand ────────────────────────────────────────────────────────
    if run_expand:
        if not selected_scenario:
            st.warning("请先选择一个已保存的场景（先在「生产计划录入」tab 中录入并保存计划）。")
        else:
            rows: List[ProductionRow] = plans.get(selected_scenario, [])
            if not rows:
                st.info("该场景暂无数据。")
            else:
                # Filter by date range and plan type
                start_dt = start_date
                end_dt   = end_date

                filtered = []
                for r in rows:
                    if selected_type != "all" and r.plan_type != selected_type:
                        continue
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
                    # Build sku→plan_qty dict (sum across selected rows)
                    sku_qty: Dict[str, float] = {}
                    for r in filtered:
                        k = str(r.sku_key).strip()
                        if k:
                            sku_qty[k] = sku_qty.get(k, 0.0) + float(r.qty)

                    # Target order date = end of range (latest delivery)
                    target_date: Optional[date] = end_dt

                    with st.spinner("BOM 展开中…"):
                        t0 = dt.datetime.now()
                        result = bom_expand_multi(
                            wb.sheets,
                            sku_qty,
                            order_date=target_date,
                            basis=selected_basis,
                            default_lead_days=default_ld,
                            default_loss_rate=default_loss,
                            default_safety_stock=0.0,
                        )
                        elapsed = (dt.datetime.now() - t0).total_seconds()

                    st.success(f"展开完成，耗时 {elapsed:.2f}s（目标 <3s）")

                    if result.empty:
                        st.info("BOM 展开结果为空（可能选中的 SKU 在出品表中无配料数据）。")
                    else:
                        # Tabs within tab6
                        inner_tab_a, inner_tab_b, inner_tab_c = st.tabs(
                            ["📦 原料需求汇总", "⚠️ 缺口预警", "📊 统计概览"]
                        )

                        with inner_tab_a:
                            st.markdown("#### 原料需求汇总表")
                            # Format for display
                            display = result.copy()
                            display["is_gap"] = display["is_gap"].map(
                                lambda x: "⚠️ 缺口" if x else "✅ 正常"
                            )
                            st.dataframe(
                                display,
                                use_container_width=True,
                                height=500,
                                column_config={
                                    "total_gross_qty": st.column_config.NumberColumn(
                                        "总需求(含损耗)", format="%.2f"
                                    ),
                                    "total_safety_stock": st.column_config.NumberColumn(
                                        "总安全库存", format="%.2f"
                                    ),
                                    "total_purchase_qty": st.column_config.NumberColumn(
                                        "建议采购量", format="%.2f"
                                    ),
                                    "unit_price": st.column_config.NumberColumn(
                                        "单价(元)", format="%.4f"
                                    ),
                                    "total_cost": st.column_config.NumberColumn(
                                        "采购成本(元)", format="%.2f"
                                    ),
                                    "lead_days": st.column_config.NumberColumn("提前期(天)"),
                                },
                            )
                            csv_data = result.to_csv(index=False).encode("utf-8-sig")
                            st.download_button(
                                "📥 下载原料需求 CSV",
                                data=csv_data,
                                file_name="bom_material_demand.csv",
                                mime="text/csv",
                            )

                        with inner_tab_b:
                            st.markdown("#### 缺口预警（无有效单价 / 供应不稳定）")
                            gaps = gaps_only(result)
                            if gaps.empty:
                                st.success("✅ 所有原料均有有效单价且供应稳定")
                            else:
                                gap_display = gaps.copy()
                                st.warning(f"发现 {len(gaps)} 个缺口项：")
                                st.dataframe(
                                    gap_display[[
                                        "material", "gap_reason", "total_purchase_qty",
                                        "unit_price", "is_semi_finished", "sku_keys",
                                    ]],
                                    use_container_width=True,
                                    height=400,
                                )

                        with inner_tab_c:
                            st.markdown("#### 统计概览")
                            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                            col_stat1.metric("原料种类", len(result))
                            col_stat2.metric(
                                "总采购成本(元)",
                                f"{result['total_cost'].sum():.2f}",
                            )
                            col_stat3.metric(
                                "半成品种类",
                                int(result["is_semi_finished"].sum()),
                            )
                            col_stat4.metric("缺口数量", int(result["is_gap"].sum()))

                            if not result["total_cost"].isna().all():
                                by_level = (
                                    result.groupby("level")
                                    .agg(
                                        {
                                            "material": "count",
                                            "total_purchase_qty": "sum",
                                            "total_cost": "sum",
                                        }
                                    )
                                    .rename(columns={"material": "原料种类数"})
                                )
                                st.markdown("##### 按层级统计")
                                st.dataframe(by_level, use_container_width=True)

    else:
        # Show guidance when not yet run
        st.divider()
        st.info(
            "👆 在上方选择场景和日期范围，点击「展开 BOM」开始。\n\n"
            "提示：\n"
            "• 场景在「生产计划录入」tab 中创建并保存\n"
            "• 日期留空表示不限制范围\n"
            "• 缺口预警 tab 展示无有效单价或供应不稳定的原料"
        )


# ── Tab7: 采购建议 ─────────────────────────────────────────────────────


with tab7:
    st.info("📌 **功能说明**：基于备料计划的原料需求，生成采购建议清单（含紧急项标注）。\n"
             "**使用方法**：选择生产计划场景和日期范围，点击「生成采购建议」。\n"
             "**字段含义**：下单日期=最晚采购日；到货日期=原料到达日期；"
             "is_urgent=已过期或今日需下单（红色高亮）；来源SKU=使用该原料的产品。")
    st.subheader("采购建议")
    st.caption("基于备料计划输出采购清单：下单日期、到货日期、原料、数量、单位、来源 SKU；红色标注最晚下单日（已过或今日）。")

    _init_session()
    plans: dict = st.session_state["production_plans"]

    col_ps1, col_ps2, col_ps3, col_ps4, col_ps5 = st.columns([2, 2, 1, 1, 1])

    with col_ps1:
        ps_scenario_opts = [""] + list(plans.keys())
        ps_selected_scenario = st.selectbox(
            "选择场景", options=ps_scenario_opts, key="ps_scenario"
        )

    with col_ps2:
        ps_plan_type_opts = ["all", "sales", "production"]
        ps_plan_type_label = {"all": "全部", "sales": "销量计划", "production": "生产计划"}
        ps_selected_type = st.selectbox(
            "计划类型",
            options=ps_plan_type_opts,
            format_func=lambda x: ps_plan_type_label[x],
            key="ps_plan_type",
        )

    with col_ps3:
        ps_lead_days = st.number_input(
            "提前期（天）", min_value=0, max_value=90, value=3, key="ps_lead_days"
        )

    with col_ps4:
        ps_loss_rate = st.number_input(
            "损耗率（%）",
            min_value=0,
            max_value=100,
            value=0,
            key="ps_loss_rate",
        ) / 100.0

    with col_ps5:
        basis_opts = ["store", "factory"]
        basis_label = {"store": "门店(加价后单价)", "factory": "出厂(加价前单价)"}
        ps_basis = st.selectbox(
            "单价口径",
            options=basis_opts,
            format_func=lambda x: basis_label[x],
            key="ps_basis",
        )

    col_ps_date1, col_ps_date2, col_ps_date3 = st.columns([1, 1, 2])
    with col_ps_date1:
        ps_start_date = st.date_input("开始日期", value=None, key="ps_start")
    with col_ps_date2:
        ps_end_date = st.date_input("结束日期", value=None, key="ps_end")
    with col_ps_date3:
        st.write("")
        st.write("")
        run_ps = st.button("📋 生成采购建议", type="primary", use_container_width=True)

    if run_ps:
        if not ps_selected_scenario:
            st.warning("请先选择一个已保存的场景（先在「生产计划录入」tab 中录入并保存计划）。")
        else:
            rows: List[ProductionRow] = plans.get(ps_selected_scenario, [])
            if not rows:
                st.info("该场景暂无数据。")
            else:
                # Filter by date range and plan type
                ps_start_dt = ps_start_date
                ps_end_dt   = ps_end_date

                filtered = []
                for r in rows:
                    if ps_selected_type != "all" and r.plan_type != ps_selected_type:
                        continue
                    rdate = _parse_date(r.date)
                    if rdate is None:
                        filtered.append(r)
                        continue
                    if ps_start_dt and rdate < ps_start_dt:
                        continue
                    if ps_end_dt and rdate > ps_end_dt:
                        continue
                    filtered.append(r)

                if not filtered:
                    st.info("日期范围内无数据。")
                else:
                    # Build sku → plan_qty dict
                    sku_qty: Dict[str, float] = {}
                    for r in filtered:
                        k = str(r.sku_key).strip()
                        if k:
                            sku_qty[k] = sku_qty.get(k, 0.0) + float(r.qty)

                    target_date: Optional[date] = ps_end_dt

                    with st.spinner("生成采购建议中…"):
                        demand = bom_expand_multi(
                            wb.sheets,
                            sku_qty,
                            order_date=target_date,
                            basis=ps_basis,
                            default_lead_days=ps_lead_days,
                            default_loss_rate=ps_loss_rate,
                            default_safety_stock=0.0,
                        )

                    if demand.empty:
                        st.info("备料结果为空（选中的 SKU 在出品表中无配料数据）。")
                    else:
                        purchase_df = build_purchase_list(
                            demand,
                            order_date=target_date,
                        )

                        if purchase_df.empty:
                            st.info("无原材料采购需求（全部为半成品）。")
                        else:
                            st.markdown("#### 采购建议清单")
                            st.caption("⚠️ 红色 = 最晚下单日已过或今日，请优先处理")

                            display_ps = purchase_df.copy()
                            display_ps["qty"] = display_ps["qty"].round(2)
                            display_ps["is_urgent_label"] = display_ps["is_urgent"].map(
                                lambda x: "🚨 紧急" if x else "✅ 正常"
                            )

                            # Urgent-only filter
                            show_urgent_only = st.checkbox(
                                "仅显示紧急项", value=False, key="ps_urgent_only"
                            )
                            if show_urgent_only:
                                display_ps = display_ps[display_ps["is_urgent"]]

                            st.dataframe(
                                display_ps[[
                                    "order_date",
                                    "arrival_date",
                                    "material",
                                    "qty",
                                    "unit",
                                    "source_skus",
                                    "is_urgent_label",
                                ]],
                                use_container_width=True,
                                height=520,
                            )

                            # Summary metrics
                            col_pm1, col_pm2, col_pm3 = st.columns(3)
                            col_pm1.metric("原料种类", len(purchase_df))
                            col_pm2.metric(
                                "总采购量",
                                f"{purchase_df['qty'].sum():.2f}",
                            )
                            col_pm3.metric(
                                "紧急项",
                                int(purchase_df["is_urgent"].sum()),
                            )

                            st.divider()

                            # CSV download
                            csv_ps = purchase_df.to_csv(index=False).encode("utf-8-sig")
                            st.download_button(
                                "📥 下载采购建议 CSV",
                                data=csv_ps,
                                file_name="purchase_suggestion.csv",
                                mime="text/csv",
                            )

                            # Highlighted urgent table (Streamlit native coloring)
                            urgent_df = purchase_df[purchase_df["is_urgent"]].copy()
                            if not urgent_df.empty:
                                st.markdown("#### 🚨 紧急采购项")
                                st.dataframe(
                                    urgent_df[[
                                        "order_date",
                                        "arrival_date",
                                        "material",
                                        "qty",
                                        "unit",
                                        "source_skus",
                                    ]],
                                    use_container_width=True,
                                    height=300,
                                )
    else:
        st.divider()
        st.info(
            "👆 在上方选择场景和日期范围，点击「生成采购建议」开始。\n\n"
            "提示：\n"
            "• 红色标注的行表示最晚下单日已过，请优先处理\n"
            "• 采购建议基于备料计划展开（仅原材料，不含半成品）\n"
            "• 「展开 BOM」tab 可查看详细备料数据"
        )


# ── Tab8: 产品组合评估 ─────────────────────────────────────────────────

# Build SKU list once
_all_skus_for_portfolio = sorted(_profit_df["product_key"].dropna().unique().tolist())


def _init_portfolio_session():
    """Initialize session-state slots for portfolio A/B/C."""
    for slot in ("portfolio_A", "portfolio_B", "portfolio_C"):
        if slot not in st.session_state:
            st.session_state[slot] = {}  # {sku_key: qty}


with tab8:
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

        with col_save_b:
            if st.button("💾 保存为方案 B", key="save_portfolio_B"):
                st.session_state["portfolio_B"] = dict(qty_values)
                for k, v in qty_values.items():
                    st.session_state[f"_last_qty_{k}"] = v
                st.success("✅ 方案 B 已保存")

        with col_save_c:
            if st.button("💾 保存为方案 C", key="save_portfolio_C"):
                st.session_state["portfolio_C"] = dict(qty_values)
                for k, v in qty_values.items():
                    st.session_state[f"_last_qty_{k}"] = v
                st.success("✅ 方案 C 已保存")

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


# ── Tab9: 多场景对比 ─────────────────────────────────────────────────


def _init_multi_scenario_session():
    if "ms_scenarios" not in st.session_state:
        st.session_state["ms_scenarios"] = {}  # name -> dict of {sku_key: qty}


with tab9:
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
        else:
            if ms_new_name not in ms_scenarios:
                ms_scenarios[ms_new_name] = {}
        st.session_state["ms_scenarios"] = ms_scenarios
        st.success(f"已保存场景：{ms_new_name}")
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

                st.divider()
                st.markdown("#### 场景对比汇总")

                # KPI row
                if results:
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

                # SKU diff (which SKUs changed)
                sku_diff = multi_scenario_diff_table(results)
                if not sku_diff.empty:
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

    if not run_compare:
        st.divider()
        st.info(
            "👆 在上方创建并保存场景，然后点击「对比场景」开始分析。\n\n"
            "提示：\n"
            "• 每个场景代表一组不同的销量假设（可复制历史场景快速创建）\n"
            "• 对比表展示各场景的总利润、毛利率、原料需求\n"
            "• 差异表高亮哪些 SKU 数量/利润在不同场景间发生变化"
        )


# ── Tab10: 选品优化器 ─────────────────────────────────────────────────


with tab10:
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
            "状态过滤", options=status_filter_opts, index=1, key="opt_status_filter"
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

    if not run_optimize:
        st.divider()
        st.info(
            "👆 设置约束条件和 SKU 候选池后，点击「运行优化」开始枚举。"
            "提示：枚举量越大（单品最大枚举量）搜索越精细，但耗时更长。"
        )
        st.stop()

    # ── Step 3: Run optimization ─────────────────────────────────────
    constraints = OptimizationConstraint(
        max_capacity=max_capacity,
        material_budget=material_budget,
        min_sales_per_sku=min_sales_per_sku,
    )

    # Filter pool to selected SKUs
    filtered_pool = sku_pool_df[sku_pool_df["product_key"].isin(selected_pool_keys)].copy()

    with st.spinner(f"枚举中…（候选 SKU {len(filtered_pool)} 个）× {max_qty_per_sku} 个数量级"):
        results = enumerate_portfolios(
            sku_pool=filtered_pool,
            constraints=constraints,
            max_qty_per_sku=max_qty_per_sku,
            max_combos=300_000,
            basis=basis_opt,
        )

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


# ── Tab11: 产能需求估算 ────────────────────────────────────────────────────────────────────

with tab11:
    st.info("📌 **功能说明**：基于生产计划，估算各 SKU/日期的产能压力评分（0-100），高压力项红色标注。\n"
             "**使用方法**：选择生产计划场景 → 选择「按 SKU」或「按日期」视图 → 点击分析 → 查看评分和柱状图。\n"
             "**字段含义**：score=产能压力总分；complexity_score=SKU 种类复杂度得分；"
             "volume_score=产量体积得分；material_score=原料多样性得分；≥60=高压力（红色）。")
    st.subheader("产能需求估算")

    _init_session()
    plans: dict = st.session_state["production_plans"]

    # Controls
    col_cp1, col_cp2, col_cp3, col_cp4 = st.columns([2, 2, 1, 1])

    with col_cp1:
        cp_scenario_opts = [""] + list(plans.keys())
        cp_selected_scenario = st.selectbox(
            "选择场景", options=cp_scenario_opts, key="cp_scenario"
        )

    with col_cp2:
        cp_plan_type_opts = ["all", "sales", "production"]
        cp_plan_type_label = {"all": "全部", "sales": "销量计划", "production": "生产计划"}
        cp_selected_type = st.selectbox(
            "计划类型",
            options=cp_plan_type_opts,
            format_func=lambda x: cp_plan_type_label[x],
            key="cp_plan_type",
        )

    with col_cp3:
        cp_view_by = st.radio(
            "视图",
            options=["sku", "date"],
            format_func=lambda x: "按 SKU" if x == "sku" else "按日期",
            horizontal=True,
            key="cp_view_by",
        )

    with col_cp4:
        st.write("")
        st.write("")
        run_cp = st.button("📊 分析产能压力", type="primary", use_container_width=True)

    if run_cp:
        if not cp_selected_scenario:
            st.warning("请先选择一个已保存的场景（先在「生产计划录入」tab 中录入并保存计划）。")
        else:
            rows: List[ProductionRow] = plans.get(cp_selected_scenario, [])
            if not rows:
                st.info("该场景暂无数据。")
            else:
                # Filter by plan type
                if cp_selected_type != "all":
                    rows = [r for r in rows if r.plan_type == cp_selected_type]

                if not rows:
                    st.info("当前计划类型下无数据。")
                else:
                    # Compute capacity pressure
                    if cp_view_by == "sku":
                        cp_results = score_capacity_from_plan(rows, wb.sheets)
                    else:
                        cp_results = score_capacity_by_date(rows, wb.sheets)

                    cp_df = capacity_to_dataframe(cp_results)

                    if cp_df.empty:
                        st.info("无法计算产能压力（可能选中的 SKU 在出品表中无配料数据）。")
                    else:
                        # Summary metrics
                        total = len(cp_df)
                        high_count = int(cp_df["is_high_pressure"].sum())
                        avg_score = float(cp_df["score"].mean())

                        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
                        col_m1.metric("SKU/日期数", total)
                        col_m2.metric("高压力项", high_count, delta_color="inverse")
                        col_m3.metric("平均压力分", f"{avg_score:.1f}")
                        col_m4.metric("最高压力分", f"{float(cp_df['score'].max()):.1f}")

                        # Bar chart: score distribution
                        st.divider()
                        st.markdown("#### 产能压力柱状图（压力分从高到低）")
                        chart_df = cp_df[["sku_key", "score"]].copy()
                        # Shorten sku_key for display
                        chart_df["label"] = chart_df["sku_key"].apply(
                            lambda x: x.split("|")[1] if "|" in x else x[:30]
                        )
                        chart_df = chart_df.set_index("label")
                        st.bar_chart(chart_df["score"])

                        # Breakdown chart: score components
                        st.markdown("#### 各维度得分明细")
                        st.bar_chart(
                            cp_df.set_index(
                                cp_df["sku_key"].apply(
                                    lambda x: x.split("|")[1] if "|" in x else x[:20]
                                )
                            )[["complexity_score", "volume_score", "material_score"]]
                        )

                        # Highlighted table
                        st.divider()
                        st.markdown("#### 产能压力明细表（高压力项红色标注）")

                        display_cp = cp_df.copy()
                        display_cp["压力等级"] = display_cp["is_high_pressure"].map(
                            lambda x: "🔴 高压力" if x else "🟢 正常"
                        )

                        # Format for display
                        st.dataframe(
                            display_cp[[
                                "sku_key", "score", "压力等级",
                                "complexity_score", "volume_score", "material_score",
                                "material_count", "plan_qty",
                            ]],
                            use_container_width=True,
                            height=480,
                            column_config={
                                "score": st.column_config.NumberColumn(
                                    "总分(0-100)", format="%.1f"
                                ),
                                "complexity_score": st.column_config.NumberColumn(
                                    "SKU复杂度分", format="%.1f"
                                ),
                                "volume_score": st.column_config.NumberColumn(
                                    "产量体积分", format="%.1f"
                                ),
                                "material_score": st.column_config.NumberColumn(
                                    "原料多样性分", format="%.1f"
                                ),
                                "material_count": st.column_config.NumberColumn("原料种类数"),
                                "plan_qty": st.column_config.NumberColumn("计划产量", format="%.0f"),
                            },
                        )

                        # Download
                        csv_cp = cp_df.to_csv(index=False).encode("utf-8-sig")
                        st.download_button(
                            "📥 下载产能压力 CSV",
                            data=csv_cp,
                            file_name="capacity_pressure.csv",
                            mime="text/csv",
                        )

                        # High pressure list
                        high_df = cp_df[cp_df["is_high_pressure"]].copy()
                        if not high_df.empty:
                            st.divider()
                            st.error(f"⚠️ 发现 {len(high_df)} 个高压力项（≥60分），请优先处理：")
                            high_display = high_df[[
                                "sku_key", "score",
                                "complexity_score", "volume_score", "material_score",
                                "material_count", "plan_qty",
                            ]].copy()
                            st.dataframe(high_display, use_container_width=True, height=260)
    else:
        st.divider()
        st.info(
            "👆 在上方选择场景，点击「分析产能压力」开始。\n\n"
            "提示：\n"
            "• 按 SKU：按 SKU 聚合，显示每个 SKU 的产能压力\n"
            "• 按日期：按「日期 × SKU」聚合，显示每日压力分布\n"
            "• 红色标注的项表示总分 ≥60 分，为高压力"
        )
