from test.util.abstract_integration_test import AbstractPostgresTest
from test.util.mock_user import mock_webui_user


class TestAuths(AbstractPostgresTest):
    BASE_PATH = "/api/v1/auths"

    def setup_class(cls):
        super().setup_class()
        from open_webui.models.auths import Auths
        from open_webui.models.users import Users

        cls.users = Users
        cls.auths = Auths

    def test_get_session_user(self):
        with mock_webui_user():
            response = self.fast_api_client.get(self.create_url(""))
        assert response.status_code == 200
        assert response.json() == {
            "id": "1",
            "name": "John Doe",
            "role": "user",
            "profile_image_url": "/user.png",
        }

    def test_update_profile(self):
        from open_webui.utils.auth import get_password_hash

        user = self.auths.insert_new_auth(
            get_password_hash("old_password"),
            "/user.png",
            "user",
            None,
            "John Doe",
        )

        with mock_webui_user(id=user.id):
            response = self.fast_api_client.post(
                self.create_url("/update/profile"),
                json={"name": "John Doe 2", "profile_image_url": "/user2.png"},
            )
        assert response.status_code == 200
        db_user = self.users.get_user_by_id(user.id)
        assert db_user.name == "John Doe 2"
        assert db_user.profile_image_url == "/user2.png"

    def test_update_password(self):
        from open_webui.utils.auth import get_password_hash, verify_password

        user = self.auths.insert_new_auth(
            get_password_hash("old_password"),
            "/user.png",
            "user",
            None,
            "John Doe",
        )

        with mock_webui_user(id=user.id):
            response = self.fast_api_client.post(
                self.create_url("/update/password"),
                json={"password": "old_password", "new_password": "new_password"},
            )
        assert response.status_code == 200

        old_auth = self.auths.authenticate_user(
            user.id, lambda h: verify_password("old_password", h)
        )
        assert old_auth is None
        new_auth = self.auths.authenticate_user(
            user.id, lambda h: verify_password("new_password", h)
        )
        assert new_auth is not None

    def test_add_user(self):
        with mock_webui_user():
            response = self.fast_api_client.post(
                self.create_url("/add"),
                json={
                    "name": "John Doe 2",
                    "password": "password2",
                    "role": "admin",
                },
            )
        assert response.status_code == 403

    def test_add_user_role_user(self):
        with mock_webui_user():
            response = self.fast_api_client.post(
                self.create_url("/add"),
                json={
                    "name": "Jane",
                    "password": "password2",
                    "role": "user",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "user"
        assert data["name"] == "Jane"

    def test_get_admin_details(self):
        from open_webui.constants import SYSTEM_ADMIN_USER_ID
        from open_webui.utils.system_admin import ensure_system_admin

        ensure_system_admin()
        with mock_webui_user():
            response = self.fast_api_client.get(self.create_url("/admin/details"))

        assert response.status_code == 200
        body = response.json()
        assert "email" not in body
        assert body["name"] == "admin"
        assert body["id"] == SYSTEM_ADMIN_USER_ID

    def test_register_public_second_user_acting_uid_response(self):
        from open_webui.utils.auth import get_password_hash

        self.auths.insert_new_auth(
            get_password_hash("password"),
            "/user.png",
            "user",
            None,
            "Seed",
        )
        app = self.fast_api_client.app
        app.state.config.ENABLE_SIGNUP = True
        app.state.config.DISALLOW_USER_REGISTRATION = False

        response = self.fast_api_client.post(self.create_url("/register"), json={})
        assert response.status_code == 200
        data = response.json()
        assert data["token_type"] == "ActingUid"
        assert data["token"] == ""
        assert data["id"] is not None
        assert data["name"] is not None
        expected_role = app.state.config.DEFAULT_USER_ROLE
        if expected_role == "admin":
            expected_role = "user"
        assert data["role"] == expected_role
        assert "email" not in data

    def test_register_public_forbidden_when_disallow(self):
        from open_webui.utils.auth import get_password_hash

        self.auths.insert_new_auth(
            get_password_hash("password"),
            "/user.png",
            "user",
            None,
            "Seed2",
        )
        app = self.fast_api_client.app
        app.state.config.ENABLE_SIGNUP = True
        app.state.config.DISALLOW_USER_REGISTRATION = True

        response = self.fast_api_client.post(self.create_url("/register"), json={})
        assert response.status_code == 403
