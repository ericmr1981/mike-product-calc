from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd


@dataclass(frozen=True)
class ValidationIssue:
    severity: str  # error|warn|info
    sheet: str
    rule: str
    message: str
    row: Optional[int] = None  # 1-based Excel-like row index (data row, not counting header)
    column: Optional[str] = None
    affected_skus: List[str] = field(default_factory=list)
    affected_materials: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class SheetSpec:
    required_columns: Sequence[str]
    key_columns: Sequence[str] = ()
    # columns that should be numeric (float-ish). We don't force parsing in loader; we validate here.
    numeric_columns: Sequence[str] = ()
    # columns that should look like "83.6%" or 0.836; we validate presence/format.
    percent_columns: Sequence[str] = ()
    # columns that should be > 0 for 上线 products
    positive_columns: Sequence[str] = ()


# -------------------------------------------------------------------------------------------------
# ValidationReport — structured summary of the validation run (V2)
# -------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class SeverityCounts:
    error: int = 0
    warn: int = 0
    info: int = 0

    @property
    def total(self) -> int:
        return self.error + self.warn + self.info

    @property
    def has_errors(self) -> bool:
        return self.error > 0

    def __str__(self) -> str:
        parts = []
        if self.error:
            parts.append(f"{self.error} error{'s' if self.error != 1 else ''}")
        if self.warn:
            parts.append(f"{self.warn} warning{'s' if self.warn != 1 else ''}")
        if self.info:
            parts.append(f"{self.info} info{'s' if self.info != 1 else ''}")
        return ", ".join(parts) if parts else "clean"


@dataclass(frozen=True)
class RuleCounts:
    rule: str
    count: int
    severity: str


@dataclass(frozen=True)
class SheetCounts:
    sheet: str
    error_count: int = 0
    warn_count: int = 0
    info_count: int = 0

    @property
    def severity_counts(self) -> SeverityCounts:
        return SeverityCounts(
            error=self.error_count, warn=self.warn_count, info=self.info_count
        )


@dataclass(frozen=True)
class ValidationReport:
    """Structured validation report with summary statistics (V2).

    Produced by :func:`issues_to_report` from a list of :class:`ValidationIssue`.
    """

    total_issues: int
    severity_counts: SeverityCounts
    rule_counts: List[RuleCounts]
    sheet_counts: List[SheetCounts]
    top_errors: List[str]  # rule names that contributed errors
    workbook_clean: bool = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "workbook_clean", self.severity_counts.error == 0)

    def markdown_summary(self) -> str:
        """Human-readable one-page summary, suitable for printing before the CSV detail."""
        lines: List[str] = []
        status = "✅ PASS" if self.workbook_clean else "❌ FAIL"
        lines.append(f"## 数据校验报告  [{status}]")
        lines.append("")
        lines.append(f"- 总问题数: **{self.total_issues}**")
        lines.append(f"  - 🔴 Error: {self.severity_counts.error}")
        lines.append(f"  - 🟡 Warning: {self.severity_counts.warn}")
        lines.append(f"  - 🔵 Info: {self.severity_counts.info}")
        lines.append("")

        if self.rule_counts:
            lines.append("### Top issues by rule")
            lines.append("")
            lines.append("| Rule | Count | Severity |")
            lines.append("|------|------:|----------|")
            for rc in sorted(self.rule_counts, key=lambda x: -x.count)[:15]:
                sev_icon = {"error": "🔴", "warn": "🟡", "info": "🔵"}.get(rc.severity, "")
                lines.append(f"| `{rc.rule}` | {rc.count} | {sev_icon} {rc.severity} |")
            lines.append("")

        if self.sheet_counts:
            lines.append("### Issues by sheet")
            lines.append("")
            lines.append("| Sheet | Errors | Warnings | Info |")
            lines.append("|-------|-------:|--------:|-----:|")
            for sc in sorted(self.sheet_counts, key=lambda x: -x.error_count - x.warn_count)[
                :15
            ]:
                lines.append(
                    f"| `{sc.sheet}` | {sc.error_count} | {sc.warn_count} | {sc.info_count} |"
                )
            lines.append("")

        if self.top_errors:
            lines.append("### ⚠️  Error categories requiring attention")
            lines.append("")
            for rule in self.top_errors:
                lines.append(f"- **`{rule}`**: see detail rows below")
            lines.append("")

        if self.workbook_clean:
            lines.append("✅ 工作簿校验通过，无 error 级别问题。")
        return "\n".join(lines)


CALC_ERROR_LITERAL = "计算错误"


