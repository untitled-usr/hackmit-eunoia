from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.memos_client_dep import MemosClientDep
from app.db.session import get_db
from app.models.users import User
from app.schemas.diary import (
    DiaryEntriesReorderRequest,
    DiaryEntryCreateRequest,
    DiaryEntryListResponse,
    DiaryEntryOut,
    DiaryEntryPatchRequest,
)
from app.services.diary_service import DiaryServiceError, diary_service

router = APIRouter()


def _handle(exc: DiaryServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/me/diary/entries", response_model=DiaryEntryListResponse)
def list_entries(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiaryEntryListResponse:
    try:
        return diary_service.list_entries(db, current_user, memos)
    except DiaryServiceError as exc:
        _handle(exc)


@router.post("/me/diary/entries", response_model=DiaryEntryOut, status_code=201)
def create_entry(
    payload: DiaryEntryCreateRequest,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiaryEntryOut:
    try:
        return diary_service.create_entry(db, current_user, memos, payload)
    except DiaryServiceError as exc:
        _handle(exc)


@router.patch("/me/diary/entries/{entry_id}", response_model=DiaryEntryOut)
def patch_entry(
    entry_id: str,
    payload: DiaryEntryPatchRequest,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiaryEntryOut:
    try:
        return diary_service.patch_entry(db, current_user, memos, entry_id, payload)
    except DiaryServiceError as exc:
        _handle(exc)


@router.patch("/me/diary/entries/reorder", response_model=DiaryEntryListResponse)
def reorder_entries(
    payload: DiaryEntriesReorderRequest,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiaryEntryListResponse:
    try:
        return diary_service.reorder_entries(db, current_user, memos, payload)
    except DiaryServiceError as exc:
        _handle(exc)

