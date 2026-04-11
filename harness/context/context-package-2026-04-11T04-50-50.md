# Context Package
> Built by ContextAssembler | 2026-04-11T04-50-50 | task: 项目 mike-product-calc：继续按既定顺序推进。收紧 F-002 的验收 oracle，使其更贴近 PRD（真实 workbook 下的 margin/profit/cost delta 证据、阈值与 top offenders）；同时继续加固 F-003 目标毛利率反推原料定价（固定/可调成本分类、锁定原料、可解释 tiers、导出证据）。验收为：真实 workbook 可跑通、pytest 全绿、产出更贴 PRD 的 CSV/UI/artifact 证据。

## 📋 Git State
- **Branch**: `main`
- **Status**: ⚠️ dirty
```
M mike-product-calc/features.json
?? .DS_Store
?? .skill-staging/
?? CliX/
?? "Coder \351\205\215\347\275\256.md"
?? "Coder+Codex \345\215\217\344\275\234\346\265\201\347\250\213.md"
?? FireRed-OpenStoryline/
?? "GitHub+VPS\350\207\252\345\212\250\351\203\250\347\275\262\351\205\215\347\275\256\346\214\207\345\215\227.md"
?? LTX-Desktop/
?? MC-Gen/
?? Nexus/
?? Obsidian/
?? "Pencil Desgin/"
?? Pipi-go/
?? README.md
?? XianyuAutoAgent/
?? _archive/
?? _tmp/
?? a2a-ws-hub/
?? agent-harness-trinity/
?? agents/
?? app-Home-Portal/
?? app-host-portal/
?? app-minesweeper/
?? app-portal/
?? app-snake/
?? autonomous-dev-harness/
?? bit-office-demo/
?? chinese-learning-kids/
?? collab/
?? debate-orchestra/
?? demo-agent-teams/
?? docker-compose.local.yml
?? edict/
?? explore-universe-kids/
?? kids-chinese-storybook/
?? local-portal/
?? mike-product-calc/.harness-master.json
?? mike-product-calc/.harness-spawn-f-001.json
?? mike-product-calc/.venv/
?? mike-product-calc/ACTIVE.md
?? mike-product-calc/README.md
?? mike-product-calc/WORKSPACE.md
?? mike-product-calc/app.py
?? mike-product-calc/data/
?? mike-product-calc/data_validation_report.csv
?? mike-product-calc/harness/artifacts/
?? mike-product-calc/harness/assignments/
?? mike-product-calc/harness/context/
?? mike-product-calc/harness/contracts/
?? mike-product-calc/harness/reports/
?? mike-product-calc/pyproject.toml
?? mike-product-calc/requirements.txt
?? mike-product-calc/scripts/
?? mike-product-calc/src/
?? mike-product-calc/tests/
?? n8n-orchestration/
?? new-project/
?? obsidian-llm-knowledge-base/
?? openclaw-agent-monitor-demo/
?? openclaw-mission-control-oc/
?? openclaw-notebooklm-ui-design/
?? openclaw-session-page-oa-style-demo/
?? openclaw-to-ltx/
?? openstoryline/
?? retail-finance-system/
?? software-registry/
?? solar-system-animator/
?? team-kanban/
?? templates/
?? wdg-data-foundation/
?? wdg-supabase-migration/
?? whatscode/
?? xxxxx-check/
?? "\346\250\241\345\236\213\351\205\215\347\275\256.md"
```

## 📜 Recent Commits (last 5)
```
  6abfe34 docs: add V1 ADR-0001 tech stack decision
  e7371be kickoff V2: 产品经营决策台 PRD+ARCH+features+goal
```

## 🔍 Uncommitted Changes
```
mike-product-calc/features.json | 6 ++++--
 1 file changed, 4 insertions(+), 2 deletions(-)
```

## 🎯 Features (0/12 passing)
### Unfinished:
- [ ] **F-001: Excel 数据解析与校验（V2）** (priority=1 | size=n/a | acceptance=0)
- [ ] **F-002: SKU 毛利分析（双口径）** (priority=2 | size=n/a | acceptance=0)
- [ ] **F-003: 目标毛利率反推原料定价** (priority=3 | size=n/a | acceptance=0)
- [ ] **F-004: 原料价格模拟器** (priority=4 | size=n/a | acceptance=0)
- [ ] **F-005: 生产计划录入** (priority=5 | size=n/a | acceptance=0)
- [ ] **F-006: 备料计划引擎（BOM展开+规则）** (priority=6 | size=n/a | acceptance=0)
- [ ] **F-007: 采购建议页** (priority=7 | size=n/a | acceptance=0)
- [ ] **F-008: 产品组合评估（实时联动）** (priority=8 | size=n/a | acceptance=0)
- [ ] **F-009: 数据健康与可信度提示** (priority=9 | size=n/a | acceptance=0)
- [ ] **F-010: 多场景对比** (priority=10 | size=n/a | acceptance=0)

