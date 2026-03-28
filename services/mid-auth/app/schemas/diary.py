from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DiaryStatus = Literal["normal", "archived", "digested"]


class DiaryEntryCreateRequest(BaseModel):
    title: str = ""
    content: str = ""
    keywords: list[str] = Field(default_factory=list)
    status: DiaryStatus = "normal"
    unlock_time: datetime | None = None
    order: int | None = None


class DiaryEntryPatchRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    keywords: list[str] | None = None
    status: DiaryStatus | None = None
    unlock_time: datetime | None = None
    order: int | None = None


class DiaryEntryReorderItem(BaseModel):
    id: str
    order: int


class DiaryEntriesReorderRequest(BaseModel):
    entries: list[DiaryEntryReorderItem]


class DiaryEntryOut(BaseModel):
    id: str
    title: str
    content: str
    keywords: list[str] = Field(default_factory=list)
    status: DiaryStatus
    locked: bool
    unlock_time: datetime | None = None
    order: int
    created_at: datetime
    updated_at: datetime


class DiaryEntryListResponse(BaseModel):
    items: list[DiaryEntryOut]

