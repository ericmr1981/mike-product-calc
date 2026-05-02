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

from mike_product_calc.calc.profit import ProfitBasis
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
        unit_qty: Optional[float] = None,
        is_gap: bool = False,
        gap_reason: str = "",
    ) -> "MaterialDemandRow":
        """Build one demand row.

        - entry.qty_per_unit is interpreted in *base units* (the unit of recipe/出品表 用量).
        - unit_qty is "单位量": how many base units in one 订货单位.

        Output qty fields (gross_qty / purchase_qty / safety_stock, etc.) are expressed
        in 订货单位 when unit_qty is valid; otherwise we fall back to base units.
        """

        q_unit = float(unit_qty) if (unit_qty is not None and unit_qty > 0) else 1.0

        # Convert base-unit recipe usage → purchase units
        qty_per_unit_pu = entry.qty_per_unit / q_unit
        gross_pu = plan_qty * entry.effective_qty_per_unit / q_unit
        total_ss_pu = (entry.safety_stock * plan_qty) / q_unit

        # Batch rounding in purchase units
        if entry.min_purchase > 0 and entry.min_purchase > 0.0:
            purchase_qty = math.ceil((gross_pu + total_ss_pu) / entry.min_purchase) * entry.min_purchase
        else:
            purchase_qty = gross_pu + total_ss_pu

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
            qty_per_unit=round(qty_per_unit_pu, 6),
            gross_qty=round(gross_pu, 4),
            safety_stock=round(entry.safety_stock / q_unit, 6),
            total_safety_stock=round(total_ss_pu, 4),
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


def _price_col_for_basis(df: pd.DataFrame, basis: ProfitBasis) -> Optional[str]:
    """Select correct price column from 总原料成本表 for the chosen basis.

    Convention:
    - 加价前单价 = 出厂单价 (factory)
    - 加价后单价 = 门店单价 (store)
    """

    if basis == "factory" and "加价前单价" in df.columns:
        return "加价前单价"
    if basis == "store" and "加价后单价" in df.columns:
        return "加价后单价"

    # Fallbacks for older/variant headers.
    return next((c for c in df.columns if "原料价格" in c), None) or next(
        (c for c in df.columns if "单价" in c),
        None,
    )





# Recipe sheets (2nd-level) — used to expand semi-finished/product items into raw ingredients.
# Workbook convention:
# - 产品配方表_*: per-product recipes (e.g. 产品配方表_Gelato)
# - 半成品配方表_*: semi-finished recipes (e.g. 半成品配方表_雪花冰)
# Columns: 品类, 品名, 配料, 用量
_RECIPE_SHEET_HINTS = ("配方表",)


def _build_recipe_index(sheets: Dict[str, pd.DataFrame]) -> Dict[Tuple[str, str], dict]:
    """Build (category, item_name) -> recipe lines.

    Returns mapping:
      (cat, name) -> {"rows": [(ingredient, qty), ...], "denom": sum(qty), "sheet": sheet_name}

    Scaling rule used in BOM expansion:
      If SKU consumes X (in the same base unit as recipe's 用量) of item,
      and recipe totals denom, then ingredient demand = X * (qty/denom).

    Note: This engine is intentionally *2-level* per Ud Lee requirements.
    """

    idx: Dict[Tuple[str, str], dict] = {}
    if not sheets:
        return idx

    for sheet_name, df in sheets.items():
        if df is None:
            continue
        if not any(h in str(sheet_name) for h in _RECIPE_SHEET_HINTS):
            continue
        required = {"品类", "品名", "配料", "用量"}
        if not required.issubset(set(df.columns)):
            continue

        for _, r in df.iterrows():
            cat = str(r.get("品类", "")).strip()
            name = str(r.get("品名", "")).strip()
            ing = str(r.get("配料", "")).strip()
            qty = to_float(r.get("用量"))
            if not cat or not name or not ing or qty is None or qty <= 0:
                continue

            key = (cat, name)
            if key not in idx:
                idx[key] = {"rows": [], "denom": 0.0, "sheet": str(sheet_name)}
            idx[key]["rows"].append((ing, float(qty)))
            idx[key]["denom"] += float(qty)

    # Keep only valid recipes
    idx = {k: v for k, v in idx.items() if v.get("denom", 0) > 0 and v.get("rows")}
    return idx


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


