import os
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ["MID_AUTH_DATABASE_URL"] = "sqlite+pysqlite:////tmp/mid_auth_chat_smoke.db"
os.environ["MID_AUTH_SESSION_COOKIE_NAME"] = "mid_auth_session"
os.environ["MID_AUTH_SESSION_COOKIE_SECURE"] = "false"
os.environ["MID_AUTH_PROVISION_USE_STUB"] = "true"
os.environ["MID_AUTH_VOCECHAT_BASE_URL"] = "http://vocechat.test/api"

from fastapi.testclient import TestClient

from app.api.deps.vocechat_client_dep import get_vocechat_client
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.integrations.vocechat_client import VoceChatClientError
from app.main import app
from app.models.user_app_mappings import UserAppMapping
from app.services.provision_service import ProvisionResult, ProvisionService

DB_FILE = Path("/tmp/mid_auth_chat_smoke.db")


class RecordingVoceChatClient:
    def __init__(self) -> None:
        self.actings: list[str] = []
        self.read_index_calls: list[dict[str, Any]] = []
        self.pin_calls: list[dict[str, Any]] = []
        self.unpin_calls: list[dict[str, Any]] = []
        self.logout_calls: int = 0
        self.delete_current_user_calls: list[str] = []
        self.file_prepare_calls: list[dict[str, Any]] = []
        self.file_upload_calls: list[dict[str, Any]] = []
        self.send_dm_file_calls: list[dict[str, Any]] = []
        self.message_edit_calls: list[dict[str, Any]] = []
        self.message_like_calls: list[dict[str, Any]] = []
        self.message_delete_calls: list[int] = []
        self.message_reply_calls: list[dict[str, Any]] = []
        self._fail_transport = False
        self._mid = 100
        self._http_error_status: int | None = None

    def close(self) -> None:
        pass

    def list_contacts(self, acting_uid: str) -> list[dict[str, Any]]:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        return [
            {
                "target_uid": 2,
                "target_info": {"uid": 2, "name": "Peer Two"},
                "contact_info": {"status": "friend", "created_at": 0, "updated_at": 0},
            }
        ]

    def get_dm_history(
        self,
        acting_uid: str,
        peer_uid: int,
        *,
        before_message_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        return [
            {
                "mid": 1,
                "from_uid": 1,
                "created_at": "2024-01-01T12:00:00Z",
                "detail": {
                    "type": "normal",
                    "content_type": "text/plain",
                    "content": "hello",
                },
            }
        ]

    def send_dm_text(self, acting_uid: str, peer_uid: int, text: str) -> int:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        if self._http_error_status is not None:
            raise VoceChatClientError(
                "forced http error", http_status=self._http_error_status
            )
        self._mid += 1
        return self._mid

    def upload_file_complete(
        self,
        acting_uid: str,
        data: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        fid = self.prepare_file_upload(
            acting_uid, content_type=content_type, filename=filename
        )
        out = self.upload_file_chunk(
            acting_uid, fid, data, chunk_is_last=True
        )
        if not out:
            raise VoceChatClientError("missing upload response")
        return out

    def prepare_file_upload(
        self,
        acting_uid: str,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> str:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.file_prepare_calls.append(
            {"content_type": content_type, "filename": filename}
        )
        return "00000000-0000-0000-0000-000000000099"

    def upload_file_chunk(
        self,
        acting_uid: str,
        file_id: str,
        chunk: bytes,
        *,
        chunk_is_last: bool,
    ) -> dict[str, Any] | None:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.file_upload_calls.append(
            {
                "file_id": file_id,
                "size": len(chunk),
                "chunk_is_last": chunk_is_last,
            }
        )
        if not chunk_is_last:
            return None
        return {
            "path": "2024/1/1/00000000-0000-0000-0000-000000000099",
            "size": len(chunk),
            "hash": "deadbeef",
        }

    def send_dm_file(self, acting_uid: str, peer_uid: int, path: str) -> int:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.send_dm_file_calls.append({"peer_uid": peer_uid, "path": path})
        if self._http_error_status is not None:
            raise VoceChatClientError(
                "forced http error", http_status=self._http_error_status
            )
        self._mid += 1
        return self._mid

    def message_edit(
        self,
        acting_uid: str,
        mid: int,
        *,
        raw_body: bytes,
        content_type: str,
        x_properties: str | None = None,
    ) -> int:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.message_edit_calls.append(
            {
                "mid": int(mid),
                "raw_body": raw_body,
                "content_type": content_type,
                "x_properties": x_properties,
            }
        )
        self._mid += 1
        return self._mid

    def message_like(self, acting_uid: str, mid: int, *, action: str) -> int:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.message_like_calls.append({"mid": int(mid), "action": action})
        self._mid += 1
        return self._mid

    def message_delete(self, acting_uid: str, mid: int) -> int:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.message_delete_calls.append(int(mid))
        self._mid += 1
        return self._mid

    def message_reply(
        self,
        acting_uid: str,
        mid: int,
        *,
        raw_body: bytes,
        content_type: str,
        x_properties: str | None = None,
    ) -> int:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.message_reply_calls.append(
            {
                "mid": int(mid),
                "raw_body": raw_body,
                "content_type": content_type,
                "x_properties": x_properties,
            }
        )
        self._mid += 1
        return self._mid

    def update_read_index(
        self,
        acting_uid: str,
        *,
        users: list[dict[str, int]] | None = None,
        groups: list[dict[str, int]] | None = None,
    ) -> None:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.read_index_calls.append(
            {"users": list(users or []), "groups": list(groups or [])}
        )

    def pin_chat(
        self,
        acting_uid: str,
        *,
        dm_peer_uid: int | None = None,
        group_gid: int | None = None,
    ) -> None:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.pin_calls.append(
            {"dm_peer_uid": dm_peer_uid, "group_gid": group_gid}
        )

    def unpin_chat(
        self,
        acting_uid: str,
        *,
        dm_peer_uid: int | None = None,
        group_gid: int | None = None,
    ) -> None:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.unpin_calls.append(
            {"dm_peer_uid": dm_peer_uid, "group_gid": group_gid}
        )

    def user_logout(self, acting_uid: str) -> None:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.logout_calls += 1

    def delete_current_user(self, acting_uid: str) -> None:
        if self._fail_transport:
            raise VoceChatClientError("net down", transport=True)
        self.actings.append(acting_uid)
        self.delete_current_user_calls.append(acting_uid)
        if self._http_error_status is not None:
            raise VoceChatClientError(
                "forced http error", http_status=self._http_error_status
            )

class ChatSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_vc = RecordingVoceChatClient()

        def _dep():
            yield self.fake_vc

        app.dependency_overrides[get_vocechat_client] = _dep
        self.client = TestClient(app)
        self._register_and_login()

    def tearDown(self) -> None:
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def _register_and_login(self) -> None:
        reg = self.client.post(
            "/auth/register",
            json={
                "username": "chatuser",
                "email": "chatuser@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(reg.status_code, 201)
        login = self.client.post(
            "/auth/login",
            json={"identifier": "chatuser", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def test_list_messages_send_success_and_acting_uid(self) -> None:
        r = self.client.get("/me/conversations")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["id"], "2")
        self.assertIsNone(data["items"][0].get("peer_display_name"))
        self.assertEqual(self.fake_vc.actings[-1], "1")

        m = self.client.get("/me/conversations/2/messages")
        self.assertEqual(m.status_code, 200)
        msgs = m.json()["items"]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["body"], "hello")
        self.assertEqual(self.fake_vc.actings[-1], "1")

        s = self.client.post(
            "/me/conversations/2/messages",
            json={"body": "  hi  "},
        )
        self.assertEqual(s.status_code, 201)
        self.assertEqual(s.json()["body"], "hi")
        self.assertEqual(self.fake_vc.actings[-1], "1")

    def test_emoji_message_not_misclassified_as_file(self) -> None:
        with patch.object(
            self.fake_vc,
            "get_dm_history",
            return_value=[
                {
                    "mid": 99,
                    "from_uid": 2,
                    "created_at": "2024-01-01T12:00:00Z",
                    "detail": {
                        "type": "normal",
                        "content_type": "vocechat/file",
                        "content": "🤡",
                        "properties": {"name": "emoji"},
                    },
                }
            ],
        ):
            r = self.client.get("/me/conversations/2/messages")
        self.assertEqual(r.status_code, 200, r.text)
        items = r.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "99")
        self.assertEqual(items[0]["kind"], "text")
        self.assertEqual(items[0]["body"], "🤡")
        self.assertIsNone(items[0]["attachment"])

    def test_conversation_message_edit_like_delete_reply(self) -> None:
        self.fake_vc.message_edit_calls.clear()
        self.fake_vc.message_like_calls.clear()
        self.fake_vc.message_delete_calls.clear()
        self.fake_vc.message_reply_calls.clear()

        ed = self.client.put(
            "/me/conversations/2/messages/77/edit",
            json={"body": "new text"},
        )
        self.assertEqual(ed.status_code, 200, ed.text)
        self.assertEqual(ed.json()["message_id"], "101")
        self.assertEqual(len(self.fake_vc.message_edit_calls), 1)
        self.assertEqual(self.fake_vc.message_edit_calls[0]["mid"], 77)
        self.assertEqual(
            self.fake_vc.message_edit_calls[0]["content_type"],
            "text/plain; charset=utf-8",
        )

        lk = self.client.put(
            "/me/conversations/2/messages/77/like",
            json={"action": "like"},
        )
        self.assertEqual(lk.status_code, 200)
        self.assertEqual(
            self.fake_vc.message_like_calls[-1],
            {"mid": 77, "action": "like"},
        )

        rp = self.client.post(
            "/me/conversations/2/messages/77/reply",
            json={"body": "  ok  "},
        )
        self.assertEqual(rp.status_code, 200)
        self.assertEqual(self.fake_vc.message_reply_calls[-1]["mid"], 77)
        self.assertEqual(self.fake_vc.message_reply_calls[-1]["raw_body"], b"ok")

        dl = self.client.delete("/me/conversations/2/messages/77")
        self.assertEqual(dl.status_code, 200)
        self.assertIn(77, self.fake_vc.message_delete_calls)

    def test_send_dm_file_multipart(self) -> None:
        self.fake_vc.file_prepare_calls.clear()
        self.fake_vc.file_upload_calls.clear()
        self.fake_vc.send_dm_file_calls.clear()
        s = self.client.post(
            "/me/conversations/2/messages",
            files={"file": ("note.txt", b"hello", "text/plain")},
        )
        self.assertEqual(s.status_code, 201, s.text)
        data = s.json()
        self.assertEqual(data["kind"], "file")
        self.assertEqual(data["body"], "note.txt")
        self.assertEqual(data["attachment"]["filename"], "note.txt")
        self.assertEqual(data["attachment"]["content_type"], "text/plain")
        self.assertEqual(data["attachment"]["size"], 5)
        self.assertEqual(
            data["attachment"]["file_path"],
            "2024/1/1/00000000-0000-0000-0000-000000000099",
        )
        self.assertNotIn("path", data)
        self.assertEqual(len(self.fake_vc.file_prepare_calls), 1)
        self.assertEqual(len(self.fake_vc.file_upload_calls), 1)
        self.assertTrue(self.fake_vc.file_upload_calls[0]["chunk_is_last"])
        self.assertEqual(self.fake_vc.send_dm_file_calls[-1]["peer_uid"], 2)
        self.assertEqual(
            self.fake_vc.send_dm_file_calls[-1]["path"],
            "2024/1/1/00000000-0000-0000-0000-000000000099",
        )

    def test_send_dm_file_empty_400(self) -> None:
        s = self.client.post(
            "/me/conversations/2/messages",
            files={"file": ("empty.bin", b"", "application/octet-stream")},
        )
        self.assertEqual(s.status_code, 400)

    def test_send_dm_file_multipart_missing_file_422(self) -> None:
        s = self.client.post(
            "/me/conversations/2/messages",
            files={"not_file": ("x.txt", b"x", "text/plain")},
        )
        self.assertEqual(s.status_code, 422)

    def test_send_dm_file_too_large_413(self) -> None:
        from app.services import chat_service as cs

        big = b"x" * 1024
        with patch.object(cs, "_MAX_DM_FILE_BYTES", 512):
            s = self.client.post(
                "/me/conversations/2/messages",
                files={"file": ("big.bin", big, "application/octet-stream")},
            )
        self.assertEqual(s.status_code, 413)

    def test_mark_conversation_read_maps_to_read_index(self) -> None:
        self.fake_vc.read_index_calls.clear()
        r = self.client.post(
            "/me/conversations/2/read",
            json={"last_message_id": 42},
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.fake_vc.actings[-1], "1")
        self.assertEqual(
            self.fake_vc.read_index_calls,
            [{"users": [{"uid": 2, "mid": 42}], "groups": []}],
        )

    def test_session_invalidate_204_calls_user_logout(self) -> None:
        self.assertEqual(self.fake_vc.logout_calls, 0)
        r = self.client.post("/me/im/session/invalidate")
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.fake_vc.logout_calls, 1)
        self.assertEqual(self.fake_vc.actings[-1], "1")

        r2 = self.client.post("/me/im/session/invalidate", json={})
        self.assertEqual(r2.status_code, 204)
        self.assertEqual(self.fake_vc.logout_calls, 2)

    def test_pin_unpin_by_conversation_id_204(self) -> None:
        p = self.client.post("/me/conversations/pin", json={"conversation_id": "2"})
        self.assertEqual(p.status_code, 204)
        self.assertEqual(
            self.fake_vc.pin_calls[-1], {"dm_peer_uid": 2, "group_gid": None}
        )
        self.assertEqual(self.fake_vc.actings[-1], "1")

        u = self.client.post("/me/conversations/unpin", json={"conversation_id": "2"})
        self.assertEqual(u.status_code, 204)
        self.assertEqual(
            self.fake_vc.unpin_calls[-1], {"dm_peer_uid": 2, "group_gid": None}
        )

    def test_pin_self_400(self) -> None:
        r = self.client.post("/me/conversations/pin", json={"conversation_id": "1"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"], "cannot pin chat with yourself")

    def test_pin_unpin_payload_must_have_exactly_one_target(self) -> None:
        r = self.client.post("/me/conversations/pin", json={})
        self.assertEqual(r.status_code, 422)
        r2 = self.client.post(
            "/me/conversations/pin",
            json={"conversation_id": "2", "target_public_id": "any"},
        )
        self.assertEqual(r2.status_code, 422)

    def test_no_vocechat_mapping_read_and_write_404(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "vocechat"
            ).delete()
            db.commit()

        r = self.client.get("/me/conversations")
        self.assertEqual(r.status_code, 404)

        w = self.client.post(
            "/me/conversations/2/messages",
            json={"body": "x"},
        )
        self.assertEqual(w.status_code, 404)

        rd = self.client.post(
            "/me/conversations/2/read",
            json={"last_message_id": 1},
        )
        self.assertEqual(rd.status_code, 404)

        pin = self.client.post(
            "/me/conversations/pin", json={"conversation_id": "2"}
        )
        self.assertEqual(pin.status_code, 404)

        inv = self.client.post("/me/im/session/invalidate")
        self.assertEqual(inv.status_code, 404)

        del_vc = self.client.post(
            "/me/im/link/delete",
            json={"confirm": "delete"},
        )
        self.assertEqual(del_vc.status_code, 404)

    def test_delete_vocechat_account_confirm_removes_mapping(self) -> None:
        r = self.client.post(
            "/me/im/link/delete",
            json={"confirm": "delete"},
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.fake_vc.delete_current_user_calls, ["1"])
        with SessionLocal() as db:
            row = (
                db.query(UserAppMapping)
                .filter(UserAppMapping.app_name == "vocechat")
                .first()
            )
            self.assertIsNone(row)

    def test_delete_vocechat_account_body_validation_422(self) -> None:
        r = self.client.post("/me/im/link/delete", json={})
        self.assertEqual(r.status_code, 422)
        r2 = self.client.post(
            "/me/im/link/delete",
            json={"confirm": "DELETE"},
        )
        self.assertEqual(r2.status_code, 422)

    def test_delete_vocechat_account_transport_503(self) -> None:
        self.fake_vc._fail_transport = True
        try:
            r = self.client.post(
                "/me/im/link/delete",
                json={"confirm": "delete"},
            )
            self.assertEqual(r.status_code, 503)
        finally:
            self.fake_vc._fail_transport = False

    def test_delete_vocechat_account_vc_http_error_mapped(self) -> None:
        self.fake_vc._http_error_status = 403
        try:
            r = self.client.post(
                "/me/im/link/delete",
                json={"confirm": "delete"},
            )
            self.assertEqual(r.status_code, 403)
        finally:
            self.fake_vc._http_error_status = None

    def test_empty_body_400(self) -> None:
        r = self.client.post(
            "/me/conversations/2/messages",
            json={"body": "   "},
        )
        self.assertEqual(r.status_code, 400)

    def test_transport_503(self) -> None:
        self.fake_vc._fail_transport = True
        r = self.client.get("/me/conversations")
        self.assertEqual(r.status_code, 503)
        self.fake_vc._fail_transport = False

    def test_session_invalidate_transport_503(self) -> None:
        self.fake_vc._fail_transport = True
        r = self.client.post("/me/im/session/invalidate")
        self.assertEqual(r.status_code, 503)

    def test_send_message_vocechat_403_maps_to_platform_403(self) -> None:
        self.fake_vc._http_error_status = 403
        try:
            r = self.client.post(
                "/me/conversations/2/messages",
                json={"body": "hi"},
            )
            self.assertEqual(r.status_code, 403)
        finally:
            self.fake_vc._http_error_status = None

    def test_unauthenticated_401(self) -> None:
        self.client.cookies.clear()
        r = self.client.get("/me/conversations")
        self.assertEqual(r.status_code, 401)

    @patch("app.services.chat_service.vocechat_acting_uid_header_value")
    def test_service_resolves_acting_for_client(self, mock_hdr) -> None:
        mock_hdr.return_value = "77"
        self.client.get("/me/conversations")
        mock_hdr.assert_called()
        self.assertEqual(self.fake_vc.actings[-1], "77")

    def test_start_direct_unknown_target_404(self) -> None:
        r = self.client.post(
            "/me/conversations",
            json={
                "target_public_id": "10000000",
                "body": "hi",
            },
        )
        self.assertEqual(r.status_code, 404)

    def test_start_direct_empty_body_400(self) -> None:
        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 200)
        pid = me.json()["public_id"]
        r = self.client.post(
            "/me/conversations",
            json={"target_public_id": pid, "body": "  "},
        )
        self.assertEqual(r.status_code, 400)

    def test_start_direct_cannot_message_self_400(self) -> None:
        me = self.client.get("/auth/me")
        pid = me.json()["public_id"]
        r = self.client.post(
            "/me/conversations",
            json={"target_public_id": pid, "body": "hello"},
        )
        self.assertEqual(r.status_code, 400)

    def test_start_direct_no_vocechat_mapping_404(self) -> None:
        me = self.client.get("/auth/me")
        self.assertEqual(me.status_code, 200)
        pid = me.json()["public_id"]
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "vocechat"
            ).delete()
            db.commit()
        r = self.client.post(
            "/me/conversations",
            json={"target_public_id": pid, "body": "x"},
        )
        self.assertEqual(r.status_code, 404)

    def test_start_direct_unauthenticated_401(self) -> None:
        raw = TestClient(app)
        r = raw.post(
            "/me/conversations",
            json={"target_public_id": "99999999", "body": "x"},
        )
        self.assertEqual(r.status_code, 401)
        raw.close()

    @patch("app.services.chat_service.vocechat_acting_uid_header_value")
    def test_start_direct_uses_acting_uid(self, mock_hdr) -> None:
        mock_hdr.return_value = "88"
        me = self.client.get("/auth/me")
        r = self.client.post(
            "/me/conversations",
            json={
                "target_public_id": me.json()["public_id"],
                "body": "self-attempt",
            },
        )
        self.assertEqual(r.status_code, 400)
        mock_hdr.assert_called()


class DirectEntryChatSmokeTestCase(unittest.TestCase):
    """Two registered users with distinct VoceChat uids (patched provision stub)."""

    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_vc = RecordingVoceChatClient()
        self._counter = {"n": 0}

        def fake_provision(
            _self: ProvisionService,
            *,
            display_name: str,
            username: str,
            password: str,
        ) -> ProvisionResult:
            self._counter["n"] += 1
            i = self._counter["n"]
            return ProvisionResult(
                openwebui_id=f"stub-ow-{i}",
                openwebui_username="stub",
                vocechat_uid=str(i),
                vocechat_username=username[:32],
                memos_resource_name=f"users/{i}",
                memos_username=None,
            )

        self._patch = patch.object(ProvisionService, "provision_user", fake_provision)
        self._patch.start()

        def _dep():
            yield self.fake_vc

        app.dependency_overrides[get_vocechat_client] = _dep
        self.client = TestClient(app)

        r1 = self.client.post(
            "/auth/register",
            json={
                "username": "dmu1",
                "email": "dmu1@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(r1.status_code, 201)
        r2 = self.client.post(
            "/auth/register",
            json={
                "username": "dmu2",
                "email": "dmu2@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(r2.status_code, 201)
        self.peer_public_id = r2.json()["user"]["public_id"]

        login = self.client.post(
            "/auth/login",
            json={"identifier": "dmu1", "password": "Secret123!"},
        )
        self.assertEqual(login.status_code, 200)

    def tearDown(self) -> None:
        self._patch.stop()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_start_direct_conversation_success(self) -> None:
        r = self.client.post(
            "/me/conversations",
            json={
                "target_public_id": self.peer_public_id,
                "body": "  first  ",
            },
        )
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["conversation"]["id"], "2")
        self.assertEqual(data["conversation"]["type"], "direct")
        self.assertEqual(data["conversation"]["peer_display_name"], "dmu2")
        self.assertEqual(data["message"]["body"], "first")
        self.assertEqual(data["message"]["sender_id"], "1")
        self.assertEqual(self.fake_vc.actings[-1], "1")

    def test_pin_unpin_by_target_public_id_204(self) -> None:
        r = self.client.post(
            "/me/conversations/pin",
            json={"target_public_id": self.peer_public_id},
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.fake_vc.pin_calls[-1], {"dm_peer_uid": 2, "group_gid": None})

        u = self.client.post(
            "/me/conversations/unpin",
            json={"target_public_id": self.peer_public_id},
        )
        self.assertEqual(u.status_code, 204)
        self.assertEqual(
            self.fake_vc.unpin_calls[-1], {"dm_peer_uid": 2, "group_gid": None}
        )

    def test_start_direct_transport_503(self) -> None:
        self.fake_vc._fail_transport = True
        r = self.client.post(
            "/me/conversations",
            json={
                "target_public_id": self.peer_public_id,
                "body": "ping",
            },
        )
        self.assertEqual(r.status_code, 503)

if __name__ == "__main__":
    unittest.main()
