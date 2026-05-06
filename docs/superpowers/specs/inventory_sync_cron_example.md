# 库存上传定时任务示例

以下示例基于新命令：

```bash
mpc inventory sync <path> [--archive-dir <dir>]
```

## 1) 本机 cron（每小时执行）

```cron
0 * * * * cd /Users/ericmr/Documents/GitHub/mike-product-calc && \
  /usr/bin/env SUPABASE_URL="https://<project>.supabase.co" \
  SUPABASE_SERVICE_KEY="<service_role_key>" \
  /usr/bin/env PYTHONPATH=src \
  /usr/bin/python3 -m mike_product_calc inventory sync /Users/ericmr/Downloads \
  --pattern "仓库库存导出*.xlsx" \
  --archive-dir /Users/ericmr/Downloads/inventory-archived \
  >> /Users/ericmr/Downloads/inventory-sync.log 2>&1
```

## 2) 先试运行（不写入 Supabase）

```bash
PYTHONPATH=src python -m mike_product_calc inventory sync /Users/ericmr/Downloads \
  --pattern "仓库库存导出*.xlsx" \
  --dry-run
```

## 3) 单文件手工上传

```bash
PYTHONPATH=src python -m mike_product_calc inventory sync \
  "/Users/ericmr/Downloads/仓库库存导出2026年05月06日20时20分44秒.xlsx"
```

## 4) 输出 JSON 到文件（供 agent 二次消费）

```bash
PYTHONPATH=src python -m mike_product_calc inventory sync /Users/ericmr/Downloads \
  --out /Users/ericmr/Downloads/inventory-sync-result.json
```
