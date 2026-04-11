from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal

PlanType = Literal["sales", "production"]


@dataclass
class ProductionRow:
    date: str          # YYYY-MM-DD
    sku_key: str       # product_key
    spec: str
    qty: float
    plan_type: PlanType  # "sales" | "production"


@dataclass
class ProductionPlan:
    name: str
    rows: List[ProductionRow] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))

    def to_dataframe(self):
        import pandas as pd
        return pd.DataFrame([
            {"日期": r.date, "SKU": r.sku_key, "规格": r.spec, "数量": r.qty, "计划类型": r.plan_type}
            for r in self.rows
        ])

    @staticmethod
    def from_dataframe(name: str, df) -> "ProductionPlan":
        rows = []
        for _, row in df.iterrows():
            rows.append(ProductionRow(
                date=str(row["日期"]),
                sku_key=str(row["SKU"]),
                spec=str(row["规格"]),
                qty=float(row["数量"]),
                plan_type=str(row["计划类型"]) if "计划类型" in df.columns else "sales",
            ))
        return ProductionPlan(name=name, rows=rows)
