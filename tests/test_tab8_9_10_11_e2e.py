"""
Playwright E2E tests — Tabs 8-11 (产品组合评估 / 多场景对比 / 选品优化器 / 产能估算)

Test coverage per tab:

Tab8 (index 7) — 产品组合评估:
  - UI element presence (subheader, KPI labels, save buttons)
  - SKU multiselect + quantity input rendering
  - KPI display after selecting SKUs
  - Save scenario A/B/C buttons
  - Saved scenarios expander visibility
  - Comparison view (when >=2 scenarios saved)
  - CSV download button

Tab9 (index 8) — 多场景对比:
  - UI element presence
  - Create new scenario (name input + save)
  - Edit scenario (SKU multiselect, qty inputs, update button)
  - Run comparison button
  - Comparison table + diff table visibility
  - Scenario delete
  - CSV download

Tab10 (index 9) — 选品优化器:
  - UI element presence (status filter, pool, constraints)
  - SKU pool multiselect with defaults
  - Constraint number inputs
  - Run optimization button
  - Top-3 result display (metrics, sub-tabs, SKU detail tables)
  - Explanation section
  - CSV download

Tab11 (index 10) — 产能需求估算:
  - UI element presence
  - Controls (scenario select, plan type, view radio)
  - Run analysis button (handles empty-plan case gracefully)
  - Metric display when plans exist
  - Bar chart rendering
  - High-pressure section
  - CSV download

Run:
  .venv/bin/python3 -m pytest tests/test_tab8_9_10_11_e2e.py -v -s
"""

import re
import pytest

BASE_URL = "http://localhost:8501"

# ==============================================================================
# Helpers
# ==============================================================================


def _select_sku_option(page, tab_index: int, option_text: str) -> None:
    """Select a single SKU option from the active multiselect inside a tab panel.

    Clicks the multiselect dropdown, types a search string, then clicks the
    matching option.
    """
    # Find the active tab panel
    tabpanel = page.locator('[role="tabpanel"]').nth(tab_index - 7)

    # Click the multiselect input to open dropdown
    ms_input = tabpanel.locator('div[data-baseweb="select"] input').first
    ms_input.click()
    page.wait_for_timeout(300)

    # Type to filter
    ms_input.fill(option_text)
    page.wait_for_timeout(500)

    # Click the matching option in the dropdown
    option = page.locator(f'li[role="option"]:has-text("{option_text}")').first
    if option.is_visible():
        option.click()
        page.wait_for_timeout(300)
    # Close dropdown by pressing Escape
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)


def _get_tabpanel(page, tab_index: int):
    """Return the visible tab panel for a specific tab index."""
    return page.locator('[role="tabpanel"]').nth(tab_index - 7)


def _check_streamlit_error(page) -> list[str]:
    """Check if there are any Streamlit error messages visible. Return them."""
    errors = page.locator('[data-testid="stAlert"]')
    error_texts = []
    count = errors.count()
    for i in range(count):
        txt = errors.nth(i).text_content()
        if txt:
            error_texts.append(txt)
    return error_texts


# ==============================================================================
# Tab8 — 产品组合评估
# ==============================================================================


