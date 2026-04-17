"""
data/upload.py — Upload registry for mike-product-calc.

管理 data/uploads/ 目录下的 xlsx 文件：
- registry.json: 文件元数据清单
- <id>__<orig_name>: 实际存储的文件

与 Streamlit UI 共用同一套 registry，CLI 修改对 UI 可见，反之亦然。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# ── Constants ─────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = ROOT / "data" / "uploads"
REGISTRY_PATH = UPLOAD_DIR / "registry.json"


# ── Data model ─────────────────────────────────────────────────────────────────

@dataclass
class UploadRegistryItem:
    id: str
    orig_name: str
    saved_name: str
    uploaded_at: str
    size: int
    sha256: str

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "UploadRegistryItem":
        return UploadRegistryItem(
            id=str(d["id"]),
            orig_name=str(d["orig_name"]),
            saved_name=str(d["saved_name"]),
            uploaded_at=str(d["uploaded_at"]),
            size=int(d["size"]),
            sha256=str(d["sha256"]),
        )


class DuplicateFileError(Exception):
    """Raised when an uploaded file has the same SHA256 as an existing entry."""
    existing_id: str

    def __init__(self, message: str, existing_id: str):
        super().__init__(message)
        self.existing_id = existing_id


# ── Registry ────────────────────────────────────────────────────────────────────

class UploadRegistry:
    """File registry backed by registry.json + data/uploads/."""

    def __init__(self, upload_dir: Path | None = None, registry_path: Path | None = None):
        self.upload_dir = (upload_dir or UPLOAD_DIR).resolve()
        self.registry_path = (registry_path or REGISTRY_PATH).resolve()

    # ── Path helpers ────────────────────────────────────────────────────────────

    def _ensure_upload_dir(self) -> Path:
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        return self.upload_dir

    def _sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    # ── Registry I/O ────────────────────────────────────────────────────────────

    def _load(self) -> List[dict]:
        if not self.registry_path.exists():
            return []
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, items: List[dict]) -> None:
        self._ensure_upload_dir()
        self.registry_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    def list_all(self) -> List[UploadRegistryItem]:
        """Return all registered files, newest first."""
        items = self._load()
        return sorted(
            [UploadRegistryItem.from_dict(it) for it in items],
            key=lambda x: x.uploaded_at,
            reverse=True,
        )

    def find_by_id(self, file_id: str) -> Optional[UploadRegistryItem]:
        """Find a file by its ID prefix or full ID."""
        items = self._load()
        fid = str(file_id).strip()
        for it in items:
            if str(it.get("id", "")).startswith(fid) or str(it.get("id", "")) == fid:
                return UploadRegistryItem.from_dict(it)
        return None

    def find_by_sha(self, sha256: str) -> Optional[UploadRegistryItem]:
        """Find an existing entry by content hash."""
        items = self._load()
        for it in items:
            if str(it.get("sha256", "")) == str(sha256).strip():
                return UploadRegistryItem.from_dict(it)
        return None

    def resolve_path(self, file_id: str) -> Optional[Path]:
        """Return the real filesystem path for a file ID, or None if not found."""
        item = self.find_by_id(file_id)
        if item is None:
            return None
        fp = self.upload_dir / item.saved_name
        return fp if fp.exists() else None

    def upload(
        self,
        data: bytes,
        orig_name: str,
        *,
        replace: bool = False,
        replace_id: str | None = None,
        skip_duplicate: bool = True,
    ) -> UploadRegistryItem:
        """
        Save an uploaded file to disk and register it.

        Args:
            data: file bytes
            orig_name: original filename
            replace: if True, delete replace_id entry first
            replace_id: ID of the file to replace (used with replace=True)
            skip_duplicate: if True and file content already exists, return existing entry

        Returns:
            UploadRegistryItem for the saved (or existing) file

        Raises:
            DuplicateFileError: if skip_duplicate=False and content already exists
        """
        self._ensure_upload_dir()
        sha = self._sha256(data)

        # Check for duplicate by content
        existing = self.find_by_sha(sha)
        if existing is not None:
            if skip_duplicate:
                return existing
            raise DuplicateFileError(
                f"File with same content already exists (id={existing.id})",
                existing_id=existing.id,
            )

        # Build entry
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fid = f"{ts}_{sha[:10]}"
        safe_name = orig_name.replace("/", "_").replace("\\", "_")
        saved_name = f"{fid}__{safe_name}"
        fp = self.upload_dir / saved_name
        fp.write_bytes(data)

        item = UploadRegistryItem(
            id=fid,
            orig_name=orig_name,
            saved_name=saved_name,
            uploaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            size=len(data),
            sha256=sha,
        )

        # Persist registry
        items = self._load()
        items.insert(0, item.to_dict())
        self._save(items)

        # Delete replaced file if needed
        if replace and replace_id:
            self.delete(replace_id, missing_ok=True)

        return item

    def delete(self, file_id: str, missing_ok: bool = False) -> bool:
        """
        Remove a file from registry and delete its on-disk copy.

        Returns True if deleted, False if not found (and missing_ok=True).
        """
        items = self._load()
        fid = str(file_id).strip()
        kept: List[dict] = []
        deleted = False

        for it in items:
            it_id = str(it.get("id", ""))
            if it_id.startswith(fid) or it_id == fid:
                saved = it.get("saved_name", "")
                fp = self.upload_dir / saved
                if fp.exists():
                    fp.unlink()
                deleted = True
            else:
                kept.append(it)

        if not deleted and not missing_ok:
            raise FileNotFoundError(f"No file found with id: {file_id}")

        self._save(kept)
        return deleted

    def count(self) -> int:
        return len(self._load())

    def disk_usage_bytes(self) -> int:
        """Total size of uploaded files on disk."""
        total = 0
        for f in self.upload_dir.glob("*__*"):
            if f.is_file():
                total += f.stat().st_size
        return total
