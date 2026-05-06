from __future__ import annotations

import ast
from pathlib import Path


def _load_overview_helpers():
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    source = app_path.read_text(encoding="utf-8")
    module = ast.parse(source, filename=str(app_path))

    keep = []
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name in {"_risk_level", "_build_action_hints"}:
            keep.append(node)

    helper_module = ast.Module(body=keep, type_ignores=[])
    ast.fix_missing_locations(helper_module)
    ns = {}
    exec(compile(helper_module, str(app_path), "exec"), ns, ns)
    return ns["_risk_level"], ns["_build_action_hints"]


_risk_level, _build_action_hints = _load_overview_helpers()


def test_risk_level_mapping():
    assert _risk_level(0) == "normal"
    assert _risk_level(1) == "medium"
    assert _risk_level(5) == "high"


def test_action_hints_prioritize_risk_first():
    hints = _build_action_hints(out_of_stock=3, abnormal=1, snapshot_stale=True)
    assert hints[0].startswith("去 Tab8 查看缺货项")
    assert hints[1].startswith("去 Tab8 检查异常项")
    assert hints[2].startswith("先刷新 Supabase 缓存")

