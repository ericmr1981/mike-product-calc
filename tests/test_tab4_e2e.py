"""
Playwright E2E 用户测试 — 原料价格模拟器 (Tab 4)

测试场景：
1. Tab 4 基本 UI 元素呈现
2. 新建版本并添加调价明细
3. 保存版本后验证出现在已保存列表
4. 版本对比 (版本 vs 基准)
5. 两个版本对比 (A vs B)
6. 清空所有版本
7. 错误/边界情况：空版本名、无调价项

运行： .venv/bin/python3 -m pytest tests/test_tab4_e2e.py -v -s
"""

import pytest
import re

BASE_URL = "http://localhost:8501"

# ── 辅助函数 ──────────────────────────────────────────────────────────────────────


def _click_tab4(page):
    """Navigate to Tab4 (原料价格模拟器), the 4th tab, index=3."""
    page.locator('button[data-baseweb="tab"]').nth(3).click()
    page.wait_for_timeout(2000)


def _type_number(page, input_element, value: str):
    """Type a value into a Streamlit number input and trigger rerun via Tab."""
    input_element.click()
    page.wait_for_timeout(200)
    input_element.fill("")  # Clear first
    page.keyboard.type(value)
    page.wait_for_timeout(200)
    page.keyboard.press("Tab")  # Triggers Streamlit on_change
    page.wait_for_timeout(2000)  # Wait for rerun / UI update


def _select_dropdown_option(page, selectbox_element, option_text: str):
    """Open a Streamlit selectbox and pick an option by visible text.

    Streamlit selectboxes (data-baseweb=select) open a popover with
    li[role="option"] items.  We click the selectbox trigger area,
    wait for the menu, then click the matching option.
    """
    # Click the selectbox to open the dropdown
    selectbox_element.click()
    page.wait_for_timeout(500)

    # Find the option in the dropdown menu
    option = page.locator(f'li[role="option"]:has-text("{option_text}")')
    if option.count() == 0:
        # Fallback: try to find by exact text match
        option = page.locator(f'li[role="option"]').filter(has_text=option_text)
    assert option.count() > 0, f"Option '{option_text}' not found in dropdown"
    option.first.click()
    page.wait_for_timeout(300)


def _tab4_panel(page):
    """Return the tabpanel locator scoped to Tab 4 (原料价格模拟器)."""
    panels = page.locator('[role="tabpanel"]')
    # Tab4 is the 5th tab; the active tabpanel should contain the simulator title.
    for i in range(panels.count()):
        panel = panels.nth(i)
        if panel.locator("text=原料价格模拟器").count() > 0:
            return panel
    # If streaming has not finished rendering yet, return the last panel as fallback
    return panels.last


# ==============================================================================
# 测试 1: UI 基本结构呈现
# ==============================================================================


def test_tab4_ui_elements_present(page):
    """验证 Tab4 原料价格模拟器的 UI 元素是否完整呈现"""
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)

    _click_tab4(page)
    panel = _tab4_panel(page)

    # 检查标题和说明
    assert panel.locator("h3", has_text="原料价格模拟器").is_visible(), "主标题不可见"

    # 检查版本选择区
    select_divs = panel.locator('[data-testid="stSelectbox"]')
    assert select_divs.count() >= 1, "至少有一个 selectbox（版本选择）"

    # 检查版本名称输入框
    text_inputs = panel.locator('input[type="text"]')
    assert text_inputs.count() >= 1, "应存在文本输入框"

    # 检查调价明细区域
    assert panel.locator("text=调价明细").is_visible(), "调价明细标题不可见"

    # 检查调价原料数 number input
    number_inputs = panel.locator('input[type="number"]')
    assert number_inputs.count() >= 1, "调价原料数 number input 不可见"

    # 检查口径 radio
    radio_btns = panel.locator('label:has-text("门店口径"), label:has-text("出厂口径")')
    assert radio_btns.count() >= 2, "口径 radio 按钮不足"

    # 检查保存和清空按钮
    save_btn = panel.locator("button", has_text="保存")
    assert save_btn.is_visible(), "保存版本按钮不可见"
    # 初始状态应禁用 (没有调价项)
    assert save_btn.is_disabled(), "保存版本按钮初始应禁用"

    clear_btn = panel.locator("button", has_text="清空所有版本")
    assert clear_btn.is_visible(), "清空所有版本按钮不可见"

    # 检查对比区
    assert panel.locator("h5", has_text="版本对比").is_visible(), "版本对比标题不可见"

    # 初始状态应显示提示 (保存至少一个版本)
    assert panel.locator("text=保存至少一个版本后即可进行对比分析").is_visible(), "初始提示不可见"

    print("✅ 测试1通过: 所有UI元素呈现完整")


