"""Smoke tests for /me/social/* and /me/groups/* with stub provision + fake VoceChat."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

os.environ["MID_AUTH_DATABASE_URL"] = (
    "sqlite+pysqlite:////tmp/mid_auth_social_groups_smoke.db"
)
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

DB_FILE = Path("/tmp/mid_auth_social_groups_smoke.db")


class FakeVoceChatClient:
    """Minimal fake covering DM + social + groups (see test_chat_smoke)."""

    def __init__(self) -> None:
        self.actings: list[str] = []
        self._fail_transport = False
        self._mid = 100
        self._fr_id = 500
        self._gid = 200
        self.incoming_fr: list[dict[str, Any]] = []
        self.outgoing_fr: list[dict[str, Any]] = []
        self.records_fr: list[dict[str, Any]] = []
        self.deleted_friend_request_ids: list[int] = []
        self.blacklist: list[dict[str, Any]] = []
        self.groups: list[dict[str, Any]] = []
        self.group_messages: dict[int, list[dict[str, Any]]] = {}
        self.contact_status_calls: list[tuple[int, str]] = []
        self.read_index_calls: list[dict[str, Any]] = []
        self.group_pin_calls: list[tuple[int, int]] = []
        self.group_unpin_calls: list[tuple[int, int]] = []
        self.last_mute_body: dict[str, Any] | None = None
        self.last_burn_body: dict[str, Any] | None = None
        self.contact_rows: list[dict[str, Any]] = []
        self.contact_remarks: dict[tuple[str, int], str] = {}
        self.last_group_send: dict[str, Any] | None = None
        self.leave_group_calls: list[tuple[str, int]] = []
        self.group_change_type_calls: list[dict[str, Any]] = []
        self.fcm_token_calls: list[tuple[str, str]] = []
        self.devices: list[str] = []
        self.deleted_devices: list[str] = []
        self.last_group_update: dict[str, Any] | None = None
        self.deleted_group_gids: list[int] = []
        self.agora_token_calls: list[tuple[str, int]] = []
        self.group_avatar_calls: list[tuple[int, int]] = []
        self.message_edit_calls: list[dict[str, Any]] = []
        self.message_like_calls: list[dict[str, Any]] = []
        self.message_delete_calls: list[int] = []
        self.message_reply_calls: list[dict[str, Any]] = []

    def close(self) -> None:
        pass

    def list_contacts(self, acting_uid: str) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        out: list[dict[str, Any]] = []
        for row in self.contact_rows:
            r = dict(row)
            tid = int(r["target_uid"])
            ci = dict(r.get("contact_info") or {})
            key = (acting_uid, tid)
            if key in self.contact_remarks:
                ci["remark"] = self.contact_remarks[key]
            else:
                ci.setdefault("remark", ci.get("remark", ""))
            r["contact_info"] = ci
            out.append(r)
        return out

    def get_dm_history(
        self,
        acting_uid: str,
        peer_uid: int,
        *,
        before_message_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        return []

    def send_dm_text(self, acting_uid: str, peer_uid: int, text: str) -> int:
        self.actings.append(acting_uid)
        self._mid += 1
        return self._mid

    def prepare_file_upload(
        self,
        acting_uid: str,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> str:
        self.actings.append(acting_uid)
        return "00000000-0000-0000-0000-000000000001"

    def upload_file_chunk(
        self,
        acting_uid: str,
        file_id: str,
        chunk: bytes,
        *,
        chunk_is_last: bool,
    ) -> dict[str, Any] | None:
        self.actings.append(acting_uid)
        if not chunk_is_last:
            return None
        return {"path": "2024/1/1/x", "size": len(chunk), "hash": "x"}

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
        out = self.upload_file_chunk(acting_uid, fid, data, chunk_is_last=True)
        assert out is not None
        return out

    def send_dm_file(self, acting_uid: str, peer_uid: int, path: str) -> int:
        self.actings.append(acting_uid)
        _ = path
        self._mid += 1
        return self._mid

    def create_friend_request(
        self, acting_uid: str, receiver_uid: int, message: str = ""
    ) -> int:
        if self._fail_transport:
            raise VoceChatClientError("net", transport=True)
        self.actings.append(acting_uid)
        self._fr_id += 1
        return self._fr_id

    def list_friend_requests_incoming(self, acting_uid: str) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        return list(self.incoming_fr)

    def list_friend_requests_outgoing(self, acting_uid: str) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        return list(self.outgoing_fr)

    def list_friend_requests_records(self, acting_uid: str) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        return list(self.records_fr)

    def delete_friend_request_record(self, acting_uid: str, request_id: int) -> None:
        self.actings.append(acting_uid)
        self.deleted_friend_request_ids.append(int(request_id))

    def accept_friend_request(self, acting_uid: str, request_id: int) -> None:
        self.actings.append(acting_uid)
        _ = request_id

    def reject_friend_request(self, acting_uid: str, request_id: int) -> None:
        self.actings.append(acting_uid)

    def cancel_friend_request(self, acting_uid: str, request_id: int) -> None:
        self.actings.append(acting_uid)

    def delete_friend(self, acting_uid: str, peer_uid: int) -> None:
        self.actings.append(acting_uid)
        _ = peer_uid

    def update_contact_status(
        self, acting_uid: str, target_uid: int, action: str
    ) -> None:
        self.actings.append(acting_uid)
        self.contact_status_calls.append((int(target_uid), action))

    def list_blacklist(self, acting_uid: str) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        return list(self.blacklist)

    def add_blacklist(self, acting_uid: str, target_uid: int) -> None:
        self.actings.append(acting_uid)
        self.blacklist.append({"uid": target_uid, "name": "blocked"})

    def remove_blacklist(self, acting_uid: str, target_uid: int) -> None:
        self.actings.append(acting_uid)
        self.blacklist = [x for x in self.blacklist if x.get("uid") != target_uid]

    def put_contact_remark(
        self, acting_uid: str, *, target_uid: int, remark: str
    ) -> None:
        self.actings.append(acting_uid)
        self.contact_remarks[(acting_uid, int(target_uid))] = remark

    def update_mute(self, acting_uid: str, body: dict[str, Any]) -> None:
        self.actings.append(acting_uid)
        self.last_mute_body = dict(body)

    def update_burn_after_reading(self, acting_uid: str, body: dict[str, Any]) -> None:
        self.actings.append(acting_uid)
        self.last_burn_body = dict(body)

    def update_fcm_token(
        self, acting_uid: str, *, device_id: str, token: str
    ) -> None:
        self.actings.append(acting_uid)
        self.fcm_token_calls.append((device_id, token))

    def list_groups(
        self, acting_uid: str, *, public_only: bool | None = None
    ) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        _ = public_only
        return list(self.groups)

    def create_group(self, acting_uid: str, body: dict[str, Any]) -> tuple[int, int]:
        self.actings.append(acting_uid)
        _ = body
        self._gid += 1
        gid = self._gid
        self.groups.append(
            {
                "gid": gid,
                "name": body.get("name", "g"),
                "description": body.get("description", ""),
                "owner": 1,
                "members": [1],
                "is_public": body.get("is_public", False),
                "avatar_updated_at": 0,
                "pinned_messages": [],
            }
        )
        self.group_messages[gid] = []
        return gid, 1_700_000_000

    def get_group(self, acting_uid: str, gid: int) -> dict[str, Any]:
        self.actings.append(acting_uid)
        for g in self.groups:
            if int(g["gid"]) == int(gid):
                return dict(g)
        raise VoceChatClientError("group not found", http_status=404)

    def get_group_agora_token(self, acting_uid: str, gid: int) -> dict[str, Any]:
        self.actings.append(acting_uid)
        self.agora_token_calls.append((acting_uid, int(gid)))
        return {
            "agora_token": "fake-rtc-token",
            "app_id": "test-app-id",
            "uid": 4242,
            "channel_name": f"vc-group-{int(gid)}",
            "expired_in": 3600,
        }

    def delete_group(self, acting_uid: str, gid: int) -> None:
        self.actings.append(acting_uid)
        ig = int(gid)
        self.deleted_group_gids.append(ig)
        self.groups = [g for g in self.groups if int(g["gid"]) != ig]
        self.group_messages.pop(ig, None)

    def update_group(
        self, acting_uid: str, gid: int, body: dict[str, Any]
    ) -> None:
        self.actings.append(acting_uid)
        self.last_group_update = {"gid": int(gid), "body": dict(body)}
        for g in self.groups:
            if int(g["gid"]) == int(gid):
                if "name" in body:
                    g["name"] = body["name"]
                if "description" in body:
                    g["description"] = body["description"]
                if "owner" in body:
                    g["owner"] = body["owner"]
                return

    def group_add_members(
        self, acting_uid: str, gid: int, member_uids: list[int]
    ) -> None:
        self.actings.append(acting_uid)
        for g in self.groups:
            if int(g["gid"]) == int(gid):
                m = list(g.get("members") or [])
                for u in member_uids:
                    if u not in m:
                        m.append(u)
                g["members"] = m

    def group_remove_members(
        self, acting_uid: str, gid: int, member_uids: list[int]
    ) -> None:
        self.actings.append(acting_uid)
        for g in self.groups:
            if int(g["gid"]) == int(gid):
                m = [x for x in (g.get("members") or []) if x not in member_uids]
                g["members"] = m

    def group_change_type(
        self,
        acting_uid: str,
        gid: int,
        *,
        is_public: bool,
        members: list[int],
    ) -> None:
        self.actings.append(acting_uid)
        self.group_change_type_calls.append(
            {
                "gid": int(gid),
                "is_public": bool(is_public),
                "members": [int(x) for x in members],
            }
        )

    def leave_group(self, acting_uid: str, gid: int) -> None:
        self.actings.append(acting_uid)
        self.leave_group_calls.append((acting_uid, int(gid)))

    def upload_group_avatar(
        self, acting_uid: str, gid: int, image_bytes: bytes
    ) -> None:
        self.actings.append(acting_uid)
        self.group_avatar_calls.append((int(gid), len(image_bytes)))

    def send_group_payload(
        self,
        acting_uid: str,
        gid: int,
        *,
        raw_body: bytes,
        content_type: str,
        x_properties: str | None = None,
    ) -> int:
        self.actings.append(acting_uid)
        self.last_group_send = {
            "gid": int(gid),
            "raw_body": raw_body,
            "content_type": content_type,
            "x_properties": x_properties,
        }
        self._mid += 1
        mid = self._mid
        preview = (
            raw_body.decode("utf-8")
            if content_type.lower().startswith("text/")
            else ""
        )
        self.group_messages.setdefault(int(gid), []).append(
            {
                "mid": mid,
                "from_uid": 1,
                "created_at": "2024-01-01T12:00:00Z",
                "detail": {
                    "type": "normal",
                    "content_type": content_type.split(";", 1)[0].strip(),
                    "content": preview,
                },
            }
        )
        return mid

    def send_group_text(self, acting_uid: str, gid: int, text: str) -> int:
        return self.send_group_payload(
            acting_uid,
            gid,
            raw_body=text.encode("utf-8"),
            content_type="text/plain; charset=utf-8",
            x_properties=None,
        )

    def message_edit(
        self,
        acting_uid: str,
        mid: int,
        *,
        raw_body: bytes,
        content_type: str,
        x_properties: str | None = None,
    ) -> int:
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
        self.actings.append(acting_uid)
        self.message_like_calls.append({"mid": int(mid), "action": action})
        self._mid += 1
        return self._mid

    def message_delete(self, acting_uid: str, mid: int) -> int:
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

    def get_group_history(
        self,
        acting_uid: str,
        gid: int,
        *,
        before_message_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        self.actings.append(acting_uid)
        _ = before_message_id, limit
        return list(self.group_messages.get(int(gid), []))

    def group_pin_message(self, acting_uid: str, gid: int, mid: int) -> None:
        self.actings.append(acting_uid)
        self.group_pin_calls.append((int(gid), int(mid)))

    def group_unpin_message(self, acting_uid: str, gid: int, mid: int) -> None:
        self.actings.append(acting_uid)
        self.group_unpin_calls.append((int(gid), int(mid)))

    def update_read_index(
        self,
        acting_uid: str,
        *,
        users: list[dict[str, int]] | None = None,
        groups: list[dict[str, int]] | None = None,
    ) -> None:
        self.actings.append(acting_uid)
        self.read_index_calls.append(
            {"users": list(users or []), "groups": list(groups or [])}
        )

    def list_user_devices(self, acting_uid: str) -> list[str]:
        self.actings.append(acting_uid)
        return list(self.devices)

    def delete_user_device(self, acting_uid: str, device: str) -> None:
        self.actings.append(acting_uid)
        if device not in self.devices:
            raise VoceChatClientError(
                "no such device", http_status=401
            )
        self.devices.remove(device)
        self.deleted_devices.append(device)


def _fake_provision_factory(counter: dict[str, int]):
    def fake_provision(
        _self: ProvisionService,
        *,
        display_name: str,
        username: str,
        password: str,
    ) -> ProvisionResult:
        counter["n"] += 1
        i = counter["n"]
        return ProvisionResult(
            openwebui_id=f"stub-ow-{i}",
            openwebui_username="stub",
            vocechat_uid=str(i),
            vocechat_username=username[:32],
            memos_resource_name=f"users/{i}",
            memos_username=None,
        )

    return fake_provision


class SocialAndGroupsSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        if DB_FILE.exists() and DB_FILE.is_dir():
            raise RuntimeError("test database path points to a directory")
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.fake_vc = FakeVoceChatClient()
        self._counter = {"n": 0}
        self._patch = patch.object(
            ProvisionService,
            "provision_user",
            _fake_provision_factory(self._counter),
        )
        self._patch.start()

        def _dep():
            yield self.fake_vc

        app.dependency_overrides[get_vocechat_client] = _dep
        self.client = TestClient(app)

        r1 = self.client.post(
            "/auth/register",
            json={
                "username": "sgu1",
                "email": "sgu1@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(r1.status_code, 201)
        self.user_a_public_id = r1.json()["user"]["public_id"]
        r2 = self.client.post(
            "/auth/register",
            json={
                "username": "sgu2",
                "email": "sgu2@example.com",
                "password": "Secret123!",
            },
        )
        self.assertEqual(r2.status_code, 201)
        self.peer_b_public_id = r2.json()["user"]["public_id"]

        login1 = self.client.post(
            "/auth/login",
            json={"identifier": "sgu1", "password": "Secret123!"},
        )
        self.assertEqual(login1.status_code, 200)

    def test_me_directory_users_lookup_smoke(self) -> None:
        """``POST /me/directory/users/lookup`` — platform ``public_id`` only; no VoceChat search."""
        rid = self.client.post(
            "/me/directory/users/lookup",
            json={"public_id": self.peer_b_public_id},
        )
        self.assertEqual(rid.status_code, 200)
        bid = rid.json()
        self.assertEqual(bid["public_id"], self.peer_b_public_id)
        self.assertIn("sgu2", bid["display_name"].lower())
        self.assertFalse(bid["in_online"])
        self.assertNotIn("password", bid)

        self.assertEqual(
            self.client.post(
                "/me/directory/users/lookup",
                json={"public_id": "199999999999"},
            ).status_code,
            404,
        )

    def tearDown(self) -> None:
        self._patch.stop()
        self.client.close()
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)

    def test_friend_request_and_lists(self) -> None:
        self.fake_vc.incoming_fr = [
            {
                "id": 9,
                "requester_uid": 2,
                "receiver_uid": 1,
                "message": "hi",
                "status": "pending",
                "created_at": 1,
            }
        ]
        inc = self.client.get("/me/social/friend-requests/incoming")
        self.assertEqual(inc.status_code, 200)
        self.assertEqual(inc.json()["items"][0]["id"], "9")
        self.assertEqual(self.fake_vc.actings[-1], "1")

        cr = self.client.post(
            "/me/social/friend-requests",
            json={"target_public_id": self.peer_b_public_id, "message": "yo"},
        )
        self.assertEqual(cr.status_code, 201)
        self.assertEqual(cr.json()["request_id"], "501")

        acc = self.client.post("/me/social/friend-requests/9/accept")
        self.assertEqual(acc.status_code, 204)

    def test_friend_request_records_list_and_delete(self) -> None:
        self.fake_vc.records_fr = [
            {
                "id": 42,
                "requester_uid": 1,
                "receiver_uid": 2,
                "message": "hey",
                "status": "accepted",
                "created_at": 10,
                "responded_at": 20,
                "can_delete": True,
            }
        ]
        rec = self.client.get("/me/social/friend-requests/records")
        self.assertEqual(rec.status_code, 200)
        body = rec.json()["items"][0]
        self.assertEqual(body["id"], "42")
        self.assertEqual(body["responded_at"], "20")
        self.assertTrue(body["can_delete"])
        self.assertEqual(self.fake_vc.actings[-1], "1")

        rm = self.client.delete("/me/social/friend-requests/42")
        self.assertEqual(rm.status_code, 204)
        self.assertEqual(self.fake_vc.deleted_friend_request_ids, [42])

    def test_blacklist_flow(self) -> None:
        bl = self.client.get("/me/social/blacklist")
        self.assertEqual(bl.status_code, 200)
        self.assertEqual(bl.json()["items"], [])

        add = self.client.post(
            "/me/social/blacklist",
            json={"target_public_id": self.peer_b_public_id},
        )
        self.assertEqual(add.status_code, 204)
        bl2 = self.client.get("/me/social/blacklist")
        self.assertEqual(len(bl2.json()["items"]), 1)
        self.assertEqual(bl2.json()["items"][0]["voce_uid"], "2")

        rm = self.client.delete(
            f"/me/social/blacklist/{self.peer_b_public_id}",
        )
        self.assertEqual(rm.status_code, 204)

    def test_remove_friend_and_unknown_target_404(self) -> None:
        rf = self.client.delete(f"/me/social/friends/{self.peer_b_public_id}")
        self.assertEqual(rf.status_code, 204)

        bad = self.client.delete("/me/social/friends/199999999999")
        self.assertEqual(bad.status_code, 404)

    def test_contact_actions_legacy_maps_peer_and_action(self) -> None:
        self.fake_vc.contact_status_calls.clear()
        for action in ("add", "remove", "block", "unblock"):
            r = self.client.post(
                "/me/social/contacts/actions",
                json={
                    "target_public_id": self.peer_b_public_id,
                    "action": action,
                },
            )
            self.assertEqual(r.status_code, 204, msg=action)
        self.assertEqual(
            self.fake_vc.contact_status_calls,
            [(2, "add"), (2, "remove"), (2, "block"), (2, "unblock")],
        )
        self.assertEqual(self.fake_vc.actings[-1], "1")

        bad_act = self.client.post(
            "/me/social/contacts/actions",
            json={"target_public_id": self.peer_b_public_id, "action": "nope"},
        )
        self.assertEqual(bad_act.status_code, 422)

    def test_groups_crud_messages(self) -> None:
        r = self.client.get("/me/groups")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["items"], [])

        c = self.client.post(
            "/me/groups",
            json={"name": "Team", "description": "d", "is_public": False},
        )
        self.assertEqual(c.status_code, 201)
        gid = c.json()["group_id"]
        self.assertEqual(gid, "201")

        g = self.client.get(f"/me/groups/{gid}")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["name"], "Team")

        addm = self.client.post(
            f"/me/groups/{gid}/members",
            json={"target_public_ids": [self.peer_b_public_id]},
        )
        self.assertEqual(addm.status_code, 204)

        sm = self.client.post(
            f"/me/groups/{gid}/messages",
            json={"body": "hello group"},
        )
        self.assertEqual(sm.status_code, 201)
        self.assertEqual(sm.json()["body"], "hello group")
        msg_id = sm.json()["id"]

        self.fake_vc.message_edit_calls.clear()
        ed = self.client.put(
            f"/me/groups/{gid}/messages/{msg_id}/edit",
            json={"body": "edited"},
        )
        self.assertEqual(ed.status_code, 200, ed.text)
        self.assertTrue(ed.json().get("message_id"))
        self.assertEqual(len(self.fake_vc.message_edit_calls), 1)
        self.assertEqual(self.fake_vc.message_edit_calls[0]["mid"], int(msg_id))

        lk = self.client.put(
            f"/me/groups/{gid}/messages/{msg_id}/like",
            json={"action": "like"},
        )
        self.assertEqual(lk.status_code, 200)
        self.assertEqual(
            self.fake_vc.message_like_calls[-1],
            {"mid": int(msg_id), "action": "like"},
        )

        rp = self.client.post(
            f"/me/groups/{gid}/messages/{msg_id}/reply",
            json={"body": "  re  "},
        )
        self.assertEqual(rp.status_code, 200)
        self.assertEqual(self.fake_vc.message_reply_calls[-1]["mid"], int(msg_id))
        self.assertEqual(
            self.fake_vc.message_reply_calls[-1]["raw_body"], b"re"
        )

        dl = self.client.delete(f"/me/groups/{gid}/messages/{msg_id}")
        self.assertEqual(dl.status_code, 200)
        self.assertIn(int(msg_id), self.fake_vc.message_delete_calls)

        hist = self.client.get(f"/me/groups/{gid}/messages")
        self.assertEqual(hist.status_code, 200)
        self.assertEqual(len(hist.json()["items"]), 1)

        self.fake_vc.read_index_calls.clear()
        mk = self.client.post(
            f"/me/groups/{gid}/read",
            json={"last_message_id": 99},
        )
        self.assertEqual(mk.status_code, 204)
        self.assertEqual(
            self.fake_vc.read_index_calls,
            [{"users": [], "groups": [{"gid": int(gid), "mid": 99}]}],
        )

        rm = self.client.delete(
            f"/me/groups/{gid}/members/{self.peer_b_public_id}",
        )
        self.assertEqual(rm.status_code, 204)

        self.fake_vc.leave_group_calls.clear()
        lv = self.client.post(f"/me/groups/{gid}/leave")
        self.assertEqual(lv.status_code, 204)
        self.assertEqual(self.fake_vc.leave_group_calls, [("1", int(gid))])

    def test_group_avatar_upload_png_forwarded(self) -> None:
        c = self.client.post(
            "/me/groups",
            json={"name": "AvatarG", "description": "", "is_public": False},
        )
        self.assertEqual(c.status_code, 201)
        gid = c.json()["group_id"]
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
        self.fake_vc.group_avatar_calls.clear()
        up = self.client.post(
            f"/me/groups/{gid}/avatar",
            files={"file": ("a.png", png, "image/png")},
        )
        self.assertEqual(up.status_code, 204, up.text)
        self.assertEqual(
            self.fake_vc.group_avatar_calls, [(int(gid), len(png))]
        )

    def test_group_realtime_token_maps_response(self) -> None:
        c = self.client.post(
            "/me/groups",
            json={"name": "Callers", "description": "", "is_public": False},
        )
        self.assertEqual(c.status_code, 201)
        gid = c.json()["group_id"]
        self.fake_vc.agora_token_calls.clear()
        r = self.client.get(f"/me/groups/{gid}/realtime-token")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["token"], "fake-rtc-token")
        self.assertEqual(body["app_id"], "test-app-id")
        self.assertEqual(body["client_uid"], 4242)
        self.assertEqual(body["channel_name"], f"vc-group-{int(gid)}")
        self.assertEqual(body["expires_in_seconds"], 3600)
        self.assertEqual(self.fake_vc.agora_token_calls, [("1", int(gid))])

        bad = self.client.get("/me/groups/not-a-gid/realtime-token")
        self.assertEqual(bad.status_code, 404)

    def test_group_patch_and_delete_metadata(self) -> None:
        c = self.client.post(
            "/me/groups",
            json={"name": "G1", "description": "old", "is_public": False},
        )
        self.assertEqual(c.status_code, 201)
        gid = c.json()["group_id"]

        bad_empty = self.client.patch(f"/me/groups/{gid}", json={})
        self.assertEqual(bad_empty.status_code, 400)

        self.fake_vc.last_group_update = None
        pch = self.client.patch(
            f"/me/groups/{gid}",
            json={"name": "G1-renamed", "description": "new desc"},
        )
        self.assertEqual(pch.status_code, 204)
        assert self.fake_vc.last_group_update is not None
        self.assertEqual(
            self.fake_vc.last_group_update,
            {
                "gid": int(gid),
                "body": {"name": "G1-renamed", "description": "new desc"},
            },
        )

        g = self.client.get(f"/me/groups/{gid}")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.json()["name"], "G1-renamed")
        self.assertEqual(g.json()["description"], "new desc")

        own = self.client.patch(
            f"/me/groups/{gid}",
            json={"owner_public_id": self.peer_b_public_id},
        )
        self.assertEqual(own.status_code, 204)
        assert self.fake_vc.last_group_update is not None
        self.assertEqual(
            self.fake_vc.last_group_update["body"],
            {"owner": 2},
        )

        self.fake_vc.deleted_group_gids.clear()
        rm = self.client.delete(f"/me/groups/{gid}")
        self.assertEqual(rm.status_code, 204)
        self.assertEqual(self.fake_vc.deleted_group_gids, [int(gid)])

        gone = self.client.get(f"/me/groups/{gid}")
        self.assertEqual(gone.status_code, 404)

    def test_group_change_type_maps_member_public_ids(self) -> None:
        c = self.client.post(
            "/me/groups",
            json={"name": "PubFlip", "description": "", "is_public": False},
        )
        self.assertEqual(c.status_code, 201)
        gid = c.json()["group_id"]
        self.fake_vc.group_change_type_calls.clear()
        r = self.client.post(
            f"/me/groups/{gid}/change-type",
            json={
                "is_public": True,
                "member_public_ids": [self.peer_b_public_id],
            },
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(
            self.fake_vc.group_change_type_calls,
            [
                {
                    "gid": int(gid),
                    "is_public": True,
                    "members": [2],
                }
            ],
        )
        self.assertEqual(self.fake_vc.actings[-1], "1")

    def test_group_messages_voce_content_types(self) -> None:
        c = self.client.post(
            "/me/groups",
            json={"name": "Rich", "description": "", "is_public": False},
        )
        self.assertEqual(c.status_code, 201)
        gid = c.json()["group_id"]

        md = self.client.post(
            f"/me/groups/{gid}/messages",
            content=b"**hello**",
            headers={"Content-Type": "text/markdown"},
        )
        self.assertEqual(md.status_code, 201)
        self.assertEqual(md.json()["body"], "**hello**")
        assert self.fake_vc.last_group_send is not None
        self.assertEqual(self.fake_vc.last_group_send["content_type"], "text/markdown")

        file_json = b'{"path":"uploads/x.bin"}'
        fi = self.client.post(
            f"/me/groups/{gid}/messages",
            content=file_json,
            headers={
                "Content-Type": "vocechat/file",
                "X-Properties": "e30=",
            },
        )
        self.assertEqual(fi.status_code, 201)
        self.assertEqual(fi.json()["body"], "")
        assert self.fake_vc.last_group_send is not None
        self.assertEqual(self.fake_vc.last_group_send["raw_body"], file_json)
        self.assertEqual(self.fake_vc.last_group_send["content_type"], "vocechat/file")
        self.assertEqual(self.fake_vc.last_group_send["x_properties"], "e30=")

        bad = self.client.post(
            f"/me/groups/{gid}/messages",
            content=b"<x/>",
            headers={"Content-Type": "application/xml"},
        )
        self.assertEqual(bad.status_code, 415)

        bad_file = self.client.post(
            f"/me/groups/{gid}/messages",
            content=b"{}",
            headers={"Content-Type": "vocechat/file"},
        )
        self.assertEqual(bad_file.status_code, 400)

    def test_social_contacts_list_get_patch_remark(self) -> None:
        self.fake_vc.contact_rows = [
            {
                "target_uid": 2,
                "target_info": {"uid": 2, "name": "Peer B"},
                "contact_info": {
                    "status": "friend",
                    "created_at": 10,
                    "updated_at": 20,
                    "removed_by_peer": False,
                },
            }
        ]
        lc = self.client.get("/me/social/contacts")
        self.assertEqual(lc.status_code, 200)
        items = lc.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["target_public_id"], self.peer_b_public_id)
        self.assertEqual(items[0]["display_name"], "sgu2")
        self.assertEqual(items[0]["contact_info"]["remark"], "")

        pch = self.client.patch(
            f"/me/social/contacts/{self.peer_b_public_id}",
            json={"remark": "work"},
        )
        self.assertEqual(pch.status_code, 200)
        self.assertEqual(pch.json()["contact_info"]["remark"], "work")

        one = self.client.get(f"/me/social/contacts/{self.peer_b_public_id}")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["contact_info"]["remark"], "work")

        missing = self.client.get("/me/social/contacts/199999999999")
        self.assertEqual(missing.status_code, 404)

    def test_no_vocechat_mapping_404_social(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "vocechat"
            ).delete()
            db.commit()
        r = self.client.get("/me/social/blacklist")
        self.assertEqual(r.status_code, 404)

    def test_preferences_mute_maps_to_vocechat_body(self) -> None:
        r = self.client.post(
            "/me/preferences/mute",
            json={
                "add_users": [
                    {"target_public_id": self.peer_b_public_id, "expired_in": 3600}
                ],
                "add_groups": [{"group_id": "201", "expired_in": 60}],
                "remove_users": [self.peer_b_public_id],
                "remove_groups": ["201"],
            },
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.fake_vc.actings[-1], "1")
        body = self.fake_vc.last_mute_body
        self.assertIsNotNone(body)
        assert body is not None
        self.assertEqual(body["add_users"], [{"uid": 2, "expired_in": 3600}])
        self.assertEqual(body["add_groups"], [{"gid": 201, "expired_in": 60}])
        self.assertEqual(body["remove_users"], [2])
        self.assertEqual(body["remove_groups"], [201])

    def test_preferences_burn_after_reading_maps_to_vocechat_body(self) -> None:
        r = self.client.post(
            "/me/preferences/burn-after-reading",
            json={
                "users": [
                    {
                        "target_public_id": self.peer_b_public_id,
                        "expires_in": 60,
                    }
                ],
                "groups": [{"group_id": "201", "expires_in": 120}],
            },
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.fake_vc.actings[-1], "1")
        body = self.fake_vc.last_burn_body
        self.assertIsNotNone(body)
        assert body is not None
        self.assertEqual(
            body,
            {
                "users": [{"uid": 2, "expires_in": 60}],
                "groups": [{"gid": 201, "expires_in": 120}],
            },
        )

    def test_preferences_burn_after_reading_rejects_self_peer(self) -> None:
        r = self.client.post(
            "/me/preferences/burn-after-reading",
            json={
                "users": [
                    {"target_public_id": self.user_a_public_id, "expires_in": 10}
                ],
                "groups": [],
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"], "invalid burn-after-reading peer")

    def test_devices_list_and_delete(self) -> None:
        self.fake_vc.devices = ["acting_uid", "mobile"]
        r = self.client.get("/me/devices")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.json(),
            {"items": [{"device_id": "acting_uid"}, {"device_id": "mobile"}]},
        )
        self.assertEqual(self.fake_vc.actings[-1], "1")

        d = self.client.delete("/me/devices/mobile")
        self.assertEqual(d.status_code, 204)
        self.assertEqual(self.fake_vc.deleted_devices, ["mobile"])

        r2 = self.client.get("/me/devices")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["items"], [{"device_id": "acting_uid"}])

        bad = self.client.delete("/me/devices/unknown")
        self.assertEqual(bad.status_code, 401)

    def test_push_token_put_json_maps_to_vocechat(self) -> None:
        r = self.client.put(
            "/me/devices/push-token",
            json={"device_id": "iphone-1", "token": "fcm-token-abc"},
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.fake_vc.actings[-1], "1")
        self.assertEqual(
            self.fake_vc.fcm_token_calls[-1], ("iphone-1", "fcm-token-abc")
        )

    def test_push_token_post_query_maps_to_vocechat(self) -> None:
        r = self.client.post(
            "/me/devices/push-token"
            "?device_id=android-9&token=reg%2Btoken%2Fxyz",
        )
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.fake_vc.actings[-1], "1")
        self.assertEqual(
            self.fake_vc.fcm_token_calls[-1], ("android-9", "reg+token/xyz")
        )

    def test_push_token_missing_params_422(self) -> None:
        r = self.client.post("/me/devices/push-token", json={})
        self.assertEqual(r.status_code, 422)

    def test_no_vocechat_mapping_404_push_token(self) -> None:
        with SessionLocal() as db:
            db.query(UserAppMapping).filter(
                UserAppMapping.app_name == "vocechat"
            ).delete()
            db.commit()
        r = self.client.put(
            "/me/devices/push-token",
            json={"device_id": "d", "token": "t"},
        )
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
