"""Platform posts (Memos-backed) request/response models.

v1: create/update accept only ``body``. New posts are created as **PRIVATE** on
the Memos side; ``visibility`` is output-only (no client-controlled field).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PostCreateRequest(BaseModel):
    """Body only. Server creates Memos content as PRIVATE; empty-after-strip → 400 in service."""

    body: str


class PostUpdateRequest(BaseModel):
    """Body only; does not change visibility (v1)."""

    body: str


class PostOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(
        ...,
        description="Memos memo UID in this version, not a separate platform post id.",
    )
    body: str
    creator_public_id: str | None = Field(
        default=None,
        description="Platform user public_id resolved from Memos creator mapping when available.",
    )
    visibility: str = Field(
        ...,
        description="Memos visibility (read-only for clients in v1; create is always private).",
    )
    created_at: datetime
    updated_at: datetime


class PostListResponse(BaseModel):
    """Paginated **current user** posts, not a public timeline."""

    items: list[PostOut]
    next_page_token: str | None = None


class PostReactionOut(BaseModel):
    """Memo reaction without exposing full Memos resource paths."""

    id: str = Field(
        ...,
        description="Opaque reaction id (Memos reactions/* tail segment only).",
    )
    reaction_type: str = Field(
        ...,
        description="Emoji or reaction key from Memos.",
    )
    created_at: datetime | None = Field(
        default=None,
        description="Creation time when provided by Memos.",
    )
    creator_public_id: str | None = Field(
        default=None,
        description="Platform public_id when the reactor maps to a platform user.",
    )


class PostReactionListResponse(BaseModel):
    items: list[PostReactionOut]
    next_page_token: str | None = None
    total_size: int | None = Field(
        default=None,
        description="Total count when Memos returns totalSize.",
    )