def _build_material_catalog(
    sheets: Dict[str, pd.DataFrame],
    *,
    basis: ProfitBasis = "store",
) -> pd.DataFrame:
    """Build a lookup table from 总原料成本表.

    Returns DataFrame with columns:
      name, category, order_unit, unit_price, unit_qty, min_unit_cost, status

    Where:
      unit_price    = price per 订货单位 (加价前单价/加价后单价)
      unit_qty      = how many "base units" in one 订货单位 (单位量)
      min_unit_cost = unit_price / unit_qty (fallback = unit_price)

    Downstream rules:
      - Purchase qty is expressed in 订货单位
      - total_cost = purchase_qty * unit_price
    """
    df = sheets.get("总原料成本表")
    if df is None:
        return pd.DataFrame(columns=[
            "name", "category", "order_unit", "unit_price", "unit_qty", "min_unit_cost", "status"
        ])

    price_col = _price_col_for_basis(df, basis)
    unit_price = df[price_col].map(to_float) if (price_col and price_col in df.columns) else pd.Series(dtype=float)
    unit_qty = df["单位量"].map(to_float) if "单位量" in df.columns else pd.Series(dtype=float)

    # min-unit cost = unit_price / unit_qty
    min_unit_cost = unit_price
    if not unit_qty.empty:
        q = unit_qty.where(unit_qty > 0)
        min_unit_cost = unit_price.where(q.isna(), unit_price / q)

    out = pd.DataFrame({
        "name":       df["品项名称"].fillna("").astype(str).map(str.strip),
        "category":   df["品项类别"].fillna("").astype(str).map(str.strip) if "品项类别" in df.columns else "",
        "order_unit": df["订货单位"].fillna("").astype(str).map(str.strip) if "订货单位" in df.columns else "",
        "unit_price": unit_price,
        "unit_qty":   unit_qty,
        "min_unit_cost": min_unit_cost,
        "status":     df["生效状态"].fillna("").astype(str).map(str.strip) if "生效状态" in df.columns else "",
    })
    out = out[out["name"] != ""].drop_duplicates(subset=["name"]).reset_index(drop=True)
    return out


def _get_material_info(
    catalog: pd.DataFrame,
    material_name: str,
) -> Tuple[Optional[float], Optional[str], Optional[float], Optional[float], bool, str]:
    """Look up a material in the catalog.

    Returns:
      (unit_price, order_unit, unit_qty, min_unit_cost, is_stable, gap_reason)
    """
    row = catalog[catalog["name"] == material_name]
    if row.empty:
        # Not in catalog — default to price=0 (辅料如水、盐无采购成本)
        return 0.0, "", None, None, True, ""

    r = row.iloc[0]
    unit_price = r["unit_price"] if pd.notna(r.get("unit_price")) else 0.0
    order_unit = str(r.get("order_unit") or "").strip()
    unit_qty = r["unit_qty"] if pd.notna(r.get("unit_qty")) else None
    min_unit_cost = r["min_unit_cost"] if pd.notna(r.get("min_unit_cost")) else None

    status = str(r.get("status") or "").strip()

    is_stable = status in ("", "已生效")
    gap_reason = ""
    if unit_price is None:
        unit_price = 0.0
    if not is_stable:
        gap_reason = f"供应状态：{status}"

    return unit_price, order_unit, unit_qty, min_unit_cost, is_stable, gap_reason


# -------------------------------------------------------------------------------------------------
# Core BOM expansion
# -------------------------------------------------------------------------------------------------

