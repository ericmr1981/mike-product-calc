from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from mike_product_calc.data.inventory_view import (
    build_inventory_kpis,
    classify_inventory_row,
    is_snapshot_stale,
)

STATUS_PRIORITY = {"异常": 0, "缺货": 1, "低库存": 2, "正常": 3}


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


def render_inventory_tab(client) -> None:
    """Render storefront-first inventory dashboard tab."""
    st.title("库存管理")
    st.subheader("门店库存驾驶舱")

    reorder_point = st.number_input("低库存阈值", min_value=0.0, value=5.0, step=1.0)
    snapshot_at = client.get_latest_inventory_snapshot_at()
    parsed_snapshot_at = _parse_snapshot_time(snapshot_at)
    if parsed_snapshot_at and is_snapshot_stale(parsed_snapshot_at):
        st.warning(f"库存快照已超过 2 小时未更新（最近: {snapshot_at}）")
    elif snapshot_at is None:
        st.caption("暂无可用快照时间")

    rows = client.list_latest_inventory_rows(limit=5000)
    df = shape_inventory_table(pd.DataFrame(rows), reorder_point=float(reorder_point))

    warehouse_options = ["全部"]
    if "warehouse_code" in df.columns:
        codes = [c for c in df["warehouse_code"].dropna().astype(str).unique().tolist() if c]
        warehouse_options.extend(sorted(codes))

    filter_col_1, filter_col_2, filter_col_3 = st.columns([1, 1, 2])
    warehouse_code = filter_col_1.selectbox("仓库", options=warehouse_options, index=0)
    status = filter_col_2.selectbox("状态", options=["全部", "异常", "缺货", "低库存", "正常"], index=0)
    keyword = filter_col_3.text_input("关键字（编码/名称）", value="")

    filtered_df = apply_inventory_filters(
        df,
        status=status,
        keyword=keyword,
        warehouse_code=warehouse_code,
    )
    kpis = build_inventory_kpis(filtered_df)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总品项", kpis["total"])
    c2.metric("缺货", kpis["out_of_stock"])
    c3.metric("低库存", kpis["low_stock"])
    c4.metric("异常", kpis["abnormal"])

    if not rows:
        st.info("暂无库存快照数据")

    st.dataframe(
        filtered_df.drop(columns=["_priority"], errors="ignore"),
        use_container_width=True,
        hide_index=True,
    )
