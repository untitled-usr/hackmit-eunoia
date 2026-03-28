"""Current-user Open WebUI tools; primary paths ``/me/ai/workbench/tools*``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.openwebui_client_dep import OpenWebUIClientDep
from app.api.routers.ai_workbench_dual import register_workbench_route
from app.db.session import get_db
from app.models.users import User
from app.services.openwebui_tools_service import (
    OpenWebUIToolsServiceError,
    get_openwebui_tool,
    get_openwebui_tool_valves,
    list_openwebui_tools,
    update_openwebui_tool_valves,
)

router = APIRouter()


def _handle(exc: OpenWebUIToolsServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def list_my_openwebui_tools(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    try:
        return list_openwebui_tools(db, current_user, ow)
    except OpenWebUIToolsServiceError as exc:
        _handle(exc)


def get_my_openwebui_tool(
    tool_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return get_openwebui_tool(db, current_user, ow, tool_id)
    except OpenWebUIToolsServiceError as exc:
        _handle(exc)


def get_my_openwebui_tool_valves(
    tool_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any] | None:
    try:
        return get_openwebui_tool_valves(db, current_user, ow, tool_id)
    except OpenWebUIToolsServiceError as exc:
        _handle(exc)


def patch_my_openwebui_tool_valves(
    tool_id: str,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    body: dict[str, Any] = Body(default_factory=dict),
) -> dict[str, Any] | None:
    try:
        return update_openwebui_tool_valves(db, current_user, ow, tool_id, body)
    except OpenWebUIToolsServiceError as exc:
        _handle(exc)


register_workbench_route(
    router,
    "/tools",
    list_my_openwebui_tools,
    methods=["GET"],
    response_model=list[dict[str, Any]],
    operation_id="me_ai_workbench_openwebui_tools_list",
)
register_workbench_route(
    router,
    "/tools/{tool_id}",
    get_my_openwebui_tool,
    methods=["GET"],
    response_model=dict[str, Any],
    operation_id="me_ai_workbench_openwebui_tool_get",
)
register_workbench_route(
    router,
    "/tools/{tool_id}/valves",
    get_my_openwebui_tool_valves,
    methods=["GET"],
    response_model=dict[str, Any] | None,
    operation_id="me_ai_workbench_openwebui_tool_valves_get",
)
register_workbench_route(
    router,
    "/tools/{tool_id}/valves",
    patch_my_openwebui_tool_valves,
    methods=["PATCH"],
    response_model=dict[str, Any] | None,
    operation_id="me_ai_workbench_openwebui_tool_valves_patch",
)
