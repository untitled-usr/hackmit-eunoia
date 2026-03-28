"""Current-user Open WebUI memories BFF; primary paths ``/me/ai/workbench/memories*``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps.current_user import get_current_user
from app.api.deps.openwebui_client_dep import OpenWebUIClientDep
from app.api.routers.ai_workbench_dual import register_workbench_route
from app.db.session import get_db
from app.models.users import User
from app.schemas.openwebui_memories import (
    MemoryCreateRequest,
    MemoryItemOut,
    MemoryQueryRequest,
    MemoryQueryResponse,
    MemoriesListResponse,
    MemoryResetResponse,
    MemoryUpdateRequest,
)
from app.services.openwebui_memory_service import (
    OpenWebUIMemoryServiceError,
    add_memory,
    list_memories,
    query_memories,
    reset_memories,
    update_memory,
)

router = APIRouter()


def _handle(exc: OpenWebUIMemoryServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def list_my_openwebui_memories(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoriesListResponse:
    try:
        return list_memories(db, current_user, ow)
    except OpenWebUIMemoryServiceError as exc:
        _handle(exc)


def create_my_openwebui_memory(
    payload: MemoryCreateRequest,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryItemOut:
    try:
        return add_memory(db, current_user, ow, body=payload.body)
    except OpenWebUIMemoryServiceError as exc:
        _handle(exc)


def query_my_openwebui_memories(
    payload: MemoryQueryRequest,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryQueryResponse:
    try:
        return query_memories(
            db, current_user, ow, body=payload.body, limit=payload.limit
        )
    except OpenWebUIMemoryServiceError as exc:
        _handle(exc)


def reset_my_openwebui_memories(
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryResetResponse:
    try:
        return reset_memories(db, current_user, ow)
    except OpenWebUIMemoryServiceError as exc:
        _handle(exc)


def patch_my_openwebui_memory(
    memory_id: str,
    payload: MemoryUpdateRequest,
    ow: OpenWebUIClientDep,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MemoryItemOut:
    try:
        return update_memory(db, current_user, ow, memory_id, body=payload.body)
    except OpenWebUIMemoryServiceError as exc:
        _handle(exc)


register_workbench_route(
    router,
    "/memories",
    list_my_openwebui_memories,
    methods=["GET"],
    response_model=MemoriesListResponse,
    summary="List memories",
    operation_id="me_ai_workbench_openwebui_memories_list",
)
register_workbench_route(
    router,
    "/memories",
    create_my_openwebui_memory,
    methods=["POST"],
    status_code=201,
    response_model=MemoryItemOut,
    summary="Add a memory",
    operation_id="me_ai_workbench_openwebui_memories_create",
)
register_workbench_route(
    router,
    "/memories/query",
    query_my_openwebui_memories,
    methods=["POST"],
    response_model=MemoryQueryResponse,
    summary="Semantic query over memories",
    operation_id="me_ai_workbench_openwebui_memories_query",
)
register_workbench_route(
    router,
    "/memories/reset",
    reset_my_openwebui_memories,
    methods=["POST"],
    response_model=MemoryResetResponse,
    summary="Rebuild vector index for all memories",
    operation_id="me_ai_workbench_openwebui_memories_reset",
)
register_workbench_route(
    router,
    "/memories/{memory_id}",
    patch_my_openwebui_memory,
    methods=["PATCH"],
    response_model=MemoryItemOut,
    summary="Update memory text",
    operation_id="me_ai_workbench_openwebui_memory_patch",
)
