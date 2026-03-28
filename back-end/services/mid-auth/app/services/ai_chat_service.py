"""Platform **AI chats** (module-07 + module-08): OpenWebUI-backed ``/me/ai/chats``.

module-07: list, messages, create, append (non-stream completion + merge into OW chat JSON).

module-08: rename title (PATCH) and delete chat (DELETE), with unified resource error mapping.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.integrations.openwebui_client import OpenWebUIClient, OpenWebUIClientError
from app.lib.openwebui_acting_uid import OpenWebUIAppUidError, openwebui_acting_uid_header_value
from app.models.user_app_mappings import UserAppMapping
from app.models.users import User
from app.schemas.ai_chat import (
    AiChatCreateEmptyResponse,
    AiChatCreateWithMessageResponse,
    AiChatMessagesResponse,
    AiChatSummary,
    AiChatsListResponse,
    AiMessageOut,
)

log = logging.getLogger(__name__)


@dataclass
class AiChatServiceError(Exception):
    status_code: int
    detail: str


def _utc_from_unix_seconds(ts: Any) -> datetime:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    return datetime.now(timezone.utc)


def _utc_from_message_ts(ts: Any) -> datetime:
    """OpenWebUI message ``timestamp`` is usually epoch ms."""
    if isinstance(ts, (int, float)):
        v = float(ts)
        if v > 1e12:  # ms
            v /= 1000.0
        return datetime.fromtimestamp(v, tz=timezone.utc)
    return datetime.now(timezone.utc)


def _get_message_list(messages_map: dict[str, Any], message_id: str | None) -> list[dict[str, Any]]:
    """Same traversal as OpenWebUI ``get_message_list`` (root → leaf)."""
    if not messages_map or not message_id:
        return []
    current = messages_map.get(message_id)
    if not current:
        return []
    out: list[dict[str, Any]] = []
    visited: set[str] = set()
    while current:
        mid = current.get("id")
        if mid is not None:
            if mid in visited:
                break
            visited.add(str(mid))
        out.append(current)
        parent_id = current.get("parentId")
        current = messages_map.get(parent_id) if parent_id else None
    out.reverse()
    return out


def _message_body_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text") is not None:
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()
    if content is None:
        return ""
    return str(content).strip()


def _message_reasoning_text(message: dict[str, Any]) -> str:
    for key in ("reasoning", "reasoning_content", "reasoning_content_text", "thinking"):
        value = message.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            return _message_body_text({"content": value})
        text = str(value).strip()
        if text:
            return text
    return ""


def _openai_thread_from_chain(chain: list[dict[str, Any]]) -> list[dict[str, str]]:
    thread: list[dict[str, str]] = []
    for m in chain:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _message_body_text(m)
        thread.append({"role": str(role), "content": text})
    return thread


def _map_openwebui_client_error(exc: OpenWebUIClientError) -> AiChatServiceError:
    if exc.transport:
        return AiChatServiceError(503, "openwebui upstream unavailable")
    status = exc.http_status
    if status is None:
        return AiChatServiceError(503, "openwebui response error")
    if status >= 500:
        return AiChatServiceError(503, "openwebui upstream error")
    if status == 404:
        return AiChatServiceError(404, "chat not found")
    if status == 403:
        return AiChatServiceError(403, "forbidden")
    if status == 401:
        # OpenWebUI may use 401 for missing chat — treat as not found for /me scope.
        return AiChatServiceError(404, "chat not found")
    if status == 422:
        return AiChatServiceError(422, "invalid request")
    return AiChatServiceError(503, "openwebui upstream error")


# Exposed for other Open WebUI BFF modules (same HTTP semantics as ``/me/ai/chats``).
map_openwebui_upstream_error = _map_openwebui_client_error


def _parse_assistant_plain(data: dict[str, Any]) -> str:
    if data.get("task_id") and not data.get("choices"):
        raise AiChatServiceError(503, "openwebui returned async task")
    err = data.get("error")
    if err:
        raise AiChatServiceError(503, "openwebui completion error")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise AiChatServiceError(503, "openwebui completion missing choices")
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        raise AiChatServiceError(503, "openwebui completion invalid message")
    content = msg.get("content")
    if content is None and msg.get("reasoning_content") is not None:
        content = msg.get("reasoning_content")
    if content is None:
        return ""
    if isinstance(content, list):
        return _message_body_text(msg)
    return str(content)


def _parse_assistant_reasoning(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        return ""
    return _message_reasoning_text(msg)


def _extract_stream_delta(data: dict[str, Any]) -> tuple[str, str]:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", ""
    first = choices[0] if isinstance(choices[0], dict) else None
    if not isinstance(first, dict):
        return "", ""
    content_out = ""
    reasoning_out = ""
    delta = first.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, list):
            content_out = _message_body_text({"content": content})
        elif content is not None:
            content_out = str(content)
        reasoning_out = _message_reasoning_text(delta)
    msg = first.get("message")
    if isinstance(msg, dict):
        if not content_out:
            content = msg.get("content")
            if isinstance(content, list):
                content_out = _message_body_text(msg)
            elif content is not None:
                content_out = str(content)
        if not reasoning_out:
            reasoning_out = _message_reasoning_text(msg)
    return content_out, reasoning_out


def _require_mapping(db: Session, user: User) -> UserAppMapping:
    row = (
        db.query(UserAppMapping)
        .filter(
            UserAppMapping.user_id == user.id,
            UserAppMapping.app_name == "openwebui",
        )
        .first()
    )
    if row is None:
        raise AiChatServiceError(404, "openwebui mapping not found")
    return row


def _acting_uid_for_client(
    mapping: UserAppMapping, settings: Settings | None = None
) -> str:
    s = settings or get_settings()
    # Stub provisioning may keep a placeholder OpenWebUI uid.
    # Use admin acting uid as fallback to keep BFF endpoints available in stub mode.
    if mapping.app_uid.startswith("stub-openwebui") and s.open_webui_admin_acting_uid:
        return s.open_webui_admin_acting_uid.strip()
    try:
        return openwebui_acting_uid_header_value(mapping.app_uid)
    except OpenWebUIAppUidError:
        raise AiChatServiceError(404, "openwebui mapping not found") from None


def resolve_openwebui_acting_uid(db: Session, user: User) -> str:
    """Shared by AI chat routes and Open WebUI BFF (acting ``X-Acting-Uid`` value)."""
    mapping = _require_mapping(db, user)
    return _acting_uid_for_client(mapping, get_settings())


def _resolve_model(settings: Settings, override: str | None) -> str:
    if override is not None and override.strip():
        return override.strip()
    if settings.openwebui_default_model_id:
        return settings.openwebui_default_model_id
    raise AiChatServiceError(400, "model is required (set MID_AUTH_OPENWEBUI_DEFAULT_MODEL_ID or pass model)")


def _empty_inner_chat(*, model_id: str | None) -> dict[str, Any]:
    models: list[str] = [model_id] if model_id else []
    return {
        "title": "New Chat",
        "models": models,
        "history": {"messages": {}, "currentId": None},
        "tags": [],
    }


def _append_user_assistant_pair(
    inner: dict[str, Any],
    *,
    leaf_parent_id: str | None,
    user_text: str,
    assistant_text: str,
    assistant_reasoning: str | None,
    model_id: str,
) -> tuple[str, str]:
    hist = inner.setdefault("history", {})
    msgs: dict[str, Any] = hist.setdefault("messages", {})
    user_msg_id = uuid.uuid4().hex
    assistant_msg_id = uuid.uuid4().hex
    now = int(time.time() * 1000)

    user_node: dict[str, Any] = {
        "id": user_msg_id,
        "parentId": leaf_parent_id,
        "childrenIds": [assistant_msg_id],
        "role": "user",
        "content": user_text,
        "timestamp": now,
    }
    assistant_node: dict[str, Any] = {
        "id": assistant_msg_id,
        "parentId": user_msg_id,
        "childrenIds": [],
        "role": "assistant",
        "content": assistant_text,
        "model": model_id,
        "timestamp": now + 1,
    }
    if assistant_reasoning:
        assistant_node["reasoning_content"] = assistant_reasoning
    msgs[user_msg_id] = user_node
    msgs[assistant_msg_id] = assistant_node
    if leaf_parent_id and leaf_parent_id in msgs:
        parent = msgs[leaf_parent_id]
        ch = parent.setdefault("childrenIds", [])
        if user_msg_id not in ch:
            ch.append(user_msg_id)
    hist["currentId"] = assistant_msg_id
    return user_msg_id, assistant_msg_id


def _maybe_set_title_from_first_message(inner: dict[str, Any], user_text: str) -> None:
    title = str(inner.get("title") or "").strip()
    if title in {"", "New Chat"}:
        line = user_text.strip().split("\n", 1)[0].strip()
        inner["title"] = (line[:120] if line else "New Chat")


def _run_completion(
    client: OpenWebUIClient,
    acting_uid: str,
    *,
    model_id: str,
    openai_messages: list[dict[str, str]],
) -> tuple[str, str]:
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": openai_messages,
        "stream": False,
    }
    try:
        data = client.chat_completion(acting_uid, payload)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    try:
        return _parse_assistant_plain(data), _parse_assistant_reasoning(data)
    except AiChatServiceError:
        raise
    except Exception:
        raise AiChatServiceError(503, "openwebui completion parse failed") from None


def _inner_from_get_chat(data: dict[str, Any]) -> dict[str, Any]:
    inner = data.get("chat")
    if not isinstance(inner, dict):
        raise AiChatServiceError(503, "openwebui chat payload invalid")
    return inner


def list_ai_chats(
    db: Session,
    user: User,
    client: OpenWebUIClient,
) -> AiChatsListResponse:
    mapping = _require_mapping(db, user)
    acting_uid = _acting_uid_for_client(mapping)
    try:
        rows = client.list_chats(acting_uid)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc

    items: list[AiChatSummary] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cid = row.get("id")
        if not cid:
            continue
        items.append(
            AiChatSummary(
                id=str(cid),
                title=str(row.get("title") or "Chat"),
                updated_at=_utc_from_unix_seconds(row.get("updated_at")),
                created_at=_utc_from_unix_seconds(row.get("created_at")),
            )
        )
    items.sort(key=lambda x: x.updated_at, reverse=True)
    return AiChatsListResponse(items=items)


def get_ai_chat_messages(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
) -> AiChatMessagesResponse:
    mapping = _require_mapping(db, user)
    acting_uid = _acting_uid_for_client(mapping)
    try:
        data = client.get_chat(acting_uid, chat_id)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc

    inner = _inner_from_get_chat(data)
    hist = inner.get("history") if isinstance(inner.get("history"), dict) else {}
    messages_map = hist.get("messages") if isinstance(hist.get("messages"), dict) else {}
    current_id = hist.get("currentId")
    current_id_str = str(current_id) if current_id else None

    chain = _get_message_list(messages_map, current_id_str)
    out: list[AiMessageOut] = []
    for m in chain:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        mid = m.get("id")
        if not mid:
            continue
        out.append(
            AiMessageOut(
                id=str(mid),
                role=str(role),
                body=_message_body_text(m),
                reasoning=_message_reasoning_text(m) or None,
                created_at=_utc_from_message_ts(m.get("timestamp")),
            )
        )
    return AiChatMessagesResponse(items=out)


def create_ai_chat_empty(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    *,
    settings: Settings | None = None,
) -> AiChatCreateEmptyResponse:
    settings = settings or get_settings()
    mapping = _require_mapping(db, user)
    acting_uid = _acting_uid_for_client(mapping)
    inner = _empty_inner_chat(model_id=None)
    try:
        created = client.create_chat(acting_uid, chat=inner)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    return AiChatCreateEmptyResponse(
        chat=AiChatSummary(
            id=str(created.get("id")),
            title=str(created.get("title") or "New Chat"),
            updated_at=_utc_from_unix_seconds(created.get("updated_at")),
            created_at=_utc_from_unix_seconds(created.get("created_at")),
        )
    )


def _append_user_turn(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
    user_text: str,
    model_override: str | None,
    *,
    settings: Settings,
) -> AiMessageOut:
    mapping = _require_mapping(db, user)
    acting_uid = _acting_uid_for_client(mapping)
    model_id = _resolve_model(settings, model_override)

    try:
        data = client.get_chat(acting_uid, chat_id)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc

    inner = copy.deepcopy(_inner_from_get_chat(data))
    hist = inner.setdefault("history", {})
    messages_map: dict[str, Any] = hist.setdefault("messages", {})  # type: ignore[assignment]
    leaf_parent_id = hist.get("currentId")
    leaf_str = str(leaf_parent_id) if leaf_parent_id else None

    chain = _get_message_list(messages_map, leaf_str)
    openai_prev = _openai_thread_from_chain(chain)
    openai_messages = [*openai_prev, {"role": "user", "content": user_text}]

    assistant_plain, assistant_reasoning = _run_completion(
        client, acting_uid, model_id=model_id, openai_messages=openai_messages
    )

    _maybe_set_title_from_first_message(inner, user_text)
    if model_id and not inner.get("models"):
        inner["models"] = [model_id]

    _user_mid, assistant_msg_id = _append_user_assistant_pair(
        inner,
        leaf_parent_id=leaf_str,
        user_text=user_text,
        assistant_text=assistant_plain,
        assistant_reasoning=assistant_reasoning,
        model_id=model_id,
    )
    _ = _user_mid

    try:
        client.update_chat(acting_uid, chat_id, chat=inner)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc

    asst_node = inner["history"]["messages"][assistant_msg_id]
    return AiMessageOut(
        id=str(assistant_msg_id),
        role="assistant",
        body=_message_body_text(asst_node),
        reasoning=_message_reasoning_text(asst_node) or None,
        created_at=_utc_from_message_ts(asst_node.get("timestamp")),
    )


@dataclass
class AiChatTurnContext:
    acting_uid: str
    chat_id: str
    model_id: str
    inner: dict[str, Any]
    leaf_parent_id: str | None
    user_text: str
    openai_messages: list[dict[str, str]]


def _prepare_user_turn_context(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str | None,
    user_text: str,
    model_override: str | None,
    *,
    settings: Settings,
) -> AiChatTurnContext:
    mapping = _require_mapping(db, user)
    acting_uid = _acting_uid_for_client(mapping)
    model_id = _resolve_model(settings, model_override)
    text = _require_user_message_body(user_text)
    normalized_chat_id = (chat_id or "").strip()

    if normalized_chat_id:
        try:
            data = client.get_chat(acting_uid, normalized_chat_id)
        except OpenWebUIClientError as exc:
            raise _map_openwebui_client_error(exc) from exc
        inner = copy.deepcopy(_inner_from_get_chat(data))
    else:
        inner = _empty_inner_chat(model_id=model_id)
        try:
            created = client.create_chat(acting_uid, chat=inner)
        except OpenWebUIClientError as exc:
            raise _map_openwebui_client_error(exc) from exc
        normalized_chat_id = str(created.get("id") or "")
        if not normalized_chat_id:
            raise AiChatServiceError(503, "openwebui create chat missing id")
        try:
            data = client.get_chat(acting_uid, normalized_chat_id)
        except OpenWebUIClientError as exc:
            raise _map_openwebui_client_error(exc) from exc
        inner = copy.deepcopy(_inner_from_get_chat(data))

    hist = inner.setdefault("history", {})
    messages_map: dict[str, Any] = hist.setdefault("messages", {})  # type: ignore[assignment]
    leaf_parent_id = hist.get("currentId")
    leaf_str = str(leaf_parent_id) if leaf_parent_id else None
    chain = _get_message_list(messages_map, leaf_str)
    openai_prev = _openai_thread_from_chain(chain)
    openai_messages = [*openai_prev, {"role": "user", "content": text}]
    return AiChatTurnContext(
        acting_uid=acting_uid,
        chat_id=normalized_chat_id,
        model_id=model_id,
        inner=inner,
        leaf_parent_id=leaf_str,
        user_text=text,
        openai_messages=openai_messages,
    )


def _persist_turn_result(
    client: OpenWebUIClient,
    *,
    ctx: AiChatTurnContext,
    assistant_text: str,
    assistant_reasoning: str,
) -> AiMessageOut:
    inner = ctx.inner
    _maybe_set_title_from_first_message(inner, ctx.user_text)
    if ctx.model_id and not inner.get("models"):
        inner["models"] = [ctx.model_id]
    _user_mid, assistant_msg_id = _append_user_assistant_pair(
        inner,
        leaf_parent_id=ctx.leaf_parent_id,
        user_text=ctx.user_text,
        assistant_text=assistant_text,
        assistant_reasoning=assistant_reasoning,
        model_id=ctx.model_id,
    )
    _ = _user_mid
    try:
        client.update_chat(ctx.acting_uid, ctx.chat_id, chat=inner)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    asst_node = inner["history"]["messages"][assistant_msg_id]
    return AiMessageOut(
        id=str(assistant_msg_id),
        role="assistant",
        body=_message_body_text(asst_node),
        reasoning=_message_reasoning_text(asst_node) or None,
        created_at=_utc_from_message_ts(asst_node.get("timestamp")),
    )


def stream_ai_chat_message(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str | None,
    user_text: str,
    model_override: str | None,
    *,
    settings: Settings | None = None,
) -> tuple[str, Iterator[bytes]]:
    settings = settings or get_settings()
    ctx = _prepare_user_turn_context(
        db,
        user,
        client,
        chat_id,
        user_text,
        model_override,
        settings=settings,
    )
    payload = {
        "model": ctx.model_id,
        "messages": ctx.openai_messages,
        "stream": True,
    }
    try:
        stream_holder = client.proxy_to_openwebui_stream(
            ctx.acting_uid,
            method="POST",
            downstream_path="/api/v1/chat/completions",
            content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            extra_headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc

    def _iter() -> Iterator[bytes]:
        assistant_full = ""
        reasoning_full = ""
        done_seen = False
        buf = ""
        meta = json.dumps({"type": "chat.meta", "chat_id": ctx.chat_id}, ensure_ascii=False)
        yield f"data: {meta}\n\n".encode("utf-8")

        try:
            for chunk in stream_holder.iter_bytes():
                if not chunk:
                    continue
                try:
                    buf += chunk.decode("utf-8", errors="ignore")
                except Exception:
                    continue
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if not body:
                        continue
                    if body == "[DONE]":
                        done_seen = True
                        continue
                    try:
                        parsed = json.loads(body)
                        if isinstance(parsed, dict):
                            delta_content, delta_reasoning = _extract_stream_delta(parsed)
                            assistant_full += delta_content
                            reasoning_full += delta_reasoning
                    except Exception:
                        pass
                    yield f"data: {body}\n\n".encode("utf-8")
            _persist_turn_result(
                client,
                ctx=ctx,
                assistant_text=assistant_full,
                assistant_reasoning=reasoning_full,
            )
            _ = done_seen
            yield b"data: [DONE]\n\n"
        except AiChatServiceError as exc:
            err = json.dumps({"error": exc.detail, "status": exc.status_code}, ensure_ascii=False)
            yield f"data: {err}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"
        except Exception:
            err = json.dumps({"error": "stream persistence failed", "status": 503}, ensure_ascii=False)
            yield f"data: {err}\n\n".encode("utf-8")
            yield b"data: [DONE]\n\n"

    return ctx.chat_id, _iter()


def _normalize_user_body(body: str) -> str:
    return body.strip()


def _require_user_message_body(body: str) -> str:
    s = _normalize_user_body(body)
    if not s:
        raise AiChatServiceError(400, "body must not be empty")
    return s


def create_ai_chat_with_first_message(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    user_text: str,
    model_override: str | None,
    *,
    settings: Settings | None = None,
) -> AiChatCreateWithMessageResponse:
    settings = settings or get_settings()
    text = _require_user_message_body(user_text)
    model_id = _resolve_model(settings, model_override)

    mapping = _require_mapping(db, user)
    acting_uid = _acting_uid_for_client(mapping)
    inner = _empty_inner_chat(model_id=model_id)
    try:
        created = client.create_chat(acting_uid, chat=inner)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    chat_id = str(created.get("id") or "")
    if not chat_id:
        raise AiChatServiceError(503, "openwebui create chat missing id")

    assistant = _append_user_turn(
        db,
        user,
        client,
        chat_id,
        text,
        model_override=model_id,
        settings=settings,
    )
    try:
        refreshed = client.get_chat(acting_uid, chat_id)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc

    summary = AiChatSummary(
        id=str(refreshed.get("id")),
        title=str(refreshed.get("title") or "New Chat"),
        updated_at=_utc_from_unix_seconds(refreshed.get("updated_at")),
        created_at=_utc_from_unix_seconds(refreshed.get("created_at")),
    )
    return AiChatCreateWithMessageResponse(chat=summary, assistant_message=assistant)


def append_ai_chat_message(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
    user_text: str,
    model_override: str | None,
    *,
    settings: Settings | None = None,
) -> AiMessageOut:
    settings = settings or get_settings()
    text = _require_user_message_body(user_text)
    return _append_user_turn(
        db, user, client, chat_id, text, model_override, settings=settings
    )


def _require_non_empty_title(title: str) -> str:
    s = title.strip()
    if not s:
        raise AiChatServiceError(400, "title must not be empty")
    return s


def update_ai_chat_title(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
    title: str,
) -> AiChatSummary:
    """module-08: PATCH title via OW shallow merge (``chat`` payload only ``title``)."""
    new_title = _require_non_empty_title(title)
    mapping = _require_mapping(db, user)
    acting_uid = _acting_uid_for_client(mapping)
    try:
        data = client.update_chat(acting_uid, chat_id, chat={"title": new_title})
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    if not isinstance(data, dict) or not data.get("id"):
        raise AiChatServiceError(503, "openwebui update chat invalid response")
    return AiChatSummary(
        id=str(data.get("id")),
        title=str(data.get("title") or new_title),
        updated_at=_utc_from_unix_seconds(data.get("updated_at")),
        created_at=_utc_from_unix_seconds(data.get("created_at")),
    )


def delete_ai_chat(
    db: Session,
    user: User,
    client: OpenWebUIClient,
    chat_id: str,
) -> None:
    """module-08: delete chat in OpenWebUI (204 on platform)."""
    mapping = _require_mapping(db, user)
    acting_uid = _acting_uid_for_client(mapping)
    try:
        ok = client.delete_chat(acting_uid, chat_id)
    except OpenWebUIClientError as exc:
        raise _map_openwebui_client_error(exc) from exc
    if not ok:
        raise AiChatServiceError(404, "chat not found")

