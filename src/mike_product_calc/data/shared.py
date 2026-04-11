from __future__ import annotations

from typing import Optional

import pandas as pd


def to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and pd.isna(v):
            return None
        return float(v)

    txt = str(v).strip()
    if txt == "" or txt.lower() in {"nan", "none"}:
        return None
    if txt.endswith("%"):
        return None
    try:
        return float(txt)
    except Exception:
        return None


def to_percent_0_1(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        if isinstance(v, float) and pd.isna(v):
            return None
        f = float(v)
        return f if 0 <= f <= 1 else None

    txt = str(v).strip()
    if txt == "" or txt.lower() in {"nan", "none"}:
        return None
    if txt.endswith("%"):
        try:
            return float(txt[:-1]) / 100.0
        except Exception:
            return None
    try:
        f = float(txt)
        return f if 0 <= f <= 1 else None
    except Exception:
        return None


def build_product_key(df: pd.DataFrame) -> pd.Series:
    def _col(name: str) -> pd.Series:
        if name not in df.columns:
            return pd.Series([""] * len(df), index=df.index)
        return df[name].fillna("").astype(str).map(str.strip)

    category = _col("品类")
    name = _col("品名")
    spec = _col("规格")
    key = category + "|" + name + "|" + spec
    incomplete = (category == "") | (name == "") | (spec == "")
    return key.mask(incomplete, "")
