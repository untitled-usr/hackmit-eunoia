"""Platform preference API (VoceChat-backed)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.vocechat_client_dep import VoceChatClientDep
from app.db.session import get_db
from app.models.users import User
from app.schemas.preferences import MuteRequest, UpdateBurnAfterReadingRequest
from app.services.chat_service import ChatServiceError
from app.services.preferences_service import preferences_service

router = APIRouter()


def _handle(exc: ChatServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/me/preferences/mute", status_code=204)
def update_mute(
    payload: MuteRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        preferences_service.update_mute(db, current_user, vc, payload)
    except ChatServiceError as exc:
        _handle(exc)


@router.post("/me/preferences/burn-after-reading", status_code=204)
def update_burn_after_reading(
    payload: UpdateBurnAfterReadingRequest,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        preferences_service.update_burn_after_reading(
            db, current_user, vc, payload
        )
    except ChatServiceError as exc:
        _handle(exc)
