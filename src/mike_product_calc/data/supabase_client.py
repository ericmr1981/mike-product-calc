"""Supabase REST API client for CRUD operations on raw materials, products,
recipes, and serving specs.

Uses ``requests`` (not supabase-py) to call the Supabase REST API directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime

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
        """Replace all recipes for a product: delete existing, insert new.

        Preserves old data to restore on failure (pseudo-transaction).
        """
        # Save old recipes before delete
        old = self.list_recipes(product_id)

        # Delete existing recipes
        del_resp = requests.delete(
            f"{self._base}/recipes?product_id=eq.{product_id}",
            headers=self._headers(),
        )
        del_resp.raise_for_status()

        # POST new recipes
        # Convert numeric fields from string to float (Supabase API returns strings)
        cleaned = []
        for r in recipes_data:
            cleaned.append({
                **r,
                "quantity": float(r["quantity"]),
                "unit_cost": float(r["unit_cost"]) if r.get("unit_cost") is not None else None,
                "store_unit_cost": float(r["store_unit_cost"]) if r.get("store_unit_cost") is not None else None,
            })

        resp = requests.post(
            f"{self._base}/recipes", headers=self._headers(), json=cleaned
        )
        if not resp.ok:
            # Restore old data on failure
            if old:
                requests.post(
                    f"{self._base}/recipes", headers=self._headers(), json=old
                )
            resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Price Scenario Apply & History
    # ------------------------------------------------------------------

    def _find_material_by_name(self, name: str) -> dict | None:
        """Find a raw_material by exact name match, preferring newest."""
        all_mats = self.list_raw_materials()
        matches = [
            m for m in all_mats
            if str(m.get("name", "")).strip() == name.strip()
        ]
        if not matches:
            return None
        matches.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return matches[0]

    def apply_scenario(
        self, scenario_name: str, adjustments: list
    ) -> dict:
        """Apply a scenario's price adjustments to raw_materials.

        adjustments: list of objects with .item (name) and .new_unit_price
        Returns {batch_id, total, ok, changes[]}.
        """
        batch_id = str(uuid.uuid4())
        changes = []
        ok_count = 0
        for adj in adjustments:
            mat = self._find_material_by_name(adj.item)
            if not mat:
                changes.append({"item": adj.item, "status": "not_found"})
                continue
            old_price = float(mat.get("final_price") or 0)
            new_price = float(adj.new_unit_price)
            try:
                self.update_raw_material(mat["id"], {"final_price": new_price})
            except requests.HTTPError:
                changes.append(
                    {"item": adj.item, "old": old_price, "status": "update_failed"}
                )
                continue
            log_entry = {
                "batch_id": batch_id,
                "material_name": adj.item,
                "material_code": mat.get("code", ""),
                "old_final_price": old_price,
                "new_final_price": new_price,
                "scenario_name": scenario_name,
            }
            requests.post(
                f"{self._base}/price_change_log",
                headers=self._headers(),
                json=[log_entry],
            )
            changes.append(
                {"item": adj.item, "old": old_price, "new": new_price, "status": "ok"}
            )
            ok_count += 1
        return {
            "batch_id": batch_id,
            "total": len(adjustments),
            "ok": ok_count,
            "changes": changes,
        }

    def rollback_batch(self, batch_id: str, reason: str = "") -> dict:
        """Rollback all price changes in a batch."""
        entries = self.query_table_where(
            "price_change_log",
            {"batch_id": f"eq.{batch_id}", "rolled_back_at": "is.null"},
        )
        rolled = 0
        for entry in entries:
            mat = self._find_material_by_name(entry["material_name"])
            if mat:
                try:
                    self.update_raw_material(
                        mat["id"], {"final_price": entry["old_final_price"]}
                    )
                    rolled += 1
                except requests.HTTPError:
                    pass
        if entries:
            now_str = datetime.utcnow().isoformat()
            requests.patch(
                f"{self._base}/price_change_log?batch_id=eq.{batch_id}",
                headers=self._headers(),
                json={"rolled_back_at": now_str, "rollback_reason": reason},
            )
        return {"batch_id": batch_id, "rolled_back": rolled}

    def list_price_change_batches(self) -> list[dict]:
        """List all batches with summary stats."""
        resp = requests.get(
            f"{self._base}/price_change_log",
            headers=self._headers(),
            params={
                "select": "batch_id,scenario_name,applied_at,rolled_back_at,material_name",
                "order": "applied_at.desc",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        batches: dict[str, dict] = {}
        for r in rows:
            bid = r["batch_id"]
            if bid not in batches:
                batches[bid] = {
                    "batch_id": bid,
                    "scenario_name": r["scenario_name"],
                    "applied_at": r["applied_at"],
                    "item_count": 0,
                    "rolled_back_count": 0,
                }
            batches[bid]["item_count"] += 1
            if r.get("rolled_back_at"):
                batches[bid]["rolled_back_count"] += 1
        result = sorted(
            batches.values(), key=lambda b: b["applied_at"], reverse=True
        )
        for b in result:
            b["all_rolled_back"] = b["rolled_back_count"] == b["item_count"]
        return result

    def get_batch_details(self, batch_id: str) -> list[dict]:
        """Get all log entries for a batch."""
        return self.query_table_where(
            "price_change_log",
            {"batch_id": f"eq.{batch_id}", "order": "material_name"},
        )

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

    def query_table_where(self, table: str, params: dict[str, str]) -> list[dict]:
        """Query a table with explicit PostgREST filter params."""
        resp = requests.get(f"{self._base}/{table}", headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Inventory snapshot upload
    # ------------------------------------------------------------------

    def find_inventory_batch(
        self, *, source_filename: str, source_file_sha256: str | None = None
    ) -> dict | None:
        params = {"source_filename": f"eq.{source_filename}", "limit": "1"}
        resp = requests.get(
            f"{self._base}/inventory_snapshot_batches", headers=self._headers(), params=params
        )
        resp.raise_for_status()
        rows = resp.json()
        if rows:
            return rows[0]
        if source_file_sha256:
            params = {"source_file_sha256": f"eq.{source_file_sha256}", "limit": "1"}
            resp = requests.get(
                f"{self._base}/inventory_snapshot_batches", headers=self._headers(), params=params
            )
            resp.raise_for_status()
            rows = resp.json()
            if rows:
                return rows[0]
        return None

    def create_inventory_batch(self, data: dict) -> dict:
        resp = requests.post(
            f"{self._base}/inventory_snapshot_batches", headers=self._headers(), json=[data]
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0]

    def update_inventory_batch(self, batch_id: str, data: dict) -> dict:
        resp = requests.patch(
            f"{self._base}/inventory_snapshot_batches?id=eq.{batch_id}",
            headers=self._headers(),
            json=data,
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else {}

    def insert_inventory_items(self, rows: list[dict]) -> list[dict]:
        resp = requests.post(
            f"{self._base}/inventory_snapshot_items", headers=self._headers(), json=rows
        )
        resp.raise_for_status()
        return resp.json()

    def list_latest_inventory_rows(self, limit: int = 5000) -> list[dict]:
        params = {"limit": str(limit), "order": "warehouse_code.asc,item_code.asc"}
        resp = requests.get(
            f"{self._base}/v_inventory_latest_item_by_warehouse",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def list_latest_inventory_rows_by_warehouse(
        self, warehouse_code: str, limit: int = 5000
    ) -> list[dict]:
        params = {
            "warehouse_code": f"eq.{warehouse_code}",
            "limit": str(limit),
            "order": "warehouse_code.asc,item_code.asc",
        }
        resp = requests.get(
            f"{self._base}/v_inventory_latest_item_by_warehouse",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def get_latest_inventory_snapshot_at(self) -> str | None:
        params = {"select": "snapshot_at", "order": "snapshot_at.desc", "limit": "1"}
        resp = requests.get(
            f"{self._base}/inventory_snapshot_batches",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0].get("snapshot_at") if rows else None

    # ------------------------------------------------------------------
    # Inventory Check Batches
    # ------------------------------------------------------------------

    def create_check_batch(self, data: dict) -> dict:
        resp = requests.post(
            f"{self._base}/inventory_check_batches", headers=self._headers(), json=[data]
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0]

    def find_check_batch(
        self, *, source_filename: str
    ) -> dict | None:
        params = {"source_filename": f"eq.{source_filename}", "limit": "1"}
        resp = requests.get(
            f"{self._base}/inventory_check_batches", headers=self._headers(), params=params
        )
        resp.raise_for_status()
        rows = resp.json()
        if rows:
            return rows[0]
        return None

    def update_check_batch(self, batch_id: str, data: dict) -> dict:
        resp = requests.patch(
            f"{self._base}/inventory_check_batches?id=eq.{batch_id}",
            headers=self._headers(),
            json=data,
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else {}

    def insert_check_items(self, rows: list[dict]) -> list[dict]:
        resp = requests.post(
            f"{self._base}/inventory_check_items", headers=self._headers(), json=rows
        )
        resp.raise_for_status()
        return resp.json()

    def list_check_batches(self) -> list[dict]:
        params = {"order": "check_at.desc", "limit": "100"}
        resp = requests.get(
            f"{self._base}/inventory_check_batches", headers=self._headers(), params=params
        )
        resp.raise_for_status()
        return resp.json()

    def list_latest_check_items(self) -> list[dict]:
        """Fetch items from the most recent inventory check batch.

        Returns items as flat dicts ready for inventory view mapping.
        Returns empty list if no check batches exist.
        """
        batches = self.list_check_batches()
        if not batches:
            return []
        latest_id = batches[0]["id"]
        params = {"batch_id": f"eq.{latest_id}", "limit": "5000"}
        resp = requests.get(
            f"{self._base}/inventory_check_items", headers=self._headers(), params=params
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Inventory Delivery Batches
    # ------------------------------------------------------------------

    def create_delivery_batch(self, data: dict) -> dict:
        resp = requests.post(
            f"{self._base}/inventory_delivery_batches", headers=self._headers(), json=[data]
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0]

    def find_delivery_batch(
        self, *, source_filename: str
    ) -> dict | None:
        params = {"source_filename": f"eq.{source_filename}", "limit": "1"}
        resp = requests.get(
            f"{self._base}/inventory_delivery_batches", headers=self._headers(), params=params
        )
        resp.raise_for_status()
        rows = resp.json()
        if rows:
            return rows[0]
        return None

    def update_delivery_batch(self, batch_id: str, data: dict) -> dict:
        resp = requests.patch(
            f"{self._base}/inventory_delivery_batches?id=eq.{batch_id}",
            headers=self._headers(),
            json=data,
        )
        resp.raise_for_status()
        rows = resp.json()
        return rows[0] if rows else {}

    def insert_delivery_items(self, rows: list[dict]) -> list[dict]:
        resp = requests.post(
            f"{self._base}/inventory_delivery_items", headers=self._headers(), json=rows
        )
        resp.raise_for_status()
        return resp.json()

    def list_delivery_batches(self) -> list[dict]:
        params = {"order": "delivery_at.desc", "limit": "100"}
        resp = requests.get(
            f"{self._base}/inventory_delivery_batches", headers=self._headers(), params=params
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Consumption Query
    # ------------------------------------------------------------------

    def query_consumption(self, start_date: str, end_date: str) -> list[dict]:
        """Query consumption analysis data between two dates.

        Finds the earliest and latest inventory check batch in the date
        range, retrieves their items, and computes consumption over the
        period (including any deliveries).
        """
        # 1. Find check batches in date range
        check_params = {
            "select": "id,check_at,source_filename",
            "check_at": f"gte.{start_date}",
            "order": "check_at.asc",
            "limit": "100",
        }
        resp = requests.get(
            f"{self._base}/inventory_check_batches",
            headers=self._headers(),
            params=check_params,
        )
        resp.raise_for_status()
        batches = resp.json()

        if len(batches) < 2:
            return []

        start_batch = batches[0]
        end_batch = batches[-1]

        # 2. Fetch items for start and end batches
        def _fetch_items(batch_id: str) -> list[dict]:
            p = {"batch_id": f"eq.{batch_id}", "limit": "5000"}
            r = requests.get(
                f"{self._base}/inventory_check_items",
                headers=self._headers(),
                params=p,
            )
            r.raise_for_status()
            return r.json()

        start_items = {it["item_code"]: it for it in _fetch_items(start_batch["id"])}
        end_items = {it["item_code"]: it for it in _fetch_items(end_batch["id"])}

        return self._compute_consumption(start_items, end_items, start_date, end_date)

    def _compute_consumption(
        self,
        start_items: dict[str, dict],
        end_items: dict[str, dict],
        start_date: str,
        end_date: str,
    ) -> list[dict]:
        """Core consumption computation.

        Fetches delivery batches in the date range, aggregates delivery
        quantities by item code, then computes consumption for each item
        that appears in either the start or end check.
        """
        # Fetch delivery batches in range
        db_params = {
            "select": "id,delivery_at",
            "delivery_at": f"gte.{start_date}",
            "order": "delivery_at.asc",
            "limit": "100",
        }
        resp = requests.get(
            f"{self._base}/inventory_delivery_batches",
            headers=self._headers(),
            params=db_params,
        )
        resp.raise_for_status()
        delivery_batches = resp.json()

        # Aggregate delivery qty by item_code
        delivery_by_item: dict[str, float] = {}
        for db in delivery_batches:
            p = {
                "batch_id": f"eq.{db['id']}",
                "select": "item_code,delivery_qty",
                "limit": "5000",
            }
            r = requests.get(
                f"{self._base}/inventory_delivery_items",
                headers=self._headers(),
                params=p,
            )
            if r.ok:
                for item in r.json():
                    code = item["item_code"]
                    delivery_by_item[code] = delivery_by_item.get(code, 0) + float(
                        item.get("delivery_qty") or 0
                    )

        days = max(1, self._date_diff_days(start_date, end_date))
        results: list[dict] = []

        all_codes = set(start_items.keys()) | set(end_items.keys())
        for code in sorted(all_codes):
            s = start_items.get(code, {})
            e = end_items.get(code, {})

            start_qty = (
                float(s.get("second_check_qty"))
                if s and s.get("second_check_qty") is not None
                else None
            )
            end_qty = (
                float(e.get("second_check_qty"))
                if e and e.get("second_check_qty") is not None
                else None
            )
            avg_price = (
                float(s.get("avg_price"))
                if s and s.get("avg_price") is not None
                else None
            )
            delivery_qty = delivery_by_item.get(code, 0)

            if start_qty is not None and end_qty is not None:
                consumption_qty = max(0, start_qty + delivery_qty - end_qty)
                consumption_amount = (
                    round(consumption_qty * (avg_price or 0), 2) if avg_price else 0
                )
                item_type = "matched"
            elif end_qty is not None:
                consumption_qty = None
                consumption_amount = None
                item_type = "new"
            else:
                continue

            results.append({
                "item_code": code,
                "item_name": s.get("item_name") or e.get("item_name", ""),
                "unit": s.get("unit") or e.get("unit", ""),
                "category": s.get("category") or e.get("category", ""),
                "spec": s.get("spec") or e.get("spec", ""),
                "start_qty": start_qty,
                "end_qty": end_qty,
                "delivery_qty": delivery_qty,
                "consumption_qty": (
                    round(consumption_qty, 6)
                    if consumption_qty is not None
                    else None
                ),
                "consumption_amount": consumption_amount,
                "avg_price": avg_price,
                "item_type": item_type,
            })

        return results

    @staticmethod
    def _date_diff_days(start_date: str, end_date: str) -> int:
        """Compute calendar days between two ISO date strings (minimum 1)."""
        from datetime import datetime

        try:
            s = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            e = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            return max(1, (e - s).days)
        except (ValueError, TypeError):
            return 1

    # ------------------------------------------------------------------
    # Cost computation
    # ------------------------------------------------------------------

    def compute_product_costs(self, product_id: str, _visited: set | None = None) -> dict:
        """Compute and update factory_cost / store_cost / batch_size for a product.

        Recursively resolves semi-product (ref_product_id) ingredients.
        Returns the update payload written to Supabase.
        """
        if _visited is None:
            _visited = set()
        if product_id in _visited:
            return {}  # circular reference guard
        _visited.add(product_id)

        # Load product details
        recipes = self.list_recipes(product_id)
        if not recipes:
            return {}

        total_factory = 0.0
        total_store = 0.0
        total_batch_size = 0.0

        for r in recipes:
            qty = float(r.get("quantity", 0) or 0)
            total_batch_size += qty
            source = r.get("ingredient_source", "raw")

            if source == "raw":
                # Direct raw material
                rm = r.get("raw_material_id")
                if isinstance(rm, dict):
                    bp = float(rm.get("base_price") or 0)
                    fp = float(rm.get("final_price") or 0)
                    ua = float(rm.get("unit_amount") or 1)
                    if ua <= 0:
                        ua = 1
                    total_factory += bp / ua * qty
                    total_store += fp / ua * qty
            else:
                # Semi-product ingredient - recurse
                ref = r.get("ref_product_id")
                ref_id = ref.get("id") if isinstance(ref, dict) else str(ref or "")
                if ref_id and ref_id not in _visited:
                    sub = self.compute_product_costs(ref_id, _visited)
                    sq = float(sub.get("batch_size", 0) or 0)
                    if sq > 0:
                        total_factory += float(sub.get("factory_cost", 0) or 0) / sq * qty
                        total_store += float(sub.get("store_cost", 0) or 0) / sq * qty

        update = {
            "computed_batch_size": round(total_batch_size, 4),
            "computed_factory_cost": round(total_factory, 4),
            "computed_store_cost": round(total_store, 4),
        }
        self.update_product(product_id, update)

        return update

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
