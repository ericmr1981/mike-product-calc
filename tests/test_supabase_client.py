from __future__ import annotations
import pytest
from unittest.mock import patch
from mike_product_calc.data.supabase_client import MpcSupabaseClient


@pytest.fixture
def client():
    return MpcSupabaseClient(url="https://test.supabase.co", key="test-key")


def test_init_creates_client(client):
    assert client.url == "https://test.supabase.co"
    assert client.key == "test-key"


def test_list_raw_materials_default(client):
    mock_data = [{"id": "1", "name": "橙子酱"}]
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_data
        result = client.list_raw_materials()
        assert result == mock_data


def test_create_raw_material(client):
    mock_data = {"id": "new-id", "name": "新原料"}
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = [mock_data]
        result = client.create_raw_material({"name": "新原料"})
        assert result == mock_data


def test_update_raw_material(client):
    mock_data = {"id": "1", "name": "更新名"}
    with patch("requests.patch") as mock_patch:
        mock_patch.return_value.status_code = 200
        mock_patch.return_value.json.return_value = [mock_data]
        result = client.update_raw_material("1", {"name": "更新名"})
        assert result == mock_data


def test_delete_raw_material(client):
    with patch("requests.delete") as mock_delete:
        mock_delete.return_value.status_code = 200
        result = client.delete_raw_material("1")
        assert result is True


def test_upsert_raw_materials(client):
    mock_return = [{"id": "1", "name": "原料A"}, {"id": "2", "name": "原料B"}]
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_return
        result = client.upsert_raw_materials([{"name": "原料A"}, {"name": "原料B"}])
        assert result == mock_return


def test_list_products_default(client):
    mock_data = [{"id": "1", "name": "木姜子甜橙"}]
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_data
        result = client.list_products()
        assert result == mock_data


def test_list_recipes(client):
    mock_data = [{"id": "r1", "product_id": "p1", "quantity": 2000}]
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_data
        result = client.list_recipes("p1")
        assert result == mock_data


def test_set_recipes(client):
    new_recipes = [
        {
            "product_id": "p1",
            "quantity": 100,
            "ingredient_source": "raw",
            "raw_material_id": "r1",
        }
    ]
    with (
        patch("requests.get") as mock_get,
        patch("requests.delete") as mock_delete,
        patch("requests.post") as mock_post,
    ):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"id": "r1"}]
        mock_delete.return_value.status_code = 200
        mock_delete.return_value.json.return_value = []
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = new_recipes
        result = client.set_recipes("p1", new_recipes)
        assert result == new_recipes
        mock_delete.assert_called_once()
        mock_post.assert_called_once()


def test_list_serving_specs(client):
    mock_data = [{"id": "s1", "spec_name": "小杯", "product_id": "p1"}]
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = mock_data
        result = client.list_serving_specs("p1")
        assert result == mock_data


def test_find_inventory_batch_by_filename(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"id": "b1", "source_filename": "f.xlsx"}]
        row = client.find_inventory_batch(source_filename="f.xlsx", source_file_sha256="abc")
        assert row["id"] == "b1"
        assert mock_get.call_count == 1


def test_find_inventory_batch_fallback_sha(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.side_effect = [[], [{"id": "b2", "source_file_sha256": "abc"}]]
        row = client.find_inventory_batch(source_filename="f.xlsx", source_file_sha256="abc")
        assert row["id"] == "b2"
        assert mock_get.call_count == 2


def test_create_and_update_inventory_batch(client):
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = [{"id": "b3"}]
        out = client.create_inventory_batch({"source_filename": "f.xlsx"})
        assert out["id"] == "b3"

    with patch("requests.patch") as mock_patch:
        mock_patch.return_value.status_code = 200
        mock_patch.return_value.json.return_value = [{"id": "b3", "status": "imported"}]
        out = client.update_inventory_batch("b3", {"status": "imported"})
        assert out["status"] == "imported"


def test_insert_inventory_items(client):
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = [{"id": "i1"}, {"id": "i2"}]
        out = client.insert_inventory_items([{"item_code": "A"}, {"item_code": "B"}])
        assert len(out) == 2


def test_list_latest_inventory_rows(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"item_code": "WP0192"}]
        rows = client.list_latest_inventory_rows(limit=1000)

        assert rows[0]["item_code"] == "WP0192"
        mock_get.assert_called_once_with(
            "https://test.supabase.co/rest/v1/v_inventory_latest_item_by_warehouse",
            headers=client._headers(),
            params={"limit": "1000", "order": "warehouse_code.asc,item_code.asc"},
        )


def test_list_latest_inventory_rows_by_warehouse(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"item_code": "WP0192"}]
        rows = client.list_latest_inventory_rows_by_warehouse("WH_SH_001", limit=300)

        assert rows[0]["item_code"] == "WP0192"
        mock_get.assert_called_once_with(
            "https://test.supabase.co/rest/v1/v_inventory_latest_item_by_warehouse",
            headers=client._headers(),
            params={
                "warehouse_code": "eq.WH_SH_001",
                "limit": "300",
                "order": "warehouse_code.asc,item_code.asc",
            },
        )


def test_get_latest_inventory_snapshot_at(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = [{"snapshot_at": "2026-05-06T12:20:44+00:00"}]
        ts = client.get_latest_inventory_snapshot_at()

        assert ts == "2026-05-06T12:20:44+00:00"
        mock_get.assert_called_once_with(
            "https://test.supabase.co/rest/v1/inventory_snapshot_batches",
            headers=client._headers(),
            params={"select": "snapshot_at", "order": "snapshot_at.desc", "limit": "1"},
        )


def test_get_latest_inventory_snapshot_at_empty(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = []
        ts = client.get_latest_inventory_snapshot_at()
        assert ts is None
