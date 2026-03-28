"""Platform group chat DTOs (VoceChat ``gid`` as string ``group_id``)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    is_public: bool = False
    initial_member_public_ids: list[str] = Field(default_factory=list)


class GroupOut(BaseModel):
    group_id: str
    name: str
    description: str | None = None
    owner_voce_uid: str | None = None
    is_public: bool = False
    member_voce_uids: list[str] = Field(default_factory=list)


class GroupListResponse(BaseModel):
    items: list[GroupOut]


class GroupCreateResponse(BaseModel):
    group_id: str
    created_at: int


class GroupMembersAddRequest(BaseModel):
    target_public_ids: list[str] = Field(..., min_length=1)


class GroupPinMessageRequest(BaseModel):
    """Pin or unpin a group message (VoceChat ``mid`` in the request body)."""

    model_config = ConfigDict(extra="forbid")

    message_id: int = Field(..., gt=0, description="VoceChat message id to pin or unpin.")


class GroupUpdateRequest(BaseModel):
    """Maps to VoceChat ``UpdateGroupRequest`` (``owner`` resolved from ``owner_public_id``)."""

    name: str | None = None
    description: str | None = None
    owner_public_id: str | None = None


class ChangeGroupTypeRequest(BaseModel):
    """Public ↔ private group type change (VoceChat ``members`` when converting to private)."""

    is_public: bool
    member_public_ids: list[str] = Field(default_factory=list)


class GroupRealtimeTokenResponse(BaseModel):
    """Credentials to join the group realtime (RTC) channel."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(
        ...,
        description="Short-lived token string for the realtime SDK (e.g. Agora RTC).",
    )
    app_id: str = Field(..., description="Vendor app identifier for the realtime SDK.")
    client_uid: int = Field(
        ...,
        ge=0,
        description="Numeric user id to pass to the realtime SDK for this session.",
    )
    channel_name: str = Field(..., description="Channel id/name for the group call.")
    expires_in_seconds: int = Field(
        ...,
        ge=0,
        description="Time until the token becomes invalid, in seconds.",
    )
