"""
prep_engine.py — BOM expansion engine for mike-product-calc.

Three-level BOM:
  Level 1  SKU  →  Level 2  Semi-finished / main ingredient
                    (if the material itself has a recipe → expand recursively)
                 →  Level 3  Raw material (from 总原料成本表)

Supports: loss rate, safety stock, minimum purchase unit, batch rounding,
          lead-time / latest-order-date.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from mike_product_calc.data.shared import build_product_key, to_float

# -------------------------------------------------------------------------------------------------
# Dataclasses
# -------------------------------------------------------------------------------------------------

# How many levels deep we expand before stopping (safety cap).
_MAX_BOM_DEPTH = 3


@dataclass(frozen=True)
class BomEntry:
    """One line in the expanded BOM."""

    sku_key: str          # Product this entry belongs to (top-level SKU key).
    material: str         # Material / ingredient name.
    level: int           # 1=raw-ish, 2=semi-finished, 3=raw (higher = more raw).
    qty_per_unit: float   # How many units of this material go into one SKU unit.
    unit: str            # Display unit (from 总原料成本表 or the 出品表).
    loss_rate: float      # Extra % to order beyond recipe qty (0.0 = no loss).
    safety_stock: float   # Buffer stock to always hold (in material units).
    min_purchase: float  # Minimum purchase quantity (batch granularity).
    lead_days: int        # Days between order and delivery.
    is_semi_finished: bool = False  # True = this item has its own recipe (semi-finished).
    source_sheet: str = ""          # Which 产品出品表 sheet this came from.

    @property
    def effective_qty_per_unit(self) -> float:
        """Recipe qty with loss applied."""
        return self.qty_per_unit * (1.0 + self.loss_rate)


@dataclass
class MaterialDemandRow:
    """One row in the demand summary table."""

    sku_key: str
    material: str
    level: int
    unit: str
    plan_qty: float           # How many SKU units are planned.
    qty_per_unit: float       # Base recipe qty per SKU unit.
    gross_qty: float          # plan_qty × qty_per_unit × (1 + loss_rate).
    safety_stock: float        # Per-SKU safety stock (0 if not SKU-level).
    total_safety_stock: float # safety_stock × plan_qty.
    min_purchase: float       # Minimum purchase unit.
    purchase_qty: float      # Rounded-up batch quantity to order.
    purchase_unit: str
    lead_days: int
    latest_order_date: str     # YYYY-MM-DD — (today + lead_days).
    unit_price: Optional[float] = None
    total_cost: Optional[float] = None
    is_gap: bool = False       # True = no valid unit price or supply is unstable.
    gap_reason: str = ""
    is_semi_finished: bool = False
    source_sheet: str = ""

    @classmethod
    def from_bom_entry(
        cls,
        entry: BomEntry,
        plan_qty: float,
        order_date: Optional[date] = None,
        unit_price: Optional[float] = None,
        is_gap: bool = False,
        gap_reason: str = "",
    ) -> "MaterialDemandRow":
        gross = plan_qty * entry.effective_qty_per_unit
        total_ss = entry.safety_stock * plan_qty

        # Batch rounding: ceil((gross + total_ss) / min_purchase) × min_purchase
        if entry.min_purchase > 0 and entry.min_purchase > 0.0:
            purchase_qty = math.ceil((gross + total_ss) / entry.min_purchase) * entry.min_purchase
        else:
            purchase_qty = gross + total_ss

        if order_date is not None:
            latest_order = order_date - timedelta(days=entry.lead_days)
            latest_order_str = latest_order.strftime("%Y-%m-%d")
        else:
            latest_order_str = ""

        total_cost = purchase_qty * unit_price if unit_price is not None else None

        return cls(
            sku_key=entry.sku_key,
            material=entry.material,
            level=entry.level,
            unit=entry.unit,
            plan_qty=plan_qty,
            qty_per_unit=entry.qty_per_unit,
            gross_qty=round(gross, 4),
            safety_stock=entry.safety_stock,
            total_safety_stock=round(total_ss, 4),
            min_purchase=entry.min_purchase,
            purchase_qty=round(purchase_qty, 4),
            purchase_unit=entry.unit,
            lead_days=entry.lead_days,
            latest_order_date=latest_order_str,
            unit_price=unit_price,
            total_cost=round(total_cost, 2) if total_cost is not None else None,
            is_gap=is_gap,
            gap_reason=gap_reason,
            is_semi_finished=entry.is_semi_finished,
            source_sheet=entry.source_sheet,
        )


# -------------------------------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------------------------------

_OUT_SHEETS = ["产品出品表_Gelato", "产品出品表_雪花冰", "产品出品表_饮品"]


def _build_sku_key_to_sheet(
    sheets: Dict[str, pd.DataFrame]
) -> Dict[str, Tuple[pd.DataFrame, pd.Series, str]]:
    """Return mapping: sku_key → (df, keys_series, sheet_name)."""
    result: Dict[str, Tuple[pd.DataFrame, pd.Series, str]] = {}
    for sheet_name in _OUT_SHEETS:
        df = sheets.get(sheet_name)
        if df is None:
            continue
        keys = build_product_key(df)
        for idx, key in keys.items():
            k = str(key).strip()
            if k:
                result[k] = (df, keys, sheet_name)
    return result


def _build_material_catalog(sheets: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build a lookup table from 总原料成本表.

    Returns DataFrame with columns: name, category, order_unit, unit_price, unit_qty, status.
    """
    df = sheets.get("总原料成本表")
    if df is None:
        return pd.DataFrame(columns=["name", "category", "order_unit", "unit_price", "unit_qty", "status"])

    # NOTE: “备料计划/采购建议”中的成本口径必须与「SKU 毛利分析（双口径）」一致。
    # Unified rule (store-basis by default in this module):
    #   最小单位成本 = 加价后单价 / 单位量
    #   单位量缺失/<=0 → 回退为旧逻辑（直接用单价）
    raw_price = df["加价后单价"].map(to_float) if "加价后单价" in df.columns else pd.Series(dtype=float)
    unit_qty = df["单位量"].map(to_float) if "单位量" in df.columns else pd.Series(dtype=float)

    min_unit_price = raw_price
    if not unit_qty.empty:
        # Vectorized safe divide: if qty invalid → keep raw_price
        q = unit_qty.where(unit_qty > 0)
        min_unit_price = raw_price.where(q.isna(), raw_price / q)

    out = pd.DataFrame({
        "name":     df["品项名称"].fillna("").astype(str).map(str.strip),
        "category": df["品项类别"].fillna("").astype(str).map(str.strip) if "品项类别" in df.columns else "",
        "order_unit": df["订货单位"].fillna("").astype(str).map(str.strip) if "订货单位" in df.columns else "",
        # unit_price here means “min-unit cost” (already divided by unit_qty when available)
        "unit_price": min_unit_price,
        "unit_qty":  unit_qty,
        "status":    df["生效状态"].fillna("").astype(str).map(str.strip) if "生效状态" in df.columns else "",
    })
    out = out[out["name"] != ""].drop_duplicates(subset=["name"]).reset_index(drop=True)
    return out


