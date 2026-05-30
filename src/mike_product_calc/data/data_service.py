"""Unified data service — single entry point for all UI data reads and writes.

Wraps ``MpcSupabaseClient`` (remote) and Excel ``load_workbook`` (fallback)
behind a consistent interface. All Streamlit UI tabs read and write through
this service, eliminating fragmented data sources and scattered write paths.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from mike_product_calc.data.supabase_client import MpcSupabaseClient
from mike_product_calc.data.supabase_adapter import build_sheets


class DataService:
    """Unified data service for the Mike Product Calc UI.

    Usage:
        ds = DataService(supabase_client=client)
        materials = ds.get_raw_materials()
        ds.create_raw_material({...})
    """

    def __init__(self, supabase_client: MpcSupabaseClient | None = None) -> None:
        self._client = supabase_client
        # Internal caches — cleared on write or explicit invalidate
        self._caches: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Connection state
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Whether a Supabase backend is available."""
        return self._client is not None

    @property
    def client(self) -> MpcSupabaseClient:
        """Access the underlying Supabase client (raises if not connected)."""
        if self._client is None:
            raise RuntimeError("Supabase is not connected")
        return self._client

    # ------------------------------------------------------------------
    # Read: Raw Materials
    # ------------------------------------------------------------------

    def get_raw_materials(
        self, category: str | None = None, search: str | None = None
    ) -> list[dict]:
        """Get raw materials list from Supabase (cached)."""
        key = "raw_materials"
        if key not in self._caches:
            self._caches[key] = self.client.list_raw_materials()
        result = self._caches[key]
        if category is not None or search is not None:
            filtered = list(result)
            if category is not None:
                filtered = [m for m in filtered if m.get("category") == category]
            if search is not None:
                filtered = [m for m in filtered if search.lower() in (m.get("name") or "").lower()]
            return filtered
        return result

    def get_raw_material(self, id: str) -> dict | None:
        return self.client.get_raw_material(id)

    # ------------------------------------------------------------------
    # Read: Products
    # ------------------------------------------------------------------

    def get_products(self, is_final: bool | None = None) -> list[dict]:
        """Get products list from Supabase (cached)."""
        key = "products"
        if key not in self._caches:
            self._caches[key] = self.client.list_products()
        result = self._caches[key]
        if is_final is not None:
            return [p for p in result if p.get("is_final_product") == is_final]
        return result

    # ------------------------------------------------------------------
    # Read: Recipes (BOM)
    # ------------------------------------------------------------------

    def get_all_recipes(self) -> list[dict]:
        """Get all recipes (batch fetch, cached)."""
        key = "all_recipes"
        if key not in self._caches:
            self._caches[key] = self.client.list_all_recipes()
        return self._caches[key]

    def get_recipes_for_product(self, product_id: str) -> list[dict]:
        """Get recipes for a single product (from cached all-recipes)."""
        all_recipes = self.get_all_recipes()
        return [r for r in all_recipes if r.get("product_id") == product_id]

    # ------------------------------------------------------------------
    # Read: Serving Specs
    # ------------------------------------------------------------------

    def get_all_serving_specs(self) -> list[dict]:
        """Get all serving specs (batch fetch, cached)."""
        key = "all_specs"
        if key not in self._caches:
            self._caches[key] = self.client.list_all_serving_specs()
        return self._caches[key]

    # ------------------------------------------------------------------
    # Read: Inventory
    # ------------------------------------------------------------------

    def get_latest_inventory_rows(self, limit: int = 5000) -> list[dict]:
        return self.client.list_latest_inventory_rows(limit=limit)

    def get_latest_inventory_rows_by_warehouse(
        self, warehouse_code: str, limit: int = 5000
    ) -> list[dict]:
        return self.client.list_latest_inventory_rows_by_warehouse(warehouse_code, limit=limit)

    def get_latest_inventory_snapshot_at(self) -> str | None:
        return self.client.get_latest_inventory_snapshot_at()

    # ------------------------------------------------------------------
    # Read: DataFrames (for calc module compatibility)
    # ------------------------------------------------------------------

    def get_sheets(self) -> dict[str, pd.DataFrame]:
        """Build DataFrames from Supabase data, cached for session lifetime.

        Returns a dict of canonical sheet name → DataFrame, matching the
        structure expected by calc modules (profit, recipe, prep_engine, etc).
        """
        key = "sheets"
        if key not in self._caches:
            self._caches[key] = build_sheets(self.client)
        return self._caches[key]

    # ------------------------------------------------------------------
    # Read: Generic table query (Tab 2)
    # ------------------------------------------------------------------

    def query_table(self, table: str, limit: int = 200) -> list[dict]:
        return self.client.query_table(table, limit=limit)

    # ------------------------------------------------------------------
    # Write: Raw Materials
    # ------------------------------------------------------------------

    def create_raw_material(self, data: dict) -> dict:
        result = self.client.create_raw_material(data)
        self._invalidate()
        return result

    def update_raw_material(self, id: str, data: dict) -> dict:
        result = self.client.update_raw_material(id, data)
        self._invalidate()
        return result

    def delete_raw_material(self, id: str) -> bool:
        result = self.client.delete_raw_material(id)
        self._invalidate()
        return result

    def upsert_raw_materials(self, records: list[dict]) -> list[dict]:
        result = self.client.upsert_raw_materials(records)
        self._invalidate()
        return result

    # ------------------------------------------------------------------
    # Write: Products
    # ------------------------------------------------------------------

    def create_product(self, data: dict) -> dict:
        result = self.client.create_product(data)
        self._invalidate()
        return result

    def update_product(self, id: str, data: dict) -> dict:
        result = self.client.update_product(id, data)
        self._invalidate()
        return result

    def delete_product(self, id: str) -> bool:
        result = self.client.delete_product(id)
        self._invalidate()
        return result

    # ------------------------------------------------------------------
    # Write: Recipes
    # ------------------------------------------------------------------

    def set_recipes(self, product_id: str, recipes_data: list[dict]) -> list[dict]:
        result = self.client.set_recipes(product_id, recipes_data)
        self._invalidate()
        return result

    # ------------------------------------------------------------------
    # Write: Serving Specs
    # ------------------------------------------------------------------

    def set_serving_specs(self, product_id: str, specs_data: list[dict]) -> list[dict]:
        result = self.client.set_serving_specs(product_id, specs_data)
        self._invalidate()
        return result

    # ------------------------------------------------------------------
    # Write: Price Scenarios
    # ------------------------------------------------------------------

    def apply_scenario(self, scenario_name: str, adjustments: list) -> dict:
        result = self.client.apply_scenario(scenario_name, adjustments)
        self._invalidate()
        return result

    def rollback_batch(self, batch_id: str, reason: str = "") -> dict:
        result = self.client.rollback_batch(batch_id, reason)
        self._invalidate()
        return result

    # ------------------------------------------------------------------
    # Price change history
    # ------------------------------------------------------------------

    def list_price_change_batches(self) -> list[dict]:
        return self.client.list_price_change_batches()

    def get_batch_details(self, batch_id: str) -> list[dict]:
        return self.client.get_batch_details(batch_id)

    # ------------------------------------------------------------------
    # Cost computation
    # ------------------------------------------------------------------

    def compute_product_costs(self, product_id: str, _visited: set | None = None) -> dict:
        return self.client.compute_product_costs(product_id, _visited)

    # ------------------------------------------------------------------
    # Cache invalidation
    # ------------------------------------------------------------------

    def _invalidate(self) -> None:
        """Invalidate internal caches after any write operation."""
        self._caches.clear()

    def invalidate_all(self) -> None:
        """Force full cache refresh (called from UI sidebar "refresh" button)."""
        self._invalidate()