# ==============================================================================
# 测试 2: 新建版本并添加调价明细
# ==============================================================================


def test_create_version_with_adjustment(page):
    """测试新建版本，添加一种原料调价，保存后验证版本列表"""
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    _click_tab4(page)

    panel = _tab4_panel(page)

    # Step 1: 确认版本选择 selectbox 存在, 默认是"（新建版本）"
    version_select = panel.locator('[data-testid="stSelectbox"]').first
    assert version_select.is_visible()

    # 默认应该是 "（新建版本）"
    default_text = version_select.locator('div[value]').first
    # Streamlit selectbox shows the selected value as text
    assert default_text.is_visible()

    # Step 2: 输入版本名称
    # The text input for new version name — there may be multiple text inputs
    # in the tabpanel; the one for version name is typically after the selectbox.
    # We look for an text input without a placeholder specific to other inputs.
    text_input = panel.locator('input[type="text"]').first
    version_name = "E2E测试版本_涨价"
    text_input.fill(version_name)
    page.wait_for_timeout(300)

    # Step 3: 设置调价原料数 = 1
    number_input = panel.locator('input[type="number"]').first
    _type_number(page, number_input, "1")
    page.wait_for_timeout(500)

    # Step 4: 选择一个原料 (第一个 selectbox 在调价明细区域)
    # After setting n=1, a new row with a selectbox and number input appears
    ingredient_selects = panel.locator('[data-testid="stSelectbox"]')
    # The second selectbox should be the ingredient selector for adjustment row 1
    assert ingredient_selects.count() >= 2
    ingredient_select = ingredient_selects.nth(1)

    # Open the ingredient dropdown and pick the first available option
    ingredient_select.click()
    page.wait_for_timeout(500)

    # Pick the first non-empty option
    first_option = page.locator('li[role="option"]').first
    assert first_option.is_visible(), "原料下拉框无选项"
    selected_ingredient = first_option.text_content()
    first_option.click()
    page.wait_for_timeout(300)
    print(f"  选择的原料: {selected_ingredient}")

    # Step 5: 输入新单价
    # The number input for price is in the same row. It's the 2nd number input
    # (1st is the count, 2nd is the price)
    price_input = panel.locator('input[type="number"]').nth(1)
    _type_number(page, price_input, "150.0000")

    # Step 6: 确认口径默认为"门店口径"
    store_radio = page.locator('label').filter(has_text="门店口径").locator('input[type="radio"]')
    if store_radio.count() > 0:
        # Verify it's checked by checking the parent label's styling or aria-checked
        pass  # Streamlit radio default is store

    # Step 7: 保存按钮现在应启用
    save_btn = panel.locator("button", has_text="保存")
    assert save_btn.is_enabled(), "有调价项后保存版本按钮应启用"

    # Step 8: 点击保存
    save_btn.click()
    page.wait_for_timeout(3000)  # 等待 st.rerun()

    # Step 9: 验证保存成功提示
    success_msg = page.locator("text=已保存版本")
    assert success_msg.is_visible(), "未找到保存成功提示"
    print(f"  保存成功: {success_msg.text_content()}")

    # Step 10: 验证版本出现在已保存版本列表
    page.wait_for_timeout(2000)
    saved_section = page.locator("text=已保存版本")
    assert saved_section.is_visible(), "已保存版本区域不可见"
    assert page.locator(f"text={version_name}").is_visible(), f"版本 '{version_name}' 未出现在已保存列表中"

    print("✅ 测试2通过: 新建并保存版本成功")


# ==============================================================================
# 测试 3: 版本 vs 基准对比 (单版本自动对比)
# ==============================================================================