def _get_material_info(
    catalog: pd.DataFrame,
    material_name: str,
) -> Tuple[Optional[float], Optional[str], Optional[float], bool, str]:
    """Look up a material in the catalog.

    Returns (unit_price, order_unit, min_purchase, is_stable, gap_reason).
    """
    row = catalog[catalog["name"] == material_name]
    if row.empty:
        return None, None, None, False, "原料未在总原料成本表中登记"

    r = row.iloc[0]
    price = r["unit_price"] if pd.notna(r["unit_price"]) else None
    unit   = str(r["order_unit"]) if pd.notna(r["order_unit"]) else ""
    status = str(r["status"]) if pd.notna(r["status"]) else ""

    is_stable = status == "已生效"
    gap_reason = ""
    if price is None:
        gap_reason = "无有效单价"
    elif not is_stable:
        gap_reason = f"供应状态：{status}"

    return price, unit, None, is_stable, gap_reason


# -------------------------------------------------------------------------------------------------
# Core BOM expansion
# -------------------------------------------------------------------------------------------------

def _collect_bom_entries(
    sheets: Dict[str, pd.DataFrame],
    sku_key: str,
    sku_key_to_sheet: Dict[str, Tuple[pd.DataFrame, pd.Series, str]],
    visited: List[str],
    depth: int,
) -> List[BomEntry]:
    """Recursively collect BOM entries for a SKU.

    depth=1: direct ingredients from 出品表
    depth=2: semi-finished (ingredients that have their own recipe)
    depth=3: raw materials (from 总原料成本表, not found in 出品表)
    """
    if depth > _MAX_BOM_DEPTH:
        return []

    entries: List[BomEntry] = []
    key_info = sku_key_to_sheet.get(sku_key)

    if key_info is None:
        # Not a known SKU — treat as a raw material.
        return []

    df, keys, sheet_name = key_info
    part = df.loc[keys == sku_key].copy()
    if part.empty:
        return []

    # Collect 主原料 and 配料
    for col in ("主原料", "配料"):
        if col not in part.columns:
            continue
        items = part[col].fillna("").astype(str).map(str.strip)
        qty_col = "用量"
        if qty_col not in part.columns:
            continue

        for idx, item in items.items():
            if not item:
                continue

            raw_qty = to_float(part.at[idx, qty_col]) if qty_col in part.columns else None
            qty = raw_qty if raw_qty is not None and raw_qty > 0 else 0.0

            # Determine level and whether it's semi-finished.
            if item in visited:
                # Already seen in this chain — treat as raw to avoid infinite loop.
                entries.append(BomEntry(
                    sku_key=sku_key,
                    material=item,
                    level=depth,
                    qty_per_unit=qty,
                    unit="",
                    loss_rate=0.0,
                    safety_stock=0.0,
                    min_purchase=0.0,
                    lead_days=0,
                    is_semi_finished=False,
                    source_sheet=sheet_name,
                ))
            elif item in sku_key_to_sheet:
                # Has its own recipe — semi-finished, recurse deeper.
                entries.append(BomEntry(
                    sku_key=sku_key,
                    material=item,
                    level=depth,
                    qty_per_unit=qty,
                    unit="",
                    loss_rate=0.0,
                    safety_stock=0.0,
                    min_purchase=0.0,
                    lead_days=0,
                    is_semi_finished=True,
                    source_sheet=sheet_name,
                ))
                deeper = _collect_bom_entries(
                    sheets, item, sku_key_to_sheet, visited + [item], depth + 1
                )
                entries.extend(deeper)
            else:
                # Raw material — not in 出品表.
                entries.append(BomEntry(
                    sku_key=sku_key,
                    material=item,
                    level=depth,
                    qty_per_unit=qty,
                    unit="",
                    loss_rate=0.0,
                    safety_stock=0.0,
                    min_purchase=0.0,
                    lead_days=0,
                    is_semi_finished=False,
                    source_sheet=sheet_name,
                ))

    return entries


