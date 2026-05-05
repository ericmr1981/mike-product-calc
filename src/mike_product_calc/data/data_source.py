"""Data source adapter — provides unified access to Excel or Supabase data.

Existing calc modules can use this to read data without caring about the source.
Initially returns Excel data; can be switched to Supabase per-module.
"""
from __future__ import annotations

from typing import Optional

import pandas as pd


class DataSource:
    """Unified data source for calc modules.

    Usage:
        ds = DataSource(sheets=wb.sheets)
        df = ds.get_sheet("产品配方表_Gelato")
    """

    def __init__(self, sheets: Optional[dict[str, pd.DataFrame]] = None):
        self._sheets = sheets or {}

    def get_sheet(self, name: str) -> Optional[pd.DataFrame]:
        """Get a sheet by name (fuzzy match)."""
        norm = {k.replace(" ", "").replace("_", "").lower(): k for k in self._sheets}
        key = name.replace(" ", "").replace("_", "").lower()
        if key in norm:
            return self._sheets[norm[key]]
        return None

    def has_supabase(self) -> bool:
        return False