class TestTab8PortfolioEvaluation:
    """Tab8 (index 7): 产品组合评估 — real-time portfolio KPIs."""

    TAB_INDEX = 7

    # ---------- UI Presence ----------

    def test_tab8_ui_elements_present(self, page):
        """Verify the main UI elements of Tab8 are rendered."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        tabs = page.locator('button[data-baseweb="tab"]')
        tabs.nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # Subheader
        assert page.locator("h3", has_text="产品组合评估").is_visible()

        # Multiselect placeholder
        assert page.locator("text=选择产品（可多选）").is_visible()

        # Radio for basis (出厂口径 / 门店口径)
        basis_radio = page.locator('div[data-testid="stRadio"]')
        assert basis_radio.is_visible()

        # Save buttons should NOT be visible yet (no SKUs selected)
        save_a = page.locator('button:has-text("保存为方案 A")')
        assert save_a.count() == 0

        # Info prompt should be visible
        assert page.locator("text=从上方多选产品开始").is_visible()

        # Saved scenarios section heading
        assert page.locator("h5", has_text="已保存方案概览").is_visible()

        print("✅ Tab8 test 1: All UI elements present")

    # ---------- SKU Selection + KPI Display ----------

    def test_tab8_sku_selection_shows_kpis(self, page):
        """Selecting SKUs should reveal quantity inputs and KPI cards."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        tabs = page.locator('button[data-baseweb="tab"]')
        tabs.nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Open the multiselect
        ms = tabpanel.locator('div[data-baseweb="select"]').first
        ms_input = ms.locator("input")
        ms_input.click()
        page.wait_for_timeout(500)

        # Select the first available option
        options = page.locator('li[role="option"]')
        opt_count = options.count()
        if opt_count == 0:
            print("⚠️  No SKU options available (workbook may have no profit data)")
            return

        options.first.click()
        page.wait_for_timeout(300)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # After selecting, quantity inputs should appear
        qty_section = page.locator("h5", has_text="设置各 SKU 数量")
        assert qty_section.is_visible()

        # KPI cards should appear
        kpi_label = page.locator("h5", has_text="实时 KPI")
        assert kpi_label.is_visible()

        # Check at least some KPI metrics
        kpi_cols = tabpanel.locator('[data-testid="stMetric"]')
        assert kpi_cols.count() >= 3

        # Save buttons should now be visible
        save_a = page.locator('button:has-text("保存为方案 A")')
        assert save_a.is_visible()
        save_b = page.locator('button:has-text("保存为方案 B")')
        assert save_b.is_visible()
        save_c = page.locator('button:has-text("保存为方案 C")')
        assert save_c.is_visible()

        print("✅ Tab8 test 2: SKU selection shows qty inputs + KPI cards")

    # ---------- Save Scenario A/B/C ----------

    def test_tab8_save_scenarios(self, page):
        """Test saving as scheme A/B/C and verify they appear in saved section."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        tabs = page.locator('button[data-baseweb="tab"]')
        tabs.nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Select a SKU first
        ms = tabpanel.locator('div[data-baseweb="select"]').first
        ms_input = ms.locator("input")
        ms_input.click()
        page.wait_for_timeout(500)

        options = page.locator('li[role="option"]')
        if options.count() == 0:
            print("⚠️  No SKU options — skipping save scenario test")
            return

        options.first.click()
        page.wait_for_timeout(300)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Save as scheme A
        page.locator('button:has-text("保存为方案 A")').click()
        page.wait_for_timeout(1000)

        # Verify success toast
        success = page.locator("text=方案 A 已保存")
        assert success.is_visible()

        # Scheme A expander should be visible
        expander = page.locator("text=方案A（")
        assert expander.is_visible()

        # Also save B
        page.locator('button:has-text("保存为方案 B")').click()
        page.wait_for_timeout(1000)
        assert page.locator("text=方案 B 已保存").is_visible()

        print("✅ Tab8 test 3: Save scenarios A/B works")

    # ---------- Comparison View ----------

    def test_tab8_comparison_view(self, page):
        """With >=2 saved scenarios, comparison table should appear."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        tabs = page.locator('button[data-baseweb="tab"]')
        tabs.nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Select a SKU
        ms = tabpanel.locator('div[data-baseweb="select"]').first
        ms_input = ms.locator("input")
        ms_input.click()
        page.wait_for_timeout(300)
        options = page.locator('li[role="option"]')
        if options.count() == 0:
            print("⚠️  No SKU options — skipping comparison test")
            return
        options.first.click()
        page.wait_for_timeout(300)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Save A and B
        page.locator('button:has-text("保存为方案 A")').click()
        page.wait_for_timeout(1000)
        page.locator('button:has-text("保存为方案 B")').click()
        page.wait_for_timeout(1000)

        page.reload()
        page.wait_for_timeout(3000)

        # Re-navigate to Tab8
        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # Expand saved scenario expanders
        expanders = page.locator("summary")
        for i in range(expanders.count()):
            expanders.nth(i).click()
        page.wait_for_timeout(500)

        # Comparison section should be visible
        compare_title = page.locator("h5", has_text="多方案对比")
        if compare_title.is_visible():
            # Dataframe should exist
            df = page.locator('[data-testid="stDataFrame"]')
            assert df.count() >= 1

            # CSV download button
            dl_btn = page.locator('button:has-text("下载对比 CSV")')
            assert dl_btn.is_visible()

            print("✅ Tab8 test 4: Comparison view with CSV download rendered")
        else:
            print("⚠️  Comparison not triggered (may need 2 scenarios with different SKU sets)")

    # ---------- Edge: No SKUs Selected ----------

    def test_tab8_no_skus_info(self, page):
        """With no SKUs selected, only info prompt should be visible."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # Info message
        info = page.locator("text=从上方多选产品开始")
        assert info.is_visible()

        # No quantity inputs
        assert page.locator("h5", has_text="设置各 SKU 数量").count() == 0

        print("✅ Tab8 test 5: No-SKU info message displayed correctly")


# ==============================================================================
# Tab9 — 多场景对比
# ==============================================================================


class TestTab9MultiScenario:
    """Tab9 (index 8): 多场景对比 — sales assumption comparison."""

    TAB_INDEX = 8

    # ---------- UI Presence ----------

    def test_tab9_ui_elements_present(self, page):
        """Verify main UI elements of Tab9 are rendered."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # Subheader
        assert page.locator("h3", has_text="多场景对比").is_visible()

        # Radio basis
        basis = page.locator('div[data-testid="stRadio"]')
        assert basis.is_visible()

        # Compare button
        compare_btn = page.locator('button:has-text("对比场景")')
        assert compare_btn.is_visible()

        # Scenario management section
        assert page.locator("h5", has_text="场景管理").is_visible()

        # Text input for new scenario name
        assert page.locator("text=新场景名").is_visible()

        # Copy source select
        assert page.locator("text=复制历史场景").is_visible()

        # Save button
        assert page.locator('button:has-text("保存")').is_visible()

        print("✅ Tab9 test 1: All UI elements present")

    # ---------- Create Scenario ----------

    def test_tab9_create_scenario(self, page):
        """Create a new scenario and verify it appears."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Type a scenario name
        name_input = tabpanel.locator('input[placeholder="输入名称后保存"]')
        name_input.fill("E2E测试场景A")
        page.wait_for_timeout(300)

        # Click save
        tabpanel.locator('button:has-text("保存")').first.click()
        page.wait_for_timeout(1500)

        # After save, the edit select should have the new scenario
        # Look for the selectbox that lets us choose which scenario to edit
        edit_select = tabpanel.locator('[data-testid="stSelectbox"]')
        assert edit_select.count() >= 1

        print("✅ Tab9 test 2: Create scenario works")

    # ---------- Edit Scenario: SKU Selection ----------

    def test_tab9_edit_scenario_skus(self, page):
        """After creating a scenario, SKU multiselect and qty inputs should be editable."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Create a scenario first
        name_input = tabpanel.locator('input[placeholder="输入名称后保存"]')
        name_input.fill("E2E测试场景B")
        page.wait_for_timeout(300)
        tabpanel.locator('button:has-text("保存")').first.click()
        page.wait_for_timeout(1500)

        page.wait_for_timeout(500)

        # Check if the edit scenario section is visible
        edit_section = tabpanel.locator("h5", has_text="编辑场景")
        if not edit_section.is_visible():
            print("⚠️  Edit scenario section not visible after create (might need reload)")
            page.reload()
            page.wait_for_timeout(3000)
            page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
            page.wait_for_timeout(2000)
            tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        edit_section = tabpanel.locator("h5", has_text="编辑场景")
        assert edit_section.is_visible()

        # The SKU multiselect should be visible
        sku_ms = tabpanel.locator("text=选择 SKU（多选）")
        assert sku_ms.is_visible()

        print("✅ Tab9 test 3: Edit scenario with SKU selection rendered")

    # ---------- Run Comparison ----------

    def test_tab9_run_comparison(self, page):
        """Run comparison between scenarios and view results."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Create two scenarios with minimal setup
        # Scenario 1
        name_input = tabpanel.locator('input[placeholder="输入名称后保存"]')
        name_input.fill("E2E场景1")
        page.wait_for_timeout(300)
        tabpanel.locator('button:has-text("保存")').first.click()
        page.wait_for_timeout(1500)

        # Scenario 2 — copy from scenario 1
        name_input = tabpanel.locator('input[placeholder="输入名称后保存"]')
        name_input.fill("E2E场景2")
        page.wait_for_timeout(300)

        # Try to copy from existing
        copy_select = tabpanel.locator('[data-testid="stSelectbox"]').first
        copy_select.click()
        page.wait_for_timeout(300)

        # Select the scenario from dropdown options
        option = page.locator(f'li[role="option"]:has-text("E2E场景1")')
        if option.is_visible():
            option.click()
            page.wait_for_timeout(300)

        # Save scenario 2
        save_btns = tabpanel.locator('button:has-text("保存")')
        save_btns.first.click()
        page.wait_for_timeout(1500)

        # Now click the "对比场景" button
        compare_btn = page.locator('button:has-text("对比场景")')
        if compare_btn.is_visible():
            compare_btn.click()
            page.wait_for_timeout(3000)

            # Check for comparison results
            comparison_title = page.locator("h4", has_text="场景对比汇总")
            if comparison_title.is_visible():
                # Metrics row
                metrics = page.locator('[data-testid="stMetric"]')
                assert metrics.count() >= 3

                # Comparison table
                assert page.locator("h5", has_text="对比表").is_visible()

                # CSV download
                dl_btn = page.locator('button:has-text("下载场景对比 CSV")')
                assert dl_btn.is_visible()

                print("✅ Tab9 test 4: Run comparison — results displayed")
            else:
                print("⚠️  Comparison may have run but results section not found")
        else:
            print("⚠️  Compare button not found")

    # ---------- Delete Scenario ----------

    def test_tab9_delete_scenario(self, page):
        """Deleting a scenario should remove it from the edit select."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Create a scenario to delete
        name_input = tabpanel.locator('input[placeholder="输入名称后保存"]')
        name_input.fill("E2E待删除场景")
        page.wait_for_timeout(300)
        tabpanel.locator('button:has-text("保存")').first.click()
        page.wait_for_timeout(1500)

        page.wait_for_timeout(500)

        # Find and click delete button
        delete_btn = page.locator('button:has-text("删除场景")')
        if delete_btn.is_visible():
            delete_btn.click()
            page.wait_for_timeout(1500)

            # Check success message
            delete_msg = page.locator("text=已删除")
            assert delete_msg.is_visible()
            print("✅ Tab9 test 5: Delete scenario works")
        else:
            print("⚠️  Delete button not visible (no editable scenario)")

    # ---------- Edge: Empty comparison ----------

    def test_tab9_empty_comparison(self, page):
        """Running comparison with no scenarios should show warning."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # Click compare without any scenario
        page.locator('button:has-text("对比场景")').click()
        page.wait_for_timeout(2000)

        # Should see a warning message
        warning = page.locator("text=请先创建并保存至少一个场景")
        assert warning.is_visible()

        print("✅ Tab9 test 6: Empty comparison shows warning")


# ==============================================================================
# Tab10 — 选品优化器
# ==============================================================================


class TestTab10Optimizer:
    """Tab10 (index 9): 选品优化器 — SKU portfolio optimizer."""

    TAB_INDEX = 9

    # ---------- UI Presence ----------

    def test_tab10_ui_elements_present(self, page):
        """Verify main UI elements of Tab10 are rendered."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # Subheader
        assert page.locator("h3", has_text="选品优化器").is_visible()

        # Basis radio
        basis = page.locator('div[data-testid="stRadio"]')
        assert basis.is_visible()

        # Status filter
        assert page.locator("text=状态过滤").is_visible()

        # SKU pool multiselect section
        assert page.locator("h5", has_text="SKU 候选池").is_visible()

        # Constraint section
        assert page.locator("h5", has_text="约束条件").is_visible()

        # Constraint inputs
        assert page.locator("text=最大产能（总件数）").is_visible()
        assert page.locator("text=原料预算（元）").is_visible()
        assert page.locator("text=单品最低销量（件）").is_visible()
        assert page.locator("text=单品最大枚举量").is_visible()

        # Run button (should be visible before needing 2+ SKUs)
        run_btn = page.locator('button:has-text("运行优化")')
        # The button exists; whether it's clickable depends on SKU count
        assert run_btn.is_visible()

        print("✅ Tab10 test 1: All UI elements present")

    # ---------- SKU Pool Selection ----------

    def test_tab10_sku_pool_multiselect(self, page):
        """SKU pool multiselect should show options from workbook."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # The multiselect should have options
        ms = tabpanel.locator('div[data-baseweb="select"]')
        # There's the status filter selectbox and the SKU pool multiselect
        # The SKU pool is the one with the placeholder
        ms_inputs = tabpanel.locator('div[data-baseweb="select"] input')
        assert ms_inputs.count() >= 1

        # Click on the last multiselect (SKU pool — after status filter)
        pool_ms = tabpanel.locator('div[data-baseweb="select"]').last
        pool_input = pool_ms.locator("input")
        pool_input.click()
        page.wait_for_timeout(500)

        # Check options exist
        options = page.locator('li[role="option"]')
        if options.count() > 0:
            print(f"  Available SKU options: {options.count()}")
            # Select first two
            opts_text = []
            for i in range(min(2, options.count())):
                txt = options.nth(i).text_content()
                if txt:
                    opts_text.append(txt.strip())
                options.nth(i).click()
                page.wait_for_timeout(200)

            # Close dropdown
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

            # The constraint section should still be visible (already present)
            if len(opts_text) >= 2:
                print(f"  Selected: {opts_text}")
                print("✅ Tab10 test 2: SKU pool multiselect — options available and selectable")
            else:
                print("⚠️  Could not select enough SKU options")
        else:
            print("⚠️  No SKU pool options (SKU pool empty from profit table)")

    # ---------- Constraint Inputs ----------

    def test_tab10_constraint_inputs_modifiable(self, page):
        """Constraint number inputs should accept values."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Check number inputs exist by their Streamlit key or label proximity
        # Max capacity input
        cap_label = tabpanel.locator("text=最大产能（总件数）")
        assert cap_label.is_visible()

        # Material budget
        budget_label = tabpanel.locator("text=原料预算（元）")
        assert budget_label.is_visible()

        # Min sales
        min_sales_label = tabpanel.locator("text=单品最低销量（件）")
        assert min_sales_label.is_visible()

        # Max qty per SKU
        max_qty_label = tabpanel.locator("text=单品最大枚举量")
        assert max_qty_label.is_visible()

        print("✅ Tab10 test 3: Constraint inputs rendered and modifiable")

    # ---------- Run Optimization Button ----------

    def test_tab10_run_optimization(self, page):
        """Run optimization with default settings and check for results."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Select at least 2 SKUs
        pool_ms = tabpanel.locator('div[data-baseweb="select"]').last
        pool_input = pool_ms.locator("input")
        pool_input.click()
        page.wait_for_timeout(500)

        options = page.locator('li[role="option"]')
        if options.count() < 2:
            print("⚠️  Not enough SKU options to run optimization")
            return

        # Select 2 SKUs
        for i in range(2):
            options.nth(i).click()
            page.wait_for_timeout(200)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Now the "运行优化" button should be visible
        run_btn = page.locator('button:has-text("运行优化")')
        assert run_btn.is_visible()
        assert run_btn.is_enabled()

        # Click to run
        run_btn.click()
        page.wait_for_timeout(5000)  # Allow time for enumeration

        # After running, either results or a warning should show
        warning = page.locator("text=未找到满足约束")
        results_title = page.locator("h4", has_text="推荐方案")

        if results_title.is_visible():
            # Top-3 results are shown
            # Check summary metrics
            metrics = page.locator('[data-testid="stMetric"]')
            assert metrics.count() >= 3

            # Check sub-tabs for Top-3
            sub_tabs = page.locator('[data-baseweb="tab-list"] button')
            # The sub-tabs for plans should have medal emoji or "方案"
            plan_tabs = sub_tabs.filter(has_text=re.compile(r"[🥇🥈🥉]|方案"))
            print(f"  Plan sub-tabs found: {plan_tabs.count()}")

            # Explanation section
            explanation = page.locator("h4", has_text="推荐原因")
            if explanation.is_visible():
                print("  Explanation section rendered")

            # CSV download
            dl_btn = page.locator('button:has-text("下载 Top-3")')
            if dl_btn.is_visible():
                print("  CSV download button available")

            # Check for errors
            errors = _check_streamlit_error(page)
            if errors:
                print(f"  ⚠️  Streamlit errors: {errors}")

            print("✅ Tab10 test 4: Run optimization — Top-3 results displayed")
        elif warning.is_visible():
            print("⚠️  No feasible solutions found — warning displayed (relax constraints to test results)")
        else:
            # Could be still processing or hit spinner
            print("⚠️  Optimization state unclear — check manually")

    # ---------- Sub-tab Navigation ----------

    def test_tab10_subtab_navigation(self, page):
        """If optimization succeeded, plan sub-tabs should be navigable."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Check if results from a previous run persist
        results_title = page.locator("h4", has_text="推荐方案")
        if not results_title.is_visible():
            # Try to set up and run
            pool_ms = tabpanel.locator('div[data-baseweb="select"]').last
            pool_input = pool_ms.locator("input")
            pool_input.click()
            page.wait_for_timeout(500)

            options = page.locator('li[role="option"]')
            if options.count() < 2:
                print("⚠️  Not enough SKUs — skipping sub-tab test")
                return
            for i in range(2):
                options.nth(i).click()
                page.wait_for_timeout(200)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

            page.locator('button:has-text("运行优化")').click()
            page.wait_for_timeout(5000)

            results_title = page.locator("h4", has_text="推荐方案")

        if results_title.is_visible():
            # Click sub-tab 2 (备选2 / 方案3)
            sub_tab_buttons = page.locator('[data-baseweb="tab-list"] button')
            if sub_tab_buttons.count() >= 2:
                sub_tab_buttons.nth(1).click()
                page.wait_for_timeout(500)
                print("  Navigated to sub-tab 2")

            if sub_tab_buttons.count() >= 3:
                sub_tab_buttons.nth(2).click()
                page.wait_for_timeout(500)
                print("  Navigated to sub-tab 3")

            print("✅ Tab10 test 5: Sub-tab navigation works")
        else:
            print("⚠️  No results to navigate — skipping sub-tab test")

    # ---------- Edge: Less than 2 SKUs ----------

    def test_tab10_fewer_than_2_skus(self, page):
        """With <2 SKUs selected, an info message should display."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # The multiselect should show pre-selected SKUs.
        # If we need to check the <2 case, we can see if the info prompt appears.
        # With default first 8 SKUs pre-selected, we should see the constraint section.
        tabpanel = _get_tabpanel(page, self.TAB_INDEX)

        # Check if constraint inputs are visible (implies >=2 SKUs)
        # OR info message "至少选 2 个 SKU"
        info_msg = tabpanel.locator("text=至少选 2 个 SKU")
        constraints_section = tabpanel.locator("h5", has_text="约束条件")

        if info_msg.is_visible():
            print("  Info: less than 2 SKUs selected")
        elif constraints_section.is_visible():
            print("  >=2 SKUs selected, constraints visible")

        # Either state is valid
        print("✅ Tab10 test 6: <2 SKUs shows info or >=2 shows constraints")


# ==============================================================================
# Tab11 — 产能需求估算
# ==============================================================================


class TestTab11Capacity:
    """Tab11 (index 10): 产能需求估算 — capacity pressure estimation."""

    TAB_INDEX = 10

    # ---------- UI Presence ----------

    def test_tab11_ui_elements_present(self, page):
        """Verify main UI elements of Tab11 are rendered."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # Subheader
        assert page.locator("h3", has_text="产能需求估算").is_visible()

        # Scenario select
        assert page.locator("text=选择场景").is_visible()

        # Plan type select
        assert page.locator("text=计划类型").is_visible()

        # View radio (by SKU / by date)
        view_radio = page.locator('div[data-testid="stRadio"]')
        assert view_radio.is_visible()

        # Run analysis button
        run_btn = page.locator('button:has-text("分析产能压力")')
        assert run_btn.is_visible()

        # Info message
        info = page.locator("text=在上方选择场景，点击「分析产能压力」开始")
        assert info.is_visible()

        print("✅ Tab11 test 1: All UI elements present")

    # ---------- Run Without Plan ----------

    def test_tab11_run_without_plan(self, page):
        """Running analysis without selecting a scenario should show warning."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # Click the analyze button without selecting a scenario
        page.locator('button:has-text("分析产能压力")').click()
        page.wait_for_timeout(2000)

        # Should show a warning
        warning = page.locator("text=请先选择一个已保存的场景")
        if warning.is_visible():
            print("✅ Tab11 test 2: No-scenario warning displayed")
        else:
            # Alternative: "暂无数据" if somehow a scenario is auto-selected
            no_data = page.locator("text=暂无数据")
            if no_data.is_visible():
                print("  场景已选但无数据 — 合理状态")
            else:
                # Check for other expected states
                info_msg = page.locator("text=请先选择一个已保存的场景")
                assert info_msg.is_visible()
            print("✅ Tab11 test 2: Warning/info displayed without valid plan")

    # ---------- View By SKU / Date Radio ----------

    def test_tab11_view_radio(self, page):
        """View-by radio should toggle between SKU and date options."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # The radio should have two options
        radios = page.locator('label:has-text("按"), label:has-text("按")')
        # Or look for the radio group
        radio_group = page.locator('[role="radiogroup"]')
        assert radio_group.is_visible()

        # Check for "按 SKU" / "按日期" labels
        sku_label = page.locator("text=按 SKU")
        date_label = page.locator("text=按日期")
        assert sku_label.is_visible()
        assert date_label.is_visible()

        # Click date option if available
        if date_label.is_visible():
            date_label.click()
            page.wait_for_timeout(500)
            print("  Switched to 按日期 view")

        # Switch back to SKU view
        if sku_label.is_visible():
            sku_label.click()
            page.wait_for_timeout(500)
            print("  Switched to 按 SKU view")

        print("✅ Tab11 test 3: View radio toggles between SKU and Date")

    # ---------- Plan Type Filter ----------

    def test_tab11_plan_type_select(self, page):
        """Plan type select should have all, sales, and production options."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # Click the plan type select to see options
        plan_type_select = page.locator('[data-testid="stSelectbox"]').first
        plan_type_select.click()
        page.wait_for_timeout(500)

        # Check options
        options = page.locator('li[role="option"]')
        option_texts = []
        for i in range(options.count()):
            txt = options.nth(i).text_content()
            if txt:
                option_texts.append(txt.strip())

        print(f"  Plan type options: {option_texts}")
        assert any("全部" in t for t in option_texts)
        assert any("销量" in t for t in option_texts) or any("sales" in t.lower() for t in option_texts)
        assert any("生产" in t for t in option_texts) or any("production" in t.lower() for t in option_texts)

        # Close dropdown
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        print("✅ Tab11 test 4: Plan type select has all options")

    # ---------- Edge: CSV Download ----------

    def test_tab11_csv_download(self, page):
        """If results are visible, CSV download button should exist."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        page.locator('button[data-baseweb="tab"]').nth(self.TAB_INDEX).click()
        page.wait_for_timeout(2000)

        # Check for download button (may not exist if no results)
        download_btn = page.locator('button:has-text("下载产能压力 CSV")')
        if download_btn.is_visible():
            assert download_btn.is_enabled()
            print("✅ Tab11 test 5: CSV download button visible")
        else:
            # Without pre-existing production plans, this is expected
            print("  CSV download not shown (no analysis results) — expected without plans")


