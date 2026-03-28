"""Schemas for VoceChat resource APIs used by ``chat_service``."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateMessageArchiveBody(BaseModel):
    """Platform body for ``POST /resource/archive`` (VoceChat ``CreateArchiveMsgRequest``)."""

    mid_list: list[int] = Field(
        default_factory=list,
        description="VoceChat message ids (``mid``) to include in the archive.",
    )


class MessageArchivePathOut(BaseModel):
    """Opaque VoceChat archive path returned after create-archive."""

    file_path: str = Field(..., min_length=1)
