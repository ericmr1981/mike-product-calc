from mike_product_calc.data.supabase_client import MpcSupabaseClient
import inspect


def test_client_has_check_delivery_methods():
    methods = {name for name, _ in inspect.getmembers(MpcSupabaseClient, predicate=inspect.isfunction)}
    required = {
        "create_check_batch", "find_check_batch", "update_check_batch",
        "insert_check_items", "list_check_batches",
        "create_delivery_batch", "find_delivery_batch", "update_delivery_batch",
        "insert_delivery_items", "list_delivery_batches",
    }
    missing = required - methods
    assert not missing, f"Missing client methods: {missing}"
