"""Current user's Memos account-level BFF (platform paths: /me/library/*).

``/me/library/*``: stats, global attachments, shortcuts, settings, webhooks, and
notifications for the mapped Memos user (via ``X-Acting-Uid``).

Content memos (posts) live under ``/me/posts*`` — separate from this account-level surface.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.memos_client_dep import MemosClientDep
from app.db.session import get_db
from app.integrations.memos_client import MemosClientError
from app.models.users import User
from app.schemas.memos_instance import MemosInstanceSettingOut
from app.services.memos_common import memos_client_http_tuple
from app.services.posts_service import PostsServiceError, posts_service

router = APIRouter()


def _hx(exc: MemosClientError) -> None:
    code, detail = memos_client_http_tuple(exc)
    raise HTTPException(status_code=code, detail=detail)


def _uid_seg(db: Session, user: User) -> tuple[str, str]:
    try:
        return posts_service.memos_acting_and_user_segment(db, user)
    except PostsServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code, detail=exc.detail
        ) from exc


def library_stats(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.get_user_stats(seg, acting_uid=acting)
    except MemosClientError as exc:
        _hx(exc)


def library_list_attachments(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page_size: int | None = Query(None, ge=1, le=1000, alias="pageSize"),
    page_token: str | None = Query(None, alias="pageToken"),
    filter_expr: str | None = Query(None, alias="filter"),
    order_by: str | None = Query(None, alias="orderBy"),
) -> dict[str, Any]:
    acting, _seg = _uid_seg(db, current_user)
    try:
        return memos.list_attachments(
            acting,
            page_size=page_size,
            page_token=page_token,
            filter_expr=filter_expr,
            order_by=order_by,
        )
    except MemosClientError as exc:
        _hx(exc)


def library_create_attachment(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
    attachment_id: str | None = Query(None, alias="attachmentId"),
) -> dict[str, Any]:
    acting, _seg = _uid_seg(db, current_user)
    try:
        return memos.create_attachment(
            acting, body=body, attachment_id=attachment_id
        )
    except MemosClientError as exc:
        _hx(exc)


def library_get_attachment(
    attachment_ref: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    acting, _seg = _uid_seg(db, current_user)
    try:
        return memos.get_attachment(attachment_ref, acting_uid=acting)
    except MemosClientError as exc:
        _hx(exc)


def library_patch_attachment(
    attachment_ref: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    update_mask: str = Query(..., alias="updateMask"),
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    acting, _seg = _uid_seg(db, current_user)
    try:
        return memos.update_attachment(
            attachment_ref,
            acting_uid=acting,
            update_mask=update_mask,
            body=body,
        )
    except MemosClientError as exc:
        _hx(exc)


def library_delete_attachment(
    attachment_ref: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    acting, _seg = _uid_seg(db, current_user)
    try:
        memos.delete_attachment(attachment_ref, acting_uid=acting)
    except MemosClientError as exc:
        _hx(exc)
    return Response(status_code=204)


def library_list_shortcuts(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.list_shortcuts(seg, acting_uid=acting)
    except MemosClientError as exc:
        _hx(exc)


def library_create_shortcut(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
    validate_only: bool | None = Query(None, alias="validateOnly"),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.create_shortcut(
            seg,
            acting_uid=acting,
            body=body,
            validate_only=validate_only,
        )
    except MemosClientError as exc:
        _hx(exc)


def library_get_shortcut(
    shortcut_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.get_shortcut(seg, shortcut_id, acting_uid=acting)
    except MemosClientError as exc:
        _hx(exc)


def library_patch_shortcut(
    shortcut_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
    update_mask: str | None = Query(None, alias="updateMask"),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.update_shortcut(
            seg,
            shortcut_id,
            acting_uid=acting,
            body=body,
            update_mask=update_mask,
        )
    except MemosClientError as exc:
        _hx(exc)


def library_delete_shortcut(
    shortcut_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    acting, seg = _uid_seg(db, current_user)
    try:
        memos.delete_shortcut(seg, shortcut_id, acting_uid=acting)
    except MemosClientError as exc:
        _hx(exc)
    return Response(status_code=204)


def library_get_instance_setting(
    setting_key: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemosInstanceSettingOut:
    acting, _seg = _uid_seg(db, current_user)
    try:
        raw = memos.get_instance_dynamic_setting(
            setting_key, acting_uid=acting
        )
        return MemosInstanceSettingOut.model_validate(raw)
    except MemosClientError as exc:
        _hx(exc)


def library_patch_instance_setting(
    setting_key: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    update_mask: str = Query(
        ...,
        alias="updateMask",
        description="Comma-separated Memos field mask for the setting payload.",
    ),
    body: dict[str, Any] = Body(...),
) -> MemosInstanceSettingOut:
    acting, _seg = _uid_seg(db, current_user)
    try:
        raw = memos.patch_instance_dynamic_setting(
            setting_key,
            acting_uid=acting,
            update_mask=update_mask,
            body=body,
        )
        return MemosInstanceSettingOut.model_validate(raw)
    except MemosClientError as exc:
        _hx(exc)


def library_list_settings(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page_size: int | None = Query(None, ge=1, le=1000, alias="pageSize"),
    page_token: str | None = Query(None, alias="pageToken"),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.list_user_settings(
            seg,
            acting_uid=acting,
            page_size=page_size,
            page_token=page_token,
        )
    except MemosClientError as exc:
        _hx(exc)


def library_get_setting(
    setting_key: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.get_user_setting(seg, setting_key, acting_uid=acting)
    except MemosClientError as exc:
        _hx(exc)


def library_patch_setting(
    setting_key: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    update_mask: str = Query(..., alias="updateMask"),
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.update_user_setting(
            seg,
            setting_key,
            acting_uid=acting,
            update_mask=update_mask,
            body=body,
        )
    except MemosClientError as exc:
        _hx(exc)


def library_list_webhooks(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.list_user_webhooks(seg, acting_uid=acting)
    except MemosClientError as exc:
        _hx(exc)


def library_create_webhook(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.create_user_webhook(seg, acting_uid=acting, body=body)
    except MemosClientError as exc:
        _hx(exc)


def library_patch_webhook(
    webhook_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    update_mask: str = Query(..., alias="updateMask"),
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.update_user_webhook(
            seg,
            webhook_id,
            acting_uid=acting,
            update_mask=update_mask,
            body=body,
        )
    except MemosClientError as exc:
        _hx(exc)


def library_delete_webhook(
    webhook_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    acting, seg = _uid_seg(db, current_user)
    try:
        memos.delete_user_webhook(seg, webhook_id, acting_uid=acting)
    except MemosClientError as exc:
        _hx(exc)
    return Response(status_code=204)


def library_list_notifications(
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page_size: int | None = Query(None, ge=1, le=1000, alias="pageSize"),
    page_token: str | None = Query(None, alias="pageToken"),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.list_user_notifications(
            seg,
            acting_uid=acting,
            page_size=page_size,
            page_token=page_token,
        )
    except MemosClientError as exc:
        _hx(exc)


def library_patch_notification(
    notification_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    update_mask: str = Query(..., alias="updateMask"),
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    acting, seg = _uid_seg(db, current_user)
    try:
        return memos.update_user_notification(
            seg,
            notification_id,
            acting_uid=acting,
            update_mask=update_mask,
            body=body,
        )
    except MemosClientError as exc:
        _hx(exc)


def library_delete_notification(
    notification_id: str,
    memos: MemosClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    acting, seg = _uid_seg(db, current_user)
    try:
        memos.delete_user_notification(
            seg, notification_id, acting_uid=acting
        )
    except MemosClientError as exc:
        _hx(exc)
    return Response(status_code=204)


def _library_route(
    path: str,
    endpoint: Callable[..., Any],
    *,
    methods: list[str],
    operation_id: str,
    status_code: int | None = None,
) -> None:
    common: dict[str, Any] = {"methods": methods}
    if status_code is not None:
        common["status_code"] = status_code
    router.add_api_route(path, endpoint, operation_id=operation_id, **common)


_library_route(
    "/me/library/stats",
    library_stats,
    methods=["GET"],
    operation_id="me_library_stats",
)

_library_route(
    "/me/library/attachments",
    library_list_attachments,
    methods=["GET"],
    operation_id="me_library_list_attachments",
)
_library_route(
    "/me/library/attachments",
    library_create_attachment,
    methods=["POST"],
    operation_id="me_library_create_attachment",
)

_library_route(
    "/me/library/attachments/{attachment_ref:path}",
    library_get_attachment,
    methods=["GET"],
    operation_id="me_library_get_attachment",
)
_library_route(
    "/me/library/attachments/{attachment_ref:path}",
    library_patch_attachment,
    methods=["PATCH"],
    operation_id="me_library_patch_attachment",
)
_library_route(
    "/me/library/attachments/{attachment_ref:path}",
    library_delete_attachment,
    methods=["DELETE"],
    status_code=204,
    operation_id="me_library_delete_attachment",
)

_library_route(
    "/me/library/shortcuts",
    library_list_shortcuts,
    methods=["GET"],
    operation_id="me_library_list_shortcuts",
)
_library_route(
    "/me/library/shortcuts",
    library_create_shortcut,
    methods=["POST"],
    operation_id="me_library_create_shortcut",
)

_library_route(
    "/me/library/shortcuts/{shortcut_id}",
    library_get_shortcut,
    methods=["GET"],
    operation_id="me_library_get_shortcut",
)
_library_route(
    "/me/library/shortcuts/{shortcut_id}",
    library_patch_shortcut,
    methods=["PATCH"],
    operation_id="me_library_patch_shortcut",
)
_library_route(
    "/me/library/shortcuts/{shortcut_id}",
    library_delete_shortcut,
    methods=["DELETE"],
    status_code=204,
    operation_id="me_library_delete_shortcut",
)

_library_route(
    "/me/library/instance/settings/{setting_key:path}",
    library_get_instance_setting,
    methods=["GET"],
    operation_id="me_library_get_instance_setting",
)
_library_route(
    "/me/library/instance/settings/{setting_key:path}",
    library_patch_instance_setting,
    methods=["PATCH"],
    operation_id="me_library_patch_instance_setting",
)

_library_route(
    "/me/library/settings",
    library_list_settings,
    methods=["GET"],
    operation_id="me_library_list_settings",
)
_library_route(
    "/me/library/settings/{setting_key:path}",
    library_get_setting,
    methods=["GET"],
    operation_id="me_library_get_setting",
)
_library_route(
    "/me/library/settings/{setting_key:path}",
    library_patch_setting,
    methods=["PATCH"],
    operation_id="me_library_patch_setting",
)

_library_route(
    "/me/library/webhooks",
    library_list_webhooks,
    methods=["GET"],
    operation_id="me_library_list_webhooks",
)
_library_route(
    "/me/library/webhooks",
    library_create_webhook,
    methods=["POST"],
    operation_id="me_library_create_webhook",
)
_library_route(
    "/me/library/webhooks/{webhook_id}",
    library_patch_webhook,
    methods=["PATCH"],
    operation_id="me_library_patch_webhook",
)
_library_route(
    "/me/library/webhooks/{webhook_id}",
    library_delete_webhook,
    methods=["DELETE"],
    status_code=204,
    operation_id="me_library_delete_webhook",
)

_library_route(
    "/me/library/notifications",
    library_list_notifications,
    methods=["GET"],
    operation_id="me_library_list_notifications",
)
_library_route(
    "/me/library/notifications/{notification_id}",
    library_patch_notification,
    methods=["PATCH"],
    operation_id="me_library_patch_notification",
)
_library_route(
    "/me/library/notifications/{notification_id}",
    library_delete_notification,
    methods=["DELETE"],
    status_code=204,
    operation_id="me_library_delete_notification",
)
