"""Platform AI chat (OpenWebUI-backed) — module-07."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AiChatTitlePatchRequest(BaseModel):
    """module-08: rename AI chat (title only)."""

    model_config = ConfigDict(extra="forbid")

    title: str


class AiChatSummary(BaseModel):
    """One row in ``GET /me/ai/chats``."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(
        ...,
        description="v1: OpenWebUI chat id (string), not a separate platform id.",
    )
    title: str
    updated_at: datetime
    created_at: datetime


class AiChatsListResponse(BaseModel):
    items: list[AiChatSummary]


class AiMessageOut(BaseModel):
    """Minimal assistant/user line for API consumers."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(
        ...,
        description=(
            "OpenWebUI message id (string) in this version, not a separate platform message id."
        ),
    )
    role: str = Field(..., description="user or assistant in v1.")
    body: str
    reasoning: str | None = None
    created_at: datetime


class AiChatMessagesResponse(BaseModel):
    items: list[AiMessageOut]


class AiChatCreateRequest(BaseModel):
    """
    Create an empty AI chat, or with ``body`` to create and run the first turn.

    ``model`` overrides ``MID_AUTH_OPENWEBUI_DEFAULT_MODEL_ID`` for this request.
    """

    body: str | None = None
    model: str | None = None
    stream: bool = False


class AiChatCreateEmptyResponse(BaseModel):
    chat: AiChatSummary


class AiChatCreateWithMessageResponse(BaseModel):
    chat: AiChatSummary
    assistant_message: AiMessageOut


class AiChatMessageCreateRequest(BaseModel):
    body: str
    model: str | None = None
    stream: bool = False
