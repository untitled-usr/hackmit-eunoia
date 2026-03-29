use std::{ops::Deref, path::Path, sync::Arc};

use futures_util::{stream::BoxStream, StreamExt};
use poem::{
    endpoint::BoxEndpoint,
    test::{TestClient, TestJson},
    EndpointExt,
};
use serde_json::json;
use sqlx::{migrate::MigrateDatabase, Sqlite, SqlitePool};
use tempfile::TempDir;

use crate::{
    config::{NetworkConfig, SystemConfig},
    server::MIGRATOR,
    Config, State,
};

pub struct TestServer {
    _tempdir: TempDir,
    state: State,
    client: TestClient<BoxEndpoint<'static>>,
}

impl Deref for TestServer {
    type Target = TestClient<BoxEndpoint<'static>>;

    fn deref(&self) -> &Self::Target {
        &self.client
    }
}

impl TestServer {
    pub async fn new() -> Self {
        Self::new_with_config(|_| {}).await
    }

    pub async fn new_with_config<F: FnOnce(&mut Config)>(f: F) -> Self {
        Self::new_inner(f, true).await
    }

    /// Fresh server with **no** seeded admin user (empty non-guest user set). For `POST /user/register` tests.
    pub async fn new_without_bootstrap_user<F: FnOnce(&mut Config)>(f: F) -> Self {
        Self::new_inner(f, false).await
    }

    async fn new_inner<F: FnOnce(&mut Config)>(f: F, bootstrap_admin: bool) -> Self {
        let tempdir = TempDir::new().unwrap();
        init_db(tempdir.path()).await;

        // create server
        let mut cfg = Config {
            system: SystemConfig {
                data_dir: tempdir.path().to_path_buf(),
                upload_avatar_limit: 1024 * 1024,
                send_image_limit: 1024 * 1024,
                upload_timeout_seconds: 300,
                file_expiry_days: 30 * 3,
                max_favorite_archives: 100,
                disable_license: false,
                test_skip_system_admin_bootstrap: !bootstrap_admin,
            },
            network: NetworkConfig {
                domain: Vec::new(),
                bind: "127.0.0.1:3000".to_string(),
                tls: None,
                frontend_url: "http://127.0.0.1:3000".to_string(),
            },
            template: Default::default(),
            users: vec![],
            webclient_url: None,
            offical_fcm_config: Default::default(),
        };
        f(&mut cfg);
        let state = crate::server::create_state(tempdir.path(), Arc::new(cfg))
            .await
            .unwrap();
        crate::license::load_license(&state).await.unwrap();
        let app = crate::server::create_endpoint(state.clone()).await;

        Self {
            _tempdir: tempdir,
            state,
            client: TestClient::new(app.map_to_response().boxed())
                .default_content_type("application/json"),
        }
    }

    pub fn state(&self) -> &State {
        &self.state
    }

    /// Next SSE JSON whose top-level `"type"` matches `want` (use when `subscribe_events(..., None)`).
    pub async fn next_sse_type(
        stream: &mut BoxStream<'static, TestJson>,
        want: &str,
    ) -> TestJson {
        while let Some(json) = stream.next().await {
            if json.value().object().get("type").string() == want {
                return json;
            }
        }
        panic!("SSE stream ended without type {want:?}");
    }

    pub async fn login(&self, uid: i64) -> String {
        uid.to_string()
    }

    pub async fn login_with_device(
        &self,
        uid: i64,
        _device: impl AsRef<str>,
    ) -> String {
        self.login(uid).await
    }

    pub async fn login_admin(&self) -> String {
        let cache = self.state.cache.read().await;
        cache
            .users
            .iter()
            .find(|(_, u)| u.is_admin && !u.is_guest)
            .map(|(id, _)| id.to_string())
            .expect("bootstrap admin")
    }

    pub async fn login_admin_with_device(&self, device: impl AsRef<str>) -> String {
        let _ = device;
        self.login_admin().await
    }

    pub async fn create_user(&self, acting_uid: impl AsRef<str>) -> i64 {
        let resp = self
            .client
            .post("/api/admin/user")
            .header("X-Acting-Uid", acting_uid.as_ref())
            .header("Referer", "http://localhost/")
            .body_json(&json!({
                "password": "123456",
                "gender": 1,
                "language": "en-US",
                "is_admin": false,
            }))
            .send()
            .await;
        resp.assert_status_is_ok();
        resp.json().await.value().object().get("uid").i64()
    }

