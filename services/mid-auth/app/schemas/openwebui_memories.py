"""Platform Open WebUI memories BFF — ``/me/ai/workbench/memories`` (JSON only)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemoryItemOut(BaseModel):
    """One user memory row (no downstream ``user_id``)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    body: str = Field(..., description="Memory text.")
    updated_at: datetime
    created_at: datetime


class MemoriesListResponse(BaseModel):
    items: list[MemoryItemOut]


class MemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str


class MemoryQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str
    limit: int | None = Field(
        default=None,
        ge=1,
        description="Max hits (maps downstream). Default left to upstream when omitted.",
    )


class MemoryQueryHitOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    body: str
    score: float | None = Field(
        default=None,
        description="Similarity-related score from vector search when present.",
    )


class MemoryQueryResponse(BaseModel):
    items: list[MemoryQueryHitOut]


class MemoryResetResponse(BaseModel):
    ok: bool


class MemoryUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str
