"""Business logic for 配方管理 BOM (Tab6)."""
from __future__ import annotations
from typing import Any
from mike_product_calc.data.supabase_client import MpcSupabaseClient

def get_product_with_recipes(client: MpcSupabaseClient, product_id: str) -> dict[str, Any]:
    product = client.get_product(product_id)
    recipes = client.list_recipes(product_id) if product else []
    return {"product": product, "recipes": recipes}

def build_ingredient_pool(client: MpcSupabaseClient) -> dict[str, list[dict]]:
    raw_materials = client.list_raw_materials()
    products = client.list_products()
    return {
        "raw_materials": raw_materials,
        "products": products,
    }
