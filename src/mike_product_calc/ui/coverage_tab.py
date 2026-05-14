"""coverage_tab.py — Streamlit UI for coverage days analysis."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import pandas as pd
import streamlit as st

from mike_product_calc.calc.coverage_analysis import (
    build_coverage_matrix,
    compute_coverage,
)
from mike_product_calc.calc.prep_engine import bom_expand_multi


def _coverage_state_path() -> Path:
    """Return path to coverage sales state file."""
    state_dir = Path(__file__).resolve().parents[3] / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "coverage_sales.json"


def _load_saved_sales() -> dict[str, float]:
    """Load previously saved weekly sales from state file."""
    fp = _coverage_state_path()
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_sales(sales: dict[str, float]) -> None:
    """Save weekly sales to state file."""
    fp = _coverage_state_path()
    fp.write_text(json.dumps(sales, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_material_catalog_map(sheets: dict) -> dict[str, dict]:
    """Extract material unit info from 总原料成本表 for unit conversion.

    Returns {material_name: {order_unit, unit_qty}}.
    """
    for sheet_name, df in sheets.items():
        if "总原料成本表" not in sheet_name:
            continue
        if "品项名称" not in df.columns:
            continue
        catalog: dict[str, dict] = {}
        for _, row in df.iterrows():
            name = str(row.get("品项名称", "")).strip()
            if not name:
                continue
            order_unit = str(row.get("订货单位", "")).strip() if "订货单位" in df.columns else ""
            try:
                unit_qty = float(row["单位量"]) if "单位量" in df.columns and row.get("单位量") else None
            except (ValueError, TypeError):
                unit_qty = None
            if unit_qty is not None and unit_qty > 0:
                catalog[name] = {"order_unit": order_unit, "unit_qty": unit_qty}
        return catalog
    return {}


def _convert_inventory_unit(
    inventory: dict[str, float],
    inv_units: dict[str, str],
    mat_catalog: dict[str, dict],
) -> tuple[dict[str, float], list[str]]:
    """Convert inventory quantities to base units using material catalog.

    Returns (converted_inventory, conversion_log).
    """
    converted: dict[str, float] = {}
    logs: list[str] = []
    for mat, qty in inventory.items():
        inv_unit = inv_units.get(mat, "")
        cat_info = mat_catalog.get(mat)
        if cat_info and inv_unit and inv_unit != cat_info["order_unit"]:
            new_qty = qty * cat_info["unit_qty"]
            converted[mat] = new_qty
            logs.append(
                f"{mat}: {qty} {inv_unit} → {new_qty:.2f} {cat_info['order_unit']} "
                f"(×{cat_info['unit_qty']})"
            )
        else:
            converted[mat] = qty
    return converted, logs


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

    # ── Section 1: Weekly sales input ──
    st.subheader("📥 每周销量输入")

    # Initialize session state for weekly sales
    if "coverage_sales" not in st.session_state:
        saved = _load_saved_sales()
        st.session_state.coverage_sales = {
            sku: saved.get(sku, 0.0) for sku in sku_options
        }

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

    # ── Save / Load buttons ──
    s_col1, s_col2 = st.columns([1, 5])
    with s_col1:
        if st.button("💾 保存销量", use_container_width=True):
            _save_sales(st.session_state.coverage_sales)
            st.success("每周销量已保存。")
    with s_col2:
        if st.button("📂 加载已保存销量", use_container_width=True):
            saved = _load_saved_sales()
            if saved:
                st.session_state.coverage_sales = {
                    sku: saved.get(sku, 0.0) for sku in sku_options
                }
                st.rerun()
            else:
                st.info("未找到已保存的销量数据。")

    # ── Warehouse selection (only if Supabase available) ──
    selected_warehouses: list[str] = []
    all_rows: list[dict] = []
    if inv_ready:
        try:
            all_rows = client.list_latest_inventory_rows(limit=5000)
            if all_rows:
                wh_codes = sorted(set(
                    str(r.get("warehouse_code", "")).strip()
                    for r in all_rows if r.get("warehouse_code")
                ))
                if wh_codes:
                    st.subheader("🏭 选择仓库")
                    selected_warehouses = st.multiselect(
                        "筛选库存仓库（默认全选）",
                        options=wh_codes,
                        default=wh_codes,
                    )
        except Exception:
            pass

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

        with st.expander("🔍 BOM 展开明细", expanded=False):
            for _sk, _df in sku_dfs.items():
                st.write(f"**{_sk}**: {len(_df)} 行")
                if not _df.empty:
                    show_cols = [c for c in [
                        "material", "level", "total_gross_qty", "purchase_unit",
                        "total_purchase_qty", "unit_price", "is_semi_finished",
                        "is_gap", "gap_reason"
                    ] if c in _df.columns]
                    st.dataframe(_df[show_cols], hide_index=True)
            st.write("**覆盖矩阵 (material × SKU):**")
            st.dataframe(matrix)

        if matrix.empty:
            st.warning("BOM 展开结果为空，无法计算。")
            return

        # 2. Load inventory from Supabase (with warehouse filter)
        inventory: Dict[str, float] = {}
        inv_units: Dict[str, str] = {}
        if inv_ready and all_rows:
            try:
                for r in all_rows:
                    wh = str(r.get("warehouse_code", "")).strip()
                    if selected_warehouses and wh and wh not in selected_warehouses:
                        continue
                    name = r.get("item_name", "")
                    qty = float(r.get("available_qty", 0) or 0)
                    if name:
                        inventory[name] = inventory.get(name, 0) + qty
                        inv_units[name] = str(r.get("unit", "")).strip()
            except Exception:
                pass
        elif not inv_ready:
            st.info("Supabase 未连接，无法获取库存数据。原料覆盖天数将显示为 0。")

        # 3. Convert inventory units via material catalog
        mat_catalog = _build_material_catalog_map(sheets)
        unit_logs: list[str] = []
        if mat_catalog:
            inventory, unit_logs = _convert_inventory_unit(inventory, inv_units, mat_catalog)
            if unit_logs:
                with st.expander("📐 单位转换记录", expanded=False):
                    for log in unit_logs:
                        st.write(f"- {log}")

        # 4. Safety stock from session state
        safety_stock: Dict[str, float] = st.session_state.get("safety_stock_map", {})

        # 5. Detect gap materials
        gap_materials: Dict[str, str] = {}
        for sku_key in weekly_sales:
            if sku_key in sku_dfs:
                sku_df = sku_dfs[sku_key]
                for _, row in sku_df.iterrows():
                    if row["is_gap"]:
                        gap_materials[row["material"]] = row.get("gap_reason", "gap")

        # 6. Compute
        progress_text.caption("计算覆盖天数...")

        # ── Detailed calculation log ──
        calc_log = ["### 覆盖天数计算步骤"]
        calc_log.append(f"\n**每周销量 (份/周):** {weekly_sales}")
        calc_log.append(f"\n**SKU 日销量 = 周销量 / 7:**")
        for sku, ws in weekly_sales.items():
            calc_log.append(f"  {sku}: {ws} / 7 = {ws/7:.3f} 份/天")

        calc_log.append(f"\n**原料矩阵 (每份用量, 含损耗率):**")
        for mat in matrix.index:
            for sku in matrix.columns:
                qty = matrix.loc[mat, sku]
                if qty > 0:
                    calc_log.append(f"  {mat} ← {sku}: {qty:.4f}")

        calc_log.append(f"\n**库存 (转换后):**")
        for mat, qty in sorted(inventory.items()):
            ss = safety_stock.get(mat, 0)
            effective = max(0, qty - ss)
            eff_str = f"{qty}" + (f" - {ss}(安全库存) = {effective}" if ss else "")
            calc_log.append(f"  {mat}: {eff_str}")

        calc_log.append(f"\n**日消耗量 = Σ(SKU日销量 × 每份用量):**")
        daily_rates = {}
        for mat in matrix.index:
            dr = 0
            parts = []
            for sku in matrix.columns:
                sku_dr = weekly_sales.get(sku, 0) / 7
                qty = matrix.loc[mat, sku]
                if qty > 0 and sku_dr > 0:
                    contrib = sku_dr * qty
                    dr += contrib
                    parts.append(f"{sku_dr:.3f}×{qty:.4f}={contrib:.4f}")
            if dr > 0:
                daily_rates[mat] = dr
                calc_log.append(f"  {mat}: {' + '.join(parts)} = {dr:.4f}")

        calc_log.append(f"\n**原料覆盖天数 = 有效库存 / 日消耗量:**")
        for mat, dr in sorted(daily_rates.items(), key=lambda x: x[1], reverse=True):
            avail = inventory.get(mat, 0)
            ss = safety_stock.get(mat, 0)
            effective = max(0, avail - ss)
            gap = " (gap)" if mat in gap_materials else ""
            if dr > 0:
                days = effective / dr if not gap_materials.get(mat) else None
                calc_log.append(f"  {mat}: {effective:.2f} / {dr:.4f} = {days:.1f} 天{gap}")
            else:
                calc_log.append(f"  {mat}: 未被消耗 ∞{gap}")

        calc_log.append(f"\n**SKU 覆盖天数 = min(所用原料覆盖天数):**")
        for sku in matrix.columns:
            ws = weekly_sales.get(sku, 0)
            if ws == 0:
                calc_log.append(f"  {sku}: 周销量=0, 跳过")
                continue
            sku_mats = [m for m in matrix.index if matrix.loc[m, sku] > 0 and m not in gap_materials]
            if not sku_mats:
                calc_log.append(f"  {sku}: 无可用原料（均为 gap）")
                continue
            mat_days = {}
            for m in sku_mats:
                dr = daily_rates.get(m, 0)
                if dr > 0:
                    avail = inventory.get(m, 0)
                    ss = safety_stock.get(m, 0)
                    effective = max(0, avail - ss)
                    mat_days[m] = effective / dr
                else:
                    mat_days[m] = float("inf")
            limiting = min(mat_days, key=mat_days.get)
            calc_log.append(f"  {sku}: min({mat_days}) = {mat_days[limiting]:.1f} 天 (限制原料: {limiting})")

        with st.expander("📐 计算明细", expanded=True):
            st.markdown("\n".join(calc_log))

        try:
            sku_cov, mat_cov = compute_coverage(
                matrix, weekly_sales, inventory,
                safety_stock=safety_stock,
                gap_materials=gap_materials,
            )
        except Exception as _cov_err:
            st.error(f"覆盖天数计算失败: {_cov_err}")
            import traceback
            st.code(traceback.format_exc())
            sku_cov = pd.DataFrame()
            mat_cov = pd.DataFrame()
        progress_text.empty()

    # ── Section 2: SKU coverage results ──
    st.subheader("🏷️ SKU 覆盖天数")
    if not sku_cov.empty:
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
