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
- **[COMPLEXITY_MED]** complexity=5 — consider multi-sprint
- **[SINGLE_STORY]** dispatch only feature F-001 in this round
## Continue Gate (v5 preview)
- **Final Oracle**: Live acceptance for feature F-001 (Excel 数据解析与校验（V2）) plus local oracle: project-local verification command not yet discovered
- **Current Blocker**: Not yet verified against final oracle. Replace with concrete blocker after the first failed live check.
- **Round Outcome**: retry_with_new_bet
- **Stop Allowed**: no
- **Next Forced Bet**: Execute one bounded bet, verify against the real acceptance path, and if the final oracle still f

## ▶️  ACTIVE.md
# ACTIVE.md — Current WIP

> This file lives inside the project repo. The workspace root WORKSPACE.md is only an index.

## Current Project
- **Name**: workspace
- **Repo**: /Users/ericmr/Documents/GitHub/mike-product-calc
- **Task**: 项目 mike-product-calc：基于真实 Excel 建立统一 ProductKey（品类/品名/规格）并实现跨表一致性校验，覆盖毛利表/成本表/出品表 join，新增 missing_product_row、cost_mismatch、price_missing 等规则，更新 tests/CLI/validation artifacts；最终验收为真实 workbook 可跑通并产出更可操作的 data_validation_report.csv。
- **Mode**: llm
- **Started**: 2

## ✂️  Relevant Snippets (extracted; large docs are NOT inlined)
> If more context is needed, request specific files/sections; do not ask for “the whole doc”.

### `harness/context/context-package-2026-04-11T02-43-57.md`
#### lines 1-53
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
```

### `harness/context/context-package-2026-04-10T17-02-21.md`
#### lines 1-53
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
?? mike-product-calc/ACTIVE.md
?? mike-product-calc/WORKSPACE.md
?? mike-product-calc/harness/artifacts/
?? mike-product-calc/harness/assignments/
?? mike-product-calc/harness/context/
?? mike-product-calc/harness/contracts/
?? mike-product-calc/harness/reports/
?? n8n-orchestration/
```

### `harness/context/context-package-2026-04-10T17-17-12.md`
#### lines 1-53
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
?? mike-product-calc/ACTIVE.md
?? mike-product-calc/WORKSPACE.md
?? mike-product-calc/harness/artifacts/
?? mike-product-calc/harness/assignments/
?? mike-product-calc/harness/context/
?? mike-product-calc/harness/contracts/
?? mike-product-calc/harness/reports/
?? n8n-orchestration/
```

### `harness/context/context-package-2026-04-10T16-41-33.md`
#### lines 1-53
```
# Context Package
> Built by ContextAssembler | 2026-04-10T16-41-33 | task: 项目 mike-product-calc：实现 PRD 的所有内容，并确保 E2E 测试通过。最终验收以 PRD 功能闭环 + E2E 全绿为准。

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
?? mike-product-calc/ACTIVE.md
?? n8n-orchestration/
?? new-project/
?? obsidian-llm-knowledge-base/
?? openclaw-agent-monitor-demo/
?? openclaw-mission-control-oc/
?? openclaw-notebooklm-ui-design/
?? openclaw-session-page-oa-style-demo/
?? openclaw-to-ltx/
?? openstoryline/
```

### `harness/artifacts/codemap.md`
#### lines 1-31
```
# CodeMap — 项目结构索引

> Auto-generated by codemap.js | 2026-04-10T17:02:21.564Z | **multi-agent harness** | Framework: **unknown** | Language: **unknown**

## 基础信息

| 项目 | 值 |
|------|-----|
| 仓库路径 | `/Users/ericmr/Documents/GitHub/mike-product-calc` |
| Git 分支 | `main` |
| 最近提交 | 2026-04-11 00:25:02 +0800 docs: add V1 ADR-0001 tech stack decision |
| 源码文件数 | 0 |
| 仓库画像 | multi-agent harness |
| 框架 | unknown |
| 语言 | unknown |
| 语言分布 | n/a |

## 生成反馈（Invocation）

| 项目 | 值 |
|------|-----|
| 调用确认 | yes |
| Invocation ID | `20260410-170221482-81240` |
| 调用脚本 | `codemap.js` |
| 调用来源 | `harness.js` |
| 请求方 | `trinity-harness` |
| 生成时间 | 2026-04-10T17:02:21.482Z |
| 输出文件 | `/Users/ericmr/Documents/GitHub/mike-product-calc/harness/artifacts/codemap.md` |

## 目录结构（Depth ≤ 3）

```

### `docs/kickoff/PRD.md`
#### lines 1-23
```
# PRD V2 — mike-product-calc（蜜可诗产品经营决策台）

> 升级版 Kickoff：2026-04-11
> 数据源：`蜜可诗产品库.xlsx`（Gelato 84SKU + 雪花冰 10SKU + 饮品 1SKU）
> 产品定位：**目标毛利驱动的产品与原料定价决策台**

---

## 1. 背景与目标

### 业务背景
蜜可诗当前用 Excel 管理产品成本与定价，缺乏系统化的：
- 单品 / 组合毛利分析
- 目标毛利率反推原料定价
- 灵活调价模拟
- 按日期的生产计划与备料
- 选品决策支持

### 产品定位
**本地优先的产品经营决策工作台**——核心不是算数，而是让运营者能快速做出"卖什么、备多少、原料什么价、赚多少、卡在哪里"的判断。

### 可量化目标
- 输入任意产品组合，< 3 秒输出完整利润 + 原料需求结果
```

#### lines 157-197
```

### 模块 6（贯穿）— 数据健康与可信度提示
**回答：这个结果能信多少**

