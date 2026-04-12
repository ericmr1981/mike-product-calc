import pandas as pd

from mike_product_calc.calc.material_sim import MaterialPriceAdjustment, Scenario, simulate_scenario


def _base_sheets():
    return {
        "产品毛利表_Gelato": pd.DataFrame(
            {
                "品类": ["Gelato"],
                "品名": ["开心果"],
                "规格": ["杯"],
                "状态": ["上线"],
                "定价": [20.0],
                "门店成本": [4.0],
                "门店毛利率": [0.8],
            }
        ),
        "产品出品表_Gelato": pd.DataFrame(
            {
                "品类": ["Gelato"],
                "品名": ["开心果"],
                "规格": ["杯"],
                "主原料": ["开心果酱"],
                "配料": [""],
                "用量": [2.0],
                "门店总成本": [4.0],
            }
        ),
        "总原料成本表": pd.DataFrame(
            {
                "品项名称": ["开心果酱"],
                "原料价格": [100.0],
                "单位量": [50.0],
                "品项类别": ["原料"],
            }
        ),
    }


def test_simulate_uses_price_div_unit_qty_as_min_unit_cost():
    sheets = _base_sheets()
    scenario = Scenario(name="baseline", adjustments=())

    out = simulate_scenario(sheets, scenario, basis="store")
    r0 = out.iloc[0]

    # min unit cost = 100 / 50 = 2; 用量=2 => adjusted_cost = 4
    assert abs(float(r0["adjusted_cost"]) - 4.0) < 1e-9


def test_simulate_adjustment_applies_on_min_unit_cost_basis():
    sheets = _base_sheets()
    # 调整原料价格到 125，最小单位成本=125/50=2.5；用量=2 => adjusted_cost=5
    scenario = Scenario(
        name="raise",
        adjustments=(MaterialPriceAdjustment(item="开心果酱", new_unit_price=125.0),),
    )

    out = simulate_scenario(sheets, scenario, basis="store")
    r0 = out.iloc[0]

    assert abs(float(r0["adjusted_cost"]) - 5.0) < 1e-9
    assert abs(float(r0["adjusted_gross_profit"]) - 15.0) < 1e-9
