"""coverage_tab.py — Streamlit UI for coverage days analysis."""
from __future__ import annotations

from typing import Dict

import pandas as pd
import streamlit as st

from mike_product_calc.calc.coverage_analysis import (
    build_coverage_matrix,
    compute_coverage,
)
from mike_product_calc.calc.prep_engine import bom_expand_multi


def render_coverage_tab() -> None:
    """Render the coverage days analysis tab."""
    st.header("📊 覆盖天数分析")
    st.caption("基于输入每周销量、BOM配方和库存快照，预估SKU和原料的覆盖天数。")

    # ── Ensure workbook is loaded ──
    sheets = st.session_state.get("sheets")
    if sheets is None:
        st.warning("请先在页面加载时上传或选择 Excel 数据文件。")
        return

    # ── Discover all sellable SKUs from product output sheets ──
    sku_options = _discover_sku_keys(sheets)
    if not sku_options:
        st.info("未在产品出品表中找到任何SKU。")
        return

    # Check for Supabase client (for inventory data)
    client = st.session_state.get("supabase_client")
    inv_ready = client is not None
    if not inv_ready:
        st.warning("Supabase 未连接，无法获取库存数据。原料覆盖天数将显示为 0。")

    # ── Section 1: Weekly sales input ──
    st.subheader("📥 每周销量输入")

    # Initialize session state for weekly sales
    if "coverage_sales" not in st.session_state:
        st.session_state.coverage_sales = {sku: 0.0 for sku in sku_options}

    # Build editable input table
    sales_data = []
    for sku in sku_options:
        parts = sku.split("|")
        category = parts[0] if len(parts) > 0 else ""
        name = parts[1] if len(parts) > 1 else sku
        spec = parts[2] if len(parts) > 2 else ""
        sales_data.append({
            "品类": category,
            "品名": name,
            "规格": spec,
            "SKU Key": sku,
            "周销量": st.session_state.coverage_sales.get(sku, 0.0),
        })

    sales_df = pd.DataFrame(sales_data)

    edited_df = st.data_editor(
        sales_df,
        column_config={
            "品类": st.column_config.TextColumn("品类", disabled=True, width="small"),
            "品名": st.column_config.TextColumn("品名", disabled=True),
            "规格": st.column_config.TextColumn("规格", disabled=True, width="small"),
            "SKU Key": st.column_config.TextColumn("SKU Key", disabled=True, width="large"),
            "周销量": st.column_config.NumberColumn(
                "周销量 (份)",
                min_value=0,
                format="%.0f",
                width="small",
            ),
        },
        use_container_width=True,
        hide_index=True,
        height=min(400, 40 * (len(sales_df) + 1)),
    )

    # Sync edited values back to session state
    for _, row in edited_df.iterrows():
        sku_key = str(row["SKU Key"])
        st.session_state.coverage_sales[sku_key] = float(row["周销量"])

    # ── Compute button ──
    st.divider()
    compute_col, _ = st.columns([1, 3])
    with compute_col:
        compute_clicked = st.button("🔍 计算覆盖天数", type="primary", use_container_width=True)

    if not compute_clicked:
        return

    # ── Gather inputs ──
    weekly_sales = {
        sku: qty for sku, qty in st.session_state.coverage_sales.items()
        if qty > 0
    }
    if not weekly_sales:
        st.warning("请至少输入一个SKU的周销量（大于0）。")
        return

    with st.spinner("计算覆盖天数中..."):
        # 1. BOM expansion per SKU with qty=1
        sku_dfs: Dict[str, pd.DataFrame] = {}
        progress_text = st.empty()
        for sku_key in weekly_sales:
            progress_text.caption(f"正在展开 BOM: {sku_key}")
            try:
                df = bom_expand_multi(
                    sheets, {sku_key: 1},
                    basis="store",
                )
                sku_dfs[sku_key] = df
                if df.empty:
                    st.warning(f"SKU '{sku_key}' BOM 展开结果为空，该 SKU 可能不在产品出品表中。")
            except Exception as _bom_err:
                st.error(f"SKU '{sku_key}' BOM 展开失败: {_bom_err}")
                sku_dfs[sku_key] = pd.DataFrame()

        progress_text.caption("构建覆盖矩阵...")
        matrix = build_coverage_matrix(sku_dfs)

        with st.expander("🔍 调试信息", expanded=False):
            st.write("SKU BOM 展开结果:")
            for _sk, _df in sku_dfs.items():
                st.write(f"**{_sk}**: {len(_df)} 行")
                if not _df.empty:
                    st.dataframe(_df[["material", "gross_qty", "is_semi_finished", "is_gap"]], hide_index=True)
            st.write("覆盖矩阵:", matrix)

        if matrix.empty:
            st.warning("BOM 展开结果为空，无法计算。")
            return

        # 2. Load inventory from Supabase
        inventory: Dict[str, float] = {}
        if client:
            try:
                inv_rows = client.list_latest_inventory_rows()
                if inv_rows:
                    for r in inv_rows:
                        name = r.get("item_name", "")
                        qty = float(r.get("available_qty", 0) or 0)
                        if name:
                            inventory[name] = inventory.get(name, 0) + qty
            except Exception:
                pass

        # 3. Safety stock from session state
        safety_stock: Dict[str, float] = st.session_state.get("safety_stock_map", {})

        # 4. Detect gap materials
        gap_materials: Dict[str, str] = {}
        for sku_key in weekly_sales:
            if sku_key in sku_dfs:
                sku_df = sku_dfs[sku_key]
                for _, row in sku_df.iterrows():
                    if row["is_gap"]:
                        gap_materials[row["material"]] = row.get("gap_reason", "gap")

        # 5. Compute
        progress_text.caption("计算覆盖天数...")
        try:
            sku_cov, mat_cov = compute_coverage(
                matrix, weekly_sales, inventory,
                safety_stock=safety_stock,
                gap_materials=gap_materials,
            )
        except Exception as _cov_err:
            st.error(f"覆盖天数计算失败: {_cov_err}")
            sku_cov = pd.DataFrame()
            mat_cov = pd.DataFrame()
        progress_text.empty()

    # ── Section 2: SKU coverage results ──
    st.subheader("🏷️ SKU 覆盖天数")
    if not sku_cov.empty:
        # Style the dataframe
        display_sku = sku_cov.copy()
        display_sku["status"] = display_sku["status"].apply(
            lambda s: f"🟢 {s}" if s == "充足"
            else (f"🔵 {s}" if s == "一般"
            else (f"🟡 {s}" if s == "不足"
            else (f"🔴 {s}" if s == "紧急" else s)))
        )
        display_sku["coverage_days"] = display_sku["coverage_days"].apply(
            lambda d: f"{d:.1f}" if d is not None and d != "-" else "-"
        )
        st.dataframe(
            display_sku,
            use_container_width=True,
            hide_index=True,
            column_order=["sku_key", "weekly_sales", "limiting_material", "coverage_days", "status"],
            column_config={
                "sku_key": "SKU",
                "weekly_sales": "周销量",
                "limiting_material": "限制原料",
                "coverage_days": "覆盖天数",
                "status": "状态",
            },
        )
    else:
        st.info("无SKU覆盖数据。")

    # ── Section 3: Material coverage results ──
    st.subheader("🧪 原料覆盖天数")
    if not mat_cov.empty:
        display_mat = mat_cov.copy()
        display_mat["status"] = display_mat["status"].apply(
            lambda s: f"🟢 {s}" if s == "充足"
            else (f"🔵 {s}" if s == "一般"
            else (f"🟡 {s}" if s == "不足"
            else (f"🔴 {s}" if s == "紧急" else s)))
        )
        st.dataframe(
            display_mat,
            use_container_width=True,
            hide_index=True,
            column_order=["material", "available_qty", "safety_stock", "effective_qty",
                           "daily_consumption", "coverage_days", "status"],
            column_config={
                "material": "原料",
                "available_qty": "库存可用量",
                "safety_stock": "安全库存",
                "effective_qty": "有效可用量",
                "daily_consumption": "日消耗量",
                "coverage_days": "覆盖天数",
                "status": "状态",
            },
        )
    else:
        st.info("无原料覆盖数据。")


def _discover_sku_keys(sheets: dict) -> list[str]:
    """Discover all SKU keys from product output sheets."""
    sku_keys: list[str] = []
    seen: set[str] = set()
    for sheet_name, df in sheets.items():
        if "产品出品表" not in sheet_name:
            continue
        if not all(c in df.columns for c in ["品类", "品名", "规格"]):
            continue
        for _, row in df.iterrows():
            cat = str(row.get("品类", "")).strip()
            name = str(row.get("品名", "")).strip()
            spec = str(row.get("规格", "")).strip()
            if not name:
                continue
            key = f"{cat}|{name}|{spec}" if spec else f"{cat}|{name}"
            if key not in seen:
                seen.add(key)
                sku_keys.append(key)
    return sku_keys