## 📄 Latest Sprint Contract
**File**: `f-001.md`

# Sprint Contract — f-001

## 任务
Feature F-001: Excel 数据解析与校验（V2）

## 项目
workspace | /Users/ericmr/Documents/GitHub/mike-product-calc

## Agent
engineering-senior-developer

## Matrix Flags
- **[COMPLEXITY_HIGH]** complexity=9 — PGE-sprint enforced
- **[COMPLEXITY_MED]** complexity=9 — consider multi-sprint
- **[SINGLE_STORY]** dispatch only feature F-001 in this round
## Continue Gate (v5 preview)
- **Final Oracle**: Live acceptance for feature F-001 (Excel 数据解析与校验（V2）) plus local oracle: project-local verification command not yet discovered
- **Current Blocker**: Not yet verified against final oracle. Replace with concrete blocker after the first failed live check.
- **Round Outcome**: retry_with_new_bet
- **Stop Allowed**: no
- **Next Forced Bet**: Execute one bounded bet, verify agains

## ▶️  ACTIVE.md
# ACTIVE.md — Current WIP

> This file lives inside the project repo. The workspace root WORKSPACE.md is only an index.

## Current Project
- **Name**: workspace
- **Repo**: /Users/ericmr/Documents/GitHub/mike-product-calc
- **Task**: 项目 mike-product-calc：目标完成 PRD 上列出的全部功能，不以 F-001 停止。以 features.json + docs/kickoff/PRD.md + harness/goal.md 为 source of truth，持续推进直到：1）12 个功能全部完成；2）关键页面与计算链路可本地验证；3）有真实可执行的 E2E/验收证据；4）features.json 可被回写到通过状态。当前已有真实 Excel、基础 parser/validator、ProductKey 跨表校验，请在此基础上继续滚

## ✂️  Relevant Snippets (extracted; large docs are NOT inlined)
> If more context is needed, request specific files/sections; do not ask for “the whole doc”.

### `harness/context/context-package-2026-04-11T03-33-06.md`
#### lines 1-22
```
# Context Package
> Built by ContextAssembler | 2026-04-11T03-33-06 | task: 项目 mike-product-calc：目标完成 PRD 上列出的全部功能，不以 F-001 停止。以 features.json + docs/kickoff/PRD.md + harness/goal.md 为 source of truth，持续推进直到：1）12 个功能全部完成；2）关键页面与计算链路可本地验证；3）有真实可执行的 E2E/验收证据；4）features.json 可被回写到通过状态。当前已有真实 Excel、基础 parser/validator、ProductKey 跨表校验，请在此基础上继续滚动实施，不要把范围错误收缩成单一子功能后就停。

## 📋 Git State
- **Branch**: `main`
- **Status**: ⚠️ dirty
```
?? .DS_Store
?? .skill-staging/
?? CliX/
?? "Coder \351\205\215\347\275\256.md"
?? "Coder+Codex \345\215\217\344\275\234\346\265\201\347\250\213.md"
?? FireRed-OpenStoryline/
?? "GitHub+VPS\350\207\252\345\212\250\351\203\250\347\275\262\351\205\215\347\275\256\346\214\207\345\215\227.md"
?? LTX-Desktop/
?? MC-Gen/
?? Nexus/
?? Obsidian/
?? "Pencil Desgin/"
?? Pipi-go/
?? README.md
?? XianyuAutoAgent/
```

#### lines 24-65
```
?? _tmp/
?? a2a-ws-hub/
?? agent-harness-trinity/
?? agents/
?? app-Home-Portal/
?? app-host-portal/
?? app-minesweeper/
?? app-portal/
?? app-snake/
?? autonomous-dev-harness/
?? bit-office-demo/
?? chinese-learning-kids/
?? collab/
?? debate-orchestra/
?? demo-agent-teams/
?? docker-compose.local.yml
?? edict/
?? explore-universe-kids/
?? kids-chinese-storybook/
?? local-portal/
?? mike-product-calc/.harness-master.json
?? mike-product-calc/.harness-spawn-f-001.json
?? mike-product-calc/.venv/
?? mike-product-calc/ACTIVE.md
?? mike-product-calc/README.md
?? mike-product-calc/WORKSPACE.md
?? mike-product-calc/app.py
?? mike-product-calc/data/
?? mike-product-calc/data_validation_report.csv
?? mike-product-calc/harness/artifacts/
?? mike-product-calc/harness/assignments/
?? mike-product-calc/harness/context/
?? mike-product-calc/harness/contracts/
?? mike-product-calc/harness/reports/
?? mike-product-calc/pyproject.toml
?? mike-product-calc/requirements.txt
?? mike-product-calc/scripts/
?? mike-product-calc/src/
?? mike-product-calc/tests/
?? n8n-orchestration/
?? new-project/
?? obsidian-llm-knowledge-base/
```

### `harness/context/context-package-2026-04-11T02-43-57.md`
#### lines 1-22
```
# Context Package
> Built by ContextAssembler | 2026-04-11T02-43-57 | task: 项目 mike-product-calc：基于真实 Excel 建立统一 ProductKey（品类/品名/规格）并实现跨表一致性校验，覆盖毛利表/成本表/出品表 join，新增 missing_product_row、cost_mismatch、price_missing 等规则，更新 tests/CLI/validation artifacts；最终验收为真实 workbook 可跑通并产出更可操作的 data_validation_report.csv。

