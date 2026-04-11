from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd


PathLike = Union[str, Path]


# -------------------------------------------------------------------------------------------------
# Sheet-name normalisation & fuzzy matching
# -------------------------------------------------------------------------------------------------

# Characters we collapse when normalising a sheet name so that
# " 产品毛利表_Gelato " or "产品毛利表_gelato" still resolves correctly.
_WHITESPACE_RE = re.compile(r"\s+")
_UNDERSCORE_DASH_RE = re.compile(r"[-_]+")


def _normalize_sheet_name(name: str) -> str:
    """Collapse whitespace, replace dashes/underscores, lowercase."""
    n = _WHITESPACE_RE.sub("", name)
    n = _UNDERSCORE_DASH_RE.sub("_", n)
    return n.lower()


@dataclass(frozen=True)
class SheetMapping:
    """Result of matching expected sheets against actual workbook sheets."""

    exact: Dict[str, str] = field(default_factory=dict)
    """expected_name -> actual_name (exact match after strip)"""

    fuzzy: Dict[str, str] = field(default_factory=dict)
    """expected_name -> actual_name (fuzzy/normalized match)"""

    missing: List[str] = field(default_factory=list)
    """expected names that were not found in the workbook"""

    unexpected: List[str] = field(default_factory=list)
    """actual sheet names that were not in the expected list"""


def match_sheets(
    expected: Sequence[str],
    actual: Sequence[str],
    *,
    allow_fuzzy: bool = True,
) -> SheetMapping:
    """Match a list of expected sheet names against actual sheet names.

    Returns a SheetMapping describing which sheets were found (exact or fuzzy)
    and which are missing / unexpected.
    """
    actual_list = list(actual)
    actual_norm: Dict[str, str] = {}  # normalized -> original

    # Build lookup: original -> normalized
    orig_norm: Dict[str, str] = {}
    for a in actual_list:
        norm = _normalize_sheet_name(a)
        orig_norm[a] = norm
        actual_norm[norm] = a  # last one wins for exact duplicates

    exact: Dict[str, str] = {}
    fuzzy: Dict[str, str] = {}
    missing: List[str] = []

    for exp in expected:
        exp_strip = exp.strip()
        exp_norm = _normalize_sheet_name(exp)

        # 1) exact strip match
        if exp_strip in actual_list:
            exact[exp] = exp_strip
        # 2) fuzzy / normalized match
        elif allow_fuzzy and exp_norm in actual_norm:
            matched_orig = actual_norm[exp_norm]
            # Only fuzzy-match if names are genuinely different
            if matched_orig != exp_strip:
                fuzzy[exp] = matched_orig
            else:
                exact[exp] = matched_orig
        else:
            missing.append(exp)

    unexpected = [a for a in actual_list if a not in exact.values() and a not in fuzzy.values()]

    return SheetMapping(exact=exact, fuzzy=fuzzy, missing=missing, unexpected=unexpected)


# -------------------------------------------------------------------------------------------------
# Header-row detection
# -------------------------------------------------------------------------------------------------

def _find_header_row(df: pd.DataFrame, required_cols: Sequence[str]) -> int:
    """Heuristic: find the first row that contains most of the required columns.

    Some Excel sheets have 1+ leading rows with instructions or merged-cell titles
    before the actual header.  We detect that by scanning from row 0 until we find a
    row where at least half of required_cols appear.
    """
    if len(df) == 0:
        return 0

    required_set = {str(c).strip() for c in required_cols}
    min_match = max(1, len(required_set) // 2)

    for i in range(min(5, len(df))):  # don't scan more than 5 rows
        row_vals = {str(v).strip() for v in df.iloc[i].tolist()}
        if len(required_set & row_vals) >= min_match:
            return i
    return 0


# -------------------------------------------------------------------------------------------------
# WorkbookData
# -------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkbookData:
    """Loaded Excel workbook data.

    sheets:   mapping canonical sheet name -> dataframe
    mapping:  SheetMapping describing how actual names were matched
    path:     original file path (None when loading from a dict)
    """

    path: Optional[Path]
    sheets: Dict[str, pd.DataFrame]
    mapping: SheetMapping = field(default_factory=SheetMapping)

    def sheet_names(self) -> List[str]:
        """Canonical names of loaded sheets."""
        return list(self.sheets.keys())


def load_workbook(
    path: PathLike,
    *,
    engine: str = "openpyxl",
    expected_sheets: Optional[Sequence[str]] = None,
    header_row: Optional[int] = None,
    required_columns_by_sheet: Optional[Dict[str, Sequence[str]]] = None,
) -> WorkbookData:
    """Load an Excel workbook into a WorkbookData structure.

    Parameters
    ----------
    path
        Path to the .xlsx file.
    engine
        pandas ExcelFile engine (default: openpyxl).
    expected_sheets
        List of expected sheet names.  Used to produce a SheetMapping and
        to drive fuzzy sheet-name matching.
    header_row
        Row index to use as column headers (0-based).  None means
        "auto-detect" (skip leading non-header rows when required_columns is
        given for that sheet).
    required_columns_by_sheet
        When header_row=None this is used for auto-detection of the header
        row.  Per-sheet list of required column names.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    xl = pd.ExcelFile(p, engine=engine)
    raw_names = [str(n).strip() for n in xl.sheet_names]

    # --- resolve expected sheets
    mapping: SheetMapping
    if expected_sheets is not None:
        mapping = match_sheets(expected_sheets, raw_names)
    else:
        mapping = SheetMapping()

    # --- load each sheet
    sheets: Dict[str, pd.DataFrame] = {}

    # Determine header rows for auto-detection
    header_hints: Dict[str, int] = {}
    if expected_sheets is not None and required_columns_by_sheet is not None:
        # Do a quick dry-read to find headers
        for name in raw_names:
            df_tmp = xl.parse(name, dtype=object, nrows=6)
            cols_tmp = [str(c).strip() if c is not None else "" for c in df_tmp.columns]
            df_tmp.columns = cols_tmp
            req = required_columns_by_sheet.get(name, [])
            if req:
                hdr = _find_header_row(df_tmp, req)
                if hdr > 0:
                    header_hints[name] = hdr

    for raw_name in raw_names:
        # Determine which canonical name to use
        canonical = raw_name  # default: use the stripped original name
        if expected_sheets is not None:
            if raw_name in mapping.exact.values():
                # Find the expected name that maps to this raw_name
                for exp, act in mapping.exact.items():
                    if act == raw_name:
                        canonical = exp
                        break
            elif raw_name in mapping.fuzzy.values():
                for exp, act in mapping.fuzzy.items():
                    if act == raw_name:
                        canonical = exp
                        break

        # Determine header row
        hdr = header_row if header_row is not None else header_hints.get(raw_name, 0)

        # Parse
        df = xl.parse(raw_name, header=hdr, dtype=object)

        # Normalize column labels
        cols = []
        for c in list(df.columns):
            if c is None:
                cols.append("")
            else:
                cols.append(str(c).strip())
        df.columns = cols

        # Drop entirely-empty leading/trailing rows
        df = df.dropna(how="all").reset_index(drop=True)

        sheets[canonical] = df

    return WorkbookData(path=p, sheets=sheets, mapping=mapping)
