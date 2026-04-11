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
## 项目全貌（必读）
执行任何操作前，请先阅读项目结构索引：
```
harness/artifacts/codemap.md
```
其中包含：模块依赖图、API 路由表、数据模型清单、跨目录引用。这些信息对理解代码传播路径和定位 bug 至关重要。


## 项目
workspace | /Users/ericmr/Documents/GitHub/mike-product-calc

## Agent
engineering-senior-developer

## Matrix Flags
- **[COMPLEXITY_HIGH]** complexity=10 — PGE-sprint enforced
- **[COMPLEXITY_MED]** complexity=10 — consider multi-sprint
- **[SINGLE_STORY]** dispatch only feature F-001 in this round
## Continue Gate (v5 preview)
- **Final Oracle**: Live acceptance for feature F-001 (Excel 数据解析与校验（V2）) plus local oracle: project-local verification command not yet discovered
- **Current Blocker**: Not yet verified against final oracle. Replace with concrete blocker after the first failed live 

## ▶️  ACTIVE.md
# ACTIVE.md — Current WIP

> This file lives inside the project repo. The workspace root WORKSPACE.md is only an index.

## Current Project
- **Name**: workspace
- **Repo**: /Users/ericmr/Documents/GitHub/mike-product-calc
- **Task**: 项目 mike-product-calc：以 features.json 为 PRD source of truth，完成全部 12 个功能（must / important / nice-to-have），持续推进直到功能闭环；最终验收必须同时满足：1）features.json 中全部功能完成；2）E2E 测试全绿；3）关键页面与计算链路可本地验证。
- **Mode**: llm-full
- **Started**: 2026-04-10T17:17:12.486Z
- **Status**: running
- *

## ✂️  Relevant Snippets (extracted; large docs are NOT inlined)
> If more context is needed, request specific files/sections; do not ask for “the whole doc”.

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

### `harness/artifacts/f001/validation_summary.md`
#### lines 1-51
```
# F-001 Validation Summary (REAL workbook)

Source report: `data_validation_report.csv`

Total issues: **197**

## Severity counts

| severity   |   count |
|:-----------|--------:|
| warn       |     105 |
| info       |      87 |
| error      |       5 |

## Top rules

| rule                   |   count |
|:-----------------------|--------:|
| null_key               |      97 |
| calc_error_literal_row |      41 |
| non_numeric_row        |      41 |
| calc_error_literal     |       5 |
| non_numeric            |       5 |
| duplicate_keys         |       5 |
| missing_ingredient_ref |       3 |

## Error issues (all)

| sheet          | rule               | message                                          | column   |
|:---------------|:-------------------|:-------------------------------------------------|:---------|
| 产品成本计算表_Gelato | calc_error_literal | Found literal '计算错误' in column '100克成本' (7 rows) | 100克成本   |
| 产品成本计算表_Gelato | calc_error_literal | Found literal '计算错误' in column '单位成本' (7 rows)   | 单位成本     |
| 产品成本计算表_Gelato | calc_error_literal | Found literal '计算错误' in column '门店单位成本' (7 rows) | 门店单位成本   |
| 总原料成本表         | calc_error_literal | Found literal '计算错误' in column '加价前成本' (41 rows) | 加价前成本    |
| 总原料成本表         | calc_error_literal | Found literal '计算错误' in column '加价后成本' (41 rows) | 加价后成本    |

## Example WARN issues (first 50)

| sheet          | rule        | message                                                      |   row | column   |
|:---------------|:------------|:-------------------------------------------------------------|------:|:---------|
| 产品成本计算表_Gelato | non_numeric | Non-numeric values found in numeric column '100克成本' (7 rows) |   nan | 100克成本   |
| 产品成本计算表_Gelato | non_numeric | Non-numeric values found in numeric column '单位成本' (7 rows)   |   nan | 单位成本     |
| 产品成本计算表_Gelato | non_numeric | Non-numeric values found in numeric column '门店单位成本' (7 rows) |   nan | 门店单位成本   |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品类'                                   |    76 | 品类       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品类'                                   |    77 | 品类       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品类'                                   |    78 | 品类       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品名'                                   |    76 | 品名       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品名'                                   |    77 | 品名       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '品名'                                   |    78 | 品名       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '配料'                                   |    76 | 配料       |
| 产品配方表_Gelato   | null_key    | Null/empty key column '配料'                                   |    77 | 配料       |
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

### `harness/context/context-package-2026-04-10T16-41-33.md`
#### lines 1-22
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
```

#### lines 24-94
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

## ▶️  ACTIVE.md
# Active — 蜜可诗产品经营决策台

> Last updated: 2026-04-11

## 当前目标
完成 M1：数据层 + SKU 毛利展示（Streamlit Web UI）

## 下一行动
搭建项目脚手架（M1）：
```

## 📂 Relevant Small File Previews (keyword matched; size-capped)

### `.venv/lib/python3.9/site-packages/streamlit/proto/ClientState_pb2.py`
```
# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: streamlit/proto/ClientState.proto
# Protobuf Python Version: 5.26.1
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from streamlit.proto import WidgetStates_pb2 as streamlit_dot_proto_dot_WidgetStates__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n!streamlit/proto/ClientState.proto\x1a\"streamlit/proto/WidgetStates.proto\"\xf3\x01\n\x0b\x43ontextInfo\x12\x15\n\x08timezone\x18\x
```

### `.venv/lib/python3.9/site-packages/streamlit/web/cli.py`
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

"""A script which is run when the Streamlit package is executed."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any, Callable, Final, T
```

### `.venv/lib/python3.9/site-packages/streamlit/cli_util.py`
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

