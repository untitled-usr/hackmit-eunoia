use std::ops::Deref;

use poem::Request;
use poem_openapi::{auth::ApiKey, OpenApi, SecurityScheme};

use crate::State;

#[derive(Debug, serde::Serialize, serde::Deserialize, Clone, Eq, PartialEq)]
pub struct CurrentUser {
    pub uid: i64,
    pub device: String,
    pub is_admin: bool,
    pub is_guest: bool,
}

/// Request identity via numeric user id in header `X-Acting-Uid`.
#[derive(SecurityScheme)]
#[oai(
    type = "api_key",
    key_name = "X-Acting-Uid",
    in = "header",
    checker = "api_checker"
)]
pub struct Token(pub CurrentUser);

impl Deref for Token {
    type Target = CurrentUser;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

async fn api_checker(req: &Request, api_key: ApiKey) -> Option<CurrentUser> {
    let state = req.extensions().get::<State>().unwrap();
    let uid = api_key.key.parse::<i64>().ok()?;
    let cache = state.cache.read().await;
    let user = cache.users.get(&uid)?;
    Some(CurrentUser {
        uid,
        device: "acting_uid".to_string(),
        is_admin: user.is_admin,
        is_guest: user.is_guest,
    })
}

/// OpenAPI security scheme for `X-Acting-Uid` (no `/token` HTTP routes).
pub struct ApiToken;

#[OpenApi(prefix_path = "/token", tag = "ApiTags::Token")]
impl ApiToken {}

#[cfg(test)]
mod tests {
    use poem::http::StatusCode;

    use crate::test_harness::TestServer;

    #[tokio::test]
    async fn test_user_me_requires_acting_uid() {
        let server = TestServer::new().await;

        let resp = server.get("/api/user/me").send().await;
        resp.assert_status(StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_admin_api_requires_acting_uid() {
        let server = TestServer::new().await;

        let resp = server
            .post("/api/admin/user")
            .body_json(&serde_json::json!({
                "password": "123456",
                "gender": 1,
                "language": "en-US",
                "is_admin": false,
            }))
            .send()
            .await;
        resp.assert_status(StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_admin_api_with_acting_uid() {
        let server = TestServer::new().await;

        let resp = server
            .post("/api/admin/user")
            .header("X-Acting-Uid", "1")
            .body_json(&serde_json::json!({
                "password": "123456",
                "gender": 1,
                "language": "en-US",
                "is_admin": false,
            }))
            .send()
            .await;
        resp.assert_status_is_ok();
    }

    #[tokio::test]
    async fn test_events_requires_acting_uid() {
        let server = TestServer::new().await;

        let resp = server
            .get("/api/user/events")
            .header("Connection", "keep-alive")
            .content_type("text/event-stream")
            .send()
            .await;
        resp.assert_status(StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_bot_requires_acting_uid() {
        let server = TestServer::new().await;

        let resp = server.get("/api/bot").send().await;
        resp.assert_status(StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn test_bot_with_acting_uid() {
        let server = TestServer::new().await;

        let resp = server.get("/api/bot").header("X-Acting-Uid", "1").send().await;
        resp.assert_status_is_ok();
    }

    #[tokio::test]
    async fn test_public_endpoint_without_acting_uid() {
        let server = TestServer::new().await;

        let resp = server.get("/api/user").send().await;
        resp.assert_status_is_ok();
    }
}
