"""Whitelisted Open WebUI ``GET /api/v1/configs/{segment}`` keys for ``/me/ai/workbench/config/...``.

Only segments listed here may be proxied for ordinary users. Do **not** add paths that return
connection strings, API keys, full ``export``, ``tool_servers`` payloads, etc.
"""

from __future__ import annotations

# Keys must match Open WebUI router path segments (no slashes).
OPENWEBUI_ME_SAFE_CONFIG_GET_KEYS: frozenset[str] = frozenset({"banners"})