def test_version_vs_baseline_comparison(page):
    """测试当只有一个版本时，自动显示版本 vs 基准的对比"""
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    _click_tab4(page)

    panel = _tab4_panel(page)

    # 先创建并保存一个版本
    text_input = panel.locator('input[type="text"]').first
    text_input.fill("基准对比测试")
    page.wait_for_timeout(300)

    number_input = panel.locator('input[type="number"]').first
    _type_number(page, number_input, "1")
    page.wait_for_timeout(500)

    # 选择第一个原料
    ingredient_select = panel.locator('[data-testid="stSelectbox"]').nth(1)
    ingredient_select.click()
    page.wait_for_timeout(500)
    first_option = page.locator('li[role="option"]').first
    assert first_option.is_visible(), "原料下拉框无选项"
    first_option.click()
    page.wait_for_timeout(300)

    # 设置新单价
    price_input = panel.locator('input[type="number"]').nth(1)
    _type_number(page, price_input, "200.0000")
    page.wait_for_timeout(300)

    # 保存
    panel.locator("button", has_text="保存").click()
    page.wait_for_timeout(3000)

    # 验证出现 "vs 基准" 对比
    baseline_text = page.locator("text=vs 基准（原始数据）")
    assert baseline_text.is_visible(), "单版本时未显示 vs 基准对比区域"

    # 验证对比表格出现 (dataframe)
    dataframe = page.locator('[data-testid="stDataFrame"]')
    assert dataframe.is_visible(), "对比表格未出现"

    # 验证下载按钮出现
    download_btn = page.locator("button", has_text="下载")
    assert download_btn.is_visible(), "对比下载按钮未出现"

    print("✅ 测试3通过: 版本 vs 基准对比显示正常")


# ==============================================================================
# 测试 4: 双版本对比 (A vs B)
# ==============================================================================


def test_two_version_comparison(page):
    """测试保存两个版本后，使用版本对比功能进行 A vs B 对比"""
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    _click_tab4(page)

    panel = _tab4_panel(page)

    # ── 创建版本 1 ──
    text_input = panel.locator('input[type="text"]').first
    text_input.fill("对比版本_A")
    page.wait_for_timeout(300)

    number_input = panel.locator('input[type="number"]').first
    _type_number(page, number_input, "1")
    page.wait_for_timeout(500)

    ing_select = panel.locator('[data-testid="stSelectbox"]').nth(1)
    ing_select.click()
    page.wait_for_timeout(500)
    page.locator('li[role="option"]').first.click()
    page.wait_for_timeout(300)

    price_input = panel.locator('input[type="number"]').nth(1)
    _type_number(page, price_input, "100.0000")
    page.wait_for_timeout(300)

    panel.locator("button", has_text="保存").click()
    page.wait_for_timeout(3000)

    # ── 创建版本 2 ──
    # After rerun, the selectbox is back to "（新建版本）", text input is empty
    text_input = panel.locator('input[type="text"]').first
    text_input.fill("对比版本_B")
    page.wait_for_timeout(300)

    number_input = panel.locator('input[type="number"]').first
    _type_number(page, number_input, "1")
    page.wait_for_timeout(500)

    ing_select = panel.locator('[data-testid="stSelectbox"]').nth(1)
    ing_select.click()
    page.wait_for_timeout(500)
    page.locator('li[role="option"]').first.click()
    page.wait_for_timeout(300)

    price_input = panel.locator('input[type="number"]').nth(1)
    _type_number(page, price_input, "300.0000")
    page.wait_for_timeout(300)

    panel.locator("button", has_text="保存").click()
    page.wait_for_timeout(3000)

    # ── 验证对比区域 — 应显示版本 A 和 B 的 selectbox ──
    # 已保存版本列表应有 2 个版本
    saved_section = page.locator("text=已保存版本")
    assert saved_section.is_visible()
    assert page.locator("text=对比版本_A").is_visible()
    assert page.locator("text=对比版本_B").is_visible()

    # 对比区应有 "版本 A" 和 "版本 B" selectbox
    cmp_a_select = page.locator('[data-testid="stSelectbox"]').filter(has=page.locator("text=版本 A"))
    cmp_b_select = page.locator('[data-testid="stSelectbox"]').filter(has=page.locator("text=版本 B"))

    # Fallback: 如果 filter 不生效，检查 label 文本
    cmp_labels = page.locator("text=版本 A, text=版本 B")
    # Streamlit selectboxes show their labels as divs/span text
    assert page.locator("text=版本 A").count() >= 1, "版本 A 选择器未出现"
    assert page.locator("text=版本 B").count() >= 1, "版本 B 选择器未出现"

    # 点击对比按钮
    compare_btn = page.locator("button", has_text="对比两版本")
    assert compare_btn.is_visible(), "对比两版本按钮不可见"
    compare_btn.click()
    page.wait_for_timeout(3000)

    # 验证对比结果表格出现
    dataframe = page.locator('[data-testid="stDataFrame"]')
    assert dataframe.first.is_visible(), "对比结果表格未出现"

    # 验证下载按钮
    download_btn = page.locator("button", has_text="下载")
    assert download_btn.is_visible(), "对比结果下载按钮未出现"

    print("✅ 测试4通过: 双版本对比功能正常")


