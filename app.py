from __future__ import annotations

import sys
import tempfile
import json
import hashlib
from datetime import date, datetime
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd
import plotly.express as px
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
from mike_product_calc.data.loader import load_workbook
from mike_product_calc.data.validator import issues_to_dataframe, validate_workbook
from mike_product_calc.calc.profit import sku_profit_table
from mike_product_calc.model.production import ProductionRow


st.set_page_config(page_title="mike-product-calc", layout="wide")

# ── Mobile full-screen CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
    /* Hide Streamlit chrome */
    #MainMenu {visibility: hidden;}
    .stAppDeployButton {display: none !important;}
    footer {display: none !important;}
    header {display: none !important;}

    /* Viewport: full-screen, no scroll outside app */
    .stApp {min-height: 100dvh;}

    /* Reduce header top padding */
    .stHeadingContainer {padding-top: 0 !important; margin-top: 0 !important;}
    section[data-testid="stBlockContainer"] > div:first-child {padding-top: 0 !important;}
    .block-container {padding-top: 0.5rem !important;}

    /* Help tip hover card */
    .help-tip {position: relative; display: inline-flex; cursor: help; margin-left: 4px; vertical-align: middle;}
    .help-icon {font-size: 18px; color: #888;}
    .help-tip:hover .help-text {visibility: visible; opacity: 1;}
    .help-text {
        visibility: hidden; opacity: 0; width: 340px;
        background: #2d2d2d; color: #f0f0f0; padding: 12px 16px; border-radius: 10px;
        font-size: 13px; line-height: 1.6; white-space: pre-wrap;
        position: absolute; bottom: 150%; left: 50%; transform: translateX(-50%);
        z-index: 9999; box-shadow: 0 6px 20px rgba(0,0,0,0.25);
        transition: opacity 0.2s ease;
        font-family: -apple-system, BlinkMacSystemFont, sans-serif;
        pointer-events: none;
    }
    .help-text::after {
        content: ''; position: absolute; top: 100%; left: 50%; margin-left: -5px;
        border: 5px solid transparent; border-top-color: #2d2d2d;
    }

    /* Responsive column collapse */
    @media (max-width: 768px) {
        .stColumn, div[data-testid="column"] {
            flex: 1 1 100% !important;
            width: 100% !important;
            min-width: 100% !important;
        }
        section[data-testid="stSidebar"] {display: none !important;}

        /* Touch-friendly controls */
        .stButton button, .stDownloadButton button {
            min-height: 44px !important;
            width: 100% !important;
        }
        .stSelectbox, .stNumberInput, .stTextInput, .stDateInput {
            width: 100% !important;
        }
        div[data-baseweb="select"] {width: 100% !important;}

        /* Bigger fonts */
        .stDataFrame td, .stDataFrame th {font-size: 14px !important;}
        .stMarkdown, .stText {font-size: 16px !important;}
        h1 {font-size: 22px !important;}
        h2 {font-size: 18px !important;}
        h3 {font-size: 16px !important;}

        /* Fix data editor overflow */
        .stDataFrame, div[data-testid="stDataFrame"] {overflow-x: auto !important;}
    }
</style>
""", unsafe_allow_html=True)

st.title("Gelato Miiix Data Foundation")
st.caption("当前版本：Excel 解析 / 校验、SKU 毛利分析（双口径）、F-002 oracle、F-003 第一版反推定价。")


def _heading_with_help(heading: str, help_text: str):
    """Subheader with a hover-triggered help card (ⓘ) on the right."""
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        f'<h3 style="margin:0;font-size:1.2rem;font-weight:600;">{heading}</h3>'
        f'<div class="help-tip"><span class="help-icon">ⓘ</span>'
        f'<span class="help-text">{help_text}</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


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
with st.expander("📁 数据文件管理（永久保存，可删除/替换）", expanded=False):
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

tab1, tab2, tab3, tab4 = st.tabs(["概览/校验", "原数据", "原料价格模拟器", "产销计划"])

with tab1:
    _heading_with_help("Workbook 概览",
        "📌 **功能说明**：上传 Excel 文件后，系统自动解析并校验所有 sheet。\n"
        "**使用方法**：上传蜜可诗产品库.xlsx，等待解析完成后查看统计与校验报告。\n"
        "**字段含义**：Sheet 数 = 工作簿中 sheet 总数；Issues = 所有校验问题数（含警告）；"
        "Errors = 高严重性问题（需优先处理）。")
    col1, col2, col3 = st.columns(3)
    col1.metric("Sheet 数", len(sheet_names))
    col2.metric("Issues", len(issues))
    col3.metric("Errors", sum(1 for i in issues if i.severity == "error"))

    st.divider()

    st.subheader("数据健康/校验报告")
    df_issues = issues_to_dataframe(issues)
    st.dataframe(df_issues, use_container_width=True, height=360, hide_index=True)

    csv = df_issues.to_csv(index=False).encode("utf-8")
    st.download_button(
        "下载 data_validation_report.csv",
        data=csv,
        file_name="data_validation_report.csv",
        mime="text/csv",
    )


with tab2:
    _heading_with_help("Sheet 浏览",
        "📌 **功能说明**：浏览工作簿中任意 sheet 的原始数据。\n"
        "**使用方法**：下拉选择 sheet 名称，查看行列数据。\n"
        "**字段含义**：Rows=数据行数；Cols=列数；表格内容即对应 sheet 的原始数据。")
    selected = st.selectbox("选择 sheet", sheet_names)
    df = wb.sheets[selected]
    st.write(f"Rows: {df.shape[0]} | Cols: {df.shape[1]}")
    st.dataframe(df.head(200), use_container_width=True, height=420, hide_index=True)

# ── Tab4: 原料价格模拟器（重设计）────────────────────────────────

if "sim_store" not in st.session_state:
    st.session_state["sim_store"] = ScenarioStore()
store: ScenarioStore = st.session_state["sim_store"]

with tab3:
    _heading_with_help("原料价格模拟器",
        "**功能说明**：选产品 → 查看 SKU 规格毛利 → 展开配方明细，调整门店价格/售价，实时看毛利变化。\n"
        "**使用方法**：选择产品 → 选 SKU 规格 → 在配方表中调整门店价格或在右侧调售价 → 保存方案对比。")
    st.caption("三步递进：选择产品 → SKU 规格毛利 → 配方明细与调价")

    # ── Step 1: Select product ──────────────────────────────────────
    all_profit = sku_profit_table(wb.sheets, basis="store", only_status=None)
    if all_profit.empty:
        st.warning("无可用毛利数据。")
        st.stop()

    # Extract product-level keys (品类|品名)
    all_pks = all_profit["product_key"].dropna().unique().tolist()
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

    # ── Step 2: SKU specs table (follows selected basis) ───────────
    profit_df_t4 = sku_profit_table(wb.sheets, basis=basis_t4, only_status=None)
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
        hide_index=True,
        column_order=["product_key", "price", "cost", "gross_margin_pct"],
        column_config={
            "product_key": "SKU",
            "price": st.column_config.NumberColumn("定价", format="%.2f"),
            "cost": st.column_config.NumberColumn("成本", format="%.2f"),
            "gross_margin_pct": "毛利率",
        },
    )

    # ── Step 3: Recipe detail + pricing ─────────────────────────────
    st.divider()
    st.markdown(f"##### 配方明细 — {selected_sku.split('|')[-1] if '|' in selected_sku else selected_sku}")

    # Build recipe table for the selected basis
    recipe_df = build_recipe_table(wb.sheets, product_key=selected_sku, basis=basis_t4)
    # Build factory-basis recipe for brand cost (only needed when current basis is store)
    factory_cost_map: dict[str, float] = {}
    if basis_t4 != "factory":
        factory_df = build_recipe_table(wb.sheets, product_key=selected_sku, basis="factory")
        if not factory_df.empty:
            for _, fr in factory_df.iterrows():
                if fr.get("level") in (2,):
                    continue
                item = str(fr.get("item", "")).strip()
                if item:
                    factory_cost_map[item] = float(fr.get("cost", 0) or 0)

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
            hide_index=True,
            column_config={
                "item": st.column_config.TextColumn("项目", disabled=True),
                "usage_qty": st.column_config.NumberColumn("用量", disabled=True, format="%.1f"),
                "cost": st.column_config.NumberColumn("成本", disabled=True, format="%.2f"),
                "spec": st.column_config.TextColumn("规格", disabled=True),
                "store_price": st.column_config.NumberColumn("门店价格", format="%.2f"),
                "brand_cost": st.column_config.NumberColumn("品牌成本", disabled=True, format="%.2f"),
                "profit_rate": st.column_config.NumberColumn("利润率(%)", disabled=True, format="%.1f"),
                "level": None,
                "is_semi": None,
            },
        )

        # Recalculate costs based on edited store_price
        total_cost = 0.0
        brand_cost_total = 0.0
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

            # Cost adjustment depends on basis:
            # - store: cost = store_price × usage_qty / spec → proportional to store_price
            # - factory: cost = brand_cost × usage_qty / spec → independent of store_price
            if basis_t4 == "store" and orig_sp_f > 0 and abs(orig_sp_f - new_sp_f) > 0.0001:
                row["cost"] = round(float(orig_cost) * (new_sp_f / orig_sp_f), 2)
            # else keep original cost (factory basis doesn't adjust with store_price)

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

            # Brand cost: factory-basis costs (only meaningful in store basis)
            if basis_t4 == "store":
                item_name = str(row.get("item", "")).strip()
                brand_cost_total += factory_cost_map.get(item_name, 0) or 0

        brand_profit = total_cost - brand_cost_total if basis_t4 == "store" else 0.0

        # ── Pricing & margin KPI cards ──────────────────────────────
        default_price = float(sku_df[sku_df["product_key"] == selected_sku]["price"].iloc[0]) if not sku_df[sku_df["product_key"] == selected_sku].empty else 0.0
        price_key = f"t4_sku_price_{selected_sku}"
        current_price = st.session_state.get(price_key, default_price)

        show_brand = basis_t4 == "store"
        cols = st.columns(4 if show_brand else 3)
        with cols[0]:
            new_price = st.number_input("门店售价（元）", value=float(current_price), step=1.0, min_value=0.0, key=f"t4_price_{selected_sku}")
            st.session_state[price_key] = new_price
        with cols[1]:
            gross_profit = new_price - total_cost
            st.metric("总成本（元）", f"{total_cost:.2f}")
        if show_brand:
            with cols[2]:
                st.metric("品牌成本（元）", f"{brand_cost_total:.2f}", delta=f"品牌利润 {brand_profit:.2f}")
            with cols[3]:
                margin_rate = (gross_profit / new_price * 100) if new_price > 0 else 0
                st.metric("毛利", f"{gross_profit:.2f} 元", delta=f"{margin_rate:.1f}%")
        else:
            with cols[2]:
                margin_rate = (gross_profit / new_price * 100) if new_price > 0 else 0
                st.metric("毛利", f"{gross_profit:.2f} 元", delta=f"{margin_rate:.1f}%")

        # ── Cost breakdown charts ────────────────────────────────────
        st.divider()
        st.markdown("##### 成本拆解")

        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            # SKU cost breakdown: donut chart
            sku_chart_rows = [r for r in recalc_data if r.get("level") != 2 and float(r.get("cost", 0) or 0) > 0]
            if sku_chart_rows:
                sku_df = pd.DataFrame([
                    {"项目": r["item"], "成本": float(r["cost"])} for r in sku_chart_rows
                ])
                colors1 = ["#1a1a1a", "#94c1ff", "#82e0aa", "#a9cce3", "#f4b8d0", "#d4a8e0"]
                fig1 = px.pie(sku_df, values="成本", names="项目", title=None, hole=0.55,
                              color_discrete_sequence=colors1)
                fig1.update_traces(textposition="outside", textinfo="percent",
                                   showlegend=True, legendgroup="sku",
                                   textfont=dict(color="#333", size=11),
                                   marker=dict(line=dict(color="white", width=2)),
                                   domain=dict(x=[0, 0.6]))
                fig1.update_layout(
                    height=260, margin=dict(t=10, b=10, l=0, r=0),
                    legend=dict(orientation="v", yanchor="middle", y=0.5,
                                xanchor="left", x=0.85, font=dict(size=11, color="#333")),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#333"),
                )
                st.plotly_chart(fig1, use_container_width=True)

        with col_chart2:
            # Semi-product cost breakdown: donut chart
            sub_rows = [r for r in recalc_data if r.get("level") == 2 and float(r.get("cost", 0) or 0) > 0]
            if sub_rows:
                semi_df = pd.DataFrame([
                    {"项目": r["item"], "成本": float(r["cost"])} for r in sub_rows
                ])
                colors2 = ["#94c1ff", "#82e0aa", "#a9cce3", "#f4b8d0", "#d4a8e0"]
                fig2 = px.pie(semi_df, values="成本", names="项目", title=None, hole=0.55,
                              color_discrete_sequence=colors2)
                fig2.update_traces(textposition="outside", textinfo="percent",
                                   showlegend=True,
                                   textfont=dict(color="#333", size=11),
                                   marker=dict(line=dict(color="white", width=2)),
                                   domain=dict(x=[0, 0.6]))
                fig2.update_layout(
                    height=260, margin=dict(t=10, b=10, l=0, r=0),
                    legend=dict(orientation="v", yanchor="middle", y=0.5,
                                xanchor="left", x=0.85, font=dict(size=11, color="#333")),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#333"),
                )
                st.plotly_chart(fig2, use_container_width=True)

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
                        st.dataframe(diff, use_container_width=True, height=420, hide_index=True)
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


with tab4:
    _init_session()
    _heading_with_help("📋 Step 1: 销售计划录入",
        "📌 **功能说明**：① 录入销售计划 → ② 生成生产计划 → ③ 展开 BOM 计算原料需求 → ④ 成本核算。\n"
        "**使用方法**：从上至下按步骤操作。\n"
        "**销售SKU**=产品毛利表成品；**生产项**=配方中的冰激淋基底。")
    plans: dict = st.session_state["production_plans"]
    SALES_KEY = "销售计划_当前"
    PROD_KEY = "生产计划_当前"

    # ════════════════════════════════════════════════════════════════════
    # Step 1: 销售计划录入
    # ════════════════════════════════════════════════════════════════════
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
        height=300, hide_index=True,
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
        height=300, hide_index=True,
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
                display, use_container_width=True, height=500, hide_index=True,
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
                st.dataframe(gap_display, use_container_width=True, height=400, hide_index=True)

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
                st.dataframe(by_level, use_container_width=True, hide_index=True)

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
        }), use_container_width=True, hide_index=True)

    elif run_expand and bom_result is not None and bom_result.empty:
        st.info("BOM 展开结果为空（可能选中的 SKU 在出品表中无配料数据）。")
    else:
        st.info("👆 完成 Step 2 后，在上方设置参数并点击「展开 BOM」，查看原料需求与成本。")