    pub async fn send_text_to_user(
        &self,
        acting_uid: impl AsRef<str>,
        uid: i64,
        text: impl Into<String>,
    ) -> i64 {
        let resp = self
            .client
            .post(format!("/api/user/{}/send", uid))
            .header("X-Acting-Uid", acting_uid.as_ref())
            .header("Referer", "http://localhost/")
            .content_type("text/plain")
            .body(text.into())
            .send()
            .await;
        resp.assert_status_is_ok();
        resp.json().await.value().i64()
    }

    pub async fn send_text_to_group(
        &self,
        acting_uid: impl AsRef<str>,
        gid: i64,
        text: impl Into<String>,
    ) -> i64 {
        let resp = self
            .client
            .post(format!("/api/group/{}/send", gid))
            .header("X-Acting-Uid", acting_uid.as_ref())
            .header("Referer", "http://localhost/")
            .content_type("text/plain")
            .body(text.into())
            .send()
            .await;
        resp.assert_status_is_ok();
        resp.json().await.value().i64()
    }

    pub async fn get_group(&self, gid: i64) -> TestJson {
        let resp = self.get(format!("/api/group/{}", gid)).send().await;
        resp.assert_status_is_ok();
        resp.json().await
    }

    async fn internal_subscribe_events(
        &self,
        acting_uid: impl AsRef<str>,
        filters: Option<&[&str]>,
        after_mid: Option<i64>,
        users_version: Option<i64>,
    ) -> BoxStream<'static, TestJson> {
        let mut builder = self
            .client
            .get("/api/user/events")
            .header("X-Acting-Uid", acting_uid.as_ref())
            .header("Referer", "http://localhost/")
            .header("Connection", "keep-alive")
            .content_type("text/event-stream");
        if let Some(after_mid) = after_mid {
            builder = builder.query("after_mid", &after_mid);
        }
        if let Some(users_version) = users_version {
            builder = builder.query("users_version", &users_version);
        }
        let resp = builder.send().await;
        resp.assert_status_is_ok();
        let mut stream = resp.json_sse_stream().boxed();
        if let Some(filters) = filters {
            let filters = filters.iter().map(ToString::to_string).collect::<Vec<_>>();
            stream = stream
                .filter(move |json| {
                    futures_util::future::ready(
                        filters
                            .iter()
                            .any(|filter| filter == json.value().object().get("type").string()),
                    )
                })
                .boxed();
        }
        stream
    }

    pub async fn subscribe_events_with_users_version(
        &self,
        acting_uid: impl AsRef<str>,
        filters: Option<&[&str]>,
        users_version: i64,
    ) -> BoxStream<'static, TestJson> {
        self.internal_subscribe_events(acting_uid, filters, None, Some(users_version))
            .await
    }

    pub async fn subscribe_events(
        &self,
        acting_uid: impl AsRef<str>,
        filters: Option<&[&str]>,
    ) -> BoxStream<'static, TestJson> {
        self.internal_subscribe_events(acting_uid, filters, None, None)
            .await
    }

    /// SSE with `acting_uid` query param only (browser EventSource path).
    pub async fn subscribe_events_acting_uid_query(
        &self,
        acting_uid: impl AsRef<str>,
        filters: Option<&[&str]>,
    ) -> BoxStream<'static, TestJson> {
        let acting_uid = acting_uid.as_ref().to_string();
        let builder = self
            .client
            .get("/api/user/events")
            .query("acting_uid", &acting_uid)
            .header("Referer", "http://localhost/")
            .header("Connection", "keep-alive")
            .content_type("text/event-stream");
        let resp = builder.send().await;
        resp.assert_status_is_ok();
        let mut stream = resp.json_sse_stream().boxed();
        if let Some(filters) = filters {
            let filters = filters.iter().map(ToString::to_string).collect::<Vec<_>>();
            stream = stream
                .filter(move |json| {
                    futures_util::future::ready(
                        filters
                            .iter()
                            .any(|filter| filter == json.value().object().get("type").string()),
                    )
                })
                .boxed();
        }
        stream
    }

    pub async fn subscribe_events_after_mid(
        &self,
        acting_uid: impl AsRef<str>,
        filters: Option<&[&str]>,
        after_mid: Option<i64>,
    ) -> BoxStream<'static, TestJson> {
        self.internal_subscribe_events(acting_uid, filters, after_mid, None)
            .await
    }
}

async fn init_db(path: &Path) {
    std::fs::create_dir(path.join("db")).unwrap();
    let dsn = format!("sqlite:{}", path.join("db").join("db.sqlite").display());
    Sqlite::create_database(&dsn).await.unwrap();
    let db = SqlitePool::connect(&dsn).await.unwrap();
    MIGRATOR.run(&db).await.unwrap();
}
