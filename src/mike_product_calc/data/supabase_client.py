"""Supabase REST API client for CRUD operations on raw materials, products,
recipes, and serving specs.

Uses ``requests`` (not supabase-py) to call the Supabase REST API directly.
"""

from __future__ import annotations

import requests


class MpcSupabaseClient:
    """Thin wrapper around the Supabase REST API for Mike product data."""

    def __init__(self, url: str, key: str) -> None:
        self.url = url.rstrip("/")
        self.key = key
        self._base = f"{self.url}/rest/v1"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _upsert_headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }

    # ------------------------------------------------------------------
    # Raw Materials
    # ------------------------------------------------------------------

    def list_raw_materials(
        self, category: str | None = None, search: str | None = None
    ) -> list[dict]:
        params: dict[str, str] = {"order": "name"}
        if category is not None:
            params["category"] = f"eq.{category}"
        if search is not None:
            params["name"] = f"ilike.*{search}*"
        resp = requests.get(f"{self._base}/raw_materials", headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_raw_material(self, id: str) -> dict | None:
        params = {"id": f"eq.{id}"}
        resp = requests.get(f"{self._base}/raw_materials", headers=self._headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None

    def create_raw_material(self, data: dict) -> dict:
        resp = requests.post(f"{self._base}/raw_materials", headers=self._headers(), json=[data])
        resp.raise_for_status()
        result = resp.json()
        return result[0]

    def update_raw_material(self, id: str, data: dict) -> dict:
        resp = requests.patch(
            f"{self._base}/raw_materials?id=eq.{id}", headers=self._headers(), json=data
        )
        resp.raise_for_status()
        result = resp.json()
        return result[0]

    def delete_raw_material(self, id: str) -> bool:
        resp = requests.delete(
            f"{self._base}/raw_materials?id=eq.{id}", headers=self._headers()
        )
        resp.raise_for_status()
        return True

    def upsert_raw_materials(self, records: list[dict]) -> list[dict]:
        resp = requests.post(
            f"{self._base}/raw_materials", headers=self._upsert_headers(), json=records
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def list_products(self, is_final: bool | None = None) -> list[dict]:
        params: dict[str, str] = {"order": "name"}
        if is_final is not None:
            params["is_final_product"] = f"eq.{str(is_final).lower()}"
        resp = requests.get(f"{self._base}/products", headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def get_product(self, id: str) -> dict | None:
        params = {"id": f"eq.{id}"}
        resp = requests.get(f"{self._base}/products", headers=self._headers(), params=params)
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None

    def create_product(self, data: dict) -> dict:
        resp = requests.post(f"{self._base}/products", headers=self._headers(), json=[data])
        resp.raise_for_status()
        result = resp.json()
        return result[0]

    def update_product(self, id: str, data: dict) -> dict:
        resp = requests.patch(
            f"{self._base}/products?id=eq.{id}", headers=self._headers(), json=data
        )
        resp.raise_for_status()
        result = resp.json()
        return result[0]

    def delete_product(self, id: str) -> bool:
        resp = requests.delete(
            f"{self._base}/products?id=eq.{id}", headers=self._headers()
        )
        resp.raise_for_status()
        return True

    # ------------------------------------------------------------------
    # Recipes (BOM)
    # ------------------------------------------------------------------

    def list_recipes(self, product_id: str) -> list[dict]:
        params = {
            "product_id": f"eq.{product_id}",
            "order": "sort_order",
            "select": "*,raw_material_id(*),ref_product_id(*)",
        }
        resp = requests.get(f"{self._base}/recipes", headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def list_all_recipes(self) -> list[dict]:
        """Get ALL recipes in a single request (batch)."""
        params = {
            "select": "*,raw_material_id(*),ref_product_id(*)",
            "order": "product_id",
        }
        resp = requests.get(f"{self._base}/recipes", headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def list_all_serving_specs(self) -> list[dict]:
        """Get ALL serving specs in a single request (batch)."""
        params = {
            "select": "*,serving_spec_toppings(*,material_id(*)),packaging_id(*),main_material_id(*)",
            "order": "product_id",
        }
        resp = requests.get(f"{self._base}/serving_specs", headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def set_recipes(self, product_id: str, recipes_data: list[dict]) -> list[dict]:
        """Replace all recipes for a product: delete existing, insert new."""
        # Delete existing recipes (and cascade sub-records)
        requests.delete(
            f"{self._base}/recipes?product_id=eq.{product_id}",
            headers=self._headers(),
        )

        # 4. POST new recipes
        resp = requests.post(
            f"{self._base}/recipes", headers=self._headers(), json=recipes_data
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Serving Specs
    # ------------------------------------------------------------------

    def list_serving_specs(self, product_id: str) -> list[dict]:
        params = {
            "product_id": f"eq.{product_id}",
            "order": "spec_name",
            "select": "*,serving_spec_toppings(*,material_id(*)),packaging_id(*),main_material_id(*)",
        }
        resp = requests.get(
            f"{self._base}/serving_specs", headers=self._headers(), params=params
        )
        resp.raise_for_status()
        return resp.json()

    def set_serving_specs(self, product_id: str, specs_data: list[dict]) -> list[dict]:
        """Replace all serving specs for a product: delete old + toppings, insert new.

        Each spec dict may include a key ``_toppings`` (list of dicts with
        ``material_id`` and ``quantity``) which will be created as
        ``serving_spec_toppings`` for that spec.
        """
        # 1. GET existing specs
        existing = self.list_serving_specs(product_id)

        # 2. Delete topping associations for each existing spec
        for spec in existing:
            sid = spec["id"]
            requests.delete(
                f"{self._base}/serving_spec_toppings?serving_spec_id=eq.{sid}",
                headers=self._headers(),
            )

        # 3. Delete existing specs
        requests.delete(
            f"{self._base}/serving_specs?product_id=eq.{product_id}",
            headers=self._headers(),
        )

        # 4. POST new specs (strip internal keys like _toppings)
        clean_specs = [
            {k: v for k, v in s.items() if not k.startswith("_")}
            for s in specs_data
        ]
        resp = requests.post(
            f"{self._base}/serving_specs", headers=self._headers(), json=clean_specs
        )
        resp.raise_for_status()
        new_specs = resp.json()

        # 5. Create toppings for each new spec
        for i, spec in enumerate(new_specs):
            toppings = specs_data[i].get("_toppings", [])
            if toppings:
                for t in toppings:
                    t["serving_spec_id"] = spec["id"]
                    try:
                        resp = requests.post(
                            f"{self._base}/serving_spec_toppings",
                            headers=self._headers(),
                            json=[t],
                        )
                        resp.raise_for_status()
                    except Exception as e:
                        print(f"[set_serving_specs] Failed to create topping: {e}")
                        raise
        return new_specs

    # ------------------------------------------------------------------
    # Generic table query
    # ------------------------------------------------------------------

    def query_table(self, table: str, limit: int = 200) -> list[dict]:
        """Query any table with a limit (for data browsing in Tab2)."""
        params = {"limit": str(limit)}
        resp = requests.get(f"{self._base}/{table}", headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Sync Log
    # ------------------------------------------------------------------

    def log_sync(
        self,
        status: str,
        summary: str,
        details: dict | None = None,
        raw_material_count: int = 0,
        product_count: int = 0,
        recipe_count: int = 0,
        sync_type: str = "xlsx_import",
    ) -> dict:
        data = {
            "sync_type": sync_type,
            "status": status,
            "summary": summary,
            "details": details or {},
            "raw_material_count": raw_material_count,
            "product_count": product_count,
            "recipe_count": recipe_count,
        }
        resp = requests.post(f"{self._base}/sync_log", headers=self._headers(), json=[data])
        resp.raise_for_status()
        result = resp.json()
        return result[0]
