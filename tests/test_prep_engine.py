import pandas as pd

from mike_product_calc.calc.prep_engine import bom_expand


def test_prep_engine_unit_price_is_min_unit_cost():
    # 总原料成本表：
    # - 门店(加价后单价)=20 元 / 单位量=5 → 最小单位成本=4
    # - 出厂(加价前单价)=10 元 / 单位量=5 → 最小单位成本=2
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

    # 产品出品表：SKU 使用 10 单位糖
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
    assert row["material"] == "糖"
    assert abs(float(row["unit_price"]) - 4.0) < 1e-9
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
    assert row2["material"] == "糖"
    assert abs(float(row2["unit_price"]) - 2.0) < 1e-9
    assert abs(float(row2["total_cost"]) - 20.0) < 1e-9
