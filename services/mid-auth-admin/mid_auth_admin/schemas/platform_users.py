from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PlatformName = Literal["vocechat", "memos", "openwebui"]


class PlatformUserRecord(BaseModel):
    id: str
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    is_active: bool | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class PlatformUserListResponse(BaseModel):
    platform: PlatformName
    limit: int
    offset: int
    items: list[PlatformUserRecord]


class PlatformUserCreateRequest(BaseModel):
    username: str | None = None
    display_name: str | None = None
    email: str | None = None
    password: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class PlatformUserPatchRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    password: str | None = None
    is_active: bool | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