## 📋 Git State
- **Branch**: `main`
- **Status**: ⚠️ dirty
```
?? .DS_Store
?? .skill-staging/
?? CliX/
?? "Coder \351\205\215\347\275\256.md"
?? "Coder+Codex \345\215\217\344\275\234\346\265\201\347\250\213.md"
?? FireRed-OpenStoryline/
?? "GitHub+VPS\350\207\252\345\212\250\351\203\250\347\275\262\351\205\215\347\275\256\346\214\207\345\215\227.md"
?? LTX-Desktop/
?? MC-Gen/
?? Nexus/
?? Obsidian/
?? "Pencil Desgin/"
?? Pipi-go/
?? README.md
?? XianyuAutoAgent/
```

#### lines 24-65
```
?? _tmp/
?? a2a-ws-hub/
?? agent-harness-trinity/
?? agents/
?? app-Home-Portal/
?? app-host-portal/
?? app-minesweeper/
?? app-portal/
?? app-snake/
?? autonomous-dev-harness/
?? bit-office-demo/
?? chinese-learning-kids/
?? collab/
?? debate-orchestra/
?? demo-agent-teams/
?? docker-compose.local.yml
?? edict/
?? explore-universe-kids/
?? kids-chinese-storybook/
?? local-portal/
?? mike-product-calc/.harness-master.json
?? mike-product-calc/.harness-spawn-f-001.json
?? mike-product-calc/.venv/
?? mike-product-calc/ACTIVE.md
?? mike-product-calc/README.md
?? mike-product-calc/WORKSPACE.md
?? mike-product-calc/app.py
?? mike-product-calc/data/
?? mike-product-calc/data_validation_report.csv
?? mike-product-calc/harness/artifacts/
?? mike-product-calc/harness/assignments/
?? mike-product-calc/harness/context/
?? mike-product-calc/harness/contracts/
?? mike-product-calc/harness/reports/
?? mike-product-calc/pyproject.toml
?? mike-product-calc/requirements.txt
?? mike-product-calc/scripts/
?? mike-product-calc/src/
?? mike-product-calc/tests/
?? n8n-orchestration/
?? new-project/
?? obsidian-llm-knowledge-base/
```

