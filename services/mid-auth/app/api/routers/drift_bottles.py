"""Current user's drift bottle API (Memos-backed)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.memos_client_dep import MemosClientDep
from app.db.session import get_db
from app.integrations.memos_client import MemosClientError
from app.models.users import User
from app.services.memos_common import memos_client_http_tuple
from app.services.posts_service import PostsServiceError, posts_service

router = APIRouter()


def _hx(exc: MemosClientError) -> None:
    code, detail = memos_client_http_tuple(exc)
    raise HTTPException(status_code=code, detail=detail)


def _acting_uid(db: Session, user: User) -> str:
    try:
        acting, _seg = posts_service.memos_acting_and_user_segment(db, user)
        return acting
    except PostsServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


@router.post("/me/bottles")
def create_my_drift_bottle(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    acting = _acting_uid(db, current_user)
    try:
        return memos.create_drift_bottle(acting, body=body)
    except MemosClientError as exc:
        _hx(exc)


@router.post("/me/bottles/pick")
def pick_my_drift_bottle(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    acting = _acting_uid(db, current_user)
    try:
        return memos.pick_drift_bottle(acting)
    except MemosClientError as exc:
        _hx(exc)


@router.post("/me/bottles/refresh")
def refresh_my_drift_candidates(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    acting = _acting_uid(db, current_user)
    try:
        return memos.refresh_my_drift_bottle_candidates(acting)
    except MemosClientError as exc:
        _hx(exc)


@router.get("/me/bottles/search")
def search_my_drift_bottles(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tag: str = Query(..., min_length=1, max_length=32),
    page_size: int | None = Query(None, ge=1, le=100, alias="pageSize"),
    page_token: str | None = Query(None, alias="pageToken"),
) -> dict[str, Any]:
    acting = _acting_uid(db, current_user)
    try:
        return memos.search_drift_bottles(
            acting,
            tag=tag,
            page_size=page_size,
            page_token=page_token,
        )
    except MemosClientError as exc:
        _hx(exc)


@router.get("/me/bottles/{bottle_id}")
def get_my_drift_bottle(
    bottle_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    acting = _acting_uid(db, current_user)
    try:
        return memos.get_drift_bottle(bottle_id, acting_uid=acting)
    except MemosClientError as exc:
        _hx(exc)


@router.post("/me/bottles/{bottle_id}/reply")
def reply_my_drift_bottle(
    bottle_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    acting = _acting_uid(db, current_user)
    try:
        payload = {"content": str(body.get("content", "")).strip()}
        if body.get("commentId"):
            payload["commentId"] = body["commentId"]
        return memos.reply_drift_bottle(
            acting,
            bottle_id,
            body=payload,
        )
    except MemosClientError as exc:
        _hx(exc)
