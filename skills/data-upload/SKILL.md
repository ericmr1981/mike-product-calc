---
name: data-upload
description: >-
  Upload warehouse stock, inventory check (盘点), and delivery (到货) data to
  Supabase via CLI commands. Use when an agent needs to upload, sync, import,
  or persist inventory-related xlsx files to the system. Also triggers when
  the user mentions shipping data files, sending inventory files, or "上传数据".
  The agent should ALWAYS consult this skill before trying to upload data through
  other means (direct API calls, file writes, etc.).
---

# Data Upload (数据上传)

A skill for external agents to upload inventory operational data to Supabase using CLI commands, and to query/manage data using business commands.

## Data Architecture

**Supabase is the only data source.** All business commands (validate, sku-list, profit-oracle, etc.) read from Supabase. Supabase credentials (`SUPABASE_URL` + `SUPABASE_SERVICE_KEY`) are always required.

Credentials resolve from:
1. Environment variables `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`
2. `.streamlit/secrets.toml` (`[supabase]` section)

Without credentials, all commands exit with code 1.

## Upload Types

There are three upload types for getting operational data INTO Supabase. Each has its own CLI command, file format, and filename conventions.

### 1. Warehouse Stock Snapshots (`mpc inventory sync`)

Uploads a warehouse inventory export xlsx. The file must come from the WMS export system.

**Filename pattern:** `仓库库存导出{YYYY}年{MM}月{DD}日{HH}时{MM}分{SS}秒.xlsx`

**Sheet name:** Must be exactly `仓库库存导出`

**Required columns (16):**
```
品项编码 | 品项名称 | 规格 | 单位 | 二级品项类别 | 一级品项类别 | 品项属性名
仓库名称 | 仓库编码 | 库存量 | 可用量 | 占用量 | 预计出库量 | 预计入库量
现存金额 | 库存单价
```

**Validation:**
- All 6 required text fields must be non-empty
- All 8 numeric fields must be parseable as numbers
- Duplicate (item_code, warehouse_code) pairs are rejected within a batch
- `库存量 × 库存单价` must match `现存金额` within tolerance (warns only)
- Negative stock quantities are flagged as warnings

**CLI:**
```bash
# Dry-run (validate only, no database writes)
mpc inventory sync /path/to/file.xlsx --dry-run

# Real upload
mpc inventory sync /path/to/file.xlsx

# Batch upload from directory with archive
mpc inventory sync /path/to/directory/ \
  --archive-dir /path/to/archived/ \
  --max-files 5
```

### 2. Inventory Check / 盘点 (`mpc inventory check-sync`)

Uploads an inventory check (stocktake) xlsx.

**Filename pattern:** `盘点...{YYYY}年{MM}月{DD}日.xlsx` (日 is optional)

**Required columns (12):**
```
品项编码 | 品项名称 | 品项规格 | 品项类别 | 库存单位
初盘数量 | 复盘数量 | 系统库存 | 盘点差异 | 库存均价 | 差异金额 | 明细状态
```

**Key fields mapped to database:**
- `品项编码` → `item_code`
- `初盘数量` → `first_check_qty`
- `复盘数量` → `second_check_qty` (primary stock source)
- `系统库存` → `system_qty`
- `盘点差异` → `diff_qty`

**Validation:**
- Required: 品项编码, 品项名称, 库存单位 must all be non-empty
- All 6 numeric fields must be parseable
- Duplicate item_code within batch is rejected
- Negative system_qty is warned

**CLI:**
```bash
# Dry-run
mpc inventory check-sync /path/to/盘点文件.xlsx --dry-run

# Real upload
mpc inventory check-sync /path/to/盘点文件.xlsx

# From directory
mpc inventory check-sync /path/to/check/files/ \
  --archive-dir /path/to/archived/
```

### 3. Delivery Record / 到货 (`mpc inventory delivery-sync`)

Uploads a delivery / goods-receipt xlsx.

**Filename pattern:** `到货记录{YYYYMMDD}.xlsx`

**Required columns (6):**
```
品项编码 | 品项名称 | 品项规格 | 品项类别 | 库存单位 | 数量
```

**Key fields:**
- `数量` → `delivery_qty`

**Validation:**
- 品项编码 and 数量 are required
- 数量 must be numeric
- Duplicate item_code within batch is rejected

**CLI:**
```bash
# Dry-run
mpc inventory delivery-sync /path/to/到货记录20250529.xlsx --dry-run

# Real upload
mpc inventory delivery-sync /path/to/file.xlsx

# From directory
mpc inventory delivery-sync /path/to/delivery/files/ \
  --archive-dir /path/to/archived/
```

## Upload Workflow

**ALWAYS follow this workflow. Never skip the dry-run step.**

