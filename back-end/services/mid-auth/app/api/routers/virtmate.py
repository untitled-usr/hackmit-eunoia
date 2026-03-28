"""VirtMate user APIs under `/me/virtmate/*`."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps.current_user import auth_service, get_current_user
from app.api.deps.openwebui_client_dep import OpenWebUIClientDep
from app.core.settings import get_settings
from app.db.session import get_db
from app.models.users import User
from app.schemas.virtmate import (
    VirtmateChatSendRequest,
    VirtmateChatSendResponse,
    VirtmateGlobalConfigUpdateRequest,
    VirtmateProfileAssetDeleteRequest,
    VirtmateProfileMoveRequest,
    VirtmateProfileUpsertRequest,
    VirtmateSessionSettingsUpdateRequest,
    VirtmateTtsPlaybackStateRequest,
)
from app.services.auth_service import AuthServiceError
from app.services.virtmate_events import virtmate_event_bus
from app.services.virtmate_service import VirtmateServiceError, virtmate_service

router = APIRouter()
logger = logging.getLogger(__name__)


def _event_key(user: User, session_id: str) -> str:
    sid = (session_id or "default").strip() or "default"
    return f"{user.id}:{sid}"


def _handle(exc: VirtmateServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/me/virtmate/config/global")
def virtmate_global_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return virtmate_service.get_global_config(db, current_user)


@router.get("/me/virtmate/profiles")
def virtmate_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return virtmate_service.list_digital_profiles(db, current_user)


@router.post("/me/virtmate/profiles")
def virtmate_create_profile(
    payload: VirtmateProfileUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    profile = virtmate_service.create_digital_profile(
        db, current_user, payload.model_dump(exclude_none=True)
    )
    return {"ok": True, "profile": profile}


@router.patch("/me/virtmate/profiles/{profile_id}")
def virtmate_update_profile(
    profile_id: str,
    payload: VirtmateProfileUpsertRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    profile = virtmate_service.update_digital_profile(
        db, current_user, profile_id, payload.model_dump(exclude_none=True)
    )
    return {"ok": True, "profile": profile}


@router.delete("/me/virtmate/profiles/{profile_id}")
def virtmate_delete_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    virtmate_service.delete_digital_profile(db, current_user, profile_id)
    return {"ok": True}


@router.post("/me/virtmate/profiles/{profile_id}/activate")
def virtmate_activate_profile(
    profile_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    state = virtmate_service.activate_digital_profile(db, current_user, profile_id)
    return {"ok": True, **state}


@router.post("/me/virtmate/profiles/{profile_id}/move")
def virtmate_move_profile(
    profile_id: str,
    payload: VirtmateProfileMoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    state = virtmate_service.move_digital_profile(
        db, current_user, profile_id, payload.direction
    )
    return {"ok": True, **state}


@router.post("/me/virtmate/profiles/assets/ref-audio")
async def virtmate_upload_profile_ref_audio(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = db
    content = await file.read()
    url = virtmate_service.save_profile_asset(
        current_user, "audio", file.filename or "ref.wav", content
    )
    return {"ok": True, "path": url}


@router.delete("/me/virtmate/profiles/assets/ref-audio")
def virtmate_delete_profile_ref_audio(
    payload: VirtmateProfileAssetDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = db
    virtmate_service.delete_profile_asset_by_url(current_user, "audio", payload.path)
    return {"ok": True}


@router.post("/me/virtmate/profiles/assets/live2d")
async def virtmate_upload_profile_live2d(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _ = db
    content = await file.read()
    url = virtmate_service.save_profile_asset(
        current_user, "live2d", file.filename or "model.zip", content
    )
    return {"ok": True, "path": url}


@router.get("/me/virtmate/profile-assets/{kind}/{filename}")
def virtmate_profile_asset_file(
    kind: str,
    filename: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    try:
        path = virtmate_service.get_profile_asset_path(current_user, kind, filename)
    except VirtmateServiceError as exc:
        _handle(exc)
    return FileResponse(path)


@router.post("/me/virtmate/config/global")
def virtmate_update_global_config(
    payload: VirtmateGlobalConfigUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return {
        "ok": True,
        "global": virtmate_service.update_global_config(
            db, current_user, payload.model_dump(exclude_none=True)
        ),
    }


@router.get("/me/virtmate/runtime/hardware")
async def virtmate_runtime_hardware(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return await virtmate_service.runtime_hardware(db, current_user)


@router.get("/me/virtmate/session/settings")
def virtmate_session_settings(
    session_id: str = "default",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return virtmate_service.get_session_settings(db, current_user, session_id)


@router.post("/me/virtmate/session/settings")
async def virtmate_update_session_settings(
    payload: VirtmateSessionSettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    settings = virtmate_service.update_session_settings(
        db,
        current_user,
        payload.session_id,
        payload.model_dump(exclude={"session_id"}, exclude_none=True),
    )
    await virtmate_event_bus.publish(
        _event_key(current_user, payload.session_id),
        {
            "type": "session.settings",
            "session_id": payload.session_id,
            "data": {"settings": settings},
        },
    )
    return settings


@router.post("/me/virtmate/chat/send", response_model=VirtmateChatSendResponse)
async def virtmate_chat_send(
    payload: VirtmateChatSendRequest,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> VirtmateChatSendResponse:
    sid = payload.session_id
    key = _event_key(current_user, sid)
    loop = asyncio.get_running_loop()

    def on_delta(chunk: str, full_text: str) -> None:
        loop.call_soon_threadsafe(
            asyncio.create_task,
            virtmate_event_bus.publish(
                key,
                {
                    "type": "chat.delta",
                    "session_id": sid,
                    "data": {"delta": chunk, "content": full_text},
                },
            ),
        )

    await virtmate_event_bus.publish(
        key, {"type": "chat.status", "session_id": sid, "data": {"status": "thinking"}}
    )
    try:
        user_record, assistant_record, conv_id = await virtmate_service.chat_send(
            db,
            current_user,
            ow,
            session_id=sid,
            text=payload.text,
            model=(payload.model or "").strip(),
            conversation_id=payload.conversation_id,
            with_tts=payload.with_tts,
            stream=payload.stream,
            on_delta=on_delta if payload.stream else None,
        )
    except VirtmateServiceError as exc:
        await virtmate_event_bus.publish(
            key,
            {"type": "chat.error", "session_id": sid, "data": {"error": exc.detail}},
        )
        await virtmate_event_bus.publish(
            key, {"type": "chat.status", "session_id": sid, "data": {"status": "error"}}
        )
        _handle(exc)

    await virtmate_event_bus.publish(
        key, {"type": "chat.message", "session_id": sid, "data": {"message": user_record}}
    )
    await virtmate_event_bus.publish(
        key,
        {"type": "chat.message", "session_id": sid, "data": {"message": assistant_record}},
    )
    tts = assistant_record.get("tts")
    tts_audio_url = ""
    tts_error = ""
    if isinstance(tts, dict) and tts.get("audio_url"):
        tts_audio_url = str(tts.get("audio_url") or "").strip()
        await virtmate_event_bus.publish(
            key, {"type": "tts.ready", "session_id": sid, "data": tts}
        )
    elif isinstance(tts, dict):
        tts_error = str(tts.get("error") or "").strip()
    if not tts_audio_url:
        logger.warning(
            "virtmate chat without tts audio: user_id=%s session_id=%s conv_id=%s tts_error=%s tts=%s",
            current_user.id,
            sid,
            conv_id,
            tts_error or "-",
            tts if isinstance(tts, dict) else type(tts).__name__,
        )
    await virtmate_event_bus.publish(
        key, {"type": "chat.status", "session_id": sid, "data": {"status": "done"}}
    )
    return VirtmateChatSendResponse(
        ok=True,
        conversation_id=conv_id,
        message=user_record,
        assistant=assistant_record,
        tts_audio_url=tts_audio_url or None,
        tts_error=tts_error or None,
    )


@router.websocket("/me/virtmate/ws/events")
async def virtmate_ws_events(
    ws: WebSocket,
    session_id: str = "default",
    db: Session = Depends(get_db),
) -> None:
    cookie_name = get_settings().session_cookie_name
    session_cookie = ws.cookies.get(cookie_name)
    try:
        user = auth_service.get_user_by_session(db=db, session_id=session_cookie)
    except AuthServiceError:
        await ws.close(code=1008)
        return
    key = _event_key(user, session_id)
    await virtmate_event_bus.connect(key, ws)
    try:
        await ws.send_json(
            {"type": "session.connected", "session_id": session_id, "data": {"ok": True}}
        )
        while True:
            _ = await ws.receive_text()
    except WebSocketDisconnect:
        await virtmate_event_bus.disconnect(key, ws)
    except Exception:
        await virtmate_event_bus.disconnect(key, ws)


@router.post("/me/virtmate/asr/recognize")
async def virtmate_asr_recognize(
    audio: UploadFile = File(...),
    session_id: str = Form("default"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    raw = await audio.read()
    payload = await virtmate_service.asr_recognize(
        raw,
        filename=audio.filename or "voice.wav",
        content_type=audio.content_type or "application/octet-stream",
    )
    text = str(payload.get("text") or "")
    if payload.get("ok") is False:
        text = f"ASR识别失败（{payload.get('error') or 'ASR API返回异常'}）"
    await virtmate_event_bus.publish(
        _event_key(current_user, session_id),
        {"type": "asr.result", "session_id": session_id, "data": {"text": text}},
    )
    return {"text": text}


@router.post("/me/virtmate/tts/playback")
async def virtmate_tts_playback(
    payload: VirtmateTtsPlaybackStateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    state = virtmate_service.set_playback_state(
        db,
        current_user,
        payload.session_id,
        payload.is_playing,
        payload.mouth_y,
    )
    await virtmate_event_bus.publish(
        _event_key(current_user, payload.session_id),
        {
            "type": "tts.playback",
            "session_id": payload.session_id,
            "data": {"is_playing": payload.is_playing, "mouth_y": state.get("mouth_y")},
        },
    )
    return {"ok": True}


@router.get("/me/virtmate/audio/{filename}")
def virtmate_audio_file(
    filename: str,
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    _ = current_user
    return FileResponse(virtmate_service.get_audio_path(filename))


@router.get("/me/virtmate/scene/mouth_y")
def virtmate_scene_mouth_y(
    session_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, float]:
    return {"y": virtmate_service.resolve_scene_mouth_y(db, current_user, session_id)}


@router.get("/me/virtmate/get_mouth_y")
def virtmate_get_mouth_y_legacy(
    session_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, float]:
    return {"y": virtmate_service.resolve_scene_mouth_y(db, current_user, session_id)}

