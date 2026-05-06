from __future__ import annotations

import re
import sys
import tempfile
import os
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd
import plotly.express as px
import streamlit as st

from mike_product_calc.calc.material_mgmt import get_categories, get_material_stats, search_materials
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
from mike_product_calc.calc.profit import sku_profit_table
from mike_product_calc.calc.recipe import build_recipe_table, _parse_spec, _calc_profit_rate
from mike_product_calc.calc.recipe_mgmt import get_product_with_recipes, build_ingredient_pool
from mike_product_calc.calc.serving_mgmt import get_final_products
from mike_product_calc.data.loader import load_workbook
from mike_product_calc.model.production import ProductionRow
from mike_product_calc.sync.excel_sync import preview_sync_raw_materials, execute_sync_raw_materials

# ── Constants ───────────────────────────────────────────────────────────────
STATUS_ACTIVE = "上线"
STATUS_INACTIVE = "下线"
CATEGORY_PACKAGING = "包材"


def _extract_id(val):
    """Extract UUID from expanded object or plain string."""
    if isinstance(val, dict):
        return val.get("id")
    return val


def _normalize_spec_payload(sp: dict) -> dict:
    """Normalize a single serving spec dict for set_serving_specs API."""
    spec_item = {
        "product_id": sp["product_id"],
        "spec_name": sp["spec_name"],
        "quantity": sp.get("quantity"),
        "main_material_id": _extract_id(sp.get("main_material_id")),
        "packaging_id": _extract_id(sp.get("packaging_id")),
        "packaging_qty": sp.get("packaging_qty", 1),
        "product_price": sp.get("product_price"),
    }
    toppings = []
    for t in sp.get("serving_spec_toppings", []):
        mat_id = _extract_id(t.get("material_id"))
        if mat_id:
            toppings.append({"material_id": mat_id, "quantity": t.get("quantity", 1)})
    if toppings:
        spec_item["_toppings"] = toppings
    return spec_item


st.set_page_config(page_title="mike-product-calc", layout="wide")