1. **Validate the file exists and is accessible** — check the path the user provides
2. **Dry-run first:**
   ```bash
   mpc inventory <type> <path> --dry-run
   ```
3. **Inspect the JSON result:**
   ```json
   {
     "cmd": "inventory-check-sync",
     "count": 1,
     "rows": [
       {
         "file": "/path/to/file.xlsx",
         "status": "dry_run",
         "inserted_rows": 50,
         "skipped_rows": 2,
         "warning_count": 3,
         "error_count": 1,
         "warning_summary": {"negative_stock": 3},
         "error_summary": {"missing_required_item_code": 1}
       }
     ]
   }
   ```
4. **If errors exist** — report them to the user and ask how to proceed. Don't proceed with the real upload if `error_count > 0` without user confirmation.
5. **If warnings exist** — mention them to the user but proceed with upload.
6. **Run the real upload:**
   ```bash
   mpc inventory <type> <path>
   ```
7. **Interpret the response:**
   - `"status": "imported"` — all rows written successfully
   - `"status": "partial"` — some rows had errors but imported what it could
   - `"status": "failed"` — nothing was imported (empty file or all rows had errors)
   - `"status": "skipped_duplicate"` — same file was already uploaded before (SHA256/name dedup)
   - `"status": "dry_run"` — dry-run mode, nothing was written

## Business Commands (reading Supabase data)

After data is uploaded, use these commands to query and verify:

```bash
# List SKUs (reads from Supabase automatically)
mpc sku-list --limit 10

# Validate data consistency
mpc validate

# BOM expansion → material demand
mpc prep-plan --sku "Gelato|木姜子甜橙|华夫碗=50"

# Purchase suggestion
mpc purchase-suggest --sku "Gelato|木姜子甜橙|华夫碗=50"

# Coverage days analysis
mpc coverage-estimate --sku "Gelato|木姜子甜橙|华夫碗=100"

# Cost reverse pricing
mpc target-pricing --product-key "Gelato|木姜子甜橙|华夫碗" --target-margin 0.35
```

These commands read master data (materials, products, recipes, specs) from Supabase automatically.

### CRUD operations (direct Supabase writes)

```bash
# Raw materials
mpc material list
mpc material create '{"name": "新原料", "category": "辅料", ...}'

# Recipes / BOM
mpc recipe list <product_id>
mpc recipe set <product_id> '[...]'

# Serving specs
mpc spec list <product_id>
mpc spec set <product_id> '[...]'

# Products
mpc product list
mpc product compute-costs <product_id>
```

## Error handling

| Scenario | Response | Action |
|----------|----------|--------|
| Sheet/header mismatch | `"status": "failed"`, error field has details | Check the xlsx has the correct columns |
| Duplicate upload | `"status": "skipped_duplicate"`, includes `batch_id` | File was already uploaded; no action needed |
| No matching files | `SystemExit(1)`: "no_files_matched" | Check the path and filename pattern |
| Supabase credentials missing | `SystemExit(1)` on upload commands | Set env vars or create secrets.toml |
| Exit code 0 | Everything OK | — |
| Exit code 1 | System/argument error | Check CLI args |
| Exit code 2 | Some files failed or business validation errors | Check `rows[].status` in the output |

## Archive workflow

When the user wants to clean up source files after upload, add `--archive-dir`:

```bash
mpc inventory check-sync /path/to/files/ \
  --archive-dir /path/to/archived/ \
  --dry-run            # first, to see what will happen
mpc inventory check-sync /path/to/files/ \
  --archive-dir /path/to/archived/   # then, upload and archive
```

Files that were successfully imported are moved to the archive directory. Duplicates and failures stay in place.

## Common patterns

### Upload and report summary to user

```bash
# Step 1: dry-run
mpc inventory check-sync 盘点单明细2025年06月01日.xlsx --dry-run --out /tmp/dry_run.json

# Step 2: show the user what will happen
# Step 3: if user confirms, run without dry-run
mpc inventory check-sync 盘点单明细2025年06月01日.xlsx --out /tmp/result.json
```

Then present a summary to the user like:
> 上传完成：成功导入 50 行，跳过 2 行（1 行缺少品项编码，1 行重复），3 个库存为负数的警告。

### Upload then verify

```bash
# Upload inventory check data
mpc inventory check-sync /path/to/checks/ --archive-dir /path/to/done/

# Verify data consistency
mpc validate
```

### Upload multiple files from a directory

```bash
mpc inventory check-sync /path/to/checks/ --max-files 10 --archive-dir /path/to/done/
```

This processes up to 10 matching files, archives successful ones, and reports a summary for each.

## Exit codes

The CLI uses standard exit codes:
- `0` — OK (all files processed, including skipped duplicates)
- `1` — system/argument error (file not found, bad args, missing Supabase credentials)
- `2` — business/validation failure (at least one file had errors, or validation rules violated)
