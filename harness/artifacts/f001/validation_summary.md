# F-001 Validation Summary (REAL workbook)

Source report: `data_validation_report.csv`

Total issues: **197**

## Severity counts

| severity   |   count |
|:-----------|--------:|
| warn       |     105 |
| info       |      87 |
| error      |       5 |

## Top rules

| rule                   |   count |
|:-----------------------|--------:|
| null_key               |      97 |
| calc_error_literal_row |      41 |
| non_numeric_row        |      41 |
| calc_error_literal     |       5 |
| non_numeric            |       5 |
| duplicate_keys         |       5 |
| missing_ingredient_ref |       3 |

## Error issues (all)

| sheet          | rule               | message                                          | column   |
|:---------------|:-------------------|:-------------------------------------------------|:---------|
| 产品成本计算表_Gelato | calc_error_literal | Found literal '计算错误' in column '100克成本' (7 rows) | 100克成本   |
| 产品成本计算表_Gelato | calc_error_literal | Found literal '计算错误' in column '单位成本' (7 rows)   | 单位成本     |
| 产品成本计算表_Gelato | calc_error_literal | Found literal '计算错误' in column '门店单位成本' (7 rows) | 门店单位成本   |
| 总原料成本表         | calc_error_literal | Found literal '计算错误' in column '加价前成本' (41 rows) | 加价前成本    |
| 总原料成本表         | calc_error_literal | Found literal '计算错误' in column '加价后成本' (41 rows) | 加价后成本    |

## Example WARN issues (first 50)

| sheet          | rule        | message                                                      |   row | column   |
|:---------------|:------------|:-------------------------------------------------------------|------:|:---------|
| 产品成本计算表_Gelato | non_numeric | Non-numeric values found in numeric column '100克成本' (7 rows) |   nan | 100克成本   |
| 产品成本计算表_Gelato | non_numeric | Non-numeric values found in numeric column '单位成本' (7 rows)   |   nan | 单位成本     |
| 产品成本计算表_Gelato | non_numeric | Non-numeric values found in numeric column '门店单位成本' (7 rows) |   nan | 门店单位成本   |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品类'                                   |    76 | 品类       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品类'                                   |    77 | 品类       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品类'                                   |    78 | 品类       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品名'                                   |    76 | 品名       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品名'                                   |    77 | 品名       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品名'                                   |    78 | 品名       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '配料'                                   |    76 | 配料       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '配料'                                   |    77 | 配料       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '配料'                                   |    78 | 配料       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   296 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   297 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   298 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   299 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   300 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   301 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   302 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   303 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   304 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   305 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   306 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   307 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   308 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   309 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   310 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   311 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   312 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   313 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   314 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   315 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   316 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   317 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   318 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   319 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   320 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   321 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   322 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   323 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   324 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   325 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   326 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   327 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   328 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   329 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   330 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   331 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   332 | 品类       |
| 产品出品表_Gelato   | null_key    | Null/empty key column '品类'                                   |   333 | 品类       |