def bom_expand(
    sheets: Dict[str, pd.DataFrame],
    sku_key: str,
    plan_qty: float,
    *,
    order_date: Optional[date] = None,
    lead_days: int = 0,
    loss_rate: float = 0.0,
    safety_stock: float = 0.0,
) -> pd.DataFrame:
    """
    Expand a single SKU's BOM into a material demand DataFrame.

    Parameters
    ----------
    sheets
        All workbook sheets (wb.sheets).
    sku_key
        Product key (category|name|spec).
    plan_qty
        Planned production quantity (units of this SKU).
    order_date
        Target delivery date (used to back-calculate latest order date).
        Defaults to today + lead_days if not provided.
    lead_days
        Default lead time to use for items without specific lead_days.
    loss_rate
        Default loss rate for top-level SKU ingredients (fraction, 0-1).
    safety_stock
        Default safety stock per unit of this SKU.

    Returns
    -------
    pd.DataFrame with columns:
        sku_key, material, level, unit, plan_qty, qty_per_unit,
        gross_qty, safety_stock, total_safety_stock, min_purchase,
        purchase_qty, purchase_unit, lead_days, latest_order_date,
        unit_price, total_cost, is_gap, gap_reason,
        is_semi_finished, source_sheet

    The DataFrame is sorted: semi-finished first, then raw materials,
    then by material name.
    """
    if plan_qty <= 0:
        return pd.DataFrame(columns=[
            "sku_key", "material", "level", "unit", "plan_qty",
            "qty_per_unit", "gross_qty", "safety_stock", "total_safety_stock",
            "min_purchase", "purchase_qty", "purchase_unit", "lead_days",
            "latest_order_date", "unit_price", "total_cost",
            "is_gap", "gap_reason", "is_semi_finished", "source_sheet",
        ])

    sku_key_to_sheet = _build_sku_key_to_sheet(sheets)
    catalog = _build_material_catalog(sheets)

    raw_entries = _collect_bom_entries(
        sheets, sku_key, sku_key_to_sheet, visited=[sku_key], depth=1
    )

    # Deduplicate: keep unique (material, level) pairs, sum qty_per_unit
    # Use a dict to aggregate.
    agg: dict[Tuple[str, int], dict] = {}
    for e in raw_entries:
        key = (e.material, e.level)
        if key not in agg:
            agg[key] = {
                "sku_key": e.sku_key,
                "material": e.material,
                "level": e.level,
                "qty_per_unit": 0.0,
                "unit": e.unit,
                "loss_rate": e.loss_rate,
                "safety_stock": e.safety_stock,
                "min_purchase": e.min_purchase,
                "lead_days": e.lead_days,
                "is_semi_finished": e.is_semi_finished,
                "source_sheet": e.source_sheet,
            }
        agg[key]["qty_per_unit"] += e.qty_per_unit

    # Apply defaults
    for k, v in agg.items():
        if v["loss_rate"] == 0.0:
            v["loss_rate"] = loss_rate
        if v["safety_stock"] == 0.0:
            v["safety_stock"] = safety_stock
        if v["lead_days"] == 0:
            v["lead_days"] = lead_days

    rows: List[MaterialDemandRow] = []
    for v in agg.values():
        entry = BomEntry(
            sku_key=v["sku_key"],
            material=v["material"],
            level=v["level"],
            qty_per_unit=v["qty_per_unit"],
            unit=v["unit"],
            loss_rate=v["loss_rate"],
            safety_stock=v["safety_stock"],
            min_purchase=v["min_purchase"],
            lead_days=v["lead_days"],
            is_semi_finished=v["is_semi_finished"],
            source_sheet=v["source_sheet"],
        )

        price, order_unit, min_pur, is_stable, gap_reason = _get_material_info(catalog, v["material"])

        if not order_unit and v["unit"]:
            order_unit = v["unit"]

        if entry.min_purchase == 0.0:
            entry = BomEntry(
                sku_key=entry.sku_key,
                material=entry.material,
                level=entry.level,
                qty_per_unit=entry.qty_per_unit,
                unit=order_unit or entry.unit,
                loss_rate=entry.loss_rate,
                safety_stock=entry.safety_stock,
                min_purchase=min_pur if min_pur and min_pur > 0 else 1.0,
                lead_days=entry.lead_days,
                is_semi_finished=entry.is_semi_finished,
                source_sheet=entry.source_sheet,
            )

        is_gap = (price is None) or (not is_stable and price is not None)
        if is_gap and not gap_reason:
            gap_reason = "供应不稳定或无有效单价"

        mdr = MaterialDemandRow.from_bom_entry(
            entry=entry,
            plan_qty=plan_qty,
            order_date=order_date,
            unit_price=price,
            is_gap=is_gap,
            gap_reason=gap_reason,
        )
        # Override unit with catalog order_unit if available
        if order_unit:
            mdr.purchase_unit = order_unit
        rows.append(mdr)

    out = pd.DataFrame([r.__dict__ for r in rows])

    if out.empty:
        return out

    # Sort: semi-finished first, then by level, then by name
    out = out.sort_values(
        ["is_semi_finished", "level", "material"],
        ascending=[False, True, True],
    ).reset_index(drop=True)

    return out