# ── Mobile full-screen CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=IBM+Plex+Mono:wght@400;600&display=swap');
    :root {
        --bg-base: #f5f7fb;
        --panel: #ffffff;
        --panel-border: #dce3ef;
        --text-strong: #1f2a37;
        --text-muted: #607085;
        --accent: #0f766e;
        --accent-soft: #e6f4f2;
        --shadow-soft: 0 10px 30px rgba(15, 23, 42, 0.06);
    }

    html, body, [class*="css"] {
        font-family: 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    }

    /* Hide Streamlit chrome */
    #MainMenu {visibility: hidden;}
    .stAppDeployButton {display: none !important;}
    footer {display: none !important;}
    header {display: none !important;}

    /* Viewport and background */
    .stApp {
        min-height: 100dvh;
        background:
            radial-gradient(circle at 10% 10%, #dff5ff 0%, rgba(223,245,255,0) 35%),
            radial-gradient(circle at 90% 20%, #e9fff0 0%, rgba(233,255,240,0) 30%),
            var(--bg-base);
    }
    .block-container {
        padding-top: 0.8rem !important;
        max-width: 1400px;
    }

    .hero-banner {
        background: linear-gradient(135deg, #113b54 0%, #0f766e 100%);
        color: #f7fbff;
        padding: 18px 20px;
        border-radius: 14px;
        margin: 6px 0 14px 0;
        box-shadow: var(--shadow-soft);
    }
    .hero-banner h2 {
        margin: 0;
        font-size: 20px;
        font-weight: 700;
        letter-spacing: 0.2px;
    }
    .hero-banner p {
        margin: 6px 0 0 0;
        color: #d9f4f2;
        font-size: 13px;
        line-height: 1.5;
    }

    /* Reduce header top padding */
    .stHeadingContainer {padding-top: 0 !important; margin-top: 0 !important;}
    section[data-testid="stBlockContainer"] > div:first-child {padding-top: 0 !important;}

    /* Card-like containers */
    div[data-testid="stVerticalBlockBorder"] {
        border: 1px solid var(--panel-border) !important;
        border-radius: 12px !important;
        box-shadow: var(--shadow-soft);
        background: var(--panel);
    }

    div[data-testid="metric-container"] {
        border: 1px solid var(--panel-border);
        border-radius: 12px;
        background: var(--panel);
        padding: 10px 14px;
        box-shadow: var(--shadow-soft);
    }
    div[data-testid="metric-container"] label {
        color: var(--text-muted) !important;
        font-weight: 500;
    }

    /* Sidebar polish */
    section[data-testid="stSidebar"] {
        border-right: 1px solid var(--panel-border);
        background: #f9fbff;
    }
    .sidebar-note {
        font-size: 12px;
        color: #5c6b7f;
        line-height: 1.5;
        padding: 10px 12px;
        background: #edf5ff;
        border: 1px solid #d6e6ff;
        border-radius: 10px;
    }

    /* Spec icon actions */
    div[class*="st-key-spec-actions-"] button {
        min-height: 32px !important;
        padding: 4px 10px !important;
        font-size: 16px !important;
        line-height: 1 !important;
        border-radius: 10px !important;
    }

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

    /* ── Responsive: mobile (≤768px) ───────────────────────────── */
    @media (max-width: 768px) {
        /* Core column collapse */
        .stColumn, div[data-testid="column"] {
            flex: 1 1 100% !important;
            width: 100% !important;
            min-width: 100% !important;
        }
        section[data-testid="stSidebar"] {display: none !important;}

        /* Metrics: 2-per-row grid */
        div[data-testid="metric-container"] {
            flex: 1 1 45% !important;
            min-width: 120px !important;
        }

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
        .hero-banner h2 {font-size: 18px !important;}
        .hero-banner p {font-size: 12px !important;}

        div[class*="st-key-spec-actions-"] {
            justify-content: flex-end !important;
            gap: 8px !important;
        }
        div[class*="st-key-spec-actions-"] button {
            min-height: 30px !important;
            min-width: 36px !important;
            padding: 4px 8px !important;
            font-size: 15px !important;
        }

        /* Tab bar: scrollable, no wrap */
        button[data-baseweb="tab"] {
            font-size: 13px !important;
            padding: 8px 6px !important;
        }
        div[data-testid="stTabs"] {
            overflow-x: auto !important;
            flex-wrap: nowrap !important;
        }

        /* Plotly charts: full width */
        .stPlotlyChart, .js-plotly-plot, .plot-container {
            max-width: 100% !important;
        }

        /* Tables: scrollable */
        .stDataFrame, div[data-testid="stDataFrame"] {
            overflow-x: auto !important;
            max-width: 100vw !important;
        }

        /* Caption text */
        .stCaption {
            font-size: 13px !important;
            line-height: 1.4 !important;
        }

        /* Form columns stack vertically */
        div[data-testid="stForm"] div[data-testid="column"] {
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }

        /* Bordered container padding */
        div[data-testid="stVerticalBlockBorder"] {
            padding: 10px !important;
        }
    }
</style>
""", unsafe_allow_html=True)

st.title("Gelato Miiix Workplace")
st.markdown(
    """
    <div class="hero-banner">
      <h2>运营数据控制台</h2>
      <p>统一查看原料、产品、配方与规格数据，并支持快速刷新缓存，减少重复操作等待。</p>
    </div>
    """,
    unsafe_allow_html=True,
)


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


# ── Supabase 初始化 ─────────────────────────────────────────

def _get_supabase_credentials() -> tuple[str, str]:
    """Read Supabase credentials from Streamlit secrets, then env fallback."""
    url = ""
    key = ""

    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["service_key"]
    except Exception:
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")

    if not url or not key:
        raise RuntimeError(
            "未找到 Supabase 凭据。请在 .streamlit/secrets.toml 中配置 [supabase] url/service_key，"
            "或设置环境变量 SUPABASE_URL / SUPABASE_SERVICE_KEY。"
        )

    return url, key


def _hydrate_cache(client) -> None:
    """Load commonly used datasets into session cache."""
    st.session_state.supabase = client
    st.session_state.cached_raw_materials = client.list_raw_materials()
    st.session_state.cached_products = client.list_products()
    st.session_state.cached_all_recipes = client.list_all_recipes()
    st.session_state.cached_all_specs = client.list_all_serving_specs()
    st.session_state.cache_loaded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


_st_supa = None
_st_sheets: dict[str, pd.DataFrame] = {}
try:
    supabase_url, supabase_key = _get_supabase_credentials()
    from mike_product_calc.data.supabase_client import MpcSupabaseClient
    _st_supa = MpcSupabaseClient(supabase_url, supabase_key)
    from mike_product_calc.data.supabase_adapter import build_sheets

    @st.cache_data(ttl=300, show_spinner="加载数据中...")
    def _cached_build_sheets(url: str, key: str) -> dict[str, pd.DataFrame]:
        """Cached wrapper: rebuilds every 5 min or when Supabase data changes."""
        _c = MpcSupabaseClient(url, key)
        return build_sheets(_c)

    _st_sheets = _cached_build_sheets(supabase_url, supabase_key)
except Exception as _e:
    st.error(f"Supabase 连接失败: {_e}")
    st.stop()

# Track supabase client and cached data in session state
if "supabase" not in st.session_state:
    _hydrate_cache(_st_supa)

with st.sidebar:
    st.subheader("操作中心")
    st.caption("更快地查看当前数据状态并执行常用刷新操作。")
    if st.button("刷新 Supabase 缓存", width="stretch"):
        with st.spinner("正在刷新缓存..."):
            st.cache_data.clear()
            _hydrate_cache(st.session_state.supabase)
        st.success("缓存已刷新")
        st.rerun()

    st.markdown("#### 当前状态")
    st.metric("原料数", len(st.session_state.cached_raw_materials))
    st.metric("产品数", len(st.session_state.cached_products))
    st.metric("规格数", len(st.session_state.cached_all_specs))
    st.caption(f"最近加载时间：{st.session_state.get('cache_loaded_at', 'N/A')}")
    st.markdown(
        """
        <div class="sidebar-note">
          建议先在“概览/校验”查看统计，再进入“原料管理/配方管理/出品规格”执行修改。
        </div>
        """,
        unsafe_allow_html=True,
    )


def _full_name(p: dict) -> str:
    """Return full name with version e.g. '木姜子甜橙 2.0'."""
    v = p.get("version", "")
    return f"{p['name']} {v}".strip() if v else p["name"]


tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["概览/校验", "原数据", "原料价格模拟器", "产销计划", "原料管理", "配方管理", "出品规格"])

with tab1:
    _heading_with_help("数据概览",
        "📌 **功能说明**：查看 Supabase 中所有数据的统计概览。\n"
        "**数据源**：Supabase (PostgreSQL)")
    _rm = st.session_state.cached_raw_materials
    _prods_c = st.session_state.cached_products
    _stats = {"total": len(_rm), "active": sum(1 for m in _rm if m.get("status") in (STATUS_ACTIVE, "已生效")), "inactive": sum(1 for m in _rm if m.get("status") not in (STATUS_ACTIVE, "已生效")), "by_category": {}}
    _final = sum(1 for p in _prods_c if p.get("is_final_product"))
    _specs_count = len(st.session_state.cached_all_specs)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("原料总数", _stats["total"])
        st.metric("最终成品", _final)
    with col2:
        st.metric("已上线", _stats["active"])
        st.metric("出品规格", _specs_count)
    with col3:
        st.metric("产品数", len(_prods_c))


with tab2:
    _heading_with_help("Supabase 数据浏览",
        "📌 **功能说明**：浏览 Supabase 中各表的数据。\n"
        "**使用方式**：下拉选择表名，查看数据内容。")
    _table_names = {
        "raw_materials": "原料表",
        "products": "产品表",
        "recipes": "配方明细",
        "serving_specs": "出品规格",
        "serving_spec_toppings": "出品规格附加配料",
    }
    _sel_table = st.selectbox("选择表", options=list(_table_names.keys()),
        format_func=lambda x: f"{_table_names.get(x, x)} ({x})")
    try:
        _table_data = _st_supa.query_table(_sel_table, limit=200)
        if _table_data:
            st.dataframe(pd.DataFrame(_table_data), use_container_width=True, height=420, hide_index=True)
        else:
            st.info("表为空")
    except Exception as e:
        st.error(f"读取失败: {e}")

# ── Tab4: 原料价格模拟器（重设计）────────────────────────────────

if "sim_store" not in st.session_state:
    st.session_state["sim_store"] = ScenarioStore()
store: ScenarioStore = st.session_state["sim_store"]

with tab3:
    _heading_with_help("原料价格模拟器",
        "**功能说明**：选产品 → 查看 SKU 规格毛利 → 展开配方明细，调整门店价格/售价，实时看毛利变化。\n"
        "**使用方法**：选择产品 → 选 SKU 规格 → 在配方表中调整门店价格或在右侧调售价 → 保存方案对比。")
    st.caption("三步递进：选择产品 → SKU 规格毛利 → 配方明细与调价")

    # ── Data source: Supabase ──
    _sheets = _st_sheets

    # ── Step 1: Select product ──────────────────────────────────────
    all_profit = sku_profit_table(_sheets, basis="store", only_status=None)
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
    profit_df_t4 = sku_profit_table(_sheets, basis=basis_t4, only_status=None)
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

    # SKU selector — key includes product name so it resets on product change
    sku_options = display_t4["product_key"].tolist()
    _sku_widget_key = f"sku_sel_{selected_product}"
    _default_sku = next(
        (pk for pk in sku_options if isinstance(pk, str) and pk.endswith("|小杯")),
        sku_options[0] if sku_options else "",
    )
    if _sku_widget_key not in st.session_state and _default_sku:
        st.session_state[_sku_widget_key] = _default_sku
    _default_sku_idx = next(
        (i for i, pk in enumerate(sku_options) if isinstance(pk, str) and pk.endswith("|小杯")),
        0,
    )
    selected_sku = st.selectbox(
        "选择 SKU 查看配方",
        options=sku_options,
        format_func=lambda pk: pk.split("|")[-1] if "|" in pk else pk,
        key=_sku_widget_key,
        index=_default_sku_idx,
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
    @st.cache_data(ttl=60, show_spinner=False)
    def _get_recipe(sku: str, basis: str) -> pd.DataFrame:
        return build_recipe_table(_st_sheets, product_key=sku, basis=basis)

    recipe_df = _get_recipe(selected_sku, basis_t4)
    # Build factory-basis recipe for brand cost (only needed when current basis is store)
    factory_cost_map: dict[str, float] = {}
    if basis_t4 != "factory":
        factory_df = _get_recipe(selected_sku, "factory")
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
                        diff = compare_scenarios(s_a, s_b, _sheets, basis=basis_t4)
                        st.dataframe(diff, use_container_width=True, height=420, hide_index=True)
# ── Tab5: 产销计划 ────────────────────────────────────────────────────

# Build SKU list from Supabase
_profit_df = sku_profit_table(_st_sheets, basis="factory", only_status=None)
_all_skus = sorted(_profit_df["product_key"].dropna().unique().tolist())

# Production SKU pool: extract from already-built sheets (no extra API calls)
_production_skus_set: set[str] = set()
for _sn in ("产品配方表_Gelato", "产品出品表_Gelato"):
    _df = _st_sheets.get(_sn)
    if _df is not None:
        for _col in ("品名", "配料"):
            if _col in _df.columns:
                for _v in _df[_col].dropna().unique():
                    _v_str = str(_v).strip()
                    if _v_str and _v_str not in ("nan", ""):
                        _production_skus_set.add(_v_str)
_production_skus = sorted(_production_skus_set)


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
                prod_rows = sales_to_production(sales_rows, _st_sheets, lead_days=lead_days)
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

    col_bom1, col_bom2, col_bom3, col_bom4 = st.columns(4)
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
                        _st_sheets, sku_qty,
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

# ── Tab5: 原料管理 ──────────────────────────────────────────

with tab5:
    _heading_with_help("原料管理",
        "📌 **功能说明**：管理所有采购原料的信息。支持 CRUD 操作，并可从 Excel 同步。\n"
        "**字段说明**：编码=品项编码（自动生成）；名称=品项名称；类别=调味酱/包材/乳制品等；"
        "单价=加价后有效采购价。")

    client = st.session_state.supabase

    # ── Stats row ──
    stats = get_material_stats(client)
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    col_s1.metric("原料总数", stats["total"])
    col_s2.metric("已上线", stats["active"])
    col_s3.metric("已下线", stats["inactive"])
    col_s4.metric("类别数", len(stats["by_category"]))

    # ── 独立上传接口 ──
    with st.expander("📤 上传原料表（Excel）", expanded=False):
        st.caption("上传包含总原料成本表的 Excel 文件。上传后预览差异再确认同步。")
        uploaded_raw = st.file_uploader("选择 Excel 文件", type=["xlsx"], key="raw_xlsx_upload")
        if uploaded_raw is not None:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(uploaded_raw.getvalue())
                tmp_path = tmp.name
            raw_wb = load_workbook(Path(tmp_path))
            diffs = preview_sync_raw_materials(raw_wb.sheets, client)
            df_diff = pd.DataFrame(diffs)
            st.dataframe(df_diff, use_container_width=True, hide_index=True)
            if st.button("确认执行同步", key="sync_upload"):
                result = execute_sync_raw_materials(raw_wb.sheets, client)
                st.success(f"同步完成: 新增 {result.inserts}, 更新 {result.updates}")
                st.cache_data.clear()
                st.rerun()

    # ── Filters (from cache) ──
    _rm_cache = st.session_state.cached_raw_materials
    _categories = ["全部"] + sorted({m["category"] for m in _rm_cache if m.get("category")})
    _status_options = ["全部", "上线", "下线"]
    if "tab5_filter_cat_applied" not in st.session_state:
        st.session_state["tab5_filter_cat_applied"] = "全部"
    if "tab5_filter_status_applied" not in st.session_state:
        st.session_state["tab5_filter_status_applied"] = "全部"
    if "tab5_filter_search_applied" not in st.session_state:
        st.session_state["tab5_filter_search_applied"] = ""

    col_f1, col_f2 = st.columns(2)
    with st.form("tab5_filter_form", clear_on_submit=False):
        with col_f1:
            filter_cat_input = st.selectbox(
                "类别过滤",
                options=_categories,
                index=_categories.index(st.session_state["tab5_filter_cat_applied"])
                if st.session_state["tab5_filter_cat_applied"] in _categories else 0,
            )
        with col_f2:
            filter_status_input = st.selectbox(
                "状态",
                options=_status_options,
                index=_status_options.index(st.session_state["tab5_filter_status_applied"])
                if st.session_state["tab5_filter_status_applied"] in _status_options else 0,
            )

        search_term_input = st.text_input(
            "搜索",
            value=st.session_state["tab5_filter_search_applied"],
            placeholder="输入原料名称...",
        )
        if st.form_submit_button("应用筛选", use_container_width=True):
            st.session_state["tab5_filter_cat_applied"] = filter_cat_input
            st.session_state["tab5_filter_status_applied"] = filter_status_input
            st.session_state["tab5_filter_search_applied"] = search_term_input

    filter_cat = st.session_state["tab5_filter_cat_applied"]
    filter_status = st.session_state["tab5_filter_status_applied"]
    search_term = st.session_state["tab5_filter_search_applied"]

    # ── Material list (filter from cache) ──
    all_materials = _rm_cache
    if filter_cat != "全部":
        all_materials = [m for m in all_materials if m.get("category") == filter_cat]
    if search_term:
        all_materials = [m for m in all_materials if search_term.lower() in (m.get("name") or "").lower()]
    if filter_status != "全部":
        all_materials = [m for m in all_materials if m.get("status") == filter_status]

    df_materials = pd.DataFrame(all_materials)
    if not df_materials.empty:
        display_cols = ["code", "name", "category", "base_price", "final_price", "unit_amount", "unit", "status"]
        available = [c for c in display_cols if c in df_materials.columns]
        df_display = df_materials[available].copy()
        df_display.columns = ["编码", "名称", "类别", "成本", "单价", "单位量", "单位", "状态"]
        st.dataframe(df_display, use_container_width=True, height=360, hide_index=True)
    else:
        st.info("暂无原料数据。请先上传 Excel 导入。")

    st.divider()

    # ── Helper: next code ──
    def _next_material_code() -> str:
        max_num = 0
        for m in st.session_state.cached_raw_materials:
            c = (m.get("code") or "").strip()
            if c.startswith("RM") and c[2:].isdigit():
                max_num = max(max_num, int(c[2:]))
        return f"RM{max_num + 1:04d}"

    # ── Tab: 新增 vs 修改 ──
    tab5_action = st.radio("操作", options=["➕ 新增原料", "✏️ 修改原料"], horizontal=True, label_visibility="collapsed")

    if tab5_action == "➕ 新增原料":
        with st.form("new_material_form", clear_on_submit=True):
            auto_code = _next_material_code()
            st.text_input("编码（自动生成）", value=auto_code, disabled=True, key="new_code_display")
            st.markdown("**必填字段**")
            col_a, col_b = st.columns(2)
            with col_a:
                new_name = st.text_input("名称 *", placeholder="必填")
                new_category = st.selectbox("类别 *", options=_categories[1:] + ["新增类别..."])
                if new_category == "新增类别...":
                    new_category = st.text_input("输入新类别")
                new_unit = st.text_input("单位 *", placeholder="必填，如 克/个/盒")
                new_unit_amount = st.number_input("单位量 *", min_value=0.0, format="%.4f", value=0.0)
            with col_b:
                new_base_price = st.number_input("加价前单价 *", min_value=0.0, format="%.4f")
                new_final_price = st.number_input("加价后单价 *", min_value=0.0001, format="%.4f")
                new_item_type = st.selectbox("品项类型 *", options=["普通", "特殊"])
                new_status = st.selectbox("状态 *", options=[STATUS_ACTIVE, STATUS_INACTIVE])
            new_notes = st.text_area("备注（可选）")

            submitted = st.form_submit_button("保存", type="primary")
            if submitted:
                errors = []
                if not new_name: errors.append("名称")
                if not new_category or new_category == "新增类别...": errors.append("类别")
                if not new_unit: errors.append("单位")
                if new_final_price <= 0: errors.append("加价后单价")
                if new_unit_amount <= 0: errors.append("单位量")
                if errors:
                    st.error(f"请填写以下必填字段: {', '.join(errors)}")
                else:
                    client.create_raw_material({
                        "code": auto_code,
                        "name": new_name,
                        "category": new_category if new_category != "新增类别..." else "",
                        "unit": new_unit,
                        "unit_amount": new_unit_amount,
                        "base_price": new_base_price,
                        "final_price": new_final_price,
                        "item_type": new_item_type,
                        "status": new_status,
                        "notes": new_notes,
                    })
                    st.success(f"已新增: {new_name} ({auto_code})")
                    st.cache_data.clear()
                    st.rerun()

    else:
        # ── Edit existing material ──
        all_names = {m["name"]: m for m in st.session_state.cached_raw_materials}
        if not all_names:
            st.info("暂无原料可修改。")
        else:
            selected_edit_name = st.selectbox("选择要修改的原料", options=list(all_names.keys()), key="tab5_edit_select")
            edit_material = all_names[selected_edit_name]

            with st.form("edit_material_form"):
                st.text_input("编码", value=edit_material.get("code", ""), disabled=True)
                col_a, col_b = st.columns(2)
                with col_a:
                    edit_name = st.text_input("名称 *", value=edit_material.get("name", ""))
                    edit_category = st.selectbox("类别 *",
                        options=_categories[1:] + ["新增类别..."],
                        index=_categories[1:].index(edit_material["category"]) + 1 if edit_material.get("category") in _categories[1:] else 0)
                    if edit_category == "新增类别...":
                        edit_category = st.text_input("输入新类别")
                    edit_unit = st.text_input("单位 *", value=edit_material.get("unit", ""))
                    edit_unit_amount = st.number_input("单位量 *", min_value=0.0, format="%.4f",
                        value=float(edit_material.get("unit_amount") or 0))
                with col_b:
                    edit_base_price = st.number_input("加价前单价 *", min_value=0.0, format="%.4f",
                        value=float(edit_material.get("base_price") or 0))
                    edit_final_price = st.number_input("加价后单价 *", min_value=0.0001, format="%.4f",
                        value=float(edit_material.get("final_price") or 0))
                    edit_item_type = st.selectbox("品项类型 *", options=["普通", "特殊"],
                        index=0 if edit_material.get("item_type") != "特殊" else 1)
                    edit_status = st.selectbox("状态 *", options=[STATUS_ACTIVE, STATUS_INACTIVE],
                        index=0 if edit_material.get("status") != STATUS_INACTIVE else 1)
                edit_notes = st.text_area("备注（可选）", value=edit_material.get("notes") or "")

                submitted = st.form_submit_button("保存修改", type="primary")
                if submitted:
                    errors = []
                    if not edit_name: errors.append("名称")
                    if not edit_category or edit_category == "新增类别...": errors.append("类别")
                    if not edit_unit: errors.append("单位")
                    if edit_final_price <= 0: errors.append("加价后单价")
                    if edit_unit_amount <= 0: errors.append("单位量")
                    if errors:
                        st.error(f"请填写以下必填字段: {', '.join(errors)}")
                    else:
                        client.update_raw_material(edit_material["id"], {
                            "name": edit_name,
                            "category": edit_category if edit_category != "新增类别..." else "",
                            "unit": edit_unit,
                            "unit_amount": edit_unit_amount,
                            "base_price": edit_base_price,
                            "final_price": edit_final_price,
                            "item_type": edit_item_type,
                            "status": edit_status,
                            "notes": edit_notes,
                        })
                        st.success(f"已更新: {edit_name}")
                        st.cache_data.clear()
                        st.rerun()

            st.markdown("---")
            col_del1, col_del2 = st.columns([1, 3])
            with col_del1:
                if st.button("🗑️ 删除此原料", type="secondary"):
                    st.session_state["confirm_delete_material"] = edit_material["id"]
                    st.rerun()
            with col_del2:
                if st.session_state.get("confirm_delete_material") == edit_material["id"]:
                    st.warning(f"确认删除「{edit_material['name']}」？此操作不可撤销。")
                    if st.button("确认删除", type="primary"):
                        client.delete_raw_material(edit_material["id"])
                        st.session_state.pop("confirm_delete_material", None)
                        st.success(f"已删除: {edit_material['name']}")
                        st.cache_data.clear()
                        st.rerun()
                    if st.button("取消"):
                        st.session_state.pop("confirm_delete_material", None)
                        st.rerun()

# ── Tab6: 配方管理 BOM ──────────────────────────────────────

with tab6:
    _heading_with_help("配方管理 (BOM)",
        "📌 **功能说明**：管理产品的配方明细。支持引用采购原料和半成品作为配料。\n"
        "**使用方式**：选择产品 → 编辑配方明细 → 保存。")

    def _split_version(name: str) -> tuple[str, str]:
        """Split '木姜子甜橙 2.0' → ('木姜子甜橙', '2.0')"""
        m = re.match(r'^(.+?)\s*(\d+\.\d+)$', name.strip())
        if m:
            return m.group(1).strip(), m.group(2)
        return name.strip(), ""

    client = st.session_state.supabase

    # ── Left column: product list ──
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("产品列表")
        _prods_cache_t6 = st.session_state.cached_products
        if not _prods_cache_t6:
            st.info("暂无产品。")
            st.stop()

        product_options = {p["name"]: p["id"] for p in _prods_cache_t6}
        selected_name = st.selectbox("选择产品", options=list(product_options.keys()), key="tab6_prod")
        selected_id = product_options[selected_name]

        # Quick actions
        st.markdown("---")
        with st.expander("➕ 新建产品", expanded=False):
            with st.form("new_product_form"):
                new_p_name = st.text_input("品名 *", placeholder="如 木姜子甜橙 2.0，版本号自动拆分")
                new_p_category = st.text_input("品类")
                new_p_type = st.selectbox("制作类型", options=["门店调配", "工厂调配"])
                new_p_final = st.checkbox("最终成品", value=True)
                if st.form_submit_button("保存"):
                    if new_p_name:
                        _name, _version = _split_version(new_p_name)
                        client.create_product({
                            "name": _name,
                            "version": _version,
                            "category": new_p_category,
                            "production_type": new_p_type,
                            "is_final_product": new_p_final,
                        })
                        st.success(f"已创建: {new_p_name}")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("品名不能为空")

        # All data is from Supabase
        st.caption("数据来源: Supabase")

    with col_right:
        # ── Product detail ──
        _prod_by_id = {p["id"]: p for p in _prods_cache_t6}
        prod_data = _prod_by_id.get(selected_id)
        if not prod_data:
            st.warning("产品不存在")
            st.stop()

        st.subheader(f"📋 {prod_data['name']}")

        # Product info form
        with st.form("edit_product_form"):
            edit_cols = st.columns(3)
            with edit_cols[0]:
                edit_name = st.text_input("品名", value=prod_data.get("name", ""))
            with edit_cols[1]:
                edit_version = st.text_input("版本", value=prod_data.get("version", ""))
            with edit_cols[2]:
                edit_category = st.text_input("品类", value=prod_data.get("category", ""))
            with edit_cols[0]:
                edit_type = st.selectbox("制作类型",
                    options=["门店调配", "工厂调配"],
                    index=0 if prod_data.get("production_type") == "门店调配" else 1)
            with edit_cols[1]:
                edit_status = st.selectbox("状态",
                    options=["上线", "下线"],
                    index=0 if prod_data.get("status") == "上线" else 1)
            with edit_cols[2]:
                edit_is_final = st.checkbox("最终成品", value=prod_data.get("is_final_product", False))

            if st.form_submit_button("保存产品信息"):
                client.update_product(selected_id, {
                    "name": edit_name,
                    "version": edit_version,
                    "category": edit_category,
                    "production_type": edit_type,
                    "status": edit_status,
                    "is_final_product": edit_is_final,
                })
                st.success("产品信息已更新")
                st.cache_data.clear()
                st.rerun()

        # ── Recipe BOM editor ──
        st.subheader("配方明细 (BOM)")

        # Load ingredient pool (from cache)
        pool = {"raw_materials": st.session_state.cached_raw_materials, "products": st.session_state.cached_products}

        # Show existing recipes
        _all_recipes_t6 = st.session_state.cached_all_recipes
        recipes = [r for r in _all_recipes_t6 if r.get("product_id") == selected_id]
        if recipes:
            recipe_rows = []
            for r in recipes:
                ing_name = ""
                if r["ingredient_source"] == "raw":
                    raw = r.get("raw_material_id")
                    if isinstance(raw, dict):
                        ing_name = raw.get("name", "")
                    else:
                        ing_name = str(raw or "")
                elif r["ingredient_source"] == "product":
                    ref = r.get("ref_product_id")
                    if isinstance(ref, dict):
                        ing_name = ref.get("name", "")
                    else:
                        ing_name = str(ref or "")

                recipe_rows.append({
                    "来源": "原料" if r["ingredient_source"] == "raw" else "半成品",
                    "配料": ing_name,
                    "用量": r.get("quantity", 0),
                })

            df_recipes = pd.DataFrame(recipe_rows)

            # ── Export ──
            col_exp1, col_exp2 = st.columns([1, 4])
            with col_exp1:
                csv_data = df_recipes.to_csv(index=False).encode("utf-8")
                st.download_button("📥 导出 CSV", data=csv_data, file_name=f"配方_{prod_data['name']}.csv", mime="text/csv")
            with col_exp2:
                if st.button("🗑️ 清空全部配方", key="clear_recipes"):
                    client.set_recipes(selected_id, [])
                    st.cache_data.clear()
                    st.rerun()

            st.dataframe(df_recipes, use_container_width=True, hide_index=True)

            # ── Delete single ingredient ──
            with st.expander("🗑️ 删除单条配料", expanded=False):
                ing_options = {f"{r['配料']} (用量: {r['用量']})": i for i, r in enumerate(recipe_rows)}
                del_choice = st.selectbox("选择要删除的配料", options=list(ing_options.keys()), key="del_ing")
                if st.button("确认删除", type="secondary"):
                    del_idx = ing_options[del_choice]
                    remaining = [r for i, r in enumerate(recipes) if i != del_idx]
                    normalized = []
                    for i, r in enumerate(remaining):
                        normalized.append({
                            "product_id": r["product_id"],
                            "ingredient_source": r["ingredient_source"],
                            "raw_material_id": _extract_id(r.get("raw_material_id")),
                            "ref_product_id": _extract_id(r.get("ref_product_id")),
                            "quantity": r["quantity"],
                            "unit_cost": None,
                            "store_unit_cost": None,
                            "sort_order": i,
                        })
                    client.set_recipes(selected_id, normalized)
                    st.success("配料已删除")
                    st.cache_data.clear()
                    st.rerun()
        else:
            st.info("暂无配方明细数据。")

        # ── Add ingredient form ──
        with st.expander("➕ 添加配料", expanded=False):
            with st.form("add_ingredient_form"):
                src_type = st.radio("配料来源", options=["原料", "半成品"], horizontal=True)

                if src_type == "原料":
                    raw_options = {f"{m['name']} ({m.get('category','')})": m["id"] for m in pool["raw_materials"]}
                    selected_raw = st.selectbox("选择原料", options=list(raw_options.keys()), key="add_raw")
                    selected_raw_id = raw_options[selected_raw]
                else:
                    prod_options = {f"{p['name']} v{p.get('version','')}": p["id"] for p in pool["products"] if p["id"] != selected_id}
                    selected_prod = st.selectbox("选择半成品", options=list(prod_options.keys()), key="add_prod")
                    selected_prod_id = prod_options[selected_prod]

                qty = st.number_input("用量", min_value=0.0, format="%.2f")

                if st.form_submit_button("添加"):
                    new_recipe = {
                        "product_id": selected_id,
                        "ingredient_source": "raw" if src_type == "原料" else "product",
                        "quantity": qty,
                        "unit_cost": None,
                        "store_unit_cost": None,
                        "sort_order": len(recipes),
                    }
                    if src_type == "原料":
                        new_recipe["raw_material_id"] = selected_raw_id
                    else:
                        new_recipe["ref_product_id"] = selected_prod_id

                    existing_recipes = [{
                        "product_id": r["product_id"],
                        "ingredient_source": r["ingredient_source"],
                        "raw_material_id": _extract_id(r.get("raw_material_id")),
                        "ref_product_id": _extract_id(r.get("ref_product_id")),
                        "quantity": r["quantity"],
                        "unit_cost": r.get("unit_cost"),
                        "store_unit_cost": r.get("store_unit_cost"),
                        "sort_order": r.get("sort_order", 0),
                    } for r in recipes]

                    existing_recipes.append(new_recipe)
                    client.set_recipes(selected_id, existing_recipes)
                    st.success("配料已添加")
                    st.cache_data.clear()
                    st.rerun()

# ── Tab7: 出品规格管理 ──────────────────────────────────────

with tab7:
    _heading_with_help("出品规格管理",
        "📌 **功能说明**：管理最终产品的售卖规格。一个产品可以有多个规格（小杯/标准杯等），"
        "每个规格可配置主原料用量和附加配料。\n"
        "**使用方式**：选择产品 → 编辑出品规格 → 保存。")

    client = st.session_state.supabase
    # ── Left column: product list ──
    col_left7, col_right7 = st.columns([1, 2])

    with col_left7:
        st.subheader("产品列表")
        _t7_prods = [p for p in st.session_state.cached_products if p.get("is_final_product")]
        if not _t7_prods:
            st.info("暂无最终成品。请先在「配方管理」中创建产品并勾选「最终成品」。")
            st.stop()

        prod_options = {p["name"]: p["id"] for p in _t7_prods}
        _t7_prod_by_id = {p["id"]: p for p in _t7_prods}
        sel_prod_name = st.selectbox("选择产品", options=list(prod_options.keys()), key="tab7_prod")
        sel_prod_id = prod_options[sel_prod_name]

    with col_right7:
        # ── Product info ──
        prod_data = _t7_prod_by_id.get(sel_prod_id, st.session_state.cached_products[0] if st.session_state.cached_products else {})
        st.subheader(f"📋 {prod_data.get('name','')} — 出品规格")

        # Load pools (from cache)
        _t7_rm = st.session_state.cached_raw_materials
        all_mat_options = {f"{m['name']} ({m.get('category','')})": m["id"] for m in _t7_rm}
        pkg_options = {rm["name"]: rm["id"] for rm in _t7_rm if rm.get("category") in (CATEGORY_PACKAGING, None)}
        _t7_all_prods = st.session_state.cached_products
        main_prod_options = {f"{p['name']} v{p.get('version','')}".rstrip("v "): p["id"] for p in _t7_all_prods}

        # Shared options for both edit and add forms
        _ingredient_cats = {"调味酱", "配料", "乳制品", "风味奶浆", "辅料", "成品", "水果"}
        _ing_mat_options = {
            f"{m['name']} ({m.get('category','')})": m["id"]
            for m in _t7_rm if m.get("category") in _ingredient_cats
        }
        _mat_unit = {m["name"]: m.get("unit", "") for m in _t7_rm}

        # ── Existing specs (from cache) ──
        specs = [s for s in st.session_state.cached_all_specs if s.get("product_id") == sel_prod_id]

        def _refresh_specs_cache():
            """Re-fetch all serving specs from Supabase into session state."""
            try:
                st.session_state.cached_all_specs = st.session_state.supabase.list_all_serving_specs()
            except Exception:
                pass

        if specs:
            for i, s in enumerate(specs):
                # Extract main material name
                main_mat_name = ""
                mm = s.get("main_material_id")
                if isinstance(mm, dict):
                    main_mat_name = mm.get("name", "")
                    ver = mm.get("version", "")
                    if ver:
                        main_mat_name += f" v{ver}"
                elif isinstance(mm, str):
                    main_mat_name = str(mm)

                # Extract topping names (separate packaging toppings from regular)
                pkg_topping_names = []
                reg_topping_names = []
                for t in s.get("serving_spec_toppings", []):
                    mat = t.get("material_id")
                    if isinstance(mat, dict):
                        _cat = mat.get("category", "")
                        _label = f"{mat.get('name','')}×{t.get('quantity',1)}"
                        if _cat == CATEGORY_PACKAGING:
                            pkg_topping_names.append(_label)
                        else:
                            reg_topping_names.append(_label)
                    elif isinstance(mat, str):
                        reg_topping_names.append(f"{mat}×{t.get('quantity',1)}")

                # Extract packaging names (from packaging_id + packaging toppings)
                pkg_names = []
                pkg = s.get("packaging_id")
                if isinstance(pkg, dict):
                    pkg_names.append(pkg.get("name", ""))
                elif isinstance(pkg, str) and pkg:
                    pkg_names.append(pkg)
                pkg_names.extend(pkg_topping_names)

                with st.container(border=True):
                    _price = s.get("product_price")
                    if _price is not None:
                        try:
                            _price_display = " — ¥" + "{:.2f}".format(float(_price))
                        except (TypeError, ValueError):
                            _price_display = ""
                    else:
                        _price_display = ""
                    st.markdown("**" + s["spec_name"] + "**" + _price_display)
                    if main_mat_name:
                        st.caption(f"主原料: {main_mat_name} × {s.get('quantity', '')} 克")
                    if pkg_names:
                        st.caption(f"包材: {', '.join(pkg_names)}")
                    if reg_topping_names:
                        st.caption(f"附加配料: {', '.join(reg_topping_names)}")

                    with st.container(horizontal=True, horizontal_alignment="right", key=f"spec-actions-{s['id']}"):
                        if st.button("✏️", key=f"edit_{s['id']}", help="编辑规格"):
                            st.session_state["_editing_spec"] = s["id"]
                            st.rerun()
                        if st.button("🗑️", key=f"del_{s['id']}", help="删除规格"):
                            remaining = [sp for sp in specs if sp["id"] != s["id"]]
                            normalized = [_normalize_spec_payload(sp) for sp in remaining]
                            client.set_serving_specs(sel_prod_id, normalized)
                            _refresh_specs_cache()
                            st.cache_data.clear()
                            st.rerun()

                    # ── Edit form (inline, below spec details) ──
                    if st.session_state.get("_editing_spec") == s["id"]:
                        st.markdown("---")
                        # Pre-fill: current packaging names (from packaging_id + 包材 toppings)
                        _edit_pkg_names = []
                        _pkg = s.get("packaging_id")
                        if isinstance(_pkg, dict) and _pkg.get("name"):
                            _edit_pkg_names.append(_pkg["name"])
                        for _t in s.get("serving_spec_toppings", []):
                            _m = _t.get("material_id")
                            if isinstance(_m, dict) and _m.get("category") == CATEGORY_PACKAGING and _m.get("name"):
                                _edit_pkg_names.append(_m["name"])
                        # Pre-fill: current toppings (non-包材 items)
                        _edit_topping_rows = []
                        for _t in s.get("serving_spec_toppings", []):
                            _m = _t.get("material_id")
                            if isinstance(_m, dict) and _m.get("category") != CATEGORY_PACKAGING:
                                _tk = f"{_m['name']} ({_m.get('category','')})"
                                if _tk in _ing_mat_options:
                                    _edit_topping_rows.append({"配料": _tk, "用量 (克/个/毫升)": _t.get("quantity", 1)})

                        with st.form(key=f"edit_form_{s['id']}"):
                            _edit_spec_name = st.text_input("规格名", value=s["spec_name"])
                            _col1, _col2 = st.columns(2)
                            with _col1:
                                # Pre-select main material
                                _mm = s.get("main_material_id")
                                _mm_key = ""
                                if isinstance(_mm, dict):
                                    _v = _mm.get("version", "")
                                    _mm_key = f"{_mm['name']} v{_v}" if _v else _mm["name"]
                                _mm_idx = list(main_prod_options.keys()).index(_mm_key) if _mm_key in main_prod_options else 0
                                _edit_main_prod = st.selectbox(
                                    "主原料 *", options=list(main_prod_options.keys()),
                                    index=_mm_idx, key=f"edit_main_{s['id']}",
                                )
                                _edit_main_qty = st.number_input(
                                    "主原料用量 (克)", min_value=0.0, format="%.1f",
                                    value=float(s.get("quantity", 0) or 0), key=f"edit_qty_{s['id']}",
                                )
                            with _col2:
                                _edit_pkgs = st.multiselect(
                                    CATEGORY_PACKAGING, options=list(pkg_options.keys()),
                                    default=_edit_pkg_names, key=f"edit_pkg_{s['id']}",
                                )
                                _edit_price = st.number_input(
                                    "定价 (元)", min_value=0.0, format="%.2f",
                                    value=float(s.get("product_price", 0) or 0), key=f"edit_price_{s['id']}",
                                )

                            st.markdown("**附加配料**")
                            _edit_topping_df = pd.DataFrame(
                                _edit_topping_rows or [{"配料": "", "用量 (克/个/毫升)": 0.0}]
                            )
                            _edit_topping_edited = st.data_editor(
                                _edit_topping_df, num_rows="dynamic",
                                use_container_width=True, hide_index=True,
                                column_config={
                                    "配料": st.column_config.SelectboxColumn(
                                        "配料", options=list(_ing_mat_options.keys()), required=True,
                                    ),
                                    "用量 (克/个/毫升)": st.column_config.NumberColumn("用量", min_value=0.0, format="%.1f"),
                                },
                                key=f"edit_tops_{s['id']}",
                            )

                            _submitted = st.form_submit_button("保存修改", type="primary")
                            if _submitted:
                                # ── Collect packaging ──
                                _edit_pkg_items = []
                                for _pn in _edit_pkgs:
                                    _edit_pkg_items.append({
                                        "material_id": pkg_options[_pn], "quantity": 1,
                                    })
                                _edit_pkg_id = _edit_pkg_items[0]["material_id"] if _edit_pkg_items else None
                                _edit_pkg_toppings = _edit_pkg_items[1:] if len(_edit_pkg_items) > 1 else []

                                # ── Collect toppings ──
                                _edit_topping_data = []
                                for _, _r in _edit_topping_edited.iterrows():
                                    _mn = str(_r.get("配料", "")).strip()
                                    _q = float(_r.get("用量 (克/个/毫升)", 0) or 0)
                                    if _mn and _mn in _ing_mat_options and _q > 0:
                                        _edit_topping_data.append({
                                            "material_id": _ing_mat_options[_mn], "quantity": _q,
                                        })

                                # ── Build full payload (all specs + edited one) ──
                                _edit_payload = []
                                for _sp in specs:
                                    if _sp["id"] == s["id"]:
                                        # Replaced with edited version
                                        _all_tops = _edit_pkg_toppings + _edit_topping_data
                                        _edit_payload.append({
                                            "product_id": sel_prod_id,
                                            "spec_name": _edit_spec_name,
                                            "quantity": _edit_main_qty,
                                            "main_material_id": main_prod_options[_edit_main_prod],
                                            "packaging_id": _edit_pkg_id,
                                            "packaging_qty": 1,
                                            "product_price": _edit_price,
                                            **({"_toppings": _all_tops} if _all_tops else {}),
                                        })
                                    else:
                                        _edit_payload.append(_normalize_spec_payload(_sp))

                                client.set_serving_specs(sel_prod_id, _edit_payload)
                                st.session_state.pop("_editing_spec", None)
                                _refresh_specs_cache()
                                st.cache_data.clear()
                                st.rerun()
        else:
            st.info("暂无出品规格。使用下方表单添加。")

        st.divider()

        # ── Add new spec (collapsed by default) ──
        with st.expander("➕ 新增出品规格", expanded=False):
            with st.form("add_spec_form7"):
                new_spec_name = st.selectbox("规格名", options=["小杯", "标准杯", "华夫蛋筒", "华夫碗", "自定义..."],
                    key="new_spec_name")
                if new_spec_name == "自定义...":
                    new_spec_name = st.text_input("输入自定义规格名", key="custom_spec_name")

                col_q1, col_q2 = st.columns(2)
                with col_q1:
                    new_main_prod = st.selectbox(
                        "主原料 *", options=list(main_prod_options.keys()),
                        index=list(main_prod_options.keys()).index(sel_prod_name) if sel_prod_name in main_prod_options else 0,
                        key="new_main_prod")
                    new_main_qty = st.number_input("主原料用量 (克)", min_value=0.0, format="%.1f", value=120.0)
                with col_q2:
                    selected_pkgs = st.multiselect(
                        CATEGORY_PACKAGING, options=list(pkg_options.keys()), key="new_pkg"
                    )
                    new_price = st.number_input("定价 (元)", min_value=0.0, format="%.2f", value=0.0, key="new_spec_price")

                st.markdown("**附加配料**")
                topping_default = pd.DataFrame([{"配料": "", "用量 (克/个/毫升)": 0.0}])
                topping_edited = st.data_editor(
                    topping_default, num_rows="dynamic",
                    use_container_width=True, hide_index=True,
                    column_config={
                        "配料": st.column_config.SelectboxColumn(
                            "配料", options=list(_ing_mat_options.keys()), required=True,
                        ),
                        "用量 (克/个/毫升)": st.column_config.NumberColumn("用量", min_value=0.0, format="%.1f"),
                    },
                    key="topping_editor",
                )
                # Show units for selected toppings below the editor
                if topping_edited is not None and not topping_edited.empty:
                    _unit_hints = []
                    for _, _r in topping_edited.iterrows():
                        _mn = str(_r.get("配料", "")).strip()
                        if _mn:
                            _rn = _mn.split(" (")[0].strip()
                            _u = _mat_unit.get(_rn, "")
                            _q = _r.get("用量 (克/个/毫升)", 0)
                            if _q and _u:
                                _unit_hints.append(f"{_rn}: {_q} {_u}")
                    if _unit_hints:
                        st.caption("📏 " + " | ".join(_unit_hints))

                if st.form_submit_button("保存规格", type="primary"):
                    # ── Collect packaging data ──
                    pkg_items = []
                    for pkg_name in selected_pkgs:
                        pkg_items.append({
                            "material_id": pkg_options[pkg_name],
                            "quantity": 1,
                        })
                    new_pkg_id = pkg_items[0]["material_id"] if pkg_items else None
                    pkg_toppings = pkg_items[1:] if len(pkg_items) > 1 else []
                    new_main_id = main_prod_options.get(new_main_prod)

                    # ── Collect topping data from editor ──
                    topping_data = []
                    _qty_col = "用量 (克/个/毫升)"
                    for _, row in topping_edited.iterrows():
                        mat_name = str(row.get("配料", "")).strip()
                        qty = float(row.get(_qty_col, 0) or 0)
                        if mat_name and mat_name in _ing_mat_options and qty > 0:
                            topping_data.append({
                                "material_id": _ing_mat_options[mat_name],
                                "quantity": qty,
                            })

                    # ── Preserve existing specs ──
                    existing_payload = [_normalize_spec_payload(sp) for sp in specs]

                    # ── New spec ──
                    all_toppings = pkg_toppings + topping_data
                    new_spec = {
                        "product_id": sel_prod_id,
                        "spec_name": new_spec_name,
                        "quantity": new_main_qty,
                        "main_material_id": new_main_id,
                        "packaging_id": new_pkg_id,
                        "packaging_qty": 1,
                        "product_price": new_price,
                    }
                    if all_toppings:
                        new_spec["_toppings"] = all_toppings
                    existing_payload.append(new_spec)

                    client.set_serving_specs(sel_prod_id, existing_payload)
                    _refresh_specs_cache()
                    st.success(f"已新增规格: {new_spec_name}")
                    st.cache_data.clear()
                    st.rerun()
