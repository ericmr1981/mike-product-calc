"""F-011: 产能需求估算 — 基于配方用量估算产能压力评分。

评分逻辑（与 F-008 产能压力对齐，总分 0-100）：
  - SKU复杂度得分：最多40分，封顶20SKU（每SKU 2分）
  - 产量体积得分：最多30分，封顶500件（线性，线性递减）
  - 原料多样性得分：最多30分，封顶30种（每种1分）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from mike_product_calc.data.shared import build_product_key


# ── Scoring constants ──────────────────────────────────────────────────────────────────────────

_MAX_SKU_SCORE       = 40.0   # 最多40分
_MAX_SKU_COUNT       = 20     # 封顶20SKU
_POINTS_PER_SKU      = _MAX_SKU_SCORE / _MAX_SKU_COUNT   # = 2

_MAX_VOLUME_SCORE    = 30.0   # 最多30分
_MAX_VOLUME_QTY      = 500.0  # 封顶500件

_MAX_MATERIAL_SCORE  = 30.0   # 最多30分
_MAX_MATERIAL_COUNT  = 30    # 封顶30种

_HIGH_PRESSURE_THRESHOLD = 60.0  # 标红阈值


# ── Dataclass ─────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CapacityPressure:
    """单个 SKU/日期组合的产能压力评估结果。"""

    sku_key: str           # SKU 唯一标识
    score: float           # 总分（0-100，越高压力越大）
    material_count: int    # 涉及原料种类数
    volume_score: float    # 产量体积得分（0-30）
    complexity_score: float  # SKU复杂度得分（0-40）
    material_score: float  # 原料多样性得分（0-30）
    plan_qty: float        # 该 SKU 的计划产量
    is_high_pressure: bool  # 是否高压力（≥ 60分）
    source_skus: List[str]  # 原始 SKU 列表（用于调试/追溯）


# ── Helper: collect unique materials per SKU from 出品表 ─────────────────────────────────────

def _collect_materials_for_sku(
    sheets: Dict[str, pd.DataFrame],
    sku_key: str,
) -> int:
    """返回指定 SKU 在所有出品表中涉及的不同原料种类数。

    只计主原料和配料列（字符串拼接后去重）。
    """
    material_names: set[str] = set()
    out_sheets = ["产品出品表_Gelato", "产品出品表_雪花冰", "产品出品表_饮品"]

    for sheet_name in out_sheets:
        df = sheets.get(sheet_name)
        if df is None:
            continue
        keys = build_product_key(df)
        mask = keys == sku_key
        if not mask.any():
            continue

        part = df.loc[mask]

        for col in ("主原料", "配料"):
            if col in part.columns:
                vals = (
                    part[col]
                    .fillna("")
                    .astype(str)
                    .map(str.strip)
                )
                for v in vals:
                    if v and v not in ("nan", "None"):
                        material_names.add(v)

    return len(material_names)


# ── Core scoring function ───────────────────────────────────────────────────────────────────

def score_capacity(
    sku_keys: List[str],
    plan_qtys: List[float],
    sheets: Dict[str, pd.DataFrame],
) -> List[CapacityPressure]:
    """根据 SKU 列表及计划产量计算产能压力。

    Parameters
    ----------
    sku_keys
        SKU 唯一标识列表（与 plan_qtys 一一对应）。
    plan_qtys
        各 SKU 的计划产量。
    sheets
        解析后的 Excel sheets dict。

    Returns
    -------
    List[CapacityPressure]
        每组（SKU / 日期 等聚合维度）的压力评估。
        这里按 sku_key 聚合返回一行。
    """
    if not sku_keys or len(sku_keys) != len(plan_qtys):
        return []

    # Build sku → qty mapping
    sku_qty: Dict[str, float] = {}
    for k, q in zip(sku_keys, plan_qtys):
        k = str(k).strip()
        if k:
            sku_qty[k] = sku_qty.get(k, 0.0) + float(q)

    results: List[CapacityPressure] = []

    for sku_key, qty in sku_qty.items():
        material_count = _collect_materials_for_sku(sheets, sku_key)

        # 1. SKU复杂度得分（最多40分，封顶20SKU，每SKU 2分）
        n_skus = len(sku_qty)
        complexity_score = min(n_skus * _POINTS_PER_SKU, _MAX_SKU_SCORE)

        # 2. 产量体积得分（最多30分，封顶500件，线性递减）
        # 公式: min(qty / MAX_QTY, 1.0) * MAX_VOLUME_SCORE
        volume_ratio = min(float(qty) / _MAX_VOLUME_QTY, 1.0)
        volume_score = volume_ratio * _MAX_VOLUME_SCORE

        # 3. 原料多样性得分（最多30分，封顶30种，每种1分）
        material_ratio = min(material_count / _MAX_MATERIAL_COUNT, 1.0)
        material_score = material_ratio * _MAX_MATERIAL_SCORE

        score = complexity_score + volume_score + material_score
        is_high = score >= _HIGH_PRESSURE_THRESHOLD

        results.append(
            CapacityPressure(
                sku_key=sku_key,
                score=round(score, 2),
                material_count=material_count,
                volume_score=round(volume_score, 2),
                complexity_score=round(complexity_score, 2),
                material_score=round(material_score, 2),
                plan_qty=qty,
                is_high_pressure=is_high,
                source_skus=[sku_key],
            )
        )

    return results


# ── Convenience: score from ProductionRow list ──────────────────────────────────────────────

def score_capacity_from_plan(
    rows: List,  # List[ProductionRow]
    sheets: Dict[str, pd.DataFrame],
    plan_type: Optional[str] = None,
) -> List[CapacityPressure]:
    """从 ProductionRow 列表计算产能压力。

    Parameters
    ----------
    rows
        ProductionRow 列表（来自 tab5 保存的场景数据）。
    sheets
        解析后的 Excel sheets dict。
    plan_type
        可选：只统计指定计划类型（"sales" | "production"）。
    """
    sku_keys: List[str] = []
    plan_qtys: List[float] = []

    for r in rows:
        if plan_type is not None and r.plan_type != plan_type:
            continue
        sku_keys.append(r.sku_key)
        plan_qtys.append(r.qty)

    return score_capacity(sku_keys, plan_qtys, sheets)


# ── Aggregate by date ───────────────────────────────────────────────────────────────────────

def score_capacity_by_date(
    rows: List,  # List[ProductionRow]
    sheets: Dict[str, pd.DataFrame],
    plan_type: Optional[str] = None,
) -> List[CapacityPressure]:
    """按「日期 × SKU」聚合计算产能压力（用于 tab11 日期视图）。"""
    # Filter
    filtered = rows
    if plan_type is not None:
        filtered = [r for r in rows if r.plan_type == plan_type]

    # Group by (date, sku_key)
    from collections import defaultdict
    date_sku_qty: Dict[tuple, float] = defaultdict(float)
    for r in filtered:
        key = (str(r.date).strip(), str(r.sku_key).strip())
        if key[1]:
            date_sku_qty[key] += float(r.qty)

    results: List[CapacityPressure] = []
    for (date_str, sku_key), qty in date_sku_qty.items():
        material_count = _collect_materials_for_sku(sheets, sku_key)

        n_skus = len({k[1] for k in date_sku_qty.keys()})
        complexity_score = min(n_skus * _POINTS_PER_SKU, _MAX_SKU_SCORE)

        volume_ratio = min(float(qty) / _MAX_VOLUME_QTY, 1.0)
        volume_score = volume_ratio * _MAX_VOLUME_SCORE

        material_ratio = min(material_count / _MAX_MATERIAL_COUNT, 1.0)
        material_score = material_ratio * _MAX_MATERIAL_SCORE

        score = complexity_score + volume_score + material_score
        is_high = score >= _HIGH_PRESSURE_THRESHOLD

        results.append(
            CapacityPressure(
                sku_key=f"{date_str} | {sku_key}",
                score=round(score, 2),
                material_count=material_count,
                volume_score=round(volume_score, 2),
                complexity_score=round(complexity_score, 2),
                material_score=round(material_score, 2),
                plan_qty=qty,
                is_high_pressure=is_high,
                source_skus=[sku_key],
            )
        )

    return results


# ── DataFrame output ────────────────────────────────────────────────────────────────────────

def capacity_to_dataframe(results: List[CapacityPressure]) -> pd.DataFrame:
    """将 List[CapacityPressure] 转为 DataFrame，方便 Streamlit 展示。"""
    if not results:
        return pd.DataFrame(columns=[
            "sku_key", "score", "material_count",
            "volume_score", "complexity_score", "material_score",
            "plan_qty", "is_high_pressure",
        ])
    rows = [
        {
            "sku_key":           r.sku_key,
            "score":             r.score,
            "material_count":    r.material_count,
            "volume_score":      r.volume_score,
            "complexity_score":  r.complexity_score,
            "material_score":    r.material_score,
            "plan_qty":          r.plan_qty,
            "is_high_pressure":  r.is_high_pressure,
        }
        for r in results
    ]
    df = pd.DataFrame(rows)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df