def _build_recipe_by_name(recipe_index: Dict[Tuple[str, str], dict]) -> Dict[str, dict]:
    """Build a flat name→recipe lookup from the (cat,name) indexed recipe_index.

    Used when a sku_key is a recipe item name (e.g. "榛子巧克力布朗尼 2.0")
    rather than a product key (e.g. "Gelato|榛子巧克力布朗尼|小杯").
    """
    by_name: Dict[str, dict] = {}
    for (cat, name), info in recipe_index.items():
        if name not in by_name:
            by_name[name] = info
    return by_name


def _collect_bom_entries(
    sheets: Dict[str, pd.DataFrame],
    sku_key: str,
    sku_key_to_sheet: Dict[str, Tuple[pd.DataFrame, pd.Series, str]],
    recipe_index: Dict[Tuple[str, str], dict],
) -> List[BomEntry]:
    """Collect BOM entries for a SKU (2-level recipe model).

    Two entry paths:
      Path A — sku_key is a product key (品类|品名|规格):
        Level 1: 产品出品表_* (主原料/配料 + 用量)
        Level 2: 配方表_* / 半成品配方表_* (品类, 品名) → 配料

      Path B — sku_key is a recipe item name (e.g. "榛子巧克力布朗尼 2.0"):
        Direct lookup in 产品配方表 → raw ingredients (level 2)

    For raw-material statistics, we keep only leaf ingredients:
    if an item is expandable (has a recipe), the intermediate item itself
    is NOT included in output; only its expanded ingredients are returned.

    Scaling rule:
      SKU consumes X of item (same unit as recipe 用量)
      recipe total denom = sum(用量)
      ingredient demand = X * (ingredient_qty / denom)
    """

    entries: List[BomEntry] = []

    key_info = sku_key_to_sheet.get(sku_key)
    if key_info is not None:
        # ── Path A: product key (品类|品名|规格) ──
        df, keys, sheet_name = key_info
        part = df.loc[keys == sku_key].copy()
        if part.empty:
            return entries

        sku_category = str(sku_key).split("|")[0].strip() if "|" in str(sku_key) else ""
        qty_col = "用量"
        if qty_col not in part.columns:
            return entries

        for _, row in part.iterrows():
            mm = str(row.get("主原料", "") or "").strip()
            ing = str(row.get("配料", "") or "").strip()
            item = ing or mm
            if not item:
                continue
            raw_qty = to_float(row.get(qty_col))
            qty = float(raw_qty) if raw_qty is not None and raw_qty > 0 else 0.0
            if qty <= 0:
                continue

            rkey = (sku_category, item)
            recipe = recipe_index.get(rkey)
            if recipe is not None:
                denom = float(recipe.get("denom") or 0.0)
                if denom > 0:
                    scale = qty / denom
                    for ing_name, ing_qty in recipe.get("rows", []):
                        iname = str(ing_name).strip()
                        if not iname:
                            continue
                        q = float(ing_qty) * scale
                        if q <= 0:
                            continue
                        entries.append(BomEntry(
                            sku_key=sku_key, material=iname, level=2,
                            qty_per_unit=q, unit="",
                            loss_rate=0.0, safety_stock=0.0, min_purchase=0.0, lead_days=0,
                            is_semi_finished=False,
                            source_sheet=f"{sheet_name}→{recipe.get('sheet','')}",
                        ))
                    continue
            # Leaf item
            entries.append(BomEntry(
                sku_key=sku_key, material=item, level=1, qty_per_unit=qty,
                unit="", loss_rate=0.0, safety_stock=0.0, min_purchase=0.0, lead_days=0,
                is_semi_finished=False, source_sheet=sheet_name,
            ))
    else:
        # ── Path B: raw material or recipe item name ──
        # Try recipe expansion first
        recipe_by_name = _build_recipe_by_name(recipe_index)
        recipe = recipe_by_name.get(sku_key)
        if recipe is not None and recipe.get("denom", 0) > 0:
            # It has a recipe — expand into ingredients
            denom = float(recipe["denom"])
            for ing_name, ing_qty in recipe.get("rows", []):
                iname = str(ing_name).strip()
                if not iname:
                    continue
                entries.append(BomEntry(
                    sku_key=sku_key, material=iname,
                    level=2, qty_per_unit=float(ing_qty) / denom,
                    unit="", loss_rate=0.0, safety_stock=0.0,
                    min_purchase=0.0, lead_days=0,
                    is_semi_finished=False,
                    source_sheet=str(recipe.get("sheet", "")),
                ))
        else:
            # No recipe — treat as raw material leaf item (level 1)
            entries.append(BomEntry(
                sku_key=sku_key, material=sku_key,
                level=1, qty_per_unit=1.0,
                unit="", loss_rate=0.0, safety_stock=0.0,
                min_purchase=0.0, lead_days=0,
                is_semi_finished=False, source_sheet="",
            ))

    return entries