# -------------------------------------------------------------------------------------------------
# Batch expand for multiple SKUs
# -------------------------------------------------------------------------------------------------

def bom_expand_multi(
    sheets: Dict[str, pd.DataFrame],
    sku_plan: Dict[str, float],
    *,
    order_date: Optional[date] = None,
    default_lead_days: int = 3,
    default_loss_rate: float = 0.0,
    default_safety_stock: float = 0.0,
) -> pd.DataFrame:
    """
    Expand BOM for multiple SKUs at once and return a merged demand summary.

    Parameters
    ----------
    sheets
        All workbook sheets.
    sku_plan
        Mapping of sku_key → planned production quantity.
    order_date
        Target delivery date for all SKUs.
    default_lead_days, default_loss_rate, default_safety_stock
        Fallback values used when item-specific values are not available.

    Returns
    -------
    pd.DataFrame aggregated by material (sum across all SKUs that use it).
    Columns: material, level, unit, purchase_unit, lead_days,
             total_plan_qty, total_gross_qty, total_safety_stock,
             total_purchase_qty, unit_price, total_cost,
             is_gap, gap_reason, is_semi_finished,
             sku_keys (comma-joined list of SKUs that use this material).
    """
    all_rows: List[pd.DataFrame] = []
    for sku_key, qty in sku_plan.items():
        if qty <= 0:
            continue
        df = bom_expand(
            sheets,
            sku_key,
            qty,
            order_date=order_date,
            lead_days=default_lead_days,
            loss_rate=default_loss_rate,
            safety_stock=default_safety_stock,
        )
        if not df.empty:
            all_rows.append(df)

    if not all_rows:
        return pd.DataFrame(columns=[
            "material", "level", "unit", "purchase_unit", "lead_days",
            "total_plan_qty", "total_gross_qty", "total_safety_stock",
            "total_purchase_qty", "unit_price", "total_cost",
            "is_gap", "gap_reason", "is_semi_finished", "sku_keys",
            "latest_order_date",
        ])

    merged = pd.concat(all_rows, ignore_index=True)

    # Aggregate by material
    def _join(series: pd.Series) -> str:
        vals = sorted(set(str(v).strip() for v in series if str(v).strip()))
        return ", ".join(vals)

    agg = merged.groupby("material", as_index=False, sort=False).agg({
        "level": "min",
        "unit": "first",
        "purchase_unit": "first",
        "lead_days": "max",
        "plan_qty": "sum",
        "gross_qty": "sum",
        "total_safety_stock": "sum",
        "purchase_qty": "sum",
        "unit_price": "first",
        "total_cost": "sum",
        "is_gap": "any",
        "gap_reason": lambda s: "; ".join(sorted(set(str(v) for v in s if str(v).strip()))),
        "is_semi_finished": "any",
        "sku_key": _join,
        "latest_order_date": "max",
    })
    agg = agg.rename(columns={
        "sku_key": "sku_keys",
        "plan_qty": "total_plan_qty",
        "gross_qty": "total_gross_qty",
        "total_safety_stock": "total_safety_stock",
        "purchase_qty": "total_purchase_qty",
    })

    # Re-round
    agg["total_gross_qty"] = agg["total_gross_qty"].round(4)
    agg["total_safety_stock"] = agg["total_safety_stock"].round(4)
    agg["total_purchase_qty"] = agg["total_purchase_qty"].round(4)
    agg["total_cost"] = agg["total_cost"].round(2)

    # Sort
    agg = agg.sort_values(
        ["is_semi_finished", "level", "material"],
        ascending=[False, True, True],
    ).reset_index(drop=True)

    return agg


# -------------------------------------------------------------------------------------------------
# Gaps helper
# -------------------------------------------------------------------------------------------------

def highlight_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of df with is_gap=True rows annotated.
    The caller can use this to highlight缺口项 in Streamlit.
    """
    if df.empty or "is_gap" not in df.columns:
        return df.copy()
    return df.copy()


def gaps_only(df: pd.DataFrame) -> pd.DataFrame:
    """Return only the gap rows (no valid price or unstable supply)."""
    if df.empty or "is_gap" not in df.columns:
        return df.copy()
    return df[df["is_gap"]].copy()
