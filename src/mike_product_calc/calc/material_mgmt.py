"""Business logic for 原料管理 (Tab5)."""
from __future__ import annotations
from typing import Any, Optional
from mike_product_calc.data.supabase_client import MpcSupabaseClient


def get_categories(client: MpcSupabaseClient) -> list[str]:
    materials = client.list_raw_materials()
    cats = sorted({m["category"] for m in materials if m.get("category")})
    return cats


def get_material_stats(client: MpcSupabaseClient) -> dict[str, Any]:
    materials = client.list_raw_materials()
    total = len(materials)
    active = sum(1 for m in materials if m.get("status") in ("上线", "已生效"))
    inactive = total - active
    by_category: dict[str, int] = {}
    for m in materials:
        cat = m.get("category", "未分类")
        by_category[cat] = by_category.get(cat, 0) + 1
    return {
        "total": total,
        "active": active,
        "inactive": inactive,
        "by_category": by_category,
    }


def search_materials(
    client: MpcSupabaseClient,
    search: Optional[str] = None,
    category: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    materials = client.list_raw_materials()
    if category:
        materials = [m for m in materials if m.get("category") == category]
    if search:
        search_lower = search.lower()
        materials = [
            m for m in materials if search_lower in (m.get("name") or "").lower()
        ]
    if status:
        materials = [m for m in materials if m.get("status") == status]
    return materials