### `harness/context/context-package-2026-04-10T17-17-12.md`
#### lines 1-22
```
# Context Package
> Built by ContextAssembler | 2026-04-10T17-17-12 | task: 项目 mike-product-calc：以 features.json 为 PRD source of truth，完成全部 12 个功能（must / important / nice-to-have），持续推进直到功能闭环；最终验收必须同时满足：1）features.json 中全部功能完成；2）E2E 测试全绿；3）关键页面与计算链路可本地验证。

## 📋 Git State
- **Branch**: `main`
- **Status**: ⚠️ dirty
```
?? .DS_Store
?? .skill-staging/
?? CliX/
?? "Coder \351\205\215\347\275\256.md"
?? "Coder+Codex \345\215\217\344\275\234\346\265\201\347\250\213.md"
?? FireRed-OpenStoryline/
?? "GitHub+VPS\350\207\252\345\212\250\351\203\250\347\275\262\351\205\215\347\275\256\346\214\207\345\215\227.md"
?? LTX-Desktop/
?? MC-Gen/
?? Nexus/
?? Obsidian/
?? "Pencil Desgin/"
?? Pipi-go/
?? README.md
?? XianyuAutoAgent/
```

#### lines 24-65
```
?? _tmp/
?? a2a-ws-hub/
?? agent-harness-trinity/
?? agents/
?? app-Home-Portal/
?? app-host-portal/
?? app-minesweeper/
?? app-portal/
?? app-snake/
?? autonomous-dev-harness/
?? bit-office-demo/
?? chinese-learning-kids/
?? collab/
?? debate-orchestra/
?? demo-agent-teams/
?? docker-compose.local.yml
?? edict/
?? explore-universe-kids/
?? kids-chinese-storybook/
?? local-portal/
?? mike-product-calc/.harness-master.json
?? mike-product-calc/.harness-spawn-f-001.json
?? mike-product-calc/ACTIVE.md
?? mike-product-calc/WORKSPACE.md
?? mike-product-calc/harness/artifacts/
?? mike-product-calc/harness/assignments/
?? mike-product-calc/harness/context/
?? mike-product-calc/harness/contracts/
?? mike-product-calc/harness/reports/
?? n8n-orchestration/
?? new-project/
?? obsidian-llm-knowledge-base/
?? openclaw-agent-monitor-demo/
?? openclaw-mission-control-oc/
?? openclaw-notebooklm-ui-design/
?? openclaw-session-page-oa-style-demo/
?? openclaw-to-ltx/
?? openstoryline/
?? retail-finance-system/
?? software-registry/
?? solar-system-animator/
?? team-kanban/
```

### `harness/context/context-package-2026-04-10T17-02-21.md`
#### lines 1-22
```
# Context Package
> Built by ContextAssembler | 2026-04-10T17-02-21 | task: 项目 mike-product-calc：以 features.json 为 PRD source of truth，完成全部 12 个功能（must / important / nice-to-have），持续推进直到功能闭环；最终验收必须同时满足：1）features.json 中全部功能完成；2）E2E 测试全绿；3）关键页面与计算链路可本地验证。

## 📋 Git State
- **Branch**: `main`
- **Status**: ⚠️ dirty
```
?? .DS_Store
?? .skill-staging/
?? CliX/
?? "Coder \351\205\215\347\275\256.md"
?? "Coder+Codex \345\215\217\344\275\234\346\265\201\347\250\213.md"
?? FireRed-OpenStoryline/
?? "GitHub+VPS\350\207\252\345\212\250\351\203\250\347\275\262\351\205\215\347\275\256\346\214\207\345\215\227.md"
?? LTX-Desktop/
?? MC-Gen/
?? Nexus/
?? Obsidian/
?? "Pencil Desgin/"
?? Pipi-go/
?? README.md
?? XianyuAutoAgent/
```

#### lines 24-65
```
?? _tmp/
?? a2a-ws-hub/
?? agent-harness-trinity/
?? agents/
?? app-Home-Portal/
?? app-host-portal/
?? app-minesweeper/
?? app-portal/
?? app-snake/
?? autonomous-dev-harness/
?? bit-office-demo/
?? chinese-learning-kids/
?? collab/
?? debate-orchestra/
?? demo-agent-teams/
?? docker-compose.local.yml
?? edict/
?? explore-universe-kids/
?? kids-chinese-storybook/
?? local-portal/
?? mike-product-calc/.harness-master.json
?? mike-product-calc/.harness-spawn-f-001.json
?? mike-product-calc/ACTIVE.md
?? mike-product-calc/WORKSPACE.md
?? mike-product-calc/harness/artifacts/
?? mike-product-calc/harness/assignments/
?? mike-product-calc/harness/context/
?? mike-product-calc/harness/contracts/
?? mike-product-calc/harness/reports/
?? n8n-orchestration/
?? new-project/
?? obsidian-llm-knowledge-base/
?? openclaw-agent-monitor-demo/
?? openclaw-mission-control-oc/
?? openclaw-notebooklm-ui-design/
?? openclaw-session-page-oa-style-demo/
?? openclaw-to-ltx/
?? openstoryline/
?? retail-finance-system/
?? software-registry/
?? solar-system-animator/
?? team-kanban/
```

