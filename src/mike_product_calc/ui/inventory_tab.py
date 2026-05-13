from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

from mike_product_calc.data.inventory_view import (
    build_inventory_kpis,
    classify_inventory_row,
    classify_safety_status,
    is_snapshot_stale,
)

STATUS_PRIORITY = {"异常": 0, "缺货": 1, "低库存": 2, "正常": 3}
SAFETY_STATUS_OPTIONS = ["全部", "正常", "低于安全库存", "零库存"]
STATUS_COLORS = {"零库存": "#FF4444", "低于安全库存": "#FFB347", "正常": None}
HIDDEN_DEFAULT_COLUMNS = {
    "snapshot_at",
    "id",
    "batch_id",
    "category_lv1",
    "item_attribute_name",
    "warehouse_code",
    "is_negative_stock",
    "created_at",
    "rn",
}


def _is_http_404(exc: Exception) -> bool:
    """Return True if exception is an HTTP 404 error from requests."""
    if not isinstance(exc, requests.HTTPError):
        return False
    resp = getattr(exc, "response", None)
    return bool(resp is not None and resp.status_code == 404)


def shape_inventory_table(df: pd.DataFrame, reorder_point: float, safety_stock_map: dict[str, float] | None = None) -> pd.DataFrame:
    """Add status columns and return a stable priority-sorted inventory table."""
    out = df.copy()

    if "item_code" not in out.columns:
        out["item_code"] = ""
    if "available_qty" not in out.columns:
        out["available_qty"] = 0
    if "is_negative_stock" not in out.columns:
        out["is_negative_stock"] = False
    if "has_amount_mismatch" not in out.columns:
        out["has_amount_mismatch"] = False

    safety_map = safety_stock_map or {}
    out["inventory_status"] = out.apply(
        lambda row: classify_inventory_row(row.to_dict(), reorder_point=reorder_point), axis=1
    )
    out["safety_stock"] = out["item_code"].map(safety_map).fillna(0.0).astype(float)
    out["safety_status"] = out.apply(
        lambda row: classify_safety_status(
            float(row.get("available_qty") or 0),
            safety_map.get(str(row.get("item_code", ""))),
        ),
        axis=1,
    )
    out["_priority"] = out["inventory_status"].map(STATUS_PRIORITY).fillna(99).astype(int)
    out = out.sort_values(
        by=["_priority", "available_qty", "item_code"],
        ascending=[True, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    return out


def apply_inventory_filters(
    df: pd.DataFrame,
    *,
    keyword: str,
    warehouse_code: str,
    safety_status: str = "全部",
    category: str = "全部",
) -> pd.DataFrame:
    """Apply storefront filters while remaining resilient to missing columns."""
    out = df.copy()

    if "warehouse_code" not in out.columns:
        out["warehouse_code"] = ""
    if "inventory_status" not in out.columns:
        out["inventory_status"] = ""
    if "item_code" not in out.columns:
        out["item_code"] = ""
    if "item_name" not in out.columns:
        out["item_name"] = ""
    if "safety_status" not in out.columns:
        out["safety_status"] = ""

    if warehouse_code != "全部":
        out = out[out["warehouse_code"] == warehouse_code]
    if safety_status == "低于安全库存":
        out = out[out["safety_status"] == "below_safety"]
    elif safety_status == "零库存":
        out = out[out["safety_status"] == "zero_stock"]
    elif safety_status == "正常":
        out = out[out["safety_status"] == "normal"]
    if category != "全部":
        out = out[out["category_lv2"] == category]

    normalized_keyword = keyword.strip()
    if normalized_keyword:
        out = out[
            out["item_code"].astype(str).str.contains(normalized_keyword, case=False, na=False)
            | out["item_name"].astype(str).str.contains(normalized_keyword, case=False, na=False)
        ]

    return out.reset_index(drop=True)


def _parse_snapshot_time(snapshot_at: str | None) -> datetime | None:
    if not snapshot_at:
        return None
    try:
        parsed = datetime.fromisoformat(snapshot_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_warehouse_label_map(df: pd.DataFrame) -> dict[str, str]:
    """Build code->name map; fallback to code when name is missing."""
    if "warehouse_code" not in df.columns:
        return {}
    if "warehouse_name" not in df.columns:
        return {
            str(code): str(code)
            for code in df["warehouse_code"].dropna().astype(str).unique().tolist()
            if str(code)
        }

    out: dict[str, str] = {}
    for _, row in df[["warehouse_code", "warehouse_name"]].dropna(subset=["warehouse_code"]).iterrows():
        code = str(row["warehouse_code"]).strip()
        if not code:
            continue
        name = str(row["warehouse_name"]).strip() if pd.notna(row["warehouse_name"]) else ""
        out[code] = name or code
    return out


def _init_safety_stock(unique_items: list[dict]) -> dict[str, float]:
    """Initialize safety stock map from session state or build fresh from items."""
    if "inv_safety_stock_map" not in st.session_state:
        st.session_state["inv_safety_stock_map"] = {}
    existing = st.session_state["inv_safety_stock_map"]
    # Ensure every item_code has at least a default entry
    for item in unique_items:
        code = str(item.get("item_code", ""))
        if code and code not in existing:
            existing[code] = 0.0
    return existing


def _styler_for_safety(row: pd.Series) -> list[str]:
    """Return per-cell background colours based on safety status."""
    status = row.get("safety_status", "normal")
    if status == "zero_stock":
        return ["background-color: #FFDDDD" if col in ("item_code", "item_name", "available_qty", "safety_stock", "safety_status", "inventory_status") else "" for col in row.index]
    if status == "below_safety":
        return ["background-color: #FFF3CD" if col in ("item_code", "item_name", "available_qty", "safety_stock", "safety_status", "inventory_status") else "" for col in row.index]
    return ["" for _ in row.index]


def render_inventory_tab(client) -> None:
    """Render storefront-first inventory dashboard tab."""
    st.title("库存状态")

    try:
        get_snapshot_fn = getattr(client, "get_latest_inventory_snapshot_at", None)
        snapshot_at = get_snapshot_fn() if callable(get_snapshot_fn) else None
        rows = client.list_latest_inventory_rows(limit=5000)
    except Exception as exc:  # noqa: BLE001 - keep tab resilient to backend schema state
        if _is_http_404(exc):
            st.error(
                "库存快照表尚未就绪（Supabase 返回 404）。"
                "请先执行 `docs/superpowers/specs/supabase_schema.sql`，"
                "并确认 `inventory_snapshot_batches` / `v_inventory_latest_item_by_warehouse` 已可访问。"
            )
            st.info("数据库就绪后，刷新页面即可使用门店库存驾驶舱。")
            return
        st.error(f"库存数据加载失败：{exc}")
        return

    parsed_snapshot_at = _parse_snapshot_time(snapshot_at)
    if parsed_snapshot_at and is_snapshot_stale(parsed_snapshot_at):
        st.warning(f"库存快照已超过 2 小时未更新（最近: {snapshot_at}）")
    elif snapshot_at is None:
        st.caption("暂无可用快照时间")

    # ── Safety stock management ──────────────────────────────────
    unique_items_raw = pd.DataFrame(rows)[["item_code", "item_name", "unit"]].drop_duplicates(subset="item_code").to_dict("records")
    _init_safety_stock(unique_items_raw)
    safety_map = st.session_state["inv_safety_stock_map"]

    with st.expander("安全库存设置", expanded=False):
        st.caption("设置每项物料的安全库存数量，低于此值会黄色标记。设为 0 表示不监控。")
        safety_df = pd.DataFrame([
            {"品项编码": k, "品项名称": next((r["item_name"] for r in unique_items_raw if r["item_code"] == k), ""), "单位": next((r.get("unit", "") for r in unique_items_raw if r["item_code"] == k), ""), "安全库存": v}
            for k, v in safety_map.items()
        ])
        edited = st.data_editor(
            safety_df,
            column_config={
                "品项编码": st.column_config.TextColumn("品项编码", disabled=True, width="medium"),
                "品项名称": st.column_config.TextColumn("品项名称", disabled=True, width="medium"),
                "单位": st.column_config.TextColumn("单位", disabled=True, width="small"),
                "安全库存": st.column_config.NumberColumn("安全库存", min_value=0, step=1, width="small"),
            },
            use_container_width=True,
            hide_index=True,
            key="safety_stock_editor",
        )
        if st.button("保存安全库存设置", type="primary"):
            updated = dict(zip(edited["品项编码"], edited["安全库存"].fillna(0).astype(float)))
            st.session_state["inv_safety_stock_map"] = updated
            st.success("安全库存已更新")

    df = shape_inventory_table(
        pd.DataFrame(rows),
        reorder_point=5.0,
        safety_stock_map=safety_map,
    )

    warehouse_label_map = _build_warehouse_label_map(df)
    warehouse_options = ["全部", *sorted(warehouse_label_map.keys())]

    category_options = ["全部"]
    if "category_lv2" in df.columns:
        category_options = ["全部"] + sorted(
            c for c in df["category_lv2"].dropna().unique().tolist() if c
        )

    if "inv_filter_warehouse_applied" not in st.session_state:
        st.session_state["inv_filter_warehouse_applied"] = "全部"
    if "inv_filter_category_applied" not in st.session_state:
        st.session_state["inv_filter_category_applied"] = "全部"
    if "inv_filter_safety_applied" not in st.session_state:
        st.session_state["inv_filter_safety_applied"] = "全部"
    if "inv_filter_keyword_applied" not in st.session_state:
        st.session_state["inv_filter_keyword_applied"] = ""

    # Use form to avoid rerun on every filter widget change.
    with st.form("inventory_filter_form", clear_on_submit=False):
        filter_col_1, filter_col_2, filter_col_3, filter_col_4 = st.columns([1, 1, 1, 2])
        wh_default = (
            warehouse_options.index(st.session_state["inv_filter_warehouse_applied"])
            if st.session_state["inv_filter_warehouse_applied"] in warehouse_options
            else 0
        )
        category_default = (
            category_options.index(st.session_state["inv_filter_category_applied"])
            if st.session_state["inv_filter_category_applied"] in category_options
            else 0
        )
        safety_default = (
            SAFETY_STATUS_OPTIONS.index(st.session_state["inv_filter_safety_applied"])
            if st.session_state["inv_filter_safety_applied"] in SAFETY_STATUS_OPTIONS
            else 0
        )
        warehouse_code_input = filter_col_1.selectbox(
            "仓库",
            options=warehouse_options,
            index=wh_default,
            format_func=lambda x: "全部" if x == "全部" else warehouse_label_map.get(x, x),
        )
        category_input = filter_col_2.selectbox("品类", options=category_options, index=category_default)
        safety_input = filter_col_3.selectbox("安全状态", options=SAFETY_STATUS_OPTIONS, index=safety_default)
        keyword_input = filter_col_4.text_input(
            "关键字（编码/名称）",
            value=st.session_state["inv_filter_keyword_applied"],
        )
        apply_clicked = st.form_submit_button("应用筛选", type="primary")

    if apply_clicked:
        st.session_state["inv_filter_warehouse_applied"] = warehouse_code_input
        st.session_state["inv_filter_category_applied"] = category_input
        st.session_state["inv_filter_safety_applied"] = safety_input
        st.session_state["inv_filter_keyword_applied"] = keyword_input

    filtered_df = apply_inventory_filters(
        df,
        keyword=st.session_state["inv_filter_keyword_applied"],
        warehouse_code=st.session_state["inv_filter_warehouse_applied"],
        safety_status=st.session_state["inv_filter_safety_applied"],
        category=st.session_state["inv_filter_category_applied"],
    )
    kpis = build_inventory_kpis(filtered_df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总品项", kpis["total"])
    c2.metric("缺货", kpis["out_of_stock"])
    c3.metric("低库存", kpis["low_stock"])
    c4.metric("异常", kpis["abnormal"])

    total_amt = kpis["total_amount"]
    tool_amt = kpis["tool_amount"]
    other_amt = total_amt - tool_amt

    def _fmt_amt(amt: float) -> str:
        if amt >= 10000:
            return f"¥{amt / 10000:,.2f}万"
        return f"¥{amt:,.2f}"

    amt_col1, amt_col2, amt_col3 = st.columns(3)
    amt_col1.metric("库存总额", _fmt_amt(total_amt))
    amt_col2.metric("原料/包材", _fmt_amt(other_amt))
    amt_col3.metric("工具", _fmt_amt(tool_amt))

    if not rows:
        st.info("暂无库存快照数据")

    hide_cols = {"_priority", "safety_status", *HIDDEN_DEFAULT_COLUMNS}
    visible_df = filtered_df.drop(columns=list(hide_cols), errors="ignore")

    NUMERIC_COLS = ["stock_qty", "available_qty", "occupied_qty", "expected_out_qty", "expected_in_qty", "current_amount", "stock_unit_price", "safety_stock"]
    format_spec = {col: "{:.2f}" for col in NUMERIC_COLS if col in visible_df.columns}
    styled = visible_df.style.apply(_styler_for_safety, axis=1).format(format_spec, na_rep="0.00")
    st.dataframe(styled, use_container_width=True, hide_index=True)