原因：源数据有 103 处计算错误，必须诚实告知用户。

功能：
- 列出所有"计算错误"单元格及影响的 SKU / 原料
- 标记：哪些被置零、哪些是估算、哪些结果需谨慎解读
- 原料缺口预警：某原料无有效单价时，提示"该原料成本为 0，建议核实"

---

## 3. 页面结构设计

| 页面 | 路由 | 核心功能 |
|------|------|---------|
| 首页导航 | `/` | 5 个模块入口 + 数据健康状态卡片 |
| SKU 毛利调价台 | `/sku-margin` | 模块 1 + 模块 2 |
| 原料价格模拟器 | `/material-sim` | 模块 3 |
| 生产计划 | `/production-plan` | 模块 4a |
| 备料计划 | `/prep-plan` | 模块 4b~4d |
| 采购建议 | `/purchase` | 模块 4e |
| 组合评估 | `/portfolio` | 模块 5 |
| 数据健康 | `/data-health` | 模块 6 |

---

## 4. 核心数据对象

### Product
```
name, category, spec, status
price, cost_factory, cost_store
margin_factory, margin_store
recipe_items: list[RecipeItem]
is_adjustable: bool  # 是否参与定价反推
```

### RecipeItem
```
```

## 📂 Relevant Small File Previews (keyword matched; size-capped)

### `tests/test_loader_and_validator.py`
```
from __future__ import annotations

from pathlib import Path

import pandas as pd

from mike_product_calc.data.loader import load_workbook
from mike_product_calc.data.validator import validate_workbook


def _write_minimal_xlsx(path: Path, *, sheet_count: int = 13):
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        for i in range(sheet_count):
            df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
            df.to_excel(w, sheet_name=f"S{i+1}", index=False)


def test_load_workbook_reads_all_sheets(tmp_path: Path):
    p = tmp_path / "wb.xlsx"
    _write_minimal_xlsx(p)

    wb = load_workbook(p)
    assert len(wb.sheets) == 13
    assert "S1" in wb.sheets
    assert wb.sheets["S1"].shape[0] == 2


def test_validate_workbook_warns_on_sheet_count_mismatch(tmp_path: Path):
 
```

### `.venv/lib/python3.9/site-packages/packaging/_parser.py`
```
"""Handwritten parser of dependency specifiers.

The docstring for each __parse_* function contains EBNF-inspired grammar representing
the implementation.
"""

from __future__ import annotations

import ast
from typing import NamedTuple, Sequence, Tuple, Union

from ._tokenizer import DEFAULT_RULES, Tokenizer


class Node:
    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}('{self}')>"

    def serialize(self) -> str:
        raise NotImplementedError


class Variable(Node):
    def serialize(self) -> str:
        return str(self)


class Value(Node):
    def serialize(self) -> str:
        return f'"{self}"'


class Op(Node):
    def seria
```

### `.venv/lib/python3.9/site-packages/streamlit/watcher/local_sources_watcher.py`
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

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any, Callable, Final, NamedTuple

from streamlit import config, file_util
from streamlit.log
```

### `.venv/lib/python3.9/site-packages/streamlit/proto/DocString_pb2.py`
```
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: streamlit/proto/DocString.proto
# Protobuf Python Version: 5.26.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1fstreamlit/proto/DocString.proto\"v\n\tDocString\x12\x12\n\ndoc_string\x18\x03 \x01(\t\x12\x0c\n\x04type\x18\x04 \x01(\t\x12\x0c\n\x04name\x18\x06 \x01(\t\x12\r\n\x05value\x18\x07 \x01(\t\x12\x18\n\x07members\x18\x08 \x03
```

### `.venv/lib/python3.9/site-packages/streamlit/proto/DeckGlJsonChart_pb2.py`
```
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: streamlit/proto/DeckGlJsonChart.proto
# Protobuf Python Version: 5.26.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n%streamlit/proto/DeckGlJsonChart.proto\"\x8d\x02\n\x0f\x44\x65\x63kGlJsonChart\x12\x0c\n\x04json\x18\x01 \x01(\t\x12\x0f\n\x07tooltip\x18\x02 \x01(\t\x12\x1b\n\x13use_container_width\x18\x04 \x01(\x08\x12\n\n\x02id\x18
```

### `.venv/lib/python3.9/site-packages/streamlit/proto/Json_pb2.py`
```
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: streamlit/proto/Json.proto
# Protobuf Python Version: 5.26.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()




DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1astreamlit/proto/Json.proto\"Z\n\x04Json\x12\x0c\n\x04\x62ody\x18\x01 \x01(\t\x12\x10\n\x08\x65xpanded\x18\x02 \x01(\x08\x12\x1d\n\x10max_expand_depth\x18\x03 \x01(\x05H\x00\x88\x01\x01\x42\x13\n\x11_max_expand_depthB)\n\x1c\x
```

### `.venv/lib/python3.9/site-packages/streamlit/source_util.py`
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

from __future__ import annotations

import re
from typing import TYPE_CHECKING, TextIO, TypedDict

from typing_extensions import NotRequired, TypeAlias

from streamlit.string_util imp
```

### `.venv/lib/python3.9/site-packages/streamlit/elements/json.py`
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

from __future__ import annotations

import json
import types
from collections import ChainMap, UserDict
from typing import TYPE_CHECKING, Any, cast

from streamlit.elements.lib.layout
```

### `.venv/lib/python3.9/site-packages/attrs/validators.py`
```
# SPDX-License-Identifier: MIT

from attr.validators import *  # noqa: F403

```

---
*ContextAssembler v1 | 2026-04-11T03-33-06*