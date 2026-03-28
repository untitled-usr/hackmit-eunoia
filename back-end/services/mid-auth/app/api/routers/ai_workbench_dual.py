"""Register ``/me/ai/workbench`` API routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter

WB_PREFIX = "/me/ai/workbench"


def register_workbench_route(
    router: APIRouter,
    path_suffix: str,
    endpoint: Callable[..., Any],
    *,
    methods: list[str],
    operation_id: str,
    **route_kwargs: Any,
) -> None:
    if not path_suffix.startswith("/"):
        raise ValueError(f"path_suffix must start with /, got {path_suffix!r}")
    new_path = f"{WB_PREFIX}{path_suffix}"
    router.add_api_route(
        new_path,
        endpoint,
        methods=methods,
        operation_id=operation_id,
        **route_kwargs,
    )
