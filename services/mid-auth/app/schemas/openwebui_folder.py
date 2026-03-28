"""Request bodies for ``/me/ai/workbench/folders`` (Open WebUI folder shapes; platform paths only)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OpenWebUIFolderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    data: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    parent_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class OpenWebUIFolderUpdateRequest(BaseModel):
    name: str | None = None
    data: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")
