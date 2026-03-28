"""Platform social API DTOs (VoceChat-backed; no downstream paths exposed)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ContactAction = Literal["add", "remove", "block", "unblock"]


class SocialTargetIdentifierPayload(BaseModel):
    """Accept a target user identifier in username/email/public_id form.

    Backward-compatible: ``target_public_id`` is still accepted and treated as
    the identifier when ``target_identifier`` is missing.
    """

    target_identifier: str | None = Field(
        default=None,
        min_length=1,
        description="Target identifier: username, email, or public_id.",
    )
    target_public_id: str | None = Field(
        default=None,
        min_length=1,
        description="Deprecated alias; kept for backward compatibility.",
    )

    def resolved_target_identifier(self) -> str:
        raw = self.target_identifier or self.target_public_id or ""
        return raw.strip()


class ContactActionPayload(BaseModel):
    target_identifier: str | None = Field(
        default=None,
        min_length=1,
        description="Target identifier: username, email, or public_id.",
    )
    target_public_id: str | None = Field(
        default=None,
        min_length=1,
        description="Deprecated alias; kept for backward compatibility.",
    )
    action: ContactAction

    def resolved_target_identifier(self) -> str:
        raw = self.target_identifier or self.target_public_id or ""
        return raw.strip()


class CreateFriendRequestPayload(SocialTargetIdentifierPayload):
    message: str = ""


class FriendRequestCreatedResponse(BaseModel):
    request_id: str


class SocialUserIdentityOut(BaseModel):
    public_id: str
    username: str
    email: str
    display_name: str


class FriendRequestItemOut(BaseModel):
    id: str
    requester: SocialUserIdentityOut | None = None
    receiver: SocialUserIdentityOut | None = None
    requester_voce_uid: str | None = None
    receiver_voce_uid: str | None = None
    message: str
    status: str
    created_at: str


class FriendRequestListResponse(BaseModel):
    items: list[FriendRequestItemOut]


class FriendRequestRecordItemOut(BaseModel):
    id: str
    requester: SocialUserIdentityOut | None = None
    receiver: SocialUserIdentityOut | None = None
    requester_voce_uid: str | None = None
    receiver_voce_uid: str | None = None
    message: str
    status: str
    created_at: str
    responded_at: str
    can_delete: bool


class FriendRequestRecordsListResponse(BaseModel):
    items: list[FriendRequestRecordItemOut]


class BlacklistUserOut(BaseModel):
    voce_uid: str
    name: str
    target_public_id: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None


class BlacklistListResponse(BaseModel):
    items: list[BlacklistUserOut]


class ContactInfoOut(BaseModel):
    """Mirrors VoceChat ``contact_info`` (plus optional ``remark`` when server supports it)."""

    status: str
    created_at: int
    updated_at: int
    removed_by_peer: bool = False
    remark: str = ""


class SocialContactOut(BaseModel):
    """Platform contact row: ``target_public_id`` replaces downstream uid in API surface."""

    target_public_id: str
    conversation_id: str
    display_name: str
    avatar_url: str | None = None
    contact_info: ContactInfoOut


class SocialContactListResponse(BaseModel):
    items: list[SocialContactOut]


class PatchContactRemarkPayload(BaseModel):
    remark: str = Field(default="", max_length=512)
