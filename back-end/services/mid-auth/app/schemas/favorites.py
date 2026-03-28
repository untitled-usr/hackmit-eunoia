"""VoceChat favorite archives (platform DTOs; downstream paths not exposed)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateFavoriteBody(BaseModel):
    """Maps to VoceChat ``CreateFavoriteRequest.mid_list``."""

    message_ids: list[int] = Field(..., min_length=1)


class FavoriteArchiveOut(BaseModel):
    id: str
    created_at: int


class FavoriteListResponse(BaseModel):
    items: list[FavoriteArchiveOut]
