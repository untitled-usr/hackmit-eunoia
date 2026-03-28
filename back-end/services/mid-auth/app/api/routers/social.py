"""Platform social API: friend requests, friends, blacklist (VoceChat-backed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.vocechat_client_dep import VoceChatClientDep
from app.db.session import get_db
from app.models.users import User
from app.schemas.social import (
    BlacklistListResponse,
    ContactActionPayload,
    CreateFriendRequestPayload,
    FriendRequestCreatedResponse,
    FriendRequestListResponse,
    FriendRequestRecordsListResponse,
    PatchContactRemarkPayload,
    SocialContactListResponse,
    SocialContactOut,
)
from app.services.chat_service import ChatServiceError
from app.services.social_service import social_service

router = APIRouter()


def _handle(exc: ChatServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


class BlacklistAddPayload(BaseModel):
    target_public_id: str = Field(..., min_length=1)


@router.post(
    "/me/social/friend-requests",
    response_model=FriendRequestCreatedResponse,
    status_code=201,
)
def create_friend_request(
    payload: CreateFriendRequestPayload,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FriendRequestCreatedResponse:
    try:
        return social_service.create_friend_request(
            db, current_user, vc, payload
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.get(
    "/me/social/friend-requests/incoming",
    response_model=FriendRequestListResponse,
)
def list_incoming_friend_requests(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FriendRequestListResponse:
    try:
        return social_service.list_incoming_friend_requests(db, current_user, vc)
    except ChatServiceError as exc:
        _handle(exc)


@router.get(
    "/me/social/friend-requests/outgoing",
    response_model=FriendRequestListResponse,
)
def list_outgoing_friend_requests(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FriendRequestListResponse:
    try:
        return social_service.list_outgoing_friend_requests(db, current_user, vc)
    except ChatServiceError as exc:
        _handle(exc)


@router.get(
    "/me/social/friend-requests/records",
    response_model=FriendRequestRecordsListResponse,
)
def list_friend_request_records(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FriendRequestRecordsListResponse:
    try:
        return social_service.list_friend_request_records(db, current_user, vc)
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/social/friend-requests/{request_id}/accept", status_code=204)
def accept_friend_request(
    request_id: int,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        social_service.accept_friend_request(db, current_user, vc, request_id)
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/social/friend-requests/{request_id}/reject", status_code=204)
def reject_friend_request(
    request_id: int,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        social_service.reject_friend_request(db, current_user, vc, request_id)
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/social/friend-requests/{request_id}/cancel", status_code=204)
def cancel_friend_request(
    request_id: int,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        social_service.cancel_friend_request(db, current_user, vc, request_id)
    except ChatServiceError as exc:
        _handle(exc)


@router.delete("/me/social/friend-requests/{request_id}", status_code=204)
def delete_friend_request_record(
    request_id: int,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        social_service.delete_friend_request_record(
            db, current_user, vc, request_id
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/social/contacts/actions", status_code=204)
def contact_action(
    payload: ContactActionPayload,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        social_service.apply_contact_action(db, current_user, vc, payload)
    except ChatServiceError as exc:
        _handle(exc)


@router.get(
    "/me/social/contacts",
    response_model=SocialContactListResponse,
)
def list_social_contacts(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SocialContactListResponse:
    try:
        return social_service.list_social_contacts(db, current_user, vc)
    except ChatServiceError as exc:
        _handle(exc)


@router.get(
    "/me/social/contacts/{target_public_id}",
    response_model=SocialContactOut,
)
def get_social_contact(
    target_public_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SocialContactOut:
    try:
        return social_service.get_social_contact(
            db, current_user, vc, target_public_id
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.patch(
    "/me/social/contacts/{target_public_id}",
    response_model=SocialContactOut,
)
def patch_social_contact_remark(
    target_public_id: str,
    payload: PatchContactRemarkPayload,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SocialContactOut:
    try:
        return social_service.patch_contact_remark(
            db, current_user, vc, target_public_id, payload.remark
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.delete("/me/social/friends/{target_public_id}", status_code=204)
def remove_friend(
    target_public_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        social_service.remove_friend(db, current_user, vc, target_public_id)
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/social/blacklist", response_model=BlacklistListResponse)
def list_blacklist(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BlacklistListResponse:
    try:
        return social_service.list_blacklist(db, current_user, vc)
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/social/blacklist", status_code=204)
def add_blacklist(
    payload: BlacklistAddPayload,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        social_service.add_blacklist(
            db, current_user, vc, payload.target_public_id
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.delete("/me/social/blacklist/{target_public_id}", status_code=204)
def remove_blacklist(
    target_public_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        social_service.remove_blacklist(db, current_user, vc, target_public_id)
    except ChatServiceError as exc:
        _handle(exc)