## 📂 Relevant Small File Previews (keyword matched; size-capped)

### `tests/test_profit_oracle.py`
```
from __future__ import annotations

import pandas as pd

from mike_product_calc.calc.profit_oracle import (
    ProfitOracleThresholds,
    sku_profit_consistency_table,
    render_profit_oracle_markdown,
)


def test_profit_consistency_table_clean():
    """All three columns computed; margin/profit/cost deltas are zero when consistent."""
    sheets = {
        "产品毛利表_Gelato": pd.DataFrame({
            "品类": ["Gelato"],
            "品名": ["X"],
            "规格": ["S"],
            "状态": ["上线"],
            "成本": [10.0],
            "门店成本": [12.0],
            "定价": [20.0],
            "毛利率": [0.5],        # price*margin = 20*0.5 = 10 = cost ✓
            "门店毛利率": [0.4],    # 20*0.4 = 8 != 12 (store not consistent)
        }),
    }
    df = sku_profit_consistency_table(sheets, basis="fac
```

### `src/mike_product_calc/calc/profit_oracle.py`
```
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .profit import ProfitBasis, sku_profit_table


@dataclass(frozen=True)
class ProfitOracleThresholds:
    """Acceptance thresholds.

    - margin_delta_abs: absolute delta on gross margin (0~1 scale)
    - rmb_delta_abs: absolute delta in RMB for profit/cost consistency
    """

    margin_delta_abs: float = 1e-4
    rmb_delta_abs: float = 0.01


def sku_profit_consistency_table(
    sheets: dict[str, pd.DataFrame],
    *,
    basis: ProfitBasis = "factory",
    only_status: Optional[str] = None,
) -> pd.DataFrame:
    """Enrich sku_profit_table with workbook-implied profit/cost deltas.

    Workbook provides (price, cost, margin). If these are internally consistent:

```

### `tests/test_margin_target.py`
```
from __future__ import annotations

import pandas as pd

from mike_product_calc.calc.margin_target import (
    _is_fixed_category,
    FIXED_CATEGORIES,
    sku_ingredient_lines,
    target_pricing,
    TargetPricingResult,
)


def test_is_fixed_category_true():
    assert _is_fixed_category("包材") is True
    assert _is_fixed_category("生产工具") is True
    assert _is_fixed_category("周边陈列") is True
    assert _is_fixed_category("生产消耗品") is True


def test_is_fixed_category_false():
    assert _is_fixed_category("配料") is False
    assert _is_fixed_category("乳制品") is False
    assert _is_fixed_category("") is False


def test_sku_ingredient_lines_unknown_key():
    sheets = {
        "产品出品表_Gelato": pd.DataFrame({
            "品类": ["Gelato"], "品名": ["X"], "规格": ["S"],
            "主原料": ["m"]
```

### `tests/test_profit.py`
```
from __future__ import annotations

import pandas as pd

from mike_product_calc.calc.profit import margin_delta_report, sku_cost_breakdown, sku_profit_table
from mike_product_calc.calc.target_pricing import suggest_adjustable_item_costs


def _base_sheets():
    return {
        "产品毛利表_Gelato": pd.DataFrame(
            {
                "品类": ["Gelato"],
                "品名": ["A"],
                "规格": ["大"],
                "状态": ["上线"],
                "成本": [10.0],
                "门店成本": [12.0],
                "定价": [20.0],
                "毛利率": [0.5],
                "门店毛利率": [0.4],
            }
        ),
        "产品出品表_Gelato": pd.DataFrame(
            {
                "品类": ["Gelato", "Gelato"],
                "品名": ["A", "A"],
                "规格": ["大", "大"],
           
```

### `.venv/lib/python3.9/site-packages/streamlit/proto/Delta_pb2.py`
```
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: streamlit/proto/Delta.proto
# Protobuf Python Version: 5.26.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from streamlit.proto import Block_pb2 as streamlit_dot_proto_dot_Block__pb2
from streamlit.proto import Element_pb2 as streamlit_dot_proto_dot_Element__pb2
from streamlit.proto import NamedDataSet_pb2 as streamlit_dot_proto_dot_NamedDataSet__pb2
from streamlit.proto import ArrowNamedDataSet_
```