"""Utilities related to the CLI."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from streamlit import env_util, errors


def print_to_cli(
```

### `.venv/lib/python3.9/site-packages/jinja2/tests.py`
```
"""Built-in template tests used with the ``is`` operator."""

import operator
import typing as t
from collections import abc
from numbers import Number

from .runtime import Undefined
from .utils import pass_environment

if t.TYPE_CHECKING:
    from .environment import Environment


def test_odd(value: int) -> bool:
    """Return true if the variable is odd."""
    return value % 2 == 1


def test_even(value: int) -> bool:
    """Return true if the variable is even."""
    return value % 2 == 0


def test_divisibleby(value: int, num: int) -> bool:
    """Check if a variable is divisible by a number."""
    return value % num == 0


def test_defined(value: t.Any) -> bool:
    """Return true if the variable is defined:

    .. sourcecode:: jinja

        {% if variable is defined %}
        
```

### `.venv/lib/python3.9/site-packages/numpy/distutils/command/install_clib.py`
```
import os
from distutils.core import Command
from distutils.ccompiler import new_compiler
from numpy.distutils.misc_util import get_cmd

class install_clib(Command):
    description = "Command to install installable C libraries"

    user_options = []

    def initialize_options(self):
        self.install_dir = None
        self.outfiles = []

    def finalize_options(self):
        self.set_undefined_options('install', ('install_lib', 'install_dir'))

    def run (self):
        build_clib_cmd = get_cmd("build_clib")
        if not build_clib_cmd.build_clib:
            # can happen if the user specified `--skip-build`
            build_clib_cmd.finalize_options()
        build_dir = build_clib_cmd.build_clib

        # We need the compiler to get the library name -> filename association
```

### `.venv/lib/python3.9/site-packages/numpy/typing/tests/data/pass/ufunclike.py`
```
from __future__ import annotations
from typing import Any, Optional
import numpy as np


class Object:
    def __ceil__(self) -> Object:
        return self

    def __floor__(self) -> Object:
        return self

    def __ge__(self, value: object) -> bool:
        return True

    def __array__(self, dtype: Optional[np.typing.DTypeLike] = None,
                  copy: Optional[bool] = None) -> np.ndarray[Any, np.dtype[np.object_]]:
        ret = np.empty((), dtype=object)
        ret[()] = self
        return ret


AR_LIKE_b = [True, True, False]
AR_LIKE_u = [np.uint32(1), np.uint32(2), np.uint32(3)]
AR_LIKE_i = [1, 2, 3]
AR_LIKE_f = [1.0, 2.0, 3.0]
AR_LIKE_O = [Object(), Object(), Object()]
AR_U: np.ndarray[Any, np.dtype[np.str_]] = np.zeros(3, dtype="U5")

np.fix(AR_LIKE_b)
np.fix(AR_L
```

### `.venv/lib/python3.9/site-packages/numpy/lib/tests/test_ufunclike.py`
```
import numpy as np

from numpy import fix, isposinf, isneginf
from numpy.testing import (
    assert_, assert_equal, assert_array_equal, assert_raises
)


class TestUfunclike:

    def test_isposinf(self):
        a = np.array([np.inf, -np.inf, np.nan, 0.0, 3.0, -3.0])
        out = np.zeros(a.shape, bool)
        tgt = np.array([True, False, False, False, False, False])

        res = isposinf(a)
        assert_equal(res, tgt)
        res = isposinf(a, out)
        assert_equal(res, tgt)
        assert_equal(out, tgt)

        a = a.astype(np.complex128)
        with assert_raises(TypeError):
            isposinf(a)

    def test_isneginf(self):
        a = np.array([np.inf, -np.inf, np.nan, 0.0, 3.0, -3.0])
        out = np.zeros(a.shape, bool)
        tgt = np.array([False, True, False,
```

### `.venv/lib/python3.9/site-packages/numpy/lib/_ufunclike_impl.py`
```
"""
Module of functions that are like ufuncs in acting on arrays and optionally
storing results in an output array.

"""
__all__ = ['fix', 'isneginf', 'isposinf']

import numpy._core.numeric as nx
from numpy._core.overrides import array_function_dispatch
import warnings
import functools


def _dispatcher(x, out=None):
    return (x, out)


@array_function_dispatch(_dispatcher, verify=False, module='numpy')
def fix(x, out=None):
    """
    Round to nearest integer towards zero.

    Round an array of floats element-wise to nearest integer towards zero.
    The rounded values are returned as floats.

    Parameters
    ----------
    x : array_like
        An array of floats to be rounded
    out : ndarray, optional
        A location into which the result is stored. If provided, it must ha
```

### `.venv/lib/python3.9/site-packages/_plotly_utils/colors/cyclical.py`
```
"""
Cyclical color scales are appropriate for continuous data that has a natural cyclical \
structure, such as temporal data (hour of day, day of week, day of year, seasons) or
complex numbers or other phase data.
"""

from ._swatches import _swatches, _swatches_continuous, _swatches_cyclical


def swatches(template=None):
    return _swatches(__name__, globals(), template)


swatches.__doc__ = _swatches.__doc__


def swatches_continuous(template=None):
    return _swatches_continuous(__name__, globals(), template)


swatches_continuous.__doc__ = _swatches_continuous.__doc__


def swatches_cyclical(template=None):
    return _swatches_cyclical(__name__, globals(), template)


swatches_cyclical.__doc__ = _swatches_cyclical.__doc__


Twilight = [
    "#e2d9e2",
    "#9ebbc9",
    "#6785be",

```

---
*ContextAssembler v1 | 2026-04-11T02-43-57*