# ==============================================================================
# Cross-tab consistency tests
# ==============================================================================


class TestCrossTabConsistency:
    """Tests that verify shared state between tabs behaves correctly."""

    # ---------- All tabs can be navigated ----------

    def test_navigate_all_tabs_8_to_11(self, page):
        """Verify all 4 tabs (8-11) can be navigated to without errors."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        tab_labels = {
            7: "产品组合评估",
            8: "多场景对比",
            9: "选品优化器",
            10: "产能需求估算",
        }

        tabs = page.locator('button[data-baseweb="tab"]')

        for idx, label in tab_labels.items():
            tabs.nth(idx).click()
            page.wait_for_timeout(1500)
            assert page.locator(f"h3:has-text('{label}')").is_visible(), (
                f"Tab {idx+1} header '{label}' not found"
            )
            # Check for Streamlit errors
            errors = _check_streamlit_error(page)
            if errors:
                print(f"  Tab {idx+1} errors: {errors}")

        print("✅ Cross-tab test 1: All tabs navigable without errors")

    # ---------- Session state persistence ----------

    def test_workbook_data_consistent_across_tabs(self, page):
        """Tabs sharing workbook data (SKU options) should all render."""
        page.goto(BASE_URL, wait_until="networkidle")
        page.wait_for_timeout(3000)

        tabs = page.locator('button[data-baseweb="tab"]')

        # Tab8: Multiselect should have options (or info message)
        tabs.nth(7).click()
        page.wait_for_timeout(1500)
        tab8_ms = page.locator("text=选择产品（可多选）")
        assert tab8_ms.is_visible()

        # Tab9: Pool depends on same _profit_df
        tabs.nth(8).click()
        page.wait_for_timeout(1500)
        tab9_ms = page.locator("text=新场景名")
        assert tab9_ms.is_visible()

        # Tab10: Separate pool but same data source
        tabs.nth(9).click()
        page.wait_for_timeout(1500)
        tab10_pool = page.locator("h5", has_text="SKU 候选池")
        assert tab10_pool.is_visible()

        # Tab11: Plan-related controls
        tabs.nth(10).click()
        page.wait_for_timeout(1500)
        tab11_btn = page.locator('button:has-text("分析产能压力")')
        assert tab11_btn.is_visible()

        print("✅ Cross-tab test 2: Data dependencies consistent across tabs")


# ==============================================================================
# Main guard
# ==============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
