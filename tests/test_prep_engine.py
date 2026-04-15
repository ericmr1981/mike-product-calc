import pandas as pd

from mike_product_calc.calc.prep_engine import bom_expand


def test_prep_engine_purchase_qty_in_order_unit_and_uses_price_basis():
    # 总原料成本表：
    # - 门店(加价后单价)=20 元/订货单位
    # - 出厂(加价前单价)=10 元/订货单位
    # - 单位量=5 (1订货单位=5个配方用量单位)
    mat = pd.DataFrame(
        {
            "品项名称": ["糖"],
            "加价后单价": [20],
            "加价前单价": [10],
            "单位量": [5],
            "订货单位": ["kg"],
            "生效状态": ["已生效"],
        }
    )

    # 产品出品表：SKU 直接使用 10 个“用量单位”的糖
    out = pd.DataFrame(
        {
            "品类": ["Gelato"],
            "品名": ["测试品"],
            "规格": ["小杯"],
            "主原料": ["糖"],
            "配料": [""],
            "用量": [10],
        }
    )

    sheets = {
        "总原料成本表": mat,
        "产品出品表_Gelato": out,
    }

    sku_key = "Gelato|测试品|小杯"

    df_store = bom_expand(
        sheets,
        sku_key,
        plan_qty=1,
        basis="store",
        lead_days=0,
        loss_rate=0.0,
        safety_stock=0.0,
    )
    assert not df_store.empty
    row = df_store.iloc[0]

    # 10 / 5 = 2 个订货单位
    assert row["material"] == "糖"
    assert row["purchase_unit"] == "kg"
    assert abs(float(row["purchase_qty"]) - 2.0) < 1e-9

    # 单价应是“订货单位单价”（而不是 min_unit_cost）
    assert abs(float(row["unit_price"]) - 20.0) < 1e-9
    assert abs(float(row["total_cost"]) - 40.0) < 1e-9

    df_factory = bom_expand(
        sheets,
        sku_key,
        plan_qty=1,
        basis="factory",
        lead_days=0,
        loss_rate=0.0,
        safety_stock=0.0,
    )
    assert not df_factory.empty
    row2 = df_factory.iloc[0]

    assert row2["purchase_unit"] == "kg"
    assert abs(float(row2["purchase_qty"]) - 2.0) < 1e-9
    assert abs(float(row2["unit_price"]) - 10.0) < 1e-9
    assert abs(float(row2["total_cost"]) - 20.0) < 1e-9