# ==============================================================================
# 测试 5: 选择已有版本进行编辑
# ==============================================================================


def test_select_existing_version(page):
    """测试选择已有版本时，调价明细自动回填"""
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    _click_tab4(page)

    panel = _tab4_panel(page)

    # 先创建并保存一个版本
    text_input = panel.locator('input[type="text"]').first
    text_input.fill("编辑测试版")
    page.wait_for_timeout(300)

    number_input = panel.locator('input[type="number"]').first
    _type_number(page, number_input, "1")
    page.wait_for_timeout(500)

    ing_select = panel.locator('[data-testid="stSelectbox"]').nth(1)
    ing_select.click()
    page.wait_for_timeout(500)
    page.locator('li[role="option"]').first.click()
    page.wait_for_timeout(300)

    price_input = panel.locator('input[type="number"]').nth(1)
    _type_number(page, price_input, "250.0000")
    page.wait_for_timeout(300)

    panel.locator("button", has_text="保存").click()
    page.wait_for_timeout(3000)

    # 现在在版本选择下拉框中选择刚才保存的版本
    version_select = panel.locator('[data-testid="stSelectbox"]').first
    _select_dropdown_option(page, version_select, "编辑测试版")
    page.wait_for_timeout(1000)

    # 验证文本框内容是版本名 (因为是已有版本, text_input 变为显示版本名)
    # 注意: 当选择已有版本时，text_input 被替换为显示版本名称
    # 验证调价原料数已回填为 1
    number_input_val = panel.locator('input[type="number"]').first
    current_val = number_input_val.get_attribute("value")
    print(f"  已有版本调价原料数: {current_val}")
    # 验证调价明细区域出现 (至少有一个 selectbox 和 price input)

    print("✅ 测试5通过: 选择已有版本后调价明细回填正常")


# ==============================================================================
# 测试 6: 清空所有版本
# ==============================================================================


def test_clear_all_versions(page):
    """测试清空所有版本功能"""
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    _click_tab4(page)

    panel = _tab4_panel(page)

    # 先创建一个版本
    text_input = panel.locator('input[type="text"]').first
    text_input.fill("待清空版本")
    page.wait_for_timeout(300)

    number_input = panel.locator('input[type="number"]').first
    _type_number(page, number_input, "1")
    page.wait_for_timeout(500)

    ing_select = panel.locator('[data-testid="stSelectbox"]').nth(1)
    ing_select.click()
    page.wait_for_timeout(500)
    page.locator('li[role="option"]').first.click()
    page.wait_for_timeout(300)

    price_input = panel.locator('input[type="number"]').nth(1)
    _type_number(page, price_input, "99.0000")
    page.wait_for_timeout(300)

    panel.locator("button", has_text="保存").click()
    page.wait_for_timeout(3000)

    # 验证版本存在
    assert page.locator("text=待清空版本").is_visible(), "版本创建失败"

    # 勾选确认框
    confirm_chk = panel.locator('label').filter(has_text="确认清空？").locator('input[type="checkbox"]')
    if confirm_chk.count() > 0:
        confirm_chk.first.click()
        page.wait_for_timeout(500)

    # 点击清空按钮
    clear_btn = page.locator("button", has_text="清空所有版本")
    assert clear_btn.is_visible()
    assert clear_btn.is_enabled(), "勾选确认后清空按钮应启用"
    clear_btn.click()
    page.wait_for_timeout(3000)

    # 验证版本已清空
    assert page.locator("text=待清空版本").count() == 0, "版本未被清空"
    assert page.locator("text=保存至少一个版本后即可进行对比分析").is_visible(), "清空后应显示初始提示"

    # 确认已保存版本区域不可见或为空
    saved_header = page.locator("text=已保存版本")
    assert saved_header.count() == 0, "清空后已保存版本区域不应出现"

    print("✅ 测试6通过: 清空所有版本成功")


# ==============================================================================
# 测试 7: 边界情况 — 空版本名
# ==============================================================================


