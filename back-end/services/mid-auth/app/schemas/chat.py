"""Platform chat (VoceChat-backed) — module-06, 1:1 DM only."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self


class ConversationOut(BaseModel):
    """
    One row in ``GET /me/conversations``.

    **v1 source:** VoceChat ``GET /user/contacts``. This is an approximation of
    “who I can DM / my contact graph”, **not** a strict “all historical inbox
    threads” index. Threads may exist that are not listed here, and listed rows
    may not imply recent message activity.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(
        ...,
        description=(
            "v1: equals the peer's VoceChat user id (string). "
            "Not a platform-owned conversation id."
        ),
    )
    type: Literal["direct"] = Field(
        default="direct",
        description="v1 supports only 1:1 direct messages.",
    )
    peer_display_name: str | None = Field(
        default=None,
        description=(
            "Display label from the platform ``users`` row for the peer (when mapped); "
            "otherwise null. Not sourced from VoceChat contact names."
        ),
    )
    peer_public_id: str | None = Field(
        default=None,
        description=(
            "Peer platform ``users.public_id`` resolved from VoceChat uid mapping when available."
        ),
    )


class ConversationListResponse(BaseModel):
    items: list[ConversationOut]


class StartDirectConversationRequest(BaseModel):
    """module-09: first DM to a peer identified by platform ``public_id``."""

    model_config = ConfigDict(extra="forbid")

    target_public_id: str = Field(
        ...,
        min_length=1,
        description="Target user's ``users.public_id`` (see ``/auth/me``).",
    )
    body: str


class StartDirectConversationResponse(BaseModel):
    """VoceChat DM started; ``conversation.id`` is the peer VoceChat uid string."""

    conversation: ConversationOut
    message: MessageOut


class ChatMessageCreateRequest(BaseModel):
    """Plain text in JSON for ``POST .../messages`` with ``Content-Type: application/json``.

    For **DM file attachments**, use the same URL with ``multipart/form-data`` and a
    single part named ``file`` (binary). The platform uploads bytes to VoceChat storage
    then sends ``vocechat/file`` metadata server-side (clients never send VoceChat paths).

    Empty-after-strip text is rejected in service (400).
    """

    body: str


class LastMessageReadRequest(BaseModel):
    """Advance the caller's read cursor for a DM or group (VoceChat ``mid``)."""

    model_config = ConfigDict(extra="forbid")

    last_message_id: int = Field(
        ...,
        ge=0,
        description=(
            "Latest VoceChat message id the user has read in this thread. "
            "There is no platform GET for this cursor; it is stored in VoceChat only."
        ),
    )


class ChatEventsSubscribeParams(BaseModel):
    """Query string for ``GET /me/im/events`` (forwarded to VoceChat SSE semantics)."""

    model_config = ConfigDict(extra="forbid")

    after_mid: int | None = Field(
        default=None,
        description="Opaque VoceChat replay cursor (``after_mid`` query on the downstream stream).",
    )
    users_version: int | None = Field(
        default=None,
        description="Optional VoceChat friend-list version hint (``users_version``).",
    )


class MessageAttachmentOut(BaseModel):
    """File metadata for a DM attachment."""

    model_config = ConfigDict(from_attributes=True)

    filename: str | None = None
    content_type: str
    size: int = Field(ge=0, description="Byte length of the uploaded object.")
    file_path: str | None = Field(
        default=None,
        description=(
            "VoceChat storage path for the attachment. "
            "Can be used with /me/im/resources/file for preview/download."
        ),
    )


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="VoceChat message id in v1.")
    body: str = Field(
        ...,
        description=(
            "Plain text for ``kind=text``. For ``kind=file``, often the original "
            "filename when known, otherwise empty."
        ),
    )
    sender_id: str = Field(
        ...,
        description="VoceChat uid of the sender as decimal string.",
    )
    created_at: datetime
    kind: Literal["text", "file"] = Field(
        default="text",
        description="``file`` when the message is a VoceChat file attachment.",
    )
    attachment: MessageAttachmentOut | None = Field(
        default=None,
        description="Present when ``kind=file`` (and in history when VoceChat exposes file properties).",
    )


class MessageListResponse(BaseModel):
    items: list[MessageOut]


class MessageLikeRequest(BaseModel):
    """Body for ``PUT .../messages/{message_id}/like`` (VoceChat ``LikeMessageRequest``)."""

    model_config = ConfigDict(extra="forbid")

    action: str = Field(
        ...,
        min_length=1,
        description="Opaque string forwarded to VoceChat (e.g. like / unlike semantics).",
    )


class ChatMessageOperationResponse(BaseModel):
    """VoceChat returns an int64 ``mid`` for edit / like / delete / reply; exposed as string."""

    model_config = ConfigDict(from_attributes=True)

    message_id: str = Field(
        ...,
        description="VoceChat message id returned by the downstream operation.",
    )


class PinUnpinChatRequest(BaseModel):
    """Pin or unpin a 1:1 chat: set exactly one identifier (maps to VoceChat ``target.uid``)."""

    model_config = ConfigDict(extra="forbid")

    conversation_id: str | None = Field(
        default=None,
        description=(
            "v1: peer VoceChat user id as decimal string (same as ``ConversationOut.id`` and as the "
            "path parameter ``conversation_id`` on ``/me/conversations/{conversation_id}/…``). "
            "Not a platform-owned conversation or thread id."
        ),
    )
    target_public_id: str | None = Field(
        default=None,
        description="Peer platform ``users.public_id``; resolved to VoceChat uid.",
    )

    @model_validator(mode="after")
    def exactly_one_target(self) -> Self:
        c = (self.conversation_id or "").strip() or None
        t = (self.target_public_id or "").strip() or None
        if (c is None) == (t is None):
            raise ValueError(
                "exactly one of conversation_id or target_public_id must be set"
            )
        self.conversation_id = c
        self.target_public_id = t
        return self


class ChatSessionInvalidateRequest(BaseModel):
    """Optional JSON body for ``POST /me/im/session/invalidate`` (v1: no fields).

    Downstream: VoceChat ``POST /user/logout``. Invalidates the acting-uid device /
    session used for chat APIs and SSE, not the platform login cookie.
    """

    model_config = ConfigDict(extra="forbid")


class VocechatAccountDeleteRequest(BaseModel):
    """Body for ``POST /me/im/link/delete``.

    Typed confirmation only. Downstream: VoceChat ``DELETE /user/delete``;
    on success the platform removes the ``vocechat`` row in ``user_app_mappings``.
    """

    model_config = ConfigDict(extra="forbid")

    confirm: Literal["delete"] = Field(
        ...,
        description='Must be the literal string "delete".',
    )
