"""Current-user posts API (Memos-backed; Memos paths not exposed).

These routes are **my posts** only: list is scoped with ``creator_id ==`` the
mapped Memos user, not a public or social feed. See ``app.services.posts_service``
module docstring for id semantics, visibility, and permission assumptions.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.memos_client_dep import MemosClientDep
from app.db.session import get_db
from app.models.users import User
from app.schemas.posts import (
    PostCreateRequest,
    PostListResponse,
    PostOut,
    PostReactionListResponse,
    PostReactionOut,
    PostUpdateRequest,
)
from app.services.posts_service import PostsServiceError, posts_service

router = APIRouter()


def _handle(exc: PostsServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/me/posts", response_model=PostOut, status_code=201)
def create_post(
    payload: PostCreateRequest,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PostOut:
    try:
        return posts_service.create_post(db, current_user, memos, payload.body)
    except PostsServiceError as exc:
        _handle(exc)


@router.get("/me/posts", response_model=PostListResponse)
def list_my_posts(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page_size: int | None = Query(None, ge=1, le=100),
    page_token: str | None = Query(None),
    filter_expr: str | None = Query(None, alias="filter"),
    creator_public_id: str | None = Query(None),
) -> PostListResponse:
    try:
        return posts_service.list_posts(
            db,
            current_user,
            memos,
            page_size=(20 if page_size is None else page_size),
            page_token=page_token,
            filter_expr=filter_expr,
            creator_public_id=creator_public_id,
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.patch("/me/posts/{post_id}/memo", response_model=PostOut)
def patch_my_post_memo(
    post_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    update_mask: str = Query(
        ...,
        alias="updateMask",
        description="Memos field mask, e.g. content,visibility,pinned",
    ),
    body: dict[str, Any] = Body(...),
) -> PostOut:
    try:
        return posts_service.patch_post_memo_raw(
            db,
            current_user,
            memos,
            post_id,
            update_mask=update_mask,
            body=body,
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.get("/me/posts/{post_id}/attachments")
def list_my_post_attachments(
    post_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page_size: int | None = Query(None, ge=1, le=1000, alias="pageSize"),
    page_token: str | None = Query(None, alias="pageToken"),
) -> dict[str, Any]:
    try:
        return posts_service.list_post_memo_attachments(
            db,
            current_user,
            memos,
            post_id,
            page_size=page_size,
            page_token=page_token,
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.patch("/me/posts/{post_id}/attachments", status_code=204)
def set_my_post_attachments(
    post_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
) -> None:
    try:
        posts_service.set_post_memo_attachments(
            db, current_user, memos, post_id, body=body
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.get("/me/posts/{post_id}/relations")
def list_my_post_relations(
    post_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page_size: int | None = Query(None, ge=1, le=1000, alias="pageSize"),
    page_token: str | None = Query(None, alias="pageToken"),
) -> dict[str, Any]:
    try:
        return posts_service.list_post_memo_relations(
            db,
            current_user,
            memos,
            post_id,
            page_size=page_size,
            page_token=page_token,
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.patch("/me/posts/{post_id}/relations", status_code=204)
def set_my_post_relations(
    post_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
) -> None:
    try:
        posts_service.set_post_memo_relations(
            db, current_user, memos, post_id, body=body
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.post("/me/posts/{post_id}/comments")
def create_my_post_comment(
    post_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    try:
        return posts_service.create_post_memo_comment(
            db, current_user, memos, post_id, body=body
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.get("/me/posts/{post_id}/comments")
def list_my_post_comments(
    post_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page_size: int | None = Query(None, ge=1, le=1000, alias="pageSize"),
    page_token: str | None = Query(None, alias="pageToken"),
    order_by: str | None = Query(None, alias="orderBy"),
) -> dict[str, Any]:
    try:
        return posts_service.list_post_memo_comments(
            db,
            current_user,
            memos,
            post_id,
            page_size=page_size,
            page_token=page_token,
            order_by=order_by,
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.get("/me/posts/{post_id}/reactions", response_model=PostReactionListResponse)
def list_my_post_reactions(
    post_id: Annotated[
        str,
        Path(
            min_length=1,
            description="Memos memo id for this post (no slashes).",
        ),
    ],
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page_size: int | None = Query(None, ge=1, le=1000, alias="pageSize"),
    page_token: str | None = Query(None, alias="pageToken"),
) -> PostReactionListResponse:
    try:
        return posts_service.list_post_memo_reactions(
            db,
            current_user,
            memos,
            post_id,
            page_size=page_size,
            page_token=page_token,
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.post("/me/posts/{post_id}/reactions", response_model=PostReactionOut)
def upsert_my_post_reaction(
    post_id: Annotated[
        str,
        Path(
            min_length=1,
            description="Memos memo id for this post (no slashes).",
        ),
    ],
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
) -> PostReactionOut:
    try:
        return posts_service.upsert_post_memo_reaction(
            db, current_user, memos, post_id, body=body
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.delete("/me/posts/{post_id}/reactions/{reaction_id}", status_code=204)
def delete_my_post_reaction(
    post_id: Annotated[
        str,
        Path(
            min_length=1,
            description="Memos memo id for this post (no slashes).",
        ),
    ],
    reaction_id: Annotated[
        str,
        Path(
            min_length=1,
            description="Memos reaction resource tail segment (no slashes).",
        ),
    ],
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        posts_service.delete_post_memo_reaction(
            db, current_user, memos, post_id, reaction_id
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.get("/me/posts/{post_id}", response_model=PostOut)
def get_my_post(
    post_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PostOut:
    try:
        return posts_service.get_post(db, current_user, memos, post_id)
    except PostsServiceError as exc:
        _handle(exc)


@router.patch("/me/posts/{post_id}", response_model=PostOut)
def update_my_post(
    post_id: str,
    payload: PostUpdateRequest,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PostOut:
    try:
        return posts_service.update_post(
            db, current_user, memos, post_id, payload.body
        )
    except PostsServiceError as exc:
        _handle(exc)


@router.delete("/me/posts/{post_id}", status_code=204)
def delete_my_post(
    post_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    try:
        posts_service.delete_post(db, current_user, memos, post_id)
    except PostsServiceError as exc:
        _handle(exc)
