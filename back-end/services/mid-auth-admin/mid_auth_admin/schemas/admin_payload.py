from __future__ import annotations

from typing import Any

from pydantic import RootModel


class AdminPayload(RootModel[dict[str, Any]]):
    """Generic payload for row create/update operations."""