def default_sheet_specs() -> Dict[str, SheetSpec]:
    """Specs derived from the REAL workbook (data/蜜可诗产品库.xlsx).

    Keep this list conservative: only define sheets/columns we have observed.
    Unknown sheets will still be checked for emptiness + calc-error literals.
    """

    return {
        "产品毛利表_Gelato": SheetSpec(
            required_columns=["品类", "品名", "规格", "状态", "成本", "门店成本", "定价", "毛利率", "门店毛利率"],
            key_columns=["品类", "品名", "规格"],
            numeric_columns=["成本", "门店成本", "定价"],
            percent_columns=["毛利率", "门店毛利率"],
            positive_columns=["成本", "门店成本", "定价"],
        ),
        "产品毛利表_雪花冰": SheetSpec(
            required_columns=["品类", "品名", "规格", "状态", "成本", "门店成本", "定价", "毛利率", "门店毛利率"],
            key_columns=["品类", "品名", "规格"],
            numeric_columns=["成本", "门店成本", "定价"],
            percent_columns=["毛利率", "门店毛利率"],
            positive_columns=["成本", "门店成本", "定价"],
        ),
        "门店产品毛利表_Gelato": SheetSpec(
            required_columns=["品类", "品名", "规格", "状态", "门店成本", "定价", "门店毛利率"],
            key_columns=["品类", "品名", "规格"],
            numeric_columns=["门店成本", "定价"],
            percent_columns=["门店毛利率"],
            positive_columns=["门店成本", "定价"],
        ),
        "产品成本计算表_Gelato": SheetSpec(
            required_columns=["品类", "品名", "100克成本", "制作类型", "规格", "状态", "成本", "单位成本", "门店成本", "门店单位成本"],
            key_columns=["品类", "品名", "规格"],
            numeric_columns=["100克成本", "成本", "单位成本", "门店成本", "门店单位成本"],
            positive_columns=["成本", "单位成本", "门店成本", "门店单位成本"],
        ),
        "产品配方表_Gelato": SheetSpec(
            required_columns=["品类", "品名", "配料", "用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            key_columns=["品类", "品名", "配料"],
            numeric_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            positive_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
        ),
        "产品出品表_Gelato": SheetSpec(
            required_columns=["品类", "品名", "规格", "主原料", "配料", "用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            key_columns=["品类", "品名", "规格"],
            numeric_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            positive_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
        ),
        "产品成本计算表_雪花冰": SheetSpec(
            required_columns=["品类", "品名", "制作类型", "规格", "状态", "成本", "单位成本", "门店成本", "门店单位成本"],
            key_columns=["品类", "品名", "规格"],
            numeric_columns=["成本", "单位成本", "门店成本", "门店单位成本"],
            positive_columns=["成本", "单位成本", "门店成本", "门店单位成本"],
        ),
        "半成品配方表_雪花冰": SheetSpec(
            required_columns=["品类", "品名", "配料", "用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            key_columns=["品类", "品名", "配料"],
            numeric_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            positive_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
        ),
        "产品出品表_雪花冰": SheetSpec(
            required_columns=[
                "品类",
                "品名",
                "规格",
                "主原料",
                "配料",
                "冰激凌",
                "用量",
                "单位成本",
                "总成本",
                "门店单位成本",
                "门店总成本",
            ],
            key_columns=["品类", "品名", "规格"],
            numeric_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            positive_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
        ),
        "产品成本计算表_饮品": SheetSpec(
            required_columns=["品类", "品名", "制作类型", "规格", "状态", "成本", "单位成本", "门店成本", "门店单位成本"],
            key_columns=["品类", "品名", "规格"],
            numeric_columns=["成本", "单位成本", "门店成本", "门店单位成本"],
            positive_columns=["成本", "单位成本", "门店成本", "门店单位成本"],
        ),
        "半成品配方表_饮品": SheetSpec(
            required_columns=["品类", "品名", "配料", "用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            key_columns=["品类", "品名", "配料"],
            numeric_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            positive_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
        ),
        "产品出品表_饮品": SheetSpec(
            required_columns=["品类", "品名", "规格", "主原料", "配料", "用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            key_columns=["品类", "品名", "规格"],
            numeric_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
            positive_columns=["用量", "单位成本", "总成本", "门店单位成本", "门店总成本"],
        ),
        "总原料成本表": SheetSpec(
            required_columns=[
                "模板编号",
                "品项编码",
                "品项名称",
                "品项标识",
                "品项类型",
                "品项类别",
                "订货单位",
                "生效状态",
                "加价前单价",
                "加价方式",
                "加价值",
                "加价后单价",
                "单位量",
                "加价前成本",
                "加价后成本",
            ],
            key_columns=["品项编码"],
            numeric_columns=["加价前单价", "加价值", "加价后单价", "单位量", "加价前成本", "加价后成本"],
            positive_columns=["加价前单价", "加价后单价", "单位量", "加价前成本", "加价后成本"],
        ),
    }


def _required_columns_issues(sheet: str, df: pd.DataFrame, required: Iterable[str]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    cols = set(map(str, df.columns))
    for c in required:
        if c not in cols:
            issues.append(
                ValidationIssue(
                    severity="error",
                    sheet=sheet,
                    rule="required_columns",
                    message=f"Missing required column: {c}",
                )
            )
    return issues


def _empty_sheet_issues(sheet: str, df: pd.DataFrame) -> List[ValidationIssue]:
    if df.shape[0] == 0 and df.shape[1] == 0:
        return [
            ValidationIssue(
                severity="warn",
                sheet=sheet,
                rule="empty_sheet",
                message="Sheet is empty",
            )
        ]
    if df.shape[0] == 0:
        return [
            ValidationIssue(
                severity="warn",
                sheet=sheet,
                rule="empty_rows",
                message="Sheet has no data rows",
            )
        ]
    return []


def _null_in_key_columns(sheet: str, df: pd.DataFrame, key_cols: Sequence[str]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for c in key_cols:
        if c not in df.columns:
            continue
        s = df[c]
        bad = s.isna() | (s.astype(str).str.strip() == "")
        # report first N rows to keep output bounded
        for i in list(df.index[bad])[:50]:
            issues.append(
                ValidationIssue(
                    severity="warn",
                    sheet=sheet,
                    rule="null_key",
                    message=f"Null/empty key column '{c}'",
                    row=int(i) + 2,  # +1 header, +1 to 1-based
                    column=c,
                )
            )
    return issues


def _duplicate_keys(sheet: str, df: pd.DataFrame, key_cols: Sequence[str]) -> List[ValidationIssue]:
    if not key_cols:
        return []
    for c in key_cols:
        if c not in df.columns:
            return []

    issues: List[ValidationIssue] = []
    key_df = df[list(key_cols)].copy()
    # treat NaN as distinct (we already report null keys)
    dupe = key_df.duplicated(keep=False)
    if dupe.any():
        sample = df.loc[dupe, list(key_cols)].head(20)
        issues.append(
            ValidationIssue(
                severity="info",
                sheet=sheet,
                rule="duplicate_keys",
                message=f"Found duplicated keys on {list(key_cols)}; sample: {sample.to_dict(orient='records')}",
            )
        )
    return issues


def _calc_error_literals(sheet: str, df: pd.DataFrame) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []

    # Scan object-like columns only (fast enough at current scale)
    for c in df.columns:
        s = df[c]
        if s.dtype == object or pd.api.types.is_string_dtype(s):
            mask = s.astype(str).str.contains(CALC_ERROR_LITERAL, na=False)
            if mask.any():
                # summarize counts, and show a few concrete positions
                idxs = list(df.index[mask])
                issues.append(
                    ValidationIssue(
                        severity="error",
                        sheet=sheet,
                        rule="calc_error_literal",
                        message=f"Found literal '{CALC_ERROR_LITERAL}' in column '{c}' ({len(idxs)} rows)",
                        column=str(c),
                    )
                )
                for i in idxs[:10]:
                    issues.append(
                        ValidationIssue(
                            severity="info",
                            sheet=sheet,
                            rule="calc_error_literal_row",
                            message=f"{CALC_ERROR_LITERAL} at row {int(i)+2}, column '{c}'",
                            row=int(i) + 2,
                            column=str(c),
                        )
                    )

    return issues


def _non_numeric_in_numeric_columns(sheet: str, df: pd.DataFrame, numeric_cols: Sequence[str]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for c in numeric_cols:
        if c not in df.columns:
            continue
        s = df[c]
        # allow NaN
        non_null = s[~pd.isna(s)]
        if non_null.empty:
            continue

        # strings that are not parseable numbers are problems (including "计算错误")
        def _is_bad(v) -> bool:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return False
            if isinstance(v, (int, float)):
                return False
            txt = str(v).strip()
            if txt == "":
                return True
            # allow percentages in percent cols; here is numeric-only so percent is suspicious
            if txt.endswith("%"):
                return True
            try:
                float(txt)
                return False
            except Exception:
                return True

        bad_mask = non_null.map(_is_bad)
        if bad_mask.any():
            bad_idxs = list(bad_mask[bad_mask].index)
            issues.append(
                ValidationIssue(
                    severity="warn",
                    sheet=sheet,
                    rule="non_numeric",
                    message=f"Non-numeric values found in numeric column '{c}' ({len(bad_idxs)} rows)",
                    column=c,
                )
            )
            for i in bad_idxs[:10]:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        sheet=sheet,
                        rule="non_numeric_row",
                        message=f"Non-numeric '{df.at[i, c]}' at row {int(i)+2}, column '{c}'",
                        row=int(i) + 2,
                        column=c,
                    )
                )
    return issues


def _duplicate_data_rows(sheet: str, df: pd.DataFrame) -> List[ValidationIssue]:
    """Detect completely identical rows (excluding all-NaN rows)."""
    issues: List[ValidationIssue] = []
    if len(df) < 2:
        return issues
    # Drop rows that are all null/empty before checking for dupes
    non_all_null = df.dropna(how="all")
    if len(non_all_null) < 2:
        return issues

    dupe_mask = non_all_null.duplicated(keep=False)
    if not dupe_mask.any():
        return issues

    # Count occurrences of each duplicate group
    dupe_df = non_all_null[dupe_mask]
    counts = dupe_df.groupby(list(dupe_df.columns), dropna=False).size()
    top = counts.sort_values(ascending=False).head(10)
    examples = []
    for _, (row, cnt) in enumerate(top.items()):
        row_vals = list(row)[:5]  # show first 5 cols as example
        examples.append(f"{cnt}x: {row_vals}")

    issues.append(
        ValidationIssue(
            severity="warn",
            sheet=sheet,
            rule="duplicate_rows",
            message=f"Found {dupe_mask.sum()} duplicated data rows ({counts.size} unique groups). Examples: {'; '.join(examples)}",
        )
    )
    return issues


def _unmapped_sheet_warning(sheet: str, df: pd.DataFrame) -> List[ValidationIssue]:
    """Warn when a sheet exists in the workbook but has no SheetSpec.

    This is informational — it helps detect extra/misnamed sheets.
    """
    issues: List[ValidationIssue] = []
    issues.append(
        ValidationIssue(
            severity="info",
            sheet=sheet,
            rule="unmapped_sheet",
            message=f"Sheet '{sheet}' is not in the known SheetSpec list ({df.shape[0]} rows × {df.shape[1]} cols).",
        )
    )
    return issues


# -------------------------------------------------------------------------------------------------
# F-009 New: zeroed / estimated / material-gap checks
# -------------------------------------------------------------------------------------------------

def _get_product_key(idx: int, df: pd.DataFrame) -> str:
    """Return the normalized ProductKey for row idx, or empty string if unavailable."""
    key = _build_product_key(df)
    return str(key.at[idx]) if idx in key.index else ""


def _zeroed_items(sheets: Dict[str, pd.DataFrame]) -> List[ValidationIssue]:
    """Detect 上线 products whose 成本/定价 have been forcibly zeroed.

    This is distinct from zero_or_negative_value (which flags <=0).
    Here we flag exactly-0 numeric values on 上线 products that should have
    a real cost / price — a strong indicator of missing-source data.
    """
    issues: List[ValidationIssue] = []
    for name, df in sheets.items():
        if "状态" not in df.columns:
            continue
        status_col = df["状态"].astype(str).str.strip()
        online_mask = status_col == "上线"
        if not online_mask.any():
            continue

        cost_cols = [c for c in ["成本", "门店成本", "定价", "单位成本", "门店单位成本"] if c in df.columns]
        for c in cost_cols:
            s = df[c]
            try:
                num_s = pd.to_numeric(s, errors="coerce")
            except Exception:
                continue
            zeroed = online_mask & (num_s == 0) & (~num_s.isna())
            if not zeroed.any():
                continue
            for idx in list(zeroed[zeroed].index)[:50]:
                sku_key = _get_product_key(idx, df)
                issues.append(
                    ValidationIssue(
                        severity="warn",
                        sheet=name,
                        rule="zeroed_item",
                        message=f"上线 product '{sku_key}' has cost/price column '{c}' = 0 (possibly missing source data)",
                        row=int(idx) + 2,
                        column=c,
                        affected_skus=[sku_key] if sku_key else [],
                    )
                )
    return issues


def _estimated_items(sheets: Dict[str, pd.DataFrame]) -> List[ValidationIssue]:
    """Detect cells or rows explicitly tagged as estimated/approximate values.

    Looks for '估算' or '估计' substrings in any cell of 上线 products,
    as well as '估算' appearing alone in numeric columns.
    """
    ESTIMATED_MARKERS = {"估算", "估计", "暂估", "预估", "≈"}
    issues: List[ValidationIssue] = []
    for name, df in sheets.items():
        obj_cols = [c for c in df.columns if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])]
        if not obj_cols:
            continue
        mask = pd.Series(False, index=df.index)
        for c in obj_cols:
            s = df[c].astype(str)
            for marker in ESTIMATED_MARKERS:
                mask = mask | s.str.contains(marker, na=False)
        if not mask.any():
            continue
        for idx in list(df.index[mask])[:100]:
            sku_key = _get_product_key(idx, df)
            hit_cols = [c for c in obj_cols if str(df.at[idx, c]) in ESTIMATED_MARKERS
                        or any(m in str(df.at[idx, c]) for m in ESTIMATED_MARKERS)]
            issues.append(
                ValidationIssue(
                    severity="info",
                    sheet=name,
                    rule="estimated_item",
                    message=f"Row contains estimated/approximate marker for '{sku_key}': {hit_cols}",
                    row=int(idx) + 2,
                    affected_skus=[sku_key] if sku_key else [],
                )
            )
    return issues


def _material_gaps(sheets: Dict[str, pd.DataFrame]) -> List[ValidationIssue]:
    """Detect materials with no valid unit price in 总原料成本表.

    A 'material gap' is a row in 总原料成本表 where:
    - 加价后单价 is missing or <= 0, OR
    - 加价前单价 and 加价后单价 are both 0 (no price source).
    """
    issues: List[ValidationIssue] = []
    raw = sheets.get("总原料成本表")
    if raw is None:
        return issues

    price_cols = ["加价后单价", "加价前单价", "加价前成本", "加价后成本"]
    available = [c for c in price_cols if c in raw.columns]
    if not available:
        return issues

    # Build numeric series for each relevant price column
    num_price = pd.to_numeric(raw["加价后单价"], errors="coerce")
    num_base = pd.to_numeric(raw.get("加价前单价", raw["加价前成本"]), errors="coerce")

    # Gap: 加价后单价 is NaN or <= 0 while a base price column is also <= 0 / NaN
    gap_mask = (num_price.isna() | (num_price <= 0)) & (num_base.isna() | (num_base <= 0))

    if not gap_mask.any():
        return issues

    # Collect gap material names
    mat_name_col = "品项名称" if "品项名称" in raw.columns else None
    mat_code_col = "品项编码" if "品项编码" in raw.columns else None

    for idx in list(raw.index[gap_mask])[:100]:
        mat_name = str(raw.at[idx, mat_name_col]).strip() if mat_name_col else ""
        mat_code = str(raw.at[idx, mat_code_col]).strip() if mat_code_col else ""
        display = mat_name if mat_name else mat_code
        price_val = raw.at[idx, "加价后单价"] if "加价后单价" in raw.columns else "N/A"
        issues.append(
            ValidationIssue(
                severity="error",
                sheet="总原料成本表",
                rule="material_gap",
                message=f"Material '{display}' has no valid unit price (加价后单价={price_val}); procurement cost cannot be computed",
                row=int(idx) + 2,
                affected_materials=[display] if display else [],
            )
        )
    return issues


def _positive_value_issues(
    sheet: str, df: pd.DataFrame, pos_cols: Sequence[str]
) -> List[ValidationIssue]:
    """Warn/error when required-positive columns contain zero or negative values for 上线 products."""
    issues: List[ValidationIssue] = []
    if "状态" not in df.columns:
        return issues

    for c in pos_cols:
        if c not in df.columns:
            continue
        s = df[c]
        if s.dropna().empty:
            continue

        # Only check 上线 rows
        status_mask = df["状态"].astype(str).str.strip() == "上线"

        # Try to convert to numeric; skip comparison if column is clearly non-numeric
        try:
            s_num = pd.to_numeric(s, errors="coerce").fillna(0)
        except Exception:
            continue

        pos_mask = status_mask & (s_num <= 0)

        if not pos_mask.any():
            continue

        bad_idxs = list(pos_mask[pos_mask].index)
        issues.append(
            ValidationIssue(
                severity="error",
                sheet=sheet,
                rule="zero_or_negative_value",
                message=f"上线 product has zero/negative '{c}' in {len(bad_idxs)} row(s)",
                column=c,
            )
        )
        for i in bad_idxs[:5]:
            issues.append(
                ValidationIssue(
                    severity="info",
                    sheet=sheet,
                    rule="zero_or_negative_row",
                    message=f"Zero/negative '{c}' at row {int(i)+2}: value={df.at[i, c]}",
                    row=int(i) + 2,
                    column=c,
                )
            )
    return issues


def _percent_format_issues(sheet: str, df: pd.DataFrame, percent_cols: Sequence[str]) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    for c in percent_cols:
        if c not in df.columns:
            continue
        s = df[c]
        non_null = s[~pd.isna(s)]
        if non_null.empty:
            continue

        def _is_bad(v) -> bool:
            if isinstance(v, (int, float)):
                # allow 0-1 floats
                return not (0 <= float(v) <= 1)
            txt = str(v).strip()
            if txt.endswith("%"):
                return False
            # allow 0-1 numeric-ish strings
            try:
                f = float(txt)
                return not (0 <= f <= 1)
            except Exception:
                return True

        bad = non_null.map(_is_bad)
        if bad.any():
            bad_idxs = list(bad[bad].index)
            issues.append(
                ValidationIssue(
                    severity="warn",
                    sheet=sheet,
                    rule="percent_format",
                    message=f"Unexpected percent format in column '{c}' ({len(bad_idxs)} rows)",
                    column=c,
                )
            )
            for i in bad_idxs[:10]:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        sheet=sheet,
                        rule="percent_format_row",
                        message=f"Bad percent '{df.at[i, c]}' at row {int(i)+2}, column '{c}'",
                        row=int(i) + 2,
                        column=c,
                    )
                )

    return issues


def _referential_integrity_issues(sheets: Dict[str, pd.DataFrame]) -> List[ValidationIssue]:
    """Lightweight referential checks using the real workbook semantics.

    - 产品出品表_*: 主原料 (when present) should exist in either 产品成本计算表_* or 半成品配方表_* of the same category.
    - 配方/半成品配方: 配料 should exist in 总原料成本表.品项名称 when possible.

    These are WARN-level because the workbook may intentionally include exceptions.
    """

    issues: List[ValidationIssue] = []

    # Build ingredient catalog from 总原料成本表
    raw = sheets.get("总原料成本表")
    ingredient_names: set[str] = set()
    if raw is not None and "品项名称" in raw.columns:
        ingredient_names = set(
            str(x).strip() for x in raw["品项名称"].dropna().astype(str).tolist() if str(x).strip() != ""
        )

    def _name_set(sheet_name: str) -> set[str]:
        df = sheets.get(sheet_name)
        if df is None or "品名" not in df.columns:
            return set()
        return set(str(x).strip() for x in df["品名"].dropna().astype(str).tolist() if str(x).strip() != "")

    # per-category refs for 主原料
    category_sources: Dict[str, set[str]] = {
        "Gelato": _name_set("产品成本计算表_Gelato"),
        "雪花冰": _name_set("产品成本计算表_雪花冰") | _name_set("半成品配方表_雪花冰"),
        "饮品": _name_set("产品成本计算表_饮品") | _name_set("半成品配方表_饮品"),
    }

    for out_sheet, cat in [("产品出品表_Gelato", "Gelato"), ("产品出品表_雪花冰", "雪花冰"), ("产品出品表_饮品", "饮品")]:
        df = sheets.get(out_sheet)
        if df is None or "主原料" not in df.columns:
            continue
        src = category_sources.get(cat, set())
        if not src:
            continue
        s = df["主原料"].dropna().astype(str).map(str.strip)
        missing = s[(s != "") & (~s.isin(src))]
        if not missing.empty:
            # summarize top missing names
            top = missing.value_counts().head(20)
            issues.append(
                ValidationIssue(
                    severity="warn",
                    sheet=out_sheet,
                    rule="missing_main_material_ref",
                    message=f"主原料 not found in cost/recipe sources for '{cat}': {top.to_dict()}",
                    column="主原料",
                )
            )

    # ingredient membership checks
    if ingredient_names:
        for sheet_name in ["产品配方表_Gelato", "半成品配方表_雪花冰", "半成品配方表_饮品"]:
            df = sheets.get(sheet_name)
            if df is None or "配料" not in df.columns:
                continue
            s = df["配料"].dropna().astype(str).map(str.strip)
            missing = s[(s != "") & (~s.isin(ingredient_names))]
            if not missing.empty:
                top = missing.value_counts().head(30)
                issues.append(
                    ValidationIssue(
                        severity="warn",
                        sheet=sheet_name,
                        rule="missing_ingredient_ref",
                        message=f"配料 not found in 总原料成本表.品项名称: {top.to_dict()}",
                        column="配料",
                    )
                )

    return issues


def _build_product_key(df: pd.DataFrame) -> pd.Series:
    """Build a normalized ProductKey for cross-sheet matching.

    Real workbook uses the tuple (品类, 品名, 规格) as the practical identity across:
    - 产品毛利表_*
    - 产品成本计算表_*
    - 产品出品表_*

    We keep it as a string so it can be safely carried into messages/CSV.
    Missing parts yield an empty key (excluded by callers).
    """

    def _col(name: str) -> pd.Series:
        if name not in df.columns:
            return pd.Series([""] * len(df), index=df.index)
        return df[name].fillna("").astype(str).map(str.strip)

    cat = _col("品类")
    name = _col("品名")
    spec = _col("规格")
    key = cat + "|" + name + "|" + spec
    incomplete = (cat == "") | (name == "") | (spec == "")
    return key.mask(incomplete, "")


def _to_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, str):
            t = v.strip()
            if t == "":
                return None
            if t.endswith("%"):
                return None
            return float(t)
        if isinstance(v, (int, float)):
            if isinstance(v, float) and pd.isna(v):
                return None
            return float(v)
    except Exception:
        return None
    return None


def _cross_sheet_product_consistency_issues(sheets: Dict[str, pd.DataFrame]) -> List[ValidationIssue]:
    """ProductKey-based consistency checks across 毛利表/成本计算表/出品表.

    Rules (F-001):
    - missing_product_row: key exists in one sheet but is missing in another (same category)
    - cost_mismatch: 成本/门店成本 differs between 毛利表 and 成本计算表 for same ProductKey
    - price_missing: 上线 products in 毛利表 must have a non-empty, >0 定价
    """

    issues: List[ValidationIssue] = []

    categories = {
        "Gelato": {
            "gross": "产品毛利表_Gelato",
            "cost": "产品成本计算表_Gelato",
            "out": "产品出品表_Gelato",
        },
        "雪花冰": {
            "gross": "产品毛利表_雪花冰",
            "cost": "产品成本计算表_雪花冰",
            "out": "产品出品表_雪花冰",
        },
        "饮品": {
            # 饮品在当前真实工作簿中没有 产品毛利表_* 对应 sheet。
            "cost": "产品成本计算表_饮品",
            "out": "产品出品表_饮品",
        },
    }

    def _key_index_map(df: pd.DataFrame) -> Dict[str, int]:
        key = _build_product_key(df)
        m: Dict[str, int] = {}
        for idx, k in key.items():
            if not k:
                continue
            m.setdefault(k, int(idx))
        return m

    def _mismatch(a: Optional[float], b: Optional[float], *, tol_abs: float = 0.01, tol_rel: float = 0.005) -> bool:
        if a is None or b is None:
            return False
        diff = abs(a - b)
        rel = diff / max(1.0, abs(b))
        return diff > tol_abs and rel > tol_rel

    for cat, spec in categories.items():
        gross_name = spec.get("gross")
        cost_name = spec.get("cost")
        out_name = spec.get("out")

        gross_df = sheets.get(gross_name) if gross_name else None
        cost_df = sheets.get(cost_name) if cost_name else None
        out_df = sheets.get(out_name) if out_name else None

        gross_idx: Dict[str, int] = _key_index_map(gross_df) if gross_df is not None else {}
        cost_idx: Dict[str, int] = _key_index_map(cost_df) if cost_df is not None else {}
        out_idx: Dict[str, int] = _key_index_map(out_df) if out_df is not None else {}

        gross_keys = set(gross_idx)
        cost_keys = set(cost_idx)
        out_keys = set(out_idx)

        # --- missing_product_row
        if gross_df is not None and cost_df is not None:
            for k in sorted(gross_keys - cost_keys)[:200]:
                i = gross_idx.get(k)
                issues.append(
                    ValidationIssue(
                        severity="error",
                        sheet=cost_name,
                        rule="missing_product_row",
                        message=f"Missing product row in {cost_name} for ProductKey '{k}' (present in {gross_name})",
                        row=(int(i) + 2) if i is not None else None,
                    )
                )

            for k in sorted(cost_keys - gross_keys)[:200]:
                i = cost_idx.get(k)
                issues.append(
                    ValidationIssue(
                        severity="warn",
                        sheet=gross_name,
                        rule="missing_product_row",
                        message=f"Missing product row in {gross_name} for ProductKey '{k}' (present in {cost_name})",
                        row=(int(i) + 2) if i is not None else None,
                    )
                )

        if out_df is not None and cost_df is not None:
            for k in sorted(cost_keys - out_keys)[:200]:
                i = cost_idx.get(k)
                issues.append(
                    ValidationIssue(
                        severity="warn",
                        sheet=out_name,
                        rule="missing_product_row",
                        message=f"Missing product row in {out_name} for ProductKey '{k}' (present in {cost_name})",
                        row=(int(i) + 2) if i is not None else None,
                    )
                )

        if out_df is not None and gross_df is not None:
            for k in sorted(gross_keys - out_keys)[:200]:
                i = gross_idx.get(k)
                issues.append(
                    ValidationIssue(
                        severity="warn",
                        sheet=out_name,
                        rule="missing_product_row",
                        message=f"Missing product row in {out_name} for ProductKey '{k}' (present in {gross_name})",
                        row=(int(i) + 2) if i is not None else None,
                    )
                )

        # --- price_missing (gross only)
        if gross_df is not None and ("状态" in gross_df.columns) and ("定价" in gross_df.columns):
            keys = _build_product_key(gross_df)
            for idx, row in gross_df.iterrows():
                st = str(row.get("状态", "")).strip()
                if st != "上线":
                    continue
                price = _to_float(row.get("定价"))
                if price is None or price <= 0:
                    issues.append(
                        ValidationIssue(
                            severity="error",
                            sheet=gross_name,
                            rule="price_missing",
                            message=f"上线 product has missing/invalid 定价 (ProductKey '{keys.at[idx]}', 定价='{row.get('定价')}')",
                            row=int(idx) + 2,
                            column="定价",
                        )
                    )

        # --- cost_mismatch (gross vs cost)
        if gross_df is not None and cost_df is not None and ("成本" in gross_df.columns) and ("成本" in cost_df.columns):
            gross_keys_ser = _build_product_key(gross_df)
            cost_keys_ser = _build_product_key(cost_df)

            gross_cost: Dict[str, Optional[float]] = {}
            gross_store_cost: Dict[str, Optional[float]] = {}
            for idx, k in gross_keys_ser.items():
                if not k or k in gross_cost:
                    continue
                gross_cost[k] = _to_float(gross_df.at[idx, "成本"])
                gross_store_cost[k] = _to_float(gross_df.at[idx, "门店成本"]) if "门店成本" in gross_df.columns else None

            cost_cost: Dict[str, Optional[float]] = {}
            cost_store_cost: Dict[str, Optional[float]] = {}
            for idx, k in cost_keys_ser.items():
                if not k or k in cost_cost:
                    continue
                cost_cost[k] = _to_float(cost_df.at[idx, "成本"])
                cost_store_cost[k] = _to_float(cost_df.at[idx, "门店成本"]) if "门店成本" in cost_df.columns else None

            common = sorted(set(gross_cost) & set(cost_cost))
            for k in common[:2000]:
                if _mismatch(gross_cost.get(k), cost_cost.get(k)):
                    issues.append(
                        ValidationIssue(
                            severity="warn",
                            sheet=gross_name,
                            rule="cost_mismatch",
                            message=f"成本 mismatch for ProductKey '{k}': {gross_name}.成本={gross_cost.get(k)} vs {cost_name}.成本={cost_cost.get(k)}",
                            row=(gross_idx.get(k) + 2) if k in gross_idx else None,
                            column="成本",
                        )
                    )

                if _mismatch(gross_store_cost.get(k), cost_store_cost.get(k)):
                    issues.append(
                        ValidationIssue(
                            severity="warn",
                            sheet=gross_name,
                            rule="cost_mismatch",
                            message=f"门店成本 mismatch for ProductKey '{k}': {gross_name}.门店成本={gross_store_cost.get(k)} vs {cost_name}.门店成本={cost_store_cost.get(k)}",
                            row=(gross_idx.get(k) + 2) if k in gross_idx else None,
                            column="门店成本",
                        )
                    )

    return issues


def validate_workbook(
    sheets: Dict[str, pd.DataFrame],
    *,
    expected_sheet_count: int = 13,
    required_columns_by_sheet: Optional[Dict[str, List[str]]] = None,
    sheet_specs: Optional[Dict[str, SheetSpec]] = None,
) -> List[ValidationIssue]:
    """Validate workbook.

    Compared to the initial scaffold, this version is grounded on the real 蜜可诗产品库.xlsx:
    - sheet-specific required columns
    - key null checks
    - calc-error literal detection ("计算错误")
    - numeric/percent format sanity checks
    - duplicate data-row detection (V2)
    - zero/negative value checks for 上线 products (V2)
    - unmapped-sheet informational warnings (V2)
    - a small set of referential integrity warnings

    Output stays CSV-friendly.
    """

    issues: List[ValidationIssue] = []
    sheet_names = list(sheets.keys())

    if len(sheet_names) != expected_sheet_count:
        issues.append(
            ValidationIssue(
                severity="warn",
                sheet="__workbook__",
                rule="sheet_count",
                message=f"Expected {expected_sheet_count} sheets, got {len(sheet_names)}",
            )
        )

    specs = sheet_specs or default_sheet_specs()
    required_columns_by_sheet = required_columns_by_sheet or {}

    for name, df in sheets.items():
        issues.extend(_empty_sheet_issues(name, df))
        issues.extend(_calc_error_literals(name, df))

        spec = specs.get(name)
        if spec is None:
            # Unknown sheet: ad-hoc required cols + informational warnings
            issues.extend(_unmapped_sheet_warning(name, df))
            required = required_columns_by_sheet.get(name)
            if required:
                issues.extend(_required_columns_issues(name, df, required))
            continue

        issues.extend(_required_columns_issues(name, df, spec.required_columns))
        issues.extend(_null_in_key_columns(name, df, spec.key_columns))
        issues.extend(_duplicate_keys(name, df, spec.key_columns))
        issues.extend(_non_numeric_in_numeric_columns(name, df, spec.numeric_columns))
        issues.extend(_percent_format_issues(name, df, spec.percent_columns))
        # V2 new checks
        issues.extend(_duplicate_data_rows(name, df))
        issues.extend(_positive_value_issues(name, df, spec.positive_columns))

    issues.extend(_referential_integrity_issues(sheets))
    issues.extend(_cross_sheet_product_consistency_issues(sheets))
    # F-009 new checks
    issues.extend(_zeroed_items(sheets))
    issues.extend(_estimated_items(sheets))
    issues.extend(_material_gaps(sheets))
    return issues


def issues_to_dataframe(issues: List[ValidationIssue]) -> pd.DataFrame:
    rows = []
    for i in issues:
        # Expand multi-value fields into multiple rows for CSV readability
        skus = i.affected_skus if i.affected_skus else [""]
        mats = i.affected_materials if i.affected_materials else [""]
        for sku in skus:
            for mat in mats:
                rows.append({
                    "severity": i.severity,
                    "sheet": i.sheet,
                    "rule": i.rule,
                    "message": i.message,
                    "row": i.row,
                    "column": i.column,
                    "affected_skus": sku,
                    "affected_materials": mat,
                })
    return pd.DataFrame(rows)


def issues_to_report(issues: List[ValidationIssue]) -> ValidationReport:
    """Build a structured ValidationReport from a flat list of issues.

    This gives callers a quick programmatic or human-readable summary without
    having to re-parse the CSV output.
    """
    sev = SeverityCounts(
        error=sum(1 for i in issues if i.severity == "error"),
        warn=sum(1 for i in issues if i.severity == "warn"),
        info=sum(1 for i in issues if i.severity == "info"),
    )

    # Rule-level counts + severity per rule
    from collections import Counter

    rule_counter: Counter = Counter()
    rule_severity: Dict = {}
    _sev_order = {"error": 0, "warn": 1, "info": 2}
    for i in issues:
        rule_counter[i.rule] += 1
        # Track worst (lowest-order) severity per rule; always set on first occurrence
        if i.rule not in rule_severity:
            rule_severity[i.rule] = i.severity
        else:
            cur = rule_severity[i.rule]
            if _sev_order.get(i.severity, 99) < _sev_order.get(cur, 99):
                rule_severity[i.rule] = i.severity

    rule_counts = [
        RuleCounts(rule=r, count=c, severity=rule_severity[r])
        for r, c in rule_counter.most_common()
    ]

    # Sheet-level counts
    sheet_errors: Dict[str, int] = {}
    sheet_warns: Dict[str, int] = {}
    sheet_infos: Dict[str, int] = {}
    for i in issues:
        if i.sheet == "__workbook__":
            continue
        if i.severity == "error":
            sheet_errors[i.sheet] = sheet_errors.get(i.sheet, 0) + 1
        elif i.severity == "warn":
            sheet_warns[i.sheet] = sheet_warns.get(i.sheet, 0) + 1
        else:
            sheet_infos[i.sheet] = sheet_infos.get(i.sheet, 0) + 1

    all_sheets = set(sheet_errors) | set(sheet_warns) | set(sheet_infos)
    sheet_counts = [
        SheetCounts(
            sheet=s,
            error_count=sheet_errors.get(s, 0),
            warn_count=sheet_warns.get(s, 0),
            info_count=sheet_infos.get(s, 0),
        )
        for s in sorted(all_sheets)
    ]

    # Rules that contributed errors (for the attention section)
    top_errors = sorted({i.rule for i in issues if i.severity == "error"})

    return ValidationReport(
        total_issues=len(issues),
        severity_counts=sev,
        rule_counts=rule_counts,
        sheet_counts=sheet_counts,
        top_errors=top_errors,
    )
