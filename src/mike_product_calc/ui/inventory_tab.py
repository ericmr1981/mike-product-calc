from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

from mike_product_calc.data.inventory_view import (
    build_inventory_kpis,
    classify_inventory_row,
    is_snapshot_stale,
)

STATUS_PRIORITY = {"异常": 0, "缺货": 1, "低库存": 2, "正常": 3}
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


def shape_inventory_table(df: pd.DataFrame, reorder_point: float) -> pd.DataFrame:
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

    out["inventory_status"] = out.apply(
        lambda row: classify_inventory_row(row.to_dict(), reorder_point=reorder_point), axis=1
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
    status: str,
    keyword: str,
    warehouse_code: str,
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

    if warehouse_code != "全部":
        out = out[out["warehouse_code"] == warehouse_code]
    if status != "全部":
        out = out[out["inventory_status"] == status]

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


def render_inventory_tab(client) -> None:
    """Render storefront-first inventory dashboard tab."""
    st.title("库存状态")

    reorder_point = st.number_input("低库存阈值", min_value=0.0, value=5.0, step=1.0)
    try:
        snapshot_at = client.get_latest_inventory_snapshot_at()
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

    df = shape_inventory_table(pd.DataFrame(rows), reorder_point=float(reorder_point))

    warehouse_label_map = _build_warehouse_label_map(df)
    warehouse_options = ["全部", *sorted(warehouse_label_map.keys())]

    status_options = ["全部", "异常", "缺货", "低库存", "正常"]
    if "inv_filter_warehouse_applied" not in st.session_state:
        st.session_state["inv_filter_warehouse_applied"] = "全部"
    if "inv_filter_status_applied" not in st.session_state:
        st.session_state["inv_filter_status_applied"] = "全部"
    if "inv_filter_keyword_applied" not in st.session_state:
        st.session_state["inv_filter_keyword_applied"] = ""

    # Use form to avoid rerun on every filter widget change.
    with st.form("inventory_filter_form", clear_on_submit=False):
        filter_col_1, filter_col_2, filter_col_3 = st.columns([1, 1, 2])
        wh_default = (
            warehouse_options.index(st.session_state["inv_filter_warehouse_applied"])
            if st.session_state["inv_filter_warehouse_applied"] in warehouse_options
            else 0
        )
        status_default = (
            status_options.index(st.session_state["inv_filter_status_applied"])
            if st.session_state["inv_filter_status_applied"] in status_options
            else 0
        )
        warehouse_code_input = filter_col_1.selectbox(
            "仓库",
            options=warehouse_options,
            index=wh_default,
            format_func=lambda x: "全部" if x == "全部" else warehouse_label_map.get(x, x),
        )
        status_input = filter_col_2.selectbox("状态", options=status_options, index=status_default)
        keyword_input = filter_col_3.text_input(
            "关键字（编码/名称）",
            value=st.session_state["inv_filter_keyword_applied"],
        )
        apply_clicked = st.form_submit_button("应用筛选", type="primary")

    if apply_clicked:
        st.session_state["inv_filter_warehouse_applied"] = warehouse_code_input
        st.session_state["inv_filter_status_applied"] = status_input
        st.session_state["inv_filter_keyword_applied"] = keyword_input

    filtered_df = apply_inventory_filters(
        df,
        status=st.session_state["inv_filter_status_applied"],
        keyword=st.session_state["inv_filter_keyword_applied"],
        warehouse_code=st.session_state["inv_filter_warehouse_applied"],
    )
    kpis = build_inventory_kpis(filtered_df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总品项", kpis["total"])
    c2.metric("缺货", kpis["out_of_stock"])
    c3.metric("低库存", kpis["low_stock"])
    c4.metric("异常", kpis["abnormal"])

    if not rows:
        st.info("暂无库存快照数据")

    hide_cols = {"_priority", *HIDDEN_DEFAULT_COLUMNS}
    visible_df = filtered_df.drop(columns=list(hide_cols), errors="ignore")

    st.dataframe(visible_df, use_container_width=True, hide_index=True)
