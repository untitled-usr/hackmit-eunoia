"""Validated request bodies for Open WebUI gap BFF endpoints (no raw downstream passthrough)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OpenWebuiChatsImportBody(BaseModel):
    chats: list[dict[str, Any]] = Field(..., min_length=1)


class OpenWebuiCloneChatBody(BaseModel):
    title: str | None = Field(default=None, max_length=512)


class OpenWebuiChatMessageContentBody(BaseModel):
    content: str = Field(..., min_length=0, max_length=2_000_000)


class OpenWebuiChatMessageEventBody(BaseModel):
    type: str = Field(..., min_length=1, max_length=256)
    data: dict[str, Any] = Field(default_factory=dict)


class OpenWebuiChatMoveFolderBody(BaseModel):
    folder_id: str | None = None


class OpenWebUIAuthAddUserBody(BaseModel):
    password: str | None = Field(default=None, max_length=256)
    profile_image_url: str | None = Field(default="/user.png", max_length=2048)
    role: str | None = Field(default="pending", max_length=32)
    name: str | None = Field(default=None, max_length=256)


class OpenWebUIAuthUpdateProfileBody(BaseModel):
    profile_image_url: str = Field(..., max_length=2048)
    name: str = Field(..., max_length=256)
    bio: str | None = Field(default=None, max_length=4096)
    gender: str | None = Field(default=None, max_length=64)
    date_of_birth: str | None = Field(default=None, max_length=32)


class OpenWebUIAuthUpdateTimezoneBody(BaseModel):
    timezone: str = Field(..., min_length=1, max_length=128)


class OpenWebUIFileDataContentBody(BaseModel):
    content: str = Field(..., min_length=0, max_length=2_000_000)


class OpenWebUIKnowledgeFileIdBody(BaseModel):
    file_id: str = Field(..., min_length=1, max_length=256)


class OpenWebUIModelAccessUpdateBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=256)
    name: str | None = Field(default=None, max_length=512)
    access_grants: list[dict[str, Any]] = Field(default_factory=list)
