"""Platform preference DTOs (VoceChat-backed); paths and IDs stay platform-native."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MuteRequestUserAdd(BaseModel):
    """Maps to VoceChat ``MuteRequestUser`` (``uid`` + optional ``expired_in``)."""

    target_public_id: str = Field(..., min_length=1)
    expired_in: int | None = Field(
        None,
        ge=0,
        le=4_294_967_295,
        description="Mute duration in seconds (VoceChat uint32).",
    )


class MuteRequestGroupAdd(BaseModel):
    """Maps to VoceChat ``MuteRequestGroup`` (``gid`` + optional ``expired_in``)."""

    group_id: str = Field(..., min_length=1)
    expired_in: int | None = Field(
        None,
        ge=0,
        le=4_294_967_295,
        description="Mute duration in seconds (VoceChat uint32).",
    )


class MuteRequest(BaseModel):
    """Aligns with VoceChat ``MuteRequest``; user/group removals use platform IDs."""

    add_users: list[MuteRequestUserAdd] = Field(default_factory=list)
    add_groups: list[MuteRequestGroupAdd] = Field(default_factory=list)
    remove_users: list[str] = Field(
        default_factory=list,
        description="VoceChat ``remove_users`` as peer public_ids (not raw uids).",
    )
    remove_groups: list[str] = Field(
        default_factory=list,
        description="VoceChat ``remove_groups`` as platform group_id strings (not raw gids).",
    )


class UpdateBurnAfterReadingRequestUser(BaseModel):
    """Per-peer DM burn-after-reading (VoceChat ``expires_in`` seconds; ``0`` clears)."""

    model_config = ConfigDict(extra="forbid")

    target_public_id: str = Field(
        ...,
        min_length=1,
        description="Other user's ``users.public_id``.",
    )
    expires_in: int = Field(
        ...,
        ge=0,
        description="TTL in seconds for messages to that peer; ``0`` removes the setting.",
    )


class UpdateBurnAfterReadingRequestGroup(BaseModel):
    """Per-group burn-after-reading."""

    model_config = ConfigDict(extra="forbid")

    group_id: str = Field(
        ...,
        min_length=1,
        description="VoceChat group id as decimal string (same as ``GET /me/groups``).",
    )
    expires_in: int = Field(
        ...,
        ge=0,
        description="TTL in seconds for messages in that group; ``0`` removes the setting.",
    )


class UpdateBurnAfterReadingRequest(BaseModel):
    """Maps to VoceChat ``UpdateBurnAfterReadingRequest`` after id resolution."""

    model_config = ConfigDict(extra="forbid")

    users: list[UpdateBurnAfterReadingRequestUser] = Field(default_factory=list)
    groups: list[UpdateBurnAfterReadingRequestGroup] = Field(default_factory=list)
