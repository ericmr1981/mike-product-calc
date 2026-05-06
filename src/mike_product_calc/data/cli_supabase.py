"""Supabase client initialisation for CLI (non-Streamlit contexts).

Reads credentials from:
  1. Environment variables  SUPABASE_URL / SUPABASE_SERVICE_KEY
  2. ``.streamlit/secrets.toml``  (TOML section ``[supabase]``)

Usage::

    from mike_product_calc.data.cli_supabase import get_client
    client = get_client()
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from mike_product_calc.data.supabase_client import MpcSupabaseClient


def _find_secrets_toml() -> Path | None:
    """Walk up from CWD to find ``.streamlit/secrets.toml``."""
    cwd = Path.cwd().resolve()
    for parent in [cwd] + list(cwd.parents):
        candidate = parent / ".streamlit" / "secrets.toml"
        if candidate.is_file():
            return candidate
    return None


def _read_toml_value(path: Path, key: str) -> str | None:
    """Simple TOML parser: read ``[section]`` key = ``value``."""
    import re as _re
    in_section = False
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_section = line[1:-1].strip() == "supabase"
            continue
        if in_section and "=" in line:
            m = _re.match(r'^\s*' + _re.escape(key) + r'\s*=\s*"(.+)"\s*$', line)
            if m:
                return m.group(1)
    return None


def get_client() -> MpcSupabaseClient:
    """Initialise a Supabase client for CLI usage.

    Raises ``SystemExit(1)`` if credentials cannot be found.
    """
    # 1. Environment variables
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")

    # 2. .streamlit/secrets.toml fallback
    if not url or not key:
        secrets_path = _find_secrets_toml()
        if secrets_path:
            if not url:
                url = _read_toml_value(secrets_path, "url")
            if not key:
                key = _read_toml_value(secrets_path, "service_key")

    if not url or not key:
        sys.stderr.write(
            "Error: Supabase credentials not found.\n"
            "  Set SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables,\n"
            "  or create .streamlit/secrets.toml with:\n"
            "    [supabase]\n"
            "    url = \"https://xxx.supabase.co\"\n"
            "    service_key = \"sb_secret_xxx\"\n"
        )
        raise SystemExit(1)

    return MpcSupabaseClient(url, key)