def bom_expand(
    sheets: Dict[str, pd.DataFrame],
    sku_key: str,
    plan_qty: float,
    *,
    basis: ProfitBasis = "store",
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
    recipe_index = _build_recipe_index(sheets)
    catalog = _build_material_catalog(sheets, basis=basis)

    raw_entries = _collect_bom_entries(
        sheets, sku_key, sku_key_to_sheet, recipe_index
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

        unit_price, order_unit, unit_qty, min_unit_cost, is_stable, gap_reason = _get_material_info(catalog, v["material"])

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
                min_purchase=1.0,
                lead_days=entry.lead_days,
                is_semi_finished=entry.is_semi_finished,
                source_sheet=entry.source_sheet,
            )

        is_gap = (unit_price is None) or (not is_stable and unit_price is not None)
        if is_gap and not gap_reason:
            gap_reason = "供应不稳定或无有效单价"

        mdr = MaterialDemandRow.from_bom_entry(
            entry=entry,
            plan_qty=plan_qty,
            order_date=order_date,
            unit_price=unit_price,
            unit_qty=unit_qty,
            is_gap=is_gap,
            gap_reason=gap_reason,
        )
        # Ensure purchase/display unit is 订货单位
        if order_unit:
            mdr.purchase_unit = order_unit
            mdr.unit = order_unit
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
    basis: ProfitBasis = "store",
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
            basis=basis,
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


# -------------------------------------------------------------------------------------------------
# Sales → Production conversion
# -------------------------------------------------------------------------------------------------


def sales_to_production(
    sales_rows: List["ProductionRow"],
    sheets: Dict[str, pd.DataFrame],
    lead_days: int = 1,
) -> List["ProductionRow"]:
    """
    Convert sales plan rows to production plan rows, expanding directly to
    recipe ingredient level.

    Formula per ingredient (from 产品配方表):
      ingredient_qty = sales_qty × 产品出品表.主原料用量 × 配方表.该配料用量 / denom

    Where denom = sum(配方表.用量) = 产品成本计算表.规格 (batch weight in g).

    Example: Gelato|榛子巧克力布朗尼|小杯 × 10
      出品表: 主原料=榛子巧克力布朗尼 2.0, 用量=120g
      配方表: 原味奶浆JYX001 2000g, 榛子巧克力 200g, 纯牛奶 100g
      denom=2300 (batch weight from 产品成本计算表)

      原味奶浆JYX001: 10×120×2000/2300 = 1043g
      榛子巧克力:     10×120×200/2300  = 104g
      纯牛奶:         10×120×100/2300  = 52g

    Returns ProductionRow list with plan_type="production".
    """
    from mike_product_calc.model.production import ProductionRow

    if not sales_rows or not sheets:
        return []

    # Build recipe index: name → {rows: [(ingredient, qty), ...], denom}
    recipe_index: Dict[str, dict] = {}
    for sname in sheets:
        if "产品配方表" in sname or "半成品配方表" in sname:
            df = sheets[sname]
            if not {"品名", "配料", "用量"}.issubset(set(df.columns)):
                continue
            for _, r in df.iterrows():
                name = str(r.get("品名", "")).strip()
                ing = str(r.get("配料", "")).strip()
                qty = to_float(r.get("用量"))
                if not name or not ing or qty is None or qty <= 0:
                    continue
                if name not in recipe_index:
                    recipe_index[name] = {"rows": [], "denom": 0.0}
                recipe_index[name]["rows"].append((ing, float(qty)))
                recipe_index[name]["denom"] += float(qty)

    out_rows: Dict[tuple, float] = {}  # (date, material_name) -> total_qty

    for row in sales_rows:
        if row.plan_type != "sales":
            continue
        parts = row.sku_key.split("|")
        if len(parts) < 2:
            continue
        category = parts[0].strip()
        product_name = parts[1].strip()
        spec = parts[2].strip() if len(parts) > 2 else row.spec

        # Find matching 产品出品表 sheet
        sheet_name = None
        for sname in sheets:
            if sname.startswith("产品出品表_") and category in sname:
                sheet_name = sname
                break
        if sheet_name is None:
            continue

        df = sheets[sheet_name].reset_index(drop=True)
        if "品类" not in df.columns or "品名" not in df.columns:
            continue
        sheet_keys = build_product_key(df)

        target_key = f"{category}|{product_name}|{spec}" if spec else f"{category}|{product_name}"
        match_mask = sheet_keys == target_key
        if not match_mask.any():
            match_mask = df["品名"].fillna("").astype(str).str.strip() == product_name
            if spec and "规格" in df.columns:
                match_mask &= df["规格"].fillna("").astype(str).str.strip() == spec

        output_rows = df[match_mask]
        if output_rows.empty:
            continue

        # Date
        try:
            sales_date = date.fromisoformat(row.date)
        except Exception:
            try:
                sales_date = pd.to_datetime(row.date).date()
            except Exception:
                continue
        prod_date = sales_date - timedelta(days=lead_days)
        prod_date_str = prod_date.strftime("%Y-%m-%d")

        # For each 出品表 row, get 主原料 and find its recipe
        for _, out_row in output_rows.iterrows():
            main_material = str(out_row.get("主原料", "")).strip()
            if not main_material or main_material.lower() in ("nan", ""):
                continue
            usage_per_unit = to_float(out_row.get("用量"))
            if usage_per_unit is None or usage_per_unit <= 0:
                continue

            # Total grams of main material needed
            total_main_grams = row.qty * usage_per_unit

            # Look up this main material's recipe
            recipe = recipe_index.get(main_material)
            if recipe is None:
                continue

            denom = recipe["denom"]
            if denom <= 0:
                continue

            # For each ingredient in the recipe, apply the formula:
            # ingredient_qty = sales_qty × 出品表.用量 × (配方表.用量 / denom)
            #                = total_main_grams × (ing_qty / denom)
            for ing_name, ing_qty in recipe["rows"]:
                ingredient_grams = total_main_grams * (ing_qty / denom)
                key = (prod_date_str, ing_name)
                out_rows[key] = out_rows.get(key, 0) + ingredient_grams

        # Also include 配料 (packaging/consumables) from 产品出品表
        for _, out_row in output_rows.iterrows():
            ingredient = str(out_row.get("配料", "")).strip()
            if not ingredient or ingredient.lower() in ("nan", ""):
                continue
            # Skip if this ingredient was already processed as 主原料
            if ingredient == str(out_row.get("主原料", "")).strip():
                continue
            usage = to_float(out_row.get("用量"))
            if usage is None or usage <= 0:
                continue
            # 配料 qty = sales_qty × 用量 (unit-based: 个/杯/份)
            ing_qty = row.qty * usage
            key = (prod_date_str, ingredient)
            out_rows[key] = out_rows.get(key, 0) + ing_qty

    result = sorted(
        [
            ProductionRow(date=d, sku_key=k, spec="", qty=round(q, 2), plan_type="production")
            for (d, k), q in out_rows.items()
        ],
        key=lambda r: (r.date, r.sku_key),
    )
    return result