### `.venv/lib/python3.9/site-packages/streamlit/delta_generator_singletons.py`
```
# Copyright (c) Streamlit Inc. (2018-2022) Snowflake Inc. (2022-2025)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
The main purpose of this module (right now at least) is to avoid a dependency
cycle between streamlit.delta_generator and some elements.
"""

from __future__ import annotations

f
```

### `.venv/lib/python3.9/site-packages/tenacity/stop.py`
```
# Copyright 2016–2021 Julien Danjou
# Copyright 2016 Joshua Harlow
# Copyright 2013-2014 Ray Holder
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import abc
import typing

from tenacity import _utils

if typing.TYPE_CHECKING:
    import threading

    from tenacity import RetryCallState


class stop_bas
```

### `.venv/lib/python3.9/site-packages/plotly/graph_objs/scatterternary/marker/colorbar/_tickformatstop.py`
```
#                   --- THIS FILE IS AUTO-GENERATED ---
# Modifications will be overwitten the next time code generation run.

from plotly.basedatatypes import BaseTraceHierarchyType as _BaseTraceHierarchyType
import copy as _copy


class Tickformatstop(_BaseTraceHierarchyType):
    _parent_path_str = "scatterternary.marker.colorbar"
    _path_str = "scatterternary.marker.colorbar.tickformatstop"
    _valid_props = {"dtickrange", "enabled", "name", "templateitemname", "value"}

    @property
    def dtickrange(self):
        """
            range [*min*, *max*], where "min", "max" - dtick values which
            describe some zoom level, it is possible to omit "min" or "max"
            value by passing "null"

            The 'dtickrange' property is an info array that may be specified a
```

### `.venv/lib/python3.9/site-packages/plotly/graph_objs/splom/marker/colorbar/_tickformatstop.py`
```
#                   --- THIS FILE IS AUTO-GENERATED ---
# Modifications will be overwitten the next time code generation run.

from plotly.basedatatypes import BaseTraceHierarchyType as _BaseTraceHierarchyType
import copy as _copy


class Tickformatstop(_BaseTraceHierarchyType):
    _parent_path_str = "splom.marker.colorbar"
    _path_str = "splom.marker.colorbar.tickformatstop"
    _valid_props = {"dtickrange", "enabled", "name", "templateitemname", "value"}

    @property
    def dtickrange(self):
        """
            range [*min*, *max*], where "min", "max" - dtick values which
            describe some zoom level, it is possible to omit "min" or "max"
            value by passing "null"

            The 'dtickrange' property is an info array that may be specified as:

            * 
```

### `.venv/lib/python3.9/site-packages/plotly/graph_objs/parcats/line/colorbar/_tickformatstop.py`
```
#                   --- THIS FILE IS AUTO-GENERATED ---
# Modifications will be overwitten the next time code generation run.

from plotly.basedatatypes import BaseTraceHierarchyType as _BaseTraceHierarchyType
import copy as _copy


class Tickformatstop(_BaseTraceHierarchyType):
    _parent_path_str = "parcats.line.colorbar"
    _path_str = "parcats.line.colorbar.tickformatstop"
    _valid_props = {"dtickrange", "enabled", "name", "templateitemname", "value"}

    @property
    def dtickrange(self):
        """
            range [*min*, *max*], where "min", "max" - dtick values which
            describe some zoom level, it is possible to omit "min" or "max"
            value by passing "null"

            The 'dtickrange' property is an info array that may be specified as:

            * 
```

### `.venv/lib/python3.9/site-packages/plotly/graph_objs/streamtube/colorbar/_tickformatstop.py`
```
#                   --- THIS FILE IS AUTO-GENERATED ---
# Modifications will be overwitten the next time code generation run.

from plotly.basedatatypes import BaseTraceHierarchyType as _BaseTraceHierarchyType
import copy as _copy


class Tickformatstop(_BaseTraceHierarchyType):
    _parent_path_str = "streamtube.colorbar"
    _path_str = "streamtube.colorbar.tickformatstop"
    _valid_props = {"dtickrange", "enabled", "name", "templateitemname", "value"}

    @property
    def dtickrange(self):
        """
            range [*min*, *max*], where "min", "max" - dtick values which
            describe some zoom level, it is possible to omit "min" or "max"
            value by passing "null"

            The 'dtickrange' property is an info array that may be specified as:

            * a li
```

---
*ContextAssembler v1 | 2026-04-11T04-50-50*