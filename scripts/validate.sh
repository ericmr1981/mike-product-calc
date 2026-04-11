#!/usr/bin/env bash
set -euo pipefail

XLSX=${1:?"Usage: scripts/validate.sh path/to/workbook.xlsx"}
OUT=${2:-data_validation_report.csv}

PYTHONPATH=src python3 -m mike_product_calc validate "$XLSX" --out "$OUT"