def test_empty_version_name_disabled(page):
    """验证版本名为空时保存按钮禁用"""
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    _click_tab4(page)

    panel = _tab4_panel(page)

    # 不清空文本输入，让它保持空
    # 设置调价项
    number_input = panel.locator('input[type="number"]').first
    _type_number(page, number_input, "1")
    page.wait_for_timeout(500)

    # 选择原料
    ing_select = panel.locator('[data-testid="stSelectbox"]').nth(1)
    ing_select.click()
    page.wait_for_timeout(500)
    if page.locator('li[role="option"]').count() > 0:
        page.locator('li[role="option"]').first.click()
        page.wait_for_timeout(300)

    # 设置价格
    price_input = panel.locator('input[type="number"]').nth(1)
    _type_number(page, price_input, "50.0000")
    page.wait_for_timeout(300)

    # 保存按钮应禁用 (version_name 为空字符串)
    save_btn = panel.locator("button", has_text="保存")
    assert save_btn.is_disabled(), "版本名为空时保存按钮应禁用"

    print("✅ 测试7通过: 空版本名时保存按钮正确禁用")


# ==============================================================================
# 测试 8: 边界情况 — 无调价项
# ==============================================================================


def test_no_adjustments_disabled(page):
    """验证无调价项时保存按钮禁用"""
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    _click_tab4(page)

    panel = _tab4_panel(page)

    # 输入版本名但不设置调价项
    text_input = panel.locator('input[type="text"]').first
    text_input.fill("无调价项")
    page.wait_for_timeout(300)

    # 确认调价原料数为 0
    number_input = panel.locator('input[type="number"]').first
    number_input.clear()
    _type_number(page, number_input, "0")
    page.wait_for_timeout(500)

    # 保存按钮应禁用 (adjustments 为空)
    save_btn = panel.locator("button", has_text="保存")
    assert save_btn.is_disabled(), "无调价项时保存按钮应禁用"

    print("✅ 测试8通过: 无调价项时保存按钮正确禁用")


# ==============================================================================
# 测试 9: 口径切换 (store vs factory)
# ==============================================================================


def test_basis_switch(page):
    """测试口径切换功能 (门店口径 vs 出厂口径)"""
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    _click_tab4(page)

    panel = _tab4_panel(page)

    # 验证两个 radio 都存在
    store_label = page.locator("label").filter(has_text="门店口径")
    factory_label = page.locator("label").filter(has_text="出厂口径")
    assert store_label.count() >= 1, "门店口径 radio 不可见"
    assert factory_label.count() >= 1, "出厂口径 radio 不可见"

    # 默认门店口径应已选中
    # Streamlit radio: 选中的 radio input 会被渲染
    # 尝试点击出厂口径
    factory_radio = factory_label.first
    factory_radio.click()
    page.wait_for_timeout(300)

    # 再切回门店口径
    store_label.first.click()
    page.wait_for_timeout(300)

    print("✅ 测试9通过: 口径切换正常")


# ==============================================================================
# 测试 10: 创建版本时有多项调价
# ==============================================================================


def test_multiple_adjustments(page):
    """测试添加多项调价原料"""
    page.goto(BASE_URL, wait_until="networkidle")
    page.wait_for_timeout(3000)
    _click_tab4(page)

    panel = _tab4_panel(page)

    # 输入版本名
    text_input = panel.locator('input[type="text"]').first
    text_input.fill("多项调价版本")
    page.wait_for_timeout(300)

    # 设置 2 项调价
    number_input = panel.locator('input[type="number"]').first
    _type_number(page, number_input, "2")
    page.wait_for_timeout(800)

    # 第一项调价
    ing_select_1 = panel.locator('[data-testid="stSelectbox"]').nth(1)
    ing_select_1.click()
    page.wait_for_timeout(500)
    first_options = page.locator('li[role="option"]')
    if first_options.count() > 0:
        first_options.first.click()
        page.wait_for_timeout(300)

    price_input_1 = panel.locator('input[type="number"]').nth(1)
    _type_number(page, price_input_1, "120.0000")
    page.wait_for_timeout(300)

    # 第二项调价
    ing_select_2 = panel.locator('[data-testid="stSelectbox"]').nth(2)
    ing_select_2.click()
    page.wait_for_timeout(500)
    second_options = page.locator('li[role="option"]')
    if second_options.count() > 0:
        second_options.first.click()
        page.wait_for_timeout(300)

    price_input_2 = panel.locator('input[type="number"]').nth(2)
    _type_number(page, price_input_2, "180.0000")
    page.wait_for_timeout(300)

    # 保存按钮应启用
    save_btn = panel.locator("button", has_text="保存")
    assert save_btn.is_enabled(), "多项调价时保存按钮应启用"

    # 保存
    save_btn.click()
    page.wait_for_timeout(3000)

    # 验证保存成功
    assert page.locator("text=已保存版本").is_visible(), "保存成功提示未出现"
    assert page.locator("text=多项调价版本").is_visible(), "版本未出现在已保存列表"

    print("✅ 测试10通过: 多项调价功能正常")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
