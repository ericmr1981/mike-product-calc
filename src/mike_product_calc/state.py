"""
state.py — 有状态 CLI 会话管理器 for mike-product-calc.

设计原则
--------
- 默认状态目录: repo 根目录下的 `state/` (可由 MPC_STATE_DIR 环境变量覆盖)
- 状态文件: JSON，命名 <name>.json
- 默认状态名: "default"
- 状态内容: xlsx_path, price_version, scenario_name, production_plan_name,
           last_output_index, material_sim_versions, optimizer_constraints

Exit codes (CLI 层)
-------------------
  0  — OK
  1  — 系统/参数错误 (SystemExit(1))
  2  — 业务校验失败 (SystemExit(2))

用法
----
  python -m mike_product_calc state init --xlsx path/to/蜜可诗产品库.xlsx
  python -m mike_product_calc state list
  python -m mike_product_calc state load [--name <name>]
  python -m mike_product_calc state save [--name <name>]
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Paths ──────────────────────────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Resolve the repo root (parent of src/)."""
    # mike_product_calc/__file__ = ...src/mike_product_calc/__init__.py
    src = Path(__file__).resolve().parents[1]
    return src.parent


def _default_state_dir() -> Path:
    """Default state directory: repo root / state/."""
    if os.environ.get("MPC_STATE_DIR"):
        p = Path(os.environ["MPC_STATE_DIR"]).expanduser().resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p
    return _repo_root() / "state"


# ── Dataclass ────────────────────────────────────────────────────────────────────────

@dataclass
class MpcState:
    """Session state for the MPC CLI.

    Persisted as JSON. All fields are serialisable.
    """

    # Identifiers
    name: str = "default"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Core paths & contexts
    xlsx_path: Optional[str] = None          # 默认 xlsx 路径
    price_version: str = "当前"             # 当前价格版本 (当前/保守/理想/旺季)
    scenario_name: str = "A"               # 默认方案名
    production_plan_name: Optional[str] = None  # 最近一次加载的生产计划名

    # Execution tracking
    last_cmd: Optional[str] = None           # 最近一次运行的命令
    last_output_index: int = 0              # 最近一次运行输出索引 (递增)

    # Material simulation versions: name -> list of adjustments
    material_sim_versions: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    # Production plans (UI/CLI shared)
    # name -> list of {date, sku_key, spec, qty, plan_type}
    production_plans: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat()
        self.last_output_index += 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MpcState":
        # Allow extra fields from future versions
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

    # ── Convenience helpers ──────────────────────────────────────────────────────

    def effective_xlsx(self, cli_arg: Optional[str]) -> str:
        """Return the xlsx path: CLI arg takes precedence over stored default."""
        return cli_arg if cli_arg else (self.xlsx_path or "")

    def effective_basis(self, cli_arg: Optional[str]) -> str:
        return cli_arg or "factory"

    def bump_output_index(self) -> int:
        self.last_output_index += 1
        return self.last_output_index


# ── State Store ────────────────────────────────────────────────────────────────────

class StateStore:
    """Manages MPC state files on disk."""

    def __init__(self, state_dir: Optional[Path] = None) -> None:
        self.dir = state_dir or _default_state_dir()
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return self.dir / f"{safe}.json"

    def init(self, name: str = "default", **kwargs) -> MpcState:
        """Create a new named state (overwrites if exists)."""
        state = MpcState(name=name, **kwargs)
        self.save(state)
        return state

    def load(self, name: str = "default") -> MpcState:
        """Load a named state. Returns empty default if file missing."""
        p = self._path(name)
        if not p.exists():
            # Return a fresh default
            return MpcState(name=name)
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            return MpcState.from_dict(d)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            sys.stderr.write(f"[MPC state] Warning: corrupt state file {p} — {exc}; starting fresh.\n")
            return MpcState(name=name)

    def save(self, state: MpcState) -> None:
        """Write state to disk."""
        p = self._path(state.name)
        p.parent.mkdir(parents=True, exist_ok=True)
        txt = json.dumps(state.to_dict(), ensure_ascii=False, indent=2)
        p.write_text(txt, encoding="utf-8")

    def list_states(self) -> List[str]:
        """List all state names (stem of .json files)."""
        return sorted(
            p.stem for p in self.dir.glob("*.json")
        )

    def delete(self, name: str) -> bool:
        """Remove a named state. Returns True if deleted."""
        p = self._path(name)
        if p.exists():
            p.unlink()
            return True
        return False

    def default_exists(self) -> bool:
        return self._path("default").exists()

    # ── Snapshots ────────────────────────────────────────────────────────────────

    MAX_SNAPSHOTS = 10

    def _snapshots_dir(self) -> Path:
        d = self.dir / "_snapshots"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _snapshot_path(self, name: str, ts: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
        return self._snapshots_dir() / f"{safe}__{ts}.json"

    def _snapshot_name_to_path(self, name: str) -> Optional[Path]:
        for p in self._snapshots_dir().glob(f"*.json"):
            if name in p.stem:
                return p
        return None

    def snapshot(self, state_name: str = "default") -> str:
        """Save a timestamped snapshot of a named state. Prunes oldest if > MAX_SNAPSHOTS."""
        state = self.load(state_name)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        p = self._snapshot_path(state_name, ts)
        p.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        # Prune oldest
        snaps = sorted(self._snapshots_dir().glob(f"{state_name}__*.json"))
        while len(snaps) > self.MAX_SNAPSHOTS:
            oldest = snaps.pop(0)
            oldest.unlink()
        return ts

    def list_snapshots(self, state_name: str = "default") -> List[Dict[str, str]]:
        """Return [{id, ts, path}] for a named state, newest first."""
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in state_name)
        snaps = sorted(self._snapshots_dir().glob(f"{safe}__*.json"), reverse=True)
        out: List[Dict[str, str]] = []
        for p in snaps:
            ts = p.stem.split("__", 1)[-1]
            # human-readable
            try:
                hr = datetime.strptime(ts, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                hr = ts
            out.append({"id": ts, "ts": hr, "path": str(p)})
        return out

    def restore_snapshot(self, snapshot_id: str, state_name: str = "default") -> MpcState:
        """Restore a state from a snapshot ID (timestamp string). Returns restored state."""
        p = self._snapshot_path(state_name, snapshot_id)
        if not p.exists():
            sys.stderr.write(f"Snapshot not found: {snapshot_id}\n")
            raise SystemExit(1)
        d = json.loads(p.read_text(encoding="utf-8"))
        state = MpcState.from_dict(d)
        state.name = state_name
        state.updated_at = datetime.now().isoformat()
        self.save(state)
        return state


# ── Global store ──────────────────────────────────────────────────────────────────

_store: Optional[StateStore] = None

def get_store() -> StateStore:
    global _store
    if _store is None:
        _store = StateStore()
    return _store


# ── CLI helpers ──────────────────────────────────────────────────────────────────

def _read_state_or_init(store: StateStore, name: str) -> MpcState:
    """Load existing state, or init with defaults if missing."""
    return store.load(name)


def _ensure_xlsx(state: MpcState, xlsx_arg: Optional[str]) -> str:
    """Validate xlsx is available. Exit(1) if missing."""
    path = state.effective_xlsx(xlsx_arg)
    if not path:
        sys.stderr.write("Error: no xlsx path. Run 'mpc state init --xlsx <path>' first.\n")
        raise SystemExit(1)
    p = Path(path)
    if not p.exists():
        sys.stderr.write(f"Error: xlsx not found: {path}\n")
        raise SystemExit(1)
    return path
