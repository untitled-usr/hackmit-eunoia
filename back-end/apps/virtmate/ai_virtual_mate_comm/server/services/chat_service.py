from __future__ import annotations

import asyncio
from typing import Any, Callable

from server.config import RuntimeConfig
from server.services.common import (
    get_think_filter_flag,
    maybe_strip_think,
    now_text,
    sanitize_answer,
)
from server.services.openwebui_service import OpenWebUiService, OpenWebUiServiceError
from server.storage import SessionStore


class ChatService:
    def __init__(self, runtime: RuntimeConfig, store: SessionStore, openwebui: OpenWebUiService) -> None:
        self.runtime = runtime
        self.store = store
        self.openwebui = openwebui

    def _think_filter_enabled(self) -> bool:
        return get_think_filter_flag(self.runtime.more_set)

    def _system_prompt_from_settings(self, settings: dict[str, Any]) -> str | None:
        prompt = str(settings.get("prompt", "") or "").strip()
        mate = str(settings.get("mate_name", "") or "").strip()
        user = str(settings.get("username", "") or "").strip()
        parts: list[str] = []
        if prompt:
            parts.append(prompt)
        elif mate:
            parts.append(f"你是虚拟伙伴「{mate}」。")
        if user and mate:
            parts.append(f"用户称呼为「{user}」。")
        out = "\n".join(parts).strip()
        return out or None

    def get_session_settings(self, session_id: str) -> dict[str, Any]:
        settings = self.store.get_settings(session_id)
        if settings:
            return settings
        default = self.runtime.get_default_session_profile()
        self.store.upsert_settings(session_id, default)
        return default

    def update_session_settings(self, session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {"tts_engine", "cam_permission", "username", "mate_name", "prompt"}
        settings = self.get_session_settings(session_id)
        for key, value in updates.items():
            if key in allowed and value is not None:
                settings[key] = value
        self.store.upsert_settings(session_id, settings)
        return settings

    def get_history(self, session_id: str, limit: int = 200) -> list[dict[str, str]]:
        return self.store.list_messages(session_id=session_id, limit=limit)

    def clear_history(self, session_id: str) -> None:
        self.store.clear_messages(session_id)

    async def chat_via_openwebui(
        self,
        *,
        user_id: str,
        session_id: str,
        user_text: str,
        model: str,
        conversation_id: str | None,
        settings: dict[str, Any],
        stream: bool = False,
        on_delta: Callable[[str, str], None] | None = None,
    ) -> tuple[str, str]:
        _ = session_id
        msg = user_text
        if any(k in msg for k in ["几点", "多少点", "时间", "时候", "日期", "多少号", "几号"]):
            msg = f"[当前时间:{now_text()}]{msg}"

        system_prompt = self._system_prompt_from_settings(settings)

        def _run() -> dict[str, Any]:
            return self.openwebui.send_user_message(
                user_id,
                model,
                msg,
                conversation_id,
                system_prompt=system_prompt,
                stream=stream,
                on_delta=on_delta,
            )

        try:
            result = await asyncio.to_thread(_run)
        except OpenWebUiServiceError as e:
            raise RuntimeError(str(e)) from e

        assistant = result.get("assistant_text") or ""
        assistant = maybe_strip_think(assistant, self._think_filter_enabled())
        assistant = sanitize_answer(assistant)
        cid = str(result.get("conversation_id") or "")
        return assistant, cid
