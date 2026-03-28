"""Request bodies for ``/me/ai/workbench/chats/*`` (Open WebUI BFF)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OpenWebuiChatsTagFilterBody(BaseModel):
    """Maps to Open WebUI ``POST /api/v1/chats/tags`` (internal only)."""

    name: str = Field(min_length=1)
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1, le=500)


class OpenWebuiChatsTagNameBody(BaseModel):
    name: str = Field(min_length=1)
