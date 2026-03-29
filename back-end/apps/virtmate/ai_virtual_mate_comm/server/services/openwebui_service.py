"""Open WebUI native chat: create/update chat JSON + /api/v1/chat/completions.

Mirrors mid-auth ``ai_chat_service`` flow; uses ``user-id`` (configurable) header for acting user.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from copy import deepcopy
from typing import Any, Callable

import requests as rq

USER_ID_HEADER_DEFAULT = "user-id"
OPENWEBUI_BASE_ENV = "OPENWEBUI_BASE_URL"
OPENWEBUI_HEADER_ENV = "OPENWEBUI_USER_ID_HEADER"
OPENWEBUI_TIMEOUT_ENV = "OPENWEBUI_TIMEOUT_SECONDS"


class OpenWebUiServiceError(Exception):
    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status


def _env_base_url() -> str:
    raw = (os.environ.get(OPENWEBUI_BASE_ENV) or "http://127.0.0.1:8080").strip().rstrip("/")
    return raw


def _env_user_id_header_name() -> str:
    return (os.environ.get(OPENWEBUI_HEADER_ENV) or USER_ID_HEADER_DEFAULT).strip() or USER_ID_HEADER_DEFAULT


def _env_timeout() -> float:
    try:
        return float(os.environ.get(OPENWEBUI_TIMEOUT_ENV) or "120")
    except ValueError:
        return 120.0


def _headers(user_id: str) -> dict[str, str]:
    name = _env_user_id_header_name()
    return {name: user_id.strip(), "Content-Type": "application/json", "Accept": "application/json"}


def _get_message_list(messages_map: dict[str, Any], message_id: str | None) -> list[dict[str, Any]]:
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
            s = str(mid)
            if s in visited:
                break
            visited.add(s)
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


def _openai_thread_from_chain(chain: list[dict[str, Any]]) -> list[dict[str, str]]:
    thread: list[dict[str, str]] = []
    for m in chain:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _message_body_text(m)
        thread.append({"role": str(role), "content": text})
    return thread


def _empty_inner_chat(*, model_id: str) -> dict[str, Any]:
    return {
        "title": "New Chat",
        "models": [model_id],
        "history": {"messages": {}, "currentId": None},
        "tags": [],
    }


def _append_user_assistant_pair(
    inner: dict[str, Any],
    *,
    leaf_parent_id: str | None,
    user_text: str,
    assistant_text: str,
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


def _inner_from_get_chat(data: dict[str, Any]) -> dict[str, Any]:
    inner = data.get("chat")
    if not isinstance(inner, dict):
        raise OpenWebUiServiceError("openwebui chat payload invalid")
    return inner


def _parse_assistant_plain(data: dict[str, Any]) -> str:
    if data.get("task_id") and not data.get("choices"):
        raise OpenWebUiServiceError("openwebui returned async task")
    err = data.get("error")
    if err:
        raise OpenWebUiServiceError(f"openwebui completion error: {err}")
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise OpenWebUiServiceError("openwebui completion missing choices")
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        raise OpenWebUiServiceError("openwebui completion invalid message")
    content = msg.get("content")
    if content is None and msg.get("reasoning_content") is not None:
        content = msg.get("reasoning_content")
    if content is None:
        return ""
    if isinstance(content, list):
        return _message_body_text(msg)
    return str(content)


def _extract_delta_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    delta = first.get("delta")
    if not isinstance(delta, dict):
        return ""
    content = delta.get("content")
    if content is None:
        return ""
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text") is not None:
                parts.append(str(item["text"]))
        return "".join(parts)
    return str(content)


class OpenWebUiService:
    def __init__(self) -> None:
        self._base = _env_base_url()
        self._timeout = _env_timeout()

    def public_config_view(self) -> dict[str, Any]:
        return {
            "base_url": self._base,
            "user_id_header": _env_user_id_header_name(),
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        user_id: str,
        json_body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        stream: bool = False,
    ) -> rq.Response:
        url = f"{self._base}{path}"
        headers = _headers(user_id)
        if extra_headers:
            headers.update(extra_headers)
        try:
            resp = rq.request(
                method,
                url,
                headers=headers,
                json=json_body,
                timeout=self._timeout,
                stream=stream,
            )
            return resp
        except rq.RequestException as e:
            raise OpenWebUiServiceError(f"openwebui request failed: {e}") from e

    def get_chat(self, user_id: str, chat_id: str) -> dict[str, Any]:
        r = self._request("GET", f"/api/v1/chats/{chat_id}", user_id=user_id)
        if r.status_code >= 400:
            raise OpenWebUiServiceError(
                f"get chat failed: {r.status_code} {r.text[:500]}",
                http_status=r.status_code,
            )
        data = r.json()
        if not isinstance(data, dict):
            raise OpenWebUiServiceError("get chat: invalid JSON")
        return data

    def create_chat(self, user_id: str, *, chat: dict[str, Any]) -> dict[str, Any]:
        r = self._request("POST", "/api/v1/chats/new", user_id=user_id, json_body={"chat": chat})
        if r.status_code >= 400:
            raise OpenWebUiServiceError(
                f"create chat failed: {r.status_code} {r.text[:500]}",
                http_status=r.status_code,
            )
        data = r.json()
        if not isinstance(data, dict):
            raise OpenWebUiServiceError("create chat: invalid response")
        return data

    def update_chat(self, user_id: str, chat_id: str, *, chat: dict[str, Any]) -> dict[str, Any]:
        r = self._request(
            "POST",
            f"/api/v1/chats/{chat_id}",
            user_id=user_id,
            json_body={"chat": chat},
        )
        if r.status_code >= 400:
            raise OpenWebUiServiceError(
                f"update chat failed: {r.status_code} {r.text[:500]}",
                http_status=r.status_code,
            )
        data = r.json()
        if not isinstance(data, dict):
            raise OpenWebUiServiceError("update chat: invalid response")
        return data

    def chat_completion(self, user_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = self._request(
            "POST",
            "/api/v1/chat/completions",
            user_id=user_id,
            json_body=payload,
        )
        if r.status_code >= 400:
            raise OpenWebUiServiceError(
                f"chat completion failed: {r.status_code} {r.text[:500]}",
                http_status=r.status_code,
            )
        try:
            data = r.json()
        except Exception as e:
            raise OpenWebUiServiceError("chat completion: invalid JSON") from e
        if not isinstance(data, dict):
            raise OpenWebUiServiceError("chat completion: expected object")
        return data

    def chat_completion_stream(
        self,
        user_id: str,
        payload: dict[str, Any],
        *,
        on_delta: Callable[[str], None] | None = None,
    ) -> str:
        r = self._request(
            "POST",
            "/api/v1/chat/completions",
            user_id=user_id,
            json_body=payload,
            extra_headers={"Accept": "text/event-stream"},
            stream=True,
        )
        if r.status_code >= 400:
            raise OpenWebUiServiceError(
                f"chat completion failed: {r.status_code} {r.text[:500]}",
                http_status=r.status_code,
            )
        full_parts: list[str] = []
        try:
            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                line = raw.strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if not body or body == "[DONE]":
                    continue
                try:
                    obj = json.loads(body)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                err = obj.get("error")
                if err:
                    raise OpenWebUiServiceError(f"openwebui completion error: {err}")
                chunk = _extract_delta_content(obj)
                if not chunk:
                    continue
                full_parts.append(chunk)
                if on_delta is not None:
                    on_delta(chunk)
        finally:
            r.close()
        return "".join(full_parts)

    def send_user_message(
        self,
        user_id: str,
        model_id: str,
        user_text: str,
        conversation_id: str | None,
        *,
        system_prompt: str | None = None,
        stream: bool = False,
        on_delta: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        """Run one user turn; create chat if needed. Returns assistant_text + conversation_id."""
        text = user_text.strip()
        if not text:
            raise OpenWebUiServiceError("message text must not be empty")
        mid = model_id.strip()
        if not mid:
            raise OpenWebUiServiceError("model is required")

        chat_id: str
        inner: dict[str, Any]

        if conversation_id and conversation_id.strip():
            chat_id = conversation_id.strip()
            data = self.get_chat(user_id, chat_id)
            inner = deepcopy(_inner_from_get_chat(data))
        else:
            inner = _empty_inner_chat(model_id=mid)
            created = self.create_chat(user_id, chat=inner)
            chat_id = str(
                created.get("id")
                or (created.get("chat") if isinstance(created.get("chat"), dict) else {}).get("id")
                or ""
            )
            if not chat_id:
                raise OpenWebUiServiceError("openwebui create chat missing id")

        hist = inner.setdefault("history", {})
        messages_map: dict[str, Any] = hist.setdefault("messages", {})
        leaf_parent_id = hist.get("currentId")
        leaf_str = str(leaf_parent_id) if leaf_parent_id else None

        chain = _get_message_list(messages_map, leaf_str)
        openai_prev = _openai_thread_from_chain(chain)
        openai_messages: list[dict[str, str]] = []
        sp = (system_prompt or "").strip()
        if sp:
            openai_messages.append({"role": "system", "content": sp})
        openai_messages.extend(openai_prev)
        openai_messages.append({"role": "user", "content": text})

        completion_payload: dict[str, Any] = {
            "model": mid,
            "messages": openai_messages,
            "stream": bool(stream),
        }
        if stream:
            parts: list[str] = []

            def _on_chunk(chunk: str) -> None:
                parts.append(chunk)
                if on_delta is not None:
                    on_delta(chunk, "".join(parts))

            assistant_plain = self.chat_completion_stream(user_id, completion_payload, on_delta=_on_chunk)
        else:
            comp = self.chat_completion(user_id, completion_payload)
            assistant_plain = _parse_assistant_plain(comp)

        _maybe_set_title_from_first_message(inner, text)
        if mid and not inner.get("models"):
            inner["models"] = [mid]

        _append_user_assistant_pair(
            inner,
            leaf_parent_id=leaf_str,
            user_text=text,
            assistant_text=assistant_plain,
            model_id=mid,
        )

        self.update_chat(user_id, chat_id, chat=inner)

        return {
            "assistant_text": assistant_plain,
            "conversation_id": chat_id,
        }
