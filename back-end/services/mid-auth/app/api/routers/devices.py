"""Platform device list / removal / push token (VoceChat-backed)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.vocechat_client_dep import VoceChatClientDep
from app.db.session import get_db
from app.models.users import User
from app.schemas.devices import PushTokenUpdate, UserDeviceListResponse
from app.services.chat_service import ChatServiceError
from app.services.devices_service import devices_service

router = APIRouter()


def _handle(exc: ChatServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def _push_token_payload(
    body: Annotated[PushTokenUpdate | None, Body()] = None,
    device_id: Annotated[str | None, Query(min_length=1)] = None,
    token: Annotated[str | None, Query(min_length=1)] = None,
) -> PushTokenUpdate:
    if body is not None:
        return body
    if device_id is not None and token is not None:
        return PushTokenUpdate(device_id=device_id, token=token)
    raise HTTPException(
        status_code=422,
        detail="Provide device_id and token in the JSON body or as query parameters.",
    )


@router.put("/me/devices/push-token", status_code=204)
@router.post("/me/devices/push-token", status_code=204)
def update_push_token(
    payload: Annotated[PushTokenUpdate, Depends(_push_token_payload)],
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        devices_service.update_push_token(
            db,
            current_user,
            vc,
            device_id=payload.device_id,
            token=payload.token,
        )
    except ChatServiceError as exc:
        _handle(exc)


@router.get("/me/devices", response_model=UserDeviceListResponse)
def list_my_devices(
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserDeviceListResponse:
    try:
        return devices_service.list_my_devices(db, current_user, vc)
    except ChatServiceError as exc:
        _handle(exc)


@router.delete("/me/devices/{device_id}", status_code=204)
def delete_my_device(
    device_id: str,
    vc: VoceChatClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        devices_service.delete_my_device(db, current_user, vc, device_id)
    except ChatServiceError as exc:
        _handle(exc)
