"""Business logic for 出品规格管理 (Tab7)."""
from __future__ import annotations
from typing import Any
from mike_product_calc.data.supabase_client import MpcSupabaseClient


def get_serving_specs_with_toppings(
    client: MpcSupabaseClient, product_id: str
) -> list[dict[str, Any]]:
    return client.list_serving_specs(product_id)


def get_final_products(
    client: MpcSupabaseClient,
) -> list[dict[str, Any]]:
    return client.list_products(is_final=True)


def format_spec_for_display(spec: dict[str, Any]) -> dict[str, Any]:
    toppings = spec.get("serving_spec_toppings", [])
    topping_names = []
    for t in toppings:
        mat = t.get("material_id")
        if isinstance(mat, dict):
            topping_names.append(mat.get("name", ""))
        elif isinstance(mat, str):
            topping_names.append(mat)
    return {
        "id": spec["id"],
        "规格": spec["spec_name"],
        "主原料用量": spec.get("quantity", ""),
        "包材": spec.get("packaging_id", ""),
        "附加配料": ", ".join(topping_names) if topping_names else "",
    }
