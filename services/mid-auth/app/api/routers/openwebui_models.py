"""Current-user Open WebUI models (read-only); primary paths ``/me/ai/workbench/models*``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.openwebui_client_dep import OpenWebUIClientDep
from app.api.routers.ai_workbench_dual import register_workbench_route
from app.db.session import get_db
from app.models.users import User
from app.services.openwebui_models_service import (
    OpenWebUIModelsServiceError,
    get_base_models,
    get_default_model_metadata,
    get_model_detail,
    get_model_tags,
    list_workspace_models,
)

router = APIRouter()


def _handle(exc: OpenWebUIModelsServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def list_my_openwebui_models(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    query: str | None = None,
    view_option: str | None = None,
    tag: str | None = None,
    order_by: str | None = None,
    direction: str | None = None,
    page: int | None = Query(default=None, ge=1),
) -> dict[str, Any]:
    try:
        return list_workspace_models(
            db,
            current_user,
            ow,
            query=query,
            view_option=view_option,
            tag=tag,
            order_by=order_by,
            direction=direction,
            page=page,
        )
    except OpenWebUIModelsServiceError as exc:
        _handle(exc)


def list_my_openwebui_base_models(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    try:
        return get_base_models(db, current_user, ow)
    except OpenWebUIModelsServiceError as exc:
        _handle(exc)


def list_my_openwebui_model_tags(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[str]:
    try:
        return get_model_tags(db, current_user, ow)
    except OpenWebUIModelsServiceError as exc:
        _handle(exc)


def get_my_openwebui_model_detail(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    model_id: str = Query(..., min_length=1),
) -> dict[str, Any]:
    try:
        return get_model_detail(db, current_user, ow, model_id)
    except OpenWebUIModelsServiceError as exc:
        _handle(exc)


def get_my_openwebui_default_model(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return get_default_model_metadata(db, current_user, ow)
    except OpenWebUIModelsServiceError as exc:
        _handle(exc)


register_workbench_route(
    router,
    "/models",
    list_my_openwebui_models,
    methods=["GET"],
    operation_id="me_ai_workbench_openwebui_models_list",
)
register_workbench_route(
    router,
    "/models/base",
    list_my_openwebui_base_models,
    methods=["GET"],
    operation_id="me_ai_workbench_openwebui_models_base",
)
register_workbench_route(
    router,
    "/models/tags",
    list_my_openwebui_model_tags,
    methods=["GET"],
    operation_id="me_ai_workbench_openwebui_models_tags",
)
register_workbench_route(
    router,
    "/models/detail",
    get_my_openwebui_model_detail,
    methods=["GET"],
    operation_id="me_ai_workbench_openwebui_models_detail",
)
register_workbench_route(
    router,
    "/models/default",
    get_my_openwebui_default_model,
    methods=["GET"],
    operation_id="me_ai_workbench_openwebui_models_default",
)
