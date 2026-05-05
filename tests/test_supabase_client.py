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
