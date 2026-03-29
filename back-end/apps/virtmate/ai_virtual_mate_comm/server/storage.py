from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SessionStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_settings (
                    session_id TEXT PRIMARY KEY,
                    settings_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_state (
                    session_id TEXT PRIMARY KEY,
                    state_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _ensure_schema(self) -> None:
        # 如果运行中数据库文件被删除，按需重建 schema，避免接口直接 500。
        self._init_db()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def append_message(self, session_id: str, role: str, content: str) -> dict[str, str]:
        self._ensure_schema()
        record = {
            "role": role,
            "content": content,
            "created_at": self._now(),
        }
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO session_messages(session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, record["role"], record["content"], record["created_at"]),
            )
        return record

    def list_messages(self, session_id: str, limit: int = 200) -> list[dict[str, str]]:
        self._ensure_schema()
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                """
                SELECT role, content, created_at
                FROM session_messages
                WHERE session_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def clear_messages(self, session_id: str) -> None:
        self._ensure_schema()
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM session_messages WHERE session_id=?", (session_id,))

    def get_settings(self, session_id: str) -> dict[str, Any] | None:
        self._ensure_schema()
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT settings_json FROM session_settings WHERE session_id=?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return json.loads(row["settings_json"])

    def upsert_settings(self, session_id: str, settings: dict[str, Any]) -> None:
        self._ensure_schema()
        payload = json.dumps(settings, ensure_ascii=False)
        now = self._now()
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO session_settings(session_id, settings_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    settings_json=excluded.settings_json,
                    updated_at=excluded.updated_at
                """,
                (session_id, payload, now),
            )

    def get_state(self, session_id: str) -> dict[str, Any]:
        self._ensure_schema()
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT state_json FROM session_state WHERE session_id=?",
                (session_id,),
            ).fetchone()
        if not row:
            return {"is_playing": False}
        return json.loads(row["state_json"])

    def upsert_state(self, session_id: str, state: dict[str, Any]) -> None:
        self._ensure_schema()
        payload = json.dumps(state, ensure_ascii=False)
        now = self._now()
        with self._lock, self._conn() as conn:
            conn.execute(
                """
                INSERT INTO session_state(session_id, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state_json=excluded.state_json,
                    updated_at=excluded.updated_at
                """,
                (session_id, payload, now),
            )

    def any_playing(self) -> bool:
        self._ensure_schema()
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT state_json FROM session_state").fetchall()
        for row in rows:
            try:
                payload = json.loads(row["state_json"] or "{}")
            except Exception:
                continue
            if bool(payload.get("is_playing", False)):
                return True
        return False

    def list_states(self) -> list[dict[str, Any]]:
        self._ensure_schema()
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT session_id, state_json FROM session_state").fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            try:
                payload = json.loads(row["state_json"] or "{}")
            except Exception:
                payload = {}
            payload["session_id"] = row["session_id"]
            out.append(payload)
        return